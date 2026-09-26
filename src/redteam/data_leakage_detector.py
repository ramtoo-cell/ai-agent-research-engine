import asyncio
import logging
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set

from pydantic import BaseModel, Field


class LeakageType(str, Enum):
    """Categories of sensitive data that must be prevented from leaking."""
    PII = "pii"
    TRAINING_DATA = "training_data"
    SYSTEM_PROMPT = "system_prompt"
    INTERNAL_STATE = "internal_state"
    SECRETS = "secrets"


class LeakageRule(BaseModel):
    """A specific rule defining how to detect a type of leakage."""
    rule_id: str
    leakage_type: LeakageType
    regex_pattern: Optional[str] = Field(default=None, description="Regex to detect the leakage")
    exact_matches: List[str] = Field(default_factory=list, description="Exact substrings to block")
    severity: str = Field(default="high", description="Severity if this rule is violated")


class PreventionPolicy(BaseModel):
    """Configurable policy dictating which rules are active and how to handle violations."""
    policy_id: str
    active_rules: List[LeakageRule] = Field(default_factory=list)
    action_on_violation: str = Field(default="block", description="Options: 'block', 'redact', 'flag_only'")
    redaction_string: str = Field(default="[REDACTED]", description="String used if action is 'redact'")

    def add_rule(self, rule: LeakageRule):
        self.active_rules.append(rule)


class LeakageDetection(BaseModel):
    """Details of a specific data leakage instance found in an output."""
    rule_id: str
    leakage_type: LeakageType
    matched_text: str = Field(..., description="The actual text that was flagged (for audit logging)")
    start_index: int = Field(..., description="Start index of the matched text in the output")
    end_index: int = Field(..., description="End index of the matched text in the output")


class LeakagePreventionReport(BaseModel):
    """Report generated after scanning an output for leakages."""
    scan_id: str = Field(..., description="Unique ID for this scan operation")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    original_output_length: int
    was_blocked: bool = Field(default=False, description="Whether the output was blocked entirely")
    was_redacted: bool = Field(default=False, description="Whether the output was redacted")
    detections: List[LeakageDetection] = Field(default_factory=list)
    final_safe_output: str = Field(..., description="The sanitized output (or empty if blocked)")
    
    @property
    def has_leakage(self) -> bool:
        return len(self.detections) > 0


class OutputLeakageScanner:
    """Scans AI outputs to detect and prevent information leakage based on a policy."""
    
    def __init__(self, policy: PreventionPolicy):
        self.policy = policy
        self.logger = logging.getLogger("OutputLeakageScanner")
        self._compiled_regexes: Dict[str, re.Pattern] = {}
        
        # Precompile regexes for performance
        for rule in self.policy.active_rules:
            if rule.regex_pattern:
                try:
                    self._compiled_regexes[rule.rule_id] = re.compile(rule.regex_pattern, re.IGNORECASE)
                except re.error as e:
                    self.logger.error(f"Failed to compile regex for rule {rule.rule_id}: {e}")

    async def scan_and_prevent(self, ai_output: str) -> LeakagePreventionReport:
        """
        Scans the output string against all active rules in the policy.
        Applies the configured action (block, redact) if leakages are found.
        """
        if not ai_output:
            return LeakagePreventionReport(
                scan_id=f"scan_{datetime.utcnow().timestamp()}",
                original_output_length=0,
                final_safe_output=""
            )
            
        detections: List[LeakageDetection] = []
        
        # 1. Scan for Exact Matches
        for rule in self.policy.active_rules:
            for exact_match in rule.exact_matches:
                start = 0
                while True:
                    idx = ai_output.find(exact_match, start)
                    if idx == -1:
                        break
                    detections.append(LeakageDetection(
                        rule_id=rule.rule_id,
                        leakage_type=rule.leakage_type,
                        matched_text=exact_match,
                        start_index=idx,
                        end_index=idx + len(exact_match)
                    ))
                    start = idx + len(exact_match)
                    
        # 2. Scan for Regex Matches
        for rule in self.policy.active_rules:
            if rule.rule_id in self._compiled_regexes:
                pattern = self._compiled_regexes[rule.rule_id]
                for match in pattern.finditer(ai_output):
                    detections.append(LeakageDetection(
                        rule_id=rule.rule_id,
                        leakage_type=rule.leakage_type,
                        matched_text=match.group(0),
                        start_index=match.start(),
                        end_index=match.end()
                    ))
                    
        # 3. Process Detections and Apply Actions
        was_blocked = False
        was_redacted = False
        final_output = ai_output
        
        if detections:
            if self.policy.action_on_violation == "block":
                was_blocked = True
                final_output = ""
                self.logger.warning(f"Blocked output due to {len(detections)} leakage detections.")
                
            elif self.policy.action_on_violation == "redact":
                was_redacted = True
                # Redact from back to front to avoid index shifting
                # Sort descending by start_index
                detections_sorted = sorted(detections, key=lambda d: d.start_index, reverse=True)
                
                for det in detections_sorted:
                    final_output = (
                        final_output[:det.start_index] + 
                        self.policy.redaction_string + 
                        final_output[det.end_index:]
                    )
                self.logger.info(f"Redacted {len(detections)} leakage instances from output.")
                
        return LeakagePreventionReport(
            scan_id=f"scan_{datetime.utcnow().timestamp()}",
            original_output_length=len(ai_output),
            was_blocked=was_blocked,
            was_redacted=was_redacted,
            detections=detections,
            final_safe_output=final_output
        )


# Helper function to generate a baseline policy
def create_baseline_prevention_policy() -> PreventionPolicy:
    """Creates a baseline policy for preventing common data leakages."""
    policy = PreventionPolicy(
        policy_id="baseline_dlp_policy",
        action_on_violation="redact"
    )
    
    # Rule for basic SSN detection (example PII)
    policy.add_rule(LeakageRule(
        rule_id="pii_ssn_basic",
        leakage_type=LeakageType.PII,
        regex_pattern=r"\b\d{3}-\d{2}-\d{4}\b",
        severity="critical"
    ))
    
    # Rule for API Key/Secrets detection (generic example)
    policy.add_rule(LeakageRule(
        rule_id="secrets_generic_key",
        leakage_type=LeakageType.SECRETS,
        regex_pattern=r"(?i)(api[_-]?key|secret|token)[\s:=]+[\"']?[A-Za-z0-9\-_]{16,}['\"]?",
        severity="critical"
    ))
    
    return policy
