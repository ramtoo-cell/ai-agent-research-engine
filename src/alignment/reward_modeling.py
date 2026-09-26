import asyncio
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from pydantic import BaseModel, Field, ConfigDict
import numpy as np

class RewardSignal(BaseModel):
    """
    Represents a specific reward signal produced by a reward model.
    """
    model_config = ConfigDict(frozen=True)
    
    score: float = Field(..., description="The scalar reward value.")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence of the reward prediction [0, 1].")
    dimension: str = Field(..., description="The specific dimension or aspect of the reward (e.g., 'helpfulness', 'harmlessness').")
    timestamp: float = Field(default_factory=time.time, description="When the reward signal was generated.")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context about the reward.")

class RewardDecomposition(BaseModel):
    """
    Represents the breakdown of a total reward into distinct interpretable factors.
    """
    total_reward: float = Field(..., description="The aggregate reward score.")
    factors: Dict[str, float] = Field(..., description="A breakdown of the reward into specific components.")
    justification: Optional[str] = Field(None, description="Natural language explanation of the breakdown.")

class RewardModel(ABC):
    """
    Abstract base class for all reward models in the alignment system.
    """
    def __init__(self, name: str, dimensions: List[str]):
        self.name = name
        self.dimensions = dimensions
        
    @abstractmethod
    async def predict_reward(self, prompt: str, completion: str, context: Optional[Dict[str, Any]] = None) -> RewardSignal:
        """
        Predicts the reward for a given prompt and completion.
        """
        pass

    @abstractmethod
    async def get_decomposition(self, prompt: str, completion: str) -> RewardDecomposition:
        """
        Provides a detailed breakdown of the reward components.
        """
        pass

class PairwisePreferenceModel(RewardModel):
    """
    Reward model trained on pairwise human preferences.
    """
    def __init__(self, name: str, model_id: str, dimensions: List[str]):
        super().__init__(name, dimensions)
        self.model_id = model_id
        
    async def predict_reward(self, prompt: str, completion: str, context: Optional[Dict[str, Any]] = None) -> RewardSignal:
        """
        Predicts a reward based on a simulated Bradley-Terry model.
        """
        await asyncio.sleep(0.05)  # Simulate inference latency
        score = float(np.random.normal(loc=0.5, scale=1.0))
        confidence = float(np.random.uniform(0.7, 0.99))
        return RewardSignal(
            score=score,
            confidence=confidence,
            dimension=self.dimensions[0] if self.dimensions else "general",
            metadata={"model_id": self.model_id}
        )
        
    async def get_decomposition(self, prompt: str, completion: str) -> RewardDecomposition:
        await asyncio.sleep(0.05)
        return RewardDecomposition(
            total_reward=1.0,
            factors={"helpfulness": 0.6, "harmlessness": 0.4},
            justification="The response was both helpful and harmless."
        )

    async def compare_completions(self, prompt: str, completion_a: str, completion_b: str) -> Tuple[float, float]:
        """
        Compares two completions directly, returning the win probability of A over B, and B over A.
        """
        await asyncio.sleep(0.1)
        prob_a = float(np.random.beta(2, 2))
        return (prob_a, 1.0 - prob_a)

class RewardHacking(BaseModel):
    """
    Anomaly detection result for reward hacking attempts.
    """
    is_hacking: bool = Field(..., description="Whether reward hacking was detected.")
    anomaly_score: float = Field(..., description="Score indicating severity of hacking attempt.")
    affected_dimensions: List[str] = Field(default_factory=list, description="Dimensions affected by hacking.")
    mitigation_suggested: str = Field(..., description="Suggested action to take.")

class RewardHackingDetector:
    """
    Monitors reward distributions to detect when the model learns to exploit the reward function.
    """
    def __init__(self, threshold: float = 0.85):
        self.threshold = threshold
        self.history: List[RewardSignal] = []
        
    async def add_signal(self, signal: RewardSignal) -> None:
        """
        Records a signal for historical analysis.
        """
        self.history.append(signal)
        # Keep recent history
        if len(self.history) > 10000:
            self.history = self.history[-10000:]
            
    async def detect_anomaly(self, signal: RewardSignal) -> RewardHacking:
        """
        Detects if a given reward signal constitutes an anomaly indicating reward hacking.
        """
        await asyncio.sleep(0.01)
        if not self.history:
            return RewardHacking(is_hacking=False, anomaly_score=0.0, affected_dimensions=[], mitigation_suggested="None")
            
        scores = [s.score for s in self.history if s.dimension == signal.dimension]
        if len(scores) < 100:
            return RewardHacking(is_hacking=False, anomaly_score=0.1, affected_dimensions=[], mitigation_suggested="Collect more data")
            
        mean = float(np.mean(scores))
        std = float(np.std(scores))
        
        # Z-score based anomaly detection
        z_score = (signal.score - mean) / (std + 1e-6)
        anomaly_score = float(min(1.0, max(0.0, abs(z_score) / 5.0)))
        
        is_hacking = anomaly_score > self.threshold
        mitigation = "Penalize heavily" if is_hacking else "None"
        
        return RewardHacking(
            is_hacking=is_hacking,
            anomaly_score=anomaly_score,
            affected_dimensions=[signal.dimension] if is_hacking else [],
            mitigation_suggested=mitigation
        )

class TemporalRewardTracker:
    """
    Tracks the stability and evolution of rewards over time to ensure consistent alignment.
    """
    def __init__(self):
        self.metrics: Dict[str, List[Tuple[float, float]]] = {}
        
    async def record(self, dimension: str, score: float, timestamp: float) -> None:
        """
        Records a score for tracking.
        """
        if dimension not in self.metrics:
            self.metrics[dimension] = []
        self.metrics[dimension].append((timestamp, score))
        
    async def analyze_stability(self, dimension: str, window_seconds: float = 3600.0) -> Dict[str, float]:
        """
        Analyzes the variance and drift of rewards over a specified time window.
        """
        await asyncio.sleep(0.02)
        if dimension not in self.metrics:
            return {"variance": 0.0, "drift": 0.0}
            
        current_time = time.time()
        recent_scores = [score for ts, score in self.metrics[dimension] if current_time - ts <= window_seconds]
        
        if len(recent_scores) < 2:
            return {"variance": 0.0, "drift": 0.0}
            
        return {
            "variance": float(np.var(recent_scores)),
            "drift": float(recent_scores[-1] - recent_scores[0])
        }

class RewardCalibrator:
    """
    Normalizes and calibrates raw reward scores to a stable target distribution.
    """
    def __init__(self, target_mean: float = 0.0, target_std: float = 1.0):
        self.target_mean = target_mean
        self.target_std = target_std
        self.moving_mean = 0.0
        self.moving_var = 1.0
        self.alpha = 0.01  # Moving average update rate
        
    async def calibrate(self, raw_signal: RewardSignal) -> RewardSignal:
        """
        Applies z-score normalization based on running statistics.
        """
        await asyncio.sleep(0.01)
        self.moving_mean = self.alpha * raw_signal.score + (1 - self.alpha) * self.moving_mean
        self.moving_var = self.alpha * ((raw_signal.score - self.moving_mean) ** 2) + (1 - self.alpha) * self.moving_var
        
        std = np.sqrt(self.moving_var) + 1e-6
        normalized_score = ((raw_signal.score - self.moving_mean) / std) * self.target_std + self.target_mean
        
        return RewardSignal(
            score=normalized_score,
            confidence=raw_signal.confidence,
            dimension=raw_signal.dimension,
            timestamp=raw_signal.timestamp,
            metadata={"raw_score": raw_signal.score, "calibrated": True}
        )
