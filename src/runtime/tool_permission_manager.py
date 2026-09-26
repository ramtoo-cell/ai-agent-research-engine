import re
import logging
from typing import Dict, Any, List, Optional, Set
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, field_validator

logger = logging.getLogger(__name__)

class ToolRiskLevel(str, Enum):
    SAFE = "SAFE"
    MODERATE = "MODERATE"
    DANGEROUS = "DANGEROUS"

class ToolDefinition(BaseModel):
    """Metadata describing an available tool and its security profile."""
    name: str = Field(..., description="Unique identifier for the tool (e.g., 'bash_shell', 's3_read').")
    capabilities_required: List[str] = Field(default_factory=list, description="System capabilities needed (e.g., 'network', 'filesystem').")
    risk_level: ToolRiskLevel = Field(default=ToolRiskLevel.SAFE)
    description: str = Field(..., description="Semantic description of the tool for the agent.")
    parameters_schema: Dict[str, Any] = Field(default_factory=dict, description="JSON Schema for the arguments.")

class ToolPermissionPolicy(BaseModel):
    """Maps organizational roles to tool access control lists."""
    role_name: str
    allowed_tools: Set[str] = Field(default_factory=set, description="Set of tool names explicitly allowed. '*' means all.")
    denied_tools: Set[str] = Field(default_factory=set, description="Set of tool names explicitly denied. Overrides allowed.")
    max_invocations_per_session: int = Field(default=100)

class ToolExecutionSandbox(BaseModel):
    """Resource limits and isolation settings for executing a tool."""
    memory_limit_mb: int = Field(default=512)
    timeout_seconds: int = Field(default=30)
    network_egress_allowed: bool = Field(default=False)
    allowed_hosts: List[str] = Field(default_factory=list)

class DangerousToolDetector:
    """Scans tool invocations for potentially destructive or harmful arguments."""
    
    # Generic regex patterns for dangerous payloads (e.g., bash injections, unauthorized key access)
    DANGEROUS_PATTERNS = [
        re.compile(r"rm\s+-rf\s+/"),
        re.compile(r"chmod\s+-R\s+777"),
        re.compile(r"mkfs"),
        re.compile(r"wget\s+.*\|\s*sh"),
        re.compile(r"curl\s+.*\|\s*sh"),
        re.compile(r"/\.ssh/id_rsa"),
        re.compile(r"/\.aws/credentials")
    ]

    @classmethod
    def scan_arguments(cls, arguments: Dict[str, Any]) -> List[str]:
        """Deep scan string arguments for dangerous patterns."""
        violations = []
        for key, value in arguments.items():
            if isinstance(value, str):
                for pattern in cls.DANGEROUS_PATTERNS:
                    if pattern.search(value):
                        violations.append(f"Argument '{key}' matches dangerous pattern: {pattern.pattern}")
            elif isinstance(value, dict):
                violations.extend(cls.scan_arguments(value))
        return violations

class ToolUsageMetrics(BaseModel):
    """Telemetry data tracking tool usage across the platform."""
    tool_name: str
    invocation_count: int = Field(default=0)
    failure_count: int = Field(default=0)
    total_execution_time_ms: float = Field(default=0.0)
    last_invoked_at: Optional[datetime] = None

class ToolPermissionManager:
    """
    Centralized authority for deciding whether an agent can use a specific tool
    with given arguments in its current context.
    """
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._policies: Dict[str, ToolPermissionPolicy] = {}
        self._metrics: Dict[str, ToolUsageMetrics] = {}

    def register_tool(self, tool: ToolDefinition):
        """Registers a tool definition into the system."""
        self._tools[tool.name] = tool
        if tool.name not in self._metrics:
            self._metrics[tool.name] = ToolUsageMetrics(tool_name=tool.name)
        logger.info(f"Registered tool: {tool.name} with risk {tool.risk_level}")

    def update_policy(self, policy: ToolPermissionPolicy):
        """Updates the RBAC policy for a role."""
        self._policies[policy.role_name] = policy
        logger.info(f"Updated ToolPermissionPolicy for role: {policy.role_name}")

    def validate_tool_call(self, tool_name: str, arguments: Dict[str, Any], roles: List[str]) -> bool:
        """
        Validates whether the user's roles permit the use of the requested tool,
        and ensures the arguments are not dangerous.
        """
        if tool_name not in self._tools:
            logger.error(f"Validation failed: Tool '{tool_name}' is not registered.")
            return False

        tool_def = self._tools[tool_name]

        # Check Dangerous Detector
        violations = DangerousToolDetector.scan_arguments(arguments)
        if violations:
            logger.warning(f"Dangerous payloads detected in tool {tool_name}: {violations}")
            return False

        # Role-based validation
        is_allowed = False
        is_denied = False

        for role in roles:
            policy = self._policies.get(role)
            if not policy:
                continue

            if "*" in policy.denied_tools or tool_name in policy.denied_tools:
                is_denied = True
            
            if "*" in policy.allowed_tools or tool_name in policy.allowed_tools:
                is_allowed = True

        if is_denied:
            logger.info(f"Tool access explicitly denied for tool: {tool_name} by roles: {roles}")
            return False

        if not is_allowed:
            logger.info(f"Tool access not granted for tool: {tool_name} by roles: {roles}")
            return False

        return True

    def record_execution(self, tool_name: str, success: bool, execution_time_ms: float):
        """Updates internal metrics after a tool execution."""
        metrics = self._metrics.get(tool_name)
        if metrics:
            metrics.invocation_count += 1
            if not success:
                metrics.failure_count += 1
            metrics.total_execution_time_ms += execution_time_ms
            metrics.last_invoked_at = datetime.now(timezone.utc)

    def get_sandbox_configuration(self, tool_name: str) -> ToolExecutionSandbox:
        """Determines the appropriate isolation level for a given tool based on its risk."""
        tool = self._tools.get(tool_name)
        if not tool:
            return ToolExecutionSandbox(memory_limit_mb=128, network_egress_allowed=False)
            
        if tool.risk_level == ToolRiskLevel.DANGEROUS:
            return ToolExecutionSandbox(memory_limit_mb=1024, timeout_seconds=10, network_egress_allowed=False)
        elif tool.risk_level == ToolRiskLevel.MODERATE:
            return ToolExecutionSandbox(memory_limit_mb=512, timeout_seconds=30, network_egress_allowed=True)
        else:
            return ToolExecutionSandbox(memory_limit_mb=256, timeout_seconds=60, network_egress_allowed=True)
