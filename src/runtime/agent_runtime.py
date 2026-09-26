import asyncio
import logging
import uuid
import time
from typing import Dict, Any, List, Optional, Callable, Awaitable, TypeVar
from datetime import datetime, timezone
from enum import Enum, auto

from pydantic import BaseModel, Field, ConfigDict, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T")

class ExecutionStatus(str, Enum):
    """Represents the lifecycle status of an agent execution request."""
    PENDING = "PENDING"
    PRE_CHECK = "PRE_CHECK"
    TOOL_SELECTION = "TOOL_SELECTION"
    EXECUTING = "EXECUTING"
    POST_VALIDATION = "POST_VALIDATION"
    AUDITING = "AUDITING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"

class ActionRiskLevel(str, Enum):
    """Categorization of risk associated with a particular action or tool call."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class AgentPolicyConfig(BaseModel):
    """Configuration constraints for agent execution."""
    model_config = ConfigDict(frozen=True)

    max_steps_per_request: int = Field(default=10, ge=1, description="Maximum internal tool loops per request.")
    max_tokens_per_request: int = Field(default=8192, ge=100)
    execution_timeout_seconds: float = Field(default=300.0, ge=1.0)
    allowed_domains: List[str] = Field(default_factory=list)
    require_human_approval_for_risk: ActionRiskLevel = Field(default=ActionRiskLevel.HIGH)

class UserContext(BaseModel):
    """Details regarding the user initiating the agent run."""
    user_id: str = Field(..., description="Unique identifier for the user.")
    organization_id: str = Field(..., description="Organization to which the user belongs.")
    roles: List[str] = Field(default_factory=list, description="RBAC roles assigned to the user.")
    session_id: Optional[str] = Field(default=None, description="Current session correlation ID.")

class AgentExecutionContext(BaseModel):
    """Contextual wrapper containing trace identifiers and user metadata."""
    correlation_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    user_context: UserContext
    permissions: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ToolCall(BaseModel):
    """Represents an intended invocation of an external or internal tool."""
    tool_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    tool_name: str = Field(..., description="The registered name of the tool.")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Parameters to pass to the tool.")
    permissions_required: List[str] = Field(default_factory=list, description="Permissions needed for this tool.")
    risk_level: ActionRiskLevel = Field(default=ActionRiskLevel.LOW)
    expected_latency_seconds: Optional[float] = None

class ExecutionResult(BaseModel):
    """Final output and telemetry of the agent execution."""
    status: ExecutionStatus
    output: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    tokens_used: int = Field(default=0)
    latency_seconds: float = Field(default=0.0)
    tool_calls_executed: int = Field(default=0)
    correlation_id: str

class PolicyEngine:
    """Evaluates requested actions against configured agent policies."""
    
    def __init__(self, config: AgentPolicyConfig):
        self.config = config

    async def evaluate_pre_execution(self, context: AgentExecutionContext, request_payload: Dict[str, Any]) -> bool:
        """Determines if the overarching request is permitted."""
        logger.debug(f"[{context.correlation_id}] Evaluating pre-execution policy.")
        # Simulated policy logic
        return True

    async def evaluate_tool_call(self, context: AgentExecutionContext, tool_call: ToolCall) -> bool:
        """Validates if a specific tool call is allowed for the user context."""
        logger.debug(f"[{context.correlation_id}] Evaluating tool call: {tool_call.tool_name}")
        # Simulated RBAC check against tool_call.permissions_required
        required_set = set(tool_call.permissions_required)
        user_set = set(context.permissions)
        if required_set and not required_set.issubset(user_set):
            logger.warning(f"[{context.correlation_id}] Permission denied for tool {tool_call.tool_name}")
            return False
        return True

class SafetyCheckResult(BaseModel):
    is_safe: bool
    violations: List[str] = Field(default_factory=list)
    confidence_score: float = Field(default=1.0)

class SafetyChecks:
    """Manages content safety, jailbreak detection, and output moderation."""

    async def analyze_input(self, text: str) -> SafetyCheckResult:
        """Checks incoming prompt for malicious instructions or prompt injection."""
        # Simulated safety analysis
        if "bypass safety" in text.lower():
            return SafetyCheckResult(is_safe=False, violations=["Prompt Injection Detected"], confidence_score=0.98)
        return SafetyCheckResult(is_safe=True)

    async def analyze_output(self, text: str) -> SafetyCheckResult:
        """Checks generated output for policy violations before returning."""
        # Simulated output scanning (PII, toxicity, etc.)
        return SafetyCheckResult(is_safe=True)

class AuditLogger:
    """Handles structured logging for all agent state transitions and actions."""

    async def log_event(self, correlation_id: str, event_type: str, details: Dict[str, Any]):
        """Persist an audit event."""
        # In a real system, this would write to a tamper-evident ledger or message queue
        logger.info(f"AUDIT [{correlation_id}] {event_type}: {details}")

class ExecutionPipeline:
    """Coordinates the staged execution of an agent request."""

    def __init__(self, policy_engine: PolicyEngine, safety_checks: SafetyChecks, audit_logger: AuditLogger):
        self.policy = policy_engine
        self.safety = safety_checks
        self.audit = audit_logger

    async def execute(self, context: AgentExecutionContext, instructions: str, available_tools: List[ToolCall]) -> ExecutionResult:
        start_time = time.time()
        tokens = 0
        executed_tools = 0
        
        try:
            # Stage 1: Pre-Checks
            await self.audit.log_event(context.correlation_id, "STAGE_ENTER", {"stage": ExecutionStatus.PRE_CHECK})
            safety_res = await self.safety.analyze_input(instructions)
            if not safety_res.is_safe:
                await self.audit.log_event(context.correlation_id, "SAFETY_VIOLATION", {"violations": safety_res.violations})
                return self._build_result(context, ExecutionStatus.REJECTED, start_time, tokens, executed_tools, error="Input failed safety checks.")
            
            policy_res = await self.policy.evaluate_pre_execution(context, {"instructions": instructions})
            if not policy_res:
                return self._build_result(context, ExecutionStatus.REJECTED, start_time, tokens, executed_tools, error="Policy rejected execution.")

            # Stage 2: Tool Selection (Simulated AI Loop)
            await self.audit.log_event(context.correlation_id, "STAGE_ENTER", {"stage": ExecutionStatus.TOOL_SELECTION})
            selected_tools = self._simulate_agent_reasoning(instructions, available_tools)
            tokens += 150 # Simulated token cost

            # Stage 3: Execution
            await self.audit.log_event(context.correlation_id, "STAGE_ENTER", {"stage": ExecutionStatus.EXECUTING})
            tool_outputs = []
            for tool in selected_tools:
                if not await self.policy.evaluate_tool_call(context, tool):
                    return self._build_result(context, ExecutionStatus.FAILED, start_time, tokens, executed_tools, error=f"Permission denied: {tool.tool_name}")
                
                output = await self._execute_tool(context, tool)
                executed_tools += 1
                tool_outputs.append(output)

            # Stage 4: Post-Validation
            await self.audit.log_event(context.correlation_id, "STAGE_ENTER", {"stage": ExecutionStatus.POST_VALIDATION})
            final_response = f"Simulated final output based on {len(tool_outputs)} tools."
            out_safety = await self.safety.analyze_output(final_response)
            if not out_safety.is_safe:
                return self._build_result(context, ExecutionStatus.FAILED, start_time, tokens, executed_tools, error="Output failed safety checks.")

            # Stage 5: Auditing
            await self.audit.log_event(context.correlation_id, "STAGE_ENTER", {"stage": ExecutionStatus.AUDITING})
            
            return self._build_result(context, ExecutionStatus.COMPLETED, start_time, tokens, executed_tools, output={"response": final_response})

        except asyncio.TimeoutError:
            await self.audit.log_event(context.correlation_id, "TIMEOUT", {})
            return self._build_result(context, ExecutionStatus.TIMEOUT, start_time, tokens, executed_tools, error="Execution timed out.")
        except Exception as e:
            logger.error(f"Execution failed: {e}", exc_info=True)
            return self._build_result(context, ExecutionStatus.FAILED, start_time, tokens, executed_tools, error=str(e))

    def _simulate_agent_reasoning(self, instructions: str, available_tools: List[ToolCall]) -> List[ToolCall]:
        """Mock method for LLM planning phase."""
        return available_tools[:1] if available_tools else []

    async def _execute_tool(self, context: AgentExecutionContext, tool: ToolCall) -> Dict[str, Any]:
        """Mock method for actual tool execution."""
        await asyncio.sleep(0.1)
        return {"tool_id": tool.tool_id, "result": "success"}

    def _build_result(self, context: AgentExecutionContext, status: ExecutionStatus, start_time: float, tokens: int, tools: int, error: Optional[str] = None, output: Optional[Dict[str, Any]] = None) -> ExecutionResult:
        return ExecutionResult(
            status=status,
            output=output,
            error_message=error,
            tokens_used=tokens,
            latency_seconds=time.time() - start_time,
            tool_calls_executed=tools,
            correlation_id=context.correlation_id
        )

class GovernedAgentRuntime:
    """
    The main entrypoint for executing AI agents within strict governance constraints.
    Integrates policy, safety, human-in-the-loop, and resource management.
    """
    
    def __init__(self, config: AgentPolicyConfig):
        self.config = config
        self.policy_engine = PolicyEngine(config)
        self.safety_checks = SafetyChecks()
        self.audit_logger = AuditLogger()
        self.pipeline = ExecutionPipeline(self.policy_engine, self.safety_checks, self.audit_logger)

    async def run(self, context: AgentExecutionContext, instructions: str, tools: List[ToolCall] = None) -> ExecutionResult:
        """
        Execute an agent task asynchronously with timeout and governance rules.
        """
        logger.info(f"Starting agent run for context {context.correlation_id}")
        tools = tools or []
        
        try:
            # Enforce execution timeout at the highest level
            result = await asyncio.wait_for(
                self.pipeline.execute(context, instructions, tools),
                timeout=self.config.execution_timeout_seconds
            )
            return result
        except asyncio.TimeoutError:
            logger.error(f"[{context.correlation_id}] Runtime exceeded configured timeout of {self.config.execution_timeout_seconds}s.")
            return ExecutionResult(
                status=ExecutionStatus.TIMEOUT,
                error_message="Runtime exceeded maximum execution time.",
                correlation_id=context.correlation_id
            )
