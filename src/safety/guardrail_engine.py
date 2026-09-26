import re
import asyncio
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple, Union, Pattern
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

class GuardrailAction(str, Enum):
    """
    Defines the actions that can be taken when a guardrail rule is matched.
    """
    BLOCK = "BLOCK"
    WARN = "WARN"
    LOG = "LOG"
    TRANSFORM = "TRANSFORM"

class ViolationSeverity(str, Enum):
    """
    Defines the severity levels of a guardrail violation.
    """
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class GuardrailViolation(BaseModel):
    """
    Represents a violation of a guardrail.
    """
    model_config = ConfigDict(frozen=True)
    
    rule_id: str = Field(..., description="The unique identifier of the rule that was violated.")
    guardrail_name: str = Field(..., description="The name of the guardrail that generated this violation.")
    severity: ViolationSeverity = Field(..., description="The severity level of the violation.")
    message: str = Field(..., description="A detailed message describing the violation.")
    action_taken: GuardrailAction = Field(..., description="The action taken in response to this violation.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or metadata.")

class GuardrailRule(BaseModel):
    """
    A rule that defines a condition for a guardrail and the corresponding action to take.
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)

    rule_id: str = Field(..., description="A unique identifier for this rule.")
    description: str = Field(..., description="A human-readable description of what the rule checks.")
    severity: ViolationSeverity = Field(default=ViolationSeverity.MEDIUM, description="Severity if this rule matches.")
    action: GuardrailAction = Field(default=GuardrailAction.BLOCK, description="Action to take if matched.")
    match_condition: Callable[[str, Dict[str, Any]], bool] = Field(
        ..., description="A callable that takes (text, context) and returns True if the rule is violated."
    )
    transform_logic: Optional[Callable[[str], str]] = Field(
        default=None, description="Logic to apply if the action is TRANSFORM."
    )

class GuardrailContext(BaseModel):
    """
    Contextual information passed along with the payload during guardrail processing.
    """
    session_id: Optional[str] = Field(default=None, description="The session identifier.")
    user_id: Optional[str] = Field(default=None, description="The user identifier.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary metadata.")

class GuardrailResult(BaseModel):
    """
    The result of processing a payload through a guardrail or a chain of guardrails.
    """
    is_safe: bool = Field(..., description="True if no blocking violations were found.")
    payload: str = Field(..., description="The resulting payload, potentially transformed.")
    violations: List[GuardrailViolation] = Field(default_factory=list, description="All violations encountered.")
    
    def merge(self, other: 'GuardrailResult') -> 'GuardrailResult':
        """
        Merge another result into this one.
        """
        return GuardrailResult(
            is_safe=self.is_safe and other.is_safe,
            payload=other.payload, # assumes sequential application where 'other' happens after 'self'
            violations=self.violations + other.violations
        )

class BaseGuardrail(ABC):
    """
    Base class for all guardrails.
    """
    def __init__(self, name: str, rules: List[GuardrailRule], stop_on_block: bool = True):
        self.name = name
        self.rules = rules
        self.stop_on_block = stop_on_block

    async def execute(self, text: str, context: GuardrailContext) -> GuardrailResult:
        """
        Execute the guardrail against the provided text.
        """
        current_text = text
        is_safe = True
        violations: List[GuardrailViolation] = []

        for rule in self.rules:
            try:
                # Run the synchronous match condition
                is_match = rule.match_condition(current_text, context.metadata)
                if is_match:
                    violation = GuardrailViolation(
                        rule_id=rule.rule_id,
                        guardrail_name=self.name,
                        severity=rule.severity,
                        message=f"Rule '{rule.description}' matched.",
                        action_taken=rule.action,
                    )
                    violations.append(violation)
                    
                    if rule.action == GuardrailAction.LOG:
                        logger.info(f"Guardrail LOG: {violation}")
                    elif rule.action == GuardrailAction.WARN:
                        logger.warning(f"Guardrail WARN: {violation}")
                    elif rule.action == GuardrailAction.TRANSFORM:
                        if rule.transform_logic:
                            current_text = rule.transform_logic(current_text)
                        else:
                            logger.error(f"Rule {rule.rule_id} specifies TRANSFORM but has no transform_logic.")
                    elif rule.action == GuardrailAction.BLOCK:
                        is_safe = False
                        if self.stop_on_block:
                            break
            except Exception as e:
                logger.error(f"Error executing rule {rule.rule_id} in guardrail {self.name}: {e}")
                
        return GuardrailResult(is_safe=is_safe, payload=current_text, violations=violations)

class InputGuardrail(BaseGuardrail):
    """
    A guardrail intended for filtering user input before it reaches the core system.
    """
    pass

class OutputGuardrail(BaseGuardrail):
    """
    A guardrail intended for filtering system output before it is returned to the user.
    """
    pass

class ContentLengthGuardrail(InputGuardrail):
    """
    Validates that the content length falls within acceptable bounds.
    """
    def __init__(self, min_length: int = 1, max_length: int = 10000):
        rules = [
            GuardrailRule(
                rule_id="length-min",
                description=f"Payload must be at least {min_length} characters.",
                severity=ViolationSeverity.LOW,
                action=GuardrailAction.BLOCK,
                match_condition=lambda text, ctx: len(text.strip()) < min_length
            ),
            GuardrailRule(
                rule_id="length-max",
                description=f"Payload must be at most {max_length} characters.",
                severity=ViolationSeverity.MEDIUM,
                action=GuardrailAction.BLOCK,
                match_condition=lambda text, ctx: len(text) > max_length
            )
        ]
        super().__init__(name="ContentLengthGuardrail", rules=rules)

class TopicGuardrail(BaseGuardrail):
    """
    Filters content based on disallowed topics using regex patterns.
    """
    def __init__(self, disallowed_topics: Dict[str, List[str]]):
        """
        Initialize with a dictionary of topic names to lists of regex patterns.
        """
        rules = []
        for topic, patterns in disallowed_topics.items():
            compiled_patterns = [re.compile(p, re.IGNORECASE) for p in patterns]
            
            def create_matcher(cp_list: List[Pattern]):
                return lambda text, ctx: any(p.search(text) for p in cp_list)
            
            rules.append(GuardrailRule(
                rule_id=f"topic-{topic.lower()}",
                description=f"Disallowed topic detected: {topic}",
                severity=ViolationSeverity.HIGH,
                action=GuardrailAction.BLOCK,
                match_condition=create_matcher(compiled_patterns)
            ))
        super().__init__(name="TopicGuardrail", rules=rules)

class FormatGuardrail(OutputGuardrail):
    """
    Ensures that the output adheres to a specific format (e.g., valid JSON, no markdown).
    """
    def __init__(self, require_json: bool = False, forbid_markdown: bool = False):
        rules = []
        if require_json:
            import json
            def check_json(text: str, ctx: Dict) -> bool:
                try:
                    json.loads(text)
                    return False
                except json.JSONDecodeError:
                    return True
                    
            rules.append(GuardrailRule(
                rule_id="format-json",
                description="Output must be valid JSON.",
                severity=ViolationSeverity.MEDIUM,
                action=GuardrailAction.BLOCK,
                match_condition=check_json
            ))
            
        if forbid_markdown:
            markdown_pattern = re.compile(r'```.*?```', re.DOTALL)
            rules.append(GuardrailRule(
                rule_id="format-no-markdown",
                description="Output must not contain markdown code blocks.",
                severity=ViolationSeverity.LOW,
                action=GuardrailAction.TRANSFORM,
                match_condition=lambda text, ctx: bool(markdown_pattern.search(text)),
                transform_logic=lambda text: markdown_pattern.sub('', text)
            ))
            
        super().__init__(name="FormatGuardrail", rules=rules)

class GuardrailChain:
    """
    A sequential chain of guardrails.
    """
    def __init__(self, guardrails: List[BaseGuardrail], fail_fast: bool = True):
        self.guardrails = guardrails
        self.fail_fast = fail_fast

    async def process(self, text: str, context: Optional[GuardrailContext] = None) -> GuardrailResult:
        """
        Process the text through all guardrails in the chain.
        """
        if context is None:
            context = GuardrailContext()
            
        current_text = text
        total_violations: List[GuardrailViolation] = []
        is_safe = True
        
        for guardrail in self.guardrails:
            result = await guardrail.execute(current_text, context)
            current_text = result.payload
            total_violations.extend(result.violations)
            
            if not result.is_safe:
                is_safe = False
                if self.fail_fast:
                    logger.warning(f"Guardrail chain blocked by {guardrail.name}, failing fast.")
                    break
                    
        return GuardrailResult(
            is_safe=is_safe,
            payload=current_text,
            violations=total_violations
        )

# Example factory method for creating standard input chains
def create_standard_input_chain() -> GuardrailChain:
    """
    Creates a standard input guardrail chain with length and basic topic checks.
    """
    return GuardrailChain(
        guardrails=[
            ContentLengthGuardrail(min_length=2, max_length=5000),
            TopicGuardrail(disallowed_topics={
                "HateSpeech": [r"\bhate\b", r"\bslurs\b"],
                "Violence": [r"\bkill\b", r"\bmurder\b"]
            })
        ],
        fail_fast=True
    )
