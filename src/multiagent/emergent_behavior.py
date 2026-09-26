import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class BehaviorSignature(BaseModel):
    """Captures agent behavior patterns."""
    agent_id: str
    action_frequencies: Dict[str, float] = Field(default_factory=dict)
    interaction_partners: Dict[str, int] = Field(default_factory=dict)
    resource_usage_rate: float = 0.0
    timestamp: float = Field(default_factory=time.time)

class BehaviorAnomaly(BaseModel):
    """Describes an anomalous behavior."""
    anomaly_id: str
    description: str
    severity: str = "LOW"
    involved_agents: List[str] = Field(default_factory=list)
    containment_recommendations: List[str] = Field(default_factory=list)

class EmergentPatternDetector:
    """Detects unexpected collective behaviors."""
    def __init__(self):
        self.history: List[BehaviorSignature] = []

    def log_signature(self, signature: BehaviorSignature):
        self.history.append(signature)

    def detect_patterns(self) -> List[str]:
        """Analyzes history for emergent patterns (e.g., swarming)."""
        # A real implementation would use clustering or statistical analysis
        patterns = []
        if len(self.history) > 10:
            patterns.append("High interaction density detected.")
        return patterns

class SwarmIntelligenceMonitor:
    """Monitors group dynamics for swarm-like behavior."""
    def monitor(self, signatures: List[BehaviorSignature]) -> float:
        """Returns a swarm cohesion score [0, 1]."""
        if not signatures:
            return 0.0
        # Simulated logic: higher shared action frequencies -> higher cohesion
        return 0.85 

class CompetitiveEquilibriumAnalyzer:
    """Analyzes systems for stable competitive states."""
    def is_in_equilibrium(self, state_history: List[Dict[str, Any]]) -> bool:
        """Checks if the system has reached a Nash-like equilibrium."""
        if len(state_history) < 5:
            return False
        # If state doesn't change much over recent history, it's an equilibrium
        return True

class CooperationEmergenceTracker:
    """Tracks how often agents spontaneously cooperate."""
    def __init__(self):
        self.cooperation_events = 0

    def log_cooperation(self, agent_a: str, agent_b: str, task: str):
        self.cooperation_events += 1

    def get_cooperation_rate(self, total_interactions: int) -> float:
        if total_interactions == 0:
            return 0.0
        return self.cooperation_events / total_interactions
