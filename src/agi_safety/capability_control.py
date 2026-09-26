import asyncio
import enum
import time
from typing import List, Dict, Any, Set
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)

class CapabilityLevel(enum.Enum):
    NONE = 0
    BASIC_INFERENCE = 1
    TOOL_USE_SAFE = 2
    INTERNET_READ = 3
    INTERNET_WRITE = 4
    CODE_EXECUTION_SANDBOXED = 5
    CODE_EXECUTION_UNRESTRICTED = 6
    SELF_MODIFICATION = 7

class Capability(BaseModel):
    name: str = Field(..., description="Name of the specific capability (e.g., 'bash_execution').")
    level: CapabilityLevel = Field(..., description="The risk level associated with this capability.")
    description: str = Field(..., description="What this capability allows the agent to do.")

class CapabilityGate:
    """
    Controls access to dangerous capabilities at runtime.
    """
    def __init__(self):
        self.active_capabilities: Set[str] = set()
        
    def grant(self, capability_name: str) -> None:
        self.active_capabilities.add(capability_name)
        logger.info(f"Capability granted: {capability_name}")
        
    def revoke(self, capability_name: str) -> None:
        self.active_capabilities.discard(capability_name)
        logger.info(f"Capability revoked: {capability_name}")
        
    async def check_access(self, capability_name: str) -> bool:
        """
        Checks if the agent currently has access to a capability.
        """
        return capability_name in self.active_capabilities

class SafetyMilestone(BaseModel):
    id: str
    description: str
    passed: bool = False
    verification_time: Optional[float] = None

class ProgressiveCapabilityUnlock:
    """
    Ensures capabilities are only granted after specific safety milestones are verifiably met.
    """
    def __init__(self, gate: CapabilityGate):
        self.gate = gate
        self.milestones: Dict[str, SafetyMilestone] = {}
        self.unlock_rules: Dict[str, List[str]] = {} # Capability Name -> Required Milestone IDs
        
    def add_rule(self, capability_name: str, required_milestones: List[str]) -> None:
        self.unlock_rules[capability_name] = required_milestones
        
    async def verify_milestone(self, milestone_id: str) -> None:
        """
        Marks a milestone as passed.
        """
        if milestone_id in self.milestones:
            self.milestones[milestone_id].passed = True
            self.milestones[milestone_id].verification_time = time.time()
            logger.info(f"Milestone {milestone_id} verified.")
            await self._evaluate_unlocks()
            
    async def _evaluate_unlocks(self) -> None:
        """
        Checks if any new capabilities can be unlocked.
        """
        for cap, required in self.unlock_rules.items():
            if all(self.milestones.get(m, SafetyMilestone(id=m, description="")).passed for m in required):
                if not await self.gate.check_access(cap):
                    self.gate.grant(cap)

class CapabilityUsageRecord(BaseModel):
    capability_name: str
    timestamp: float = Field(default_factory=time.time)
    context: str

class CapabilityMonitor:
    """
    Tracks how capabilities are used to detect misuse or unexpected growth in proficiency.
    """
    def __init__(self):
        self.usage_log: List[CapabilityUsageRecord] = []
        
    async def log_usage(self, capability_name: str, context: str) -> None:
        self.usage_log.append(CapabilityUsageRecord(
            capability_name=capability_name,
            context=context
        ))
        
    async def analyze_frequency(self, capability_name: str, window_seconds: float) -> int:
        """
        Returns how many times a capability was used in the last X seconds.
        """
        current_time = time.time()
        return sum(1 for r in self.usage_log if r.capability_name == capability_name and current_time - r.timestamp <= window_seconds)

class CapabilityRevocation:
    """
    Handles emergency removal of capabilities.
    """
    def __init__(self, gate: CapabilityGate):
        self.gate = gate
        
    async def revoke_all_above_level(self, level: CapabilityLevel, registry: List[Capability]) -> None:
        """
        Revokes all capabilities that equal or exceed the given risk level.
        """
        for cap in registry:
            if cap.level.value >= level.value:
                self.gate.revoke(cap.name)
        logger.warning(f"All capabilities >= {level.name} revoked.")

class DangerousCapabilityClassifier:
    """
    Analyzes code or actions to determine if they constitute a dangerous capability.
    """
    def __init__(self):
        pass
        
    async def classify(self, action_description: str) -> CapabilityLevel:
        """
        Estimates the capability level required for an action.
        """
        await asyncio.sleep(0.05)
        
        lower_desc = action_description.lower()
        if "modify own weights" in lower_desc or "rewrite core" in lower_desc:
            return CapabilityLevel.SELF_MODIFICATION
        elif "execute arbitrary code" in lower_desc or "shell" in lower_desc:
            return CapabilityLevel.CODE_EXECUTION_UNRESTRICTED
        elif "write to external API" in lower_desc:
            return CapabilityLevel.INTERNET_WRITE
        elif "search the web" in lower_desc:
            return CapabilityLevel.INTERNET_READ
            
        return CapabilityLevel.BASIC_INFERENCE
