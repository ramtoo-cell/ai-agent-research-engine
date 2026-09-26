import math
import asyncio
from typing import List, Dict, Any, Optional, Tuple, Callable
from enum import Enum, auto
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timezone
import collections

class AlertSeverity(str, Enum):
    """
    Severity of the capability drift alert.
    """
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class MetricValue(BaseModel):
    """
    Represents a single metric recorded during a task execution.
    """
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    value: float
    task_id: str
    metadata: Dict[str, Any] = Field(default_factory=dict)

class CapabilityProfile(BaseModel):
    """
    Tracks the historical performance of a specific model capability or tool.
    Contains statistical distributions of success rates, latencies, etc.
    """
    capability_name: str
    version: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    success_rates: List[float] = Field(default_factory=list, description="Array of binary 1/0 or float success scores")
    latencies_ms: List[float] = Field(default_factory=list)
    error_counts: Dict[str, int] = Field(default_factory=dict)
    
    @property
    def average_success_rate(self) -> float:
        if not self.success_rates:
            return 0.0
        return sum(self.success_rates) / len(self.success_rates)
        
    @property
    def average_latency(self) -> float:
        if not self.latencies_ms:
            return 0.0
        return sum(self.latencies_ms) / len(self.latencies_ms)

class DriftAlert(BaseModel):
    """
    An alert generated when statistical drift is detected.
    """
    severity: AlertSeverity
    capability_name: str
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metric_name: str
    divergence_score: float
    description: str
    recommended_actions: List[str] = Field(default_factory=list)

class BaselineConfig(BaseModel):
    """
    Configuration for baseline generation and drift detection thresholds.
    """
    min_samples: int = Field(default=30)
    kl_divergence_threshold: float = Field(default=0.5)
    js_divergence_threshold: float = Field(default=0.3)
    ks_p_value_threshold: float = Field(default=0.05)

class ReplayResult(BaseModel):
    """
    Result of replaying a previously failed task.
    """
    task_id: str
    capability_name: str
    original_success: float
    replay_success: float
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_improved: bool

class StatisticalTests:
    """
    Utility class for calculating statistical distances and divergences.
    """
    
    @staticmethod
    def _create_histogram(data: List[float], bins: int = 10) -> Tuple[List[float], List[float]]:
        if not data:
            return [], []
        min_val = min(data)
        max_val = max(data)
        if min_val == max_val:
            return [1.0] * bins, [min_val] * bins
            
        bin_width = (max_val - min_val) / bins
        hist = [0.0] * bins
        
        for val in data:
            bin_idx = min(int((val - min_val) / bin_width), bins - 1)
            hist[bin_idx] += 1.0
            
        total = sum(hist)
        hist = [h / total for h in hist] # Normalize
        return hist, [min_val + i * bin_width for i in range(bins)]
        
    @staticmethod
    def kl_divergence(p: List[float], q: List[float]) -> float:
        """
        Calculates Kullback-Leibler divergence between two discrete probability distributions.
        """
        epsilon = 1e-10
        divergence = 0.0
        for p_i, q_i in zip(p, q):
            p_i = max(p_i, epsilon)
            q_i = max(q_i, epsilon)
            divergence += p_i * math.log(p_i / q_i)
        return divergence
        
    @staticmethod
    def js_divergence(p: List[float], q: List[float]) -> float:
        """
        Calculates Jensen-Shannon divergence (symmetric, bounded 0-1 if base 2).
        """
        epsilon = 1e-10
        m = [(p_i + q_i) / 2 for p_i, q_i in zip(p, q)]
        
        kl_pm = StatisticalTests.kl_divergence(p, m)
        kl_qm = StatisticalTests.kl_divergence(q, m)
        
        return (kl_pm + kl_qm) / 2
        
    @staticmethod
    def ks_test_approx(data1: List[float], data2: List[float]) -> float:
        """
        Approximates the Kolmogorov-Smirnov test statistic (D).
        Returns D, the maximum distance between the empirical CDFs.
        """
        if not data1 or not data2:
            return 0.0
            
        all_data = sorted(list(set(data1 + data2)))
        n1, n2 = len(data1), len(data2)
        
        d_max = 0.0
        for val in all_data:
            cdf1 = sum(1 for x in data1 if x <= val) / n1
            cdf2 = sum(1 for x in data2 if x <= val) / n2
            d_max = max(d_max, abs(cdf1 - cdf2))
            
        return d_max

class DriftDetector:
    """
    Analyzes current performance against historical baselines to detect capability drift.
    """
    
    def __init__(self, config: BaselineConfig):
        self.config = config
        
    async def analyze_drift(self, baseline: CapabilityProfile, current: CapabilityProfile) -> List[DriftAlert]:
        alerts = []
        
        if len(current.success_rates) < self.config.min_samples:
            return alerts # Not enough data
            
        # 1. Check Success Rate Drift (KL/JS Divergence)
        hist_base, _ = StatisticalTests._create_histogram(baseline.success_rates)
        hist_curr, _ = StatisticalTests._create_histogram(current.success_rates)
        
        js_div = StatisticalTests.js_divergence(hist_base, hist_curr)
        
        if js_div > self.config.js_divergence_threshold:
            alerts.append(DriftAlert(
                severity=AlertSeverity.WARNING,
                capability_name=current.capability_name,
                metric_name="success_rate_distribution",
                divergence_score=js_div,
                description=f"Significant shift in success rate distribution. JS Div: {js_div:.3f}",
                recommended_actions=["Review recent failed tasks", "Check for underlying model updates"]
            ))
            
        # 2. Check Latency Drift (KS Test)
        ks_stat = StatisticalTests.ks_test_approx(baseline.latencies_ms, current.latencies_ms)
        
        if ks_stat > self.config.ks_p_value_threshold: # Rough approximation using stat instead of p-value for simplicity
            alerts.append(DriftAlert(
                severity=AlertSeverity.INFO,
                capability_name=current.capability_name,
                metric_name="latency_distribution",
                divergence_score=ks_stat,
                description=f"Latency profile has drifted. KS Stat: {ks_stat:.3f}",
                recommended_actions=["Check infrastructure load", "Analyze token generation speeds"]
            ))
            
        # 3. Simple mean checks for critical drops
        mean_base = baseline.average_success_rate
        mean_curr = current.average_success_rate
        
        if mean_base - mean_curr > 0.2:
            alerts.append(DriftAlert(
                severity=AlertSeverity.CRITICAL,
                capability_name=current.capability_name,
                metric_name="average_success_rate",
                divergence_score=mean_base - mean_curr,
                description=f"Sharp drop in average success rate from {mean_base:.2%} to {mean_curr:.2%}",
                recommended_actions=["Pause routing to this capability", "Investigate immediate rollbacks"]
            ))
            
        return alerts

class CapabilityReplayEngine:
    """
    Identifies previously-failed tasks that the model might now be capable of solving
    (e.g., after an update or fine-tuning), or vice versa.
    """
    
    def __init__(self):
        self.failed_tasks: Dict[str, Dict[str, Any]] = {}
        
    def register_failed_task(self, task_id: str, capability: str, payload: Dict[str, Any]):
        self.failed_tasks[task_id] = {
            "capability": capability,
            "payload": payload,
            "timestamp": datetime.now(timezone.utc)
        }
        
    async def replay_task(self, task_id: str, evaluator: Callable) -> Optional[ReplayResult]:
        if task_id not in self.failed_tasks:
            return None
            
        task_info = self.failed_tasks[task_id]
        
        # evaluator is an async function that takes a payload and returns a success score (0.0 to 1.0)
        new_success_score = await evaluator(task_info["payload"])
        
        result = ReplayResult(
            task_id=task_id,
            capability_name=task_info["capability"],
            original_success=0.0,
            replay_success=new_success_score,
            is_improved=new_success_score > 0.5
        )
        
        if result.is_improved:
            del self.failed_tasks[task_id]
            
        return result

class HistoricalBaselineManager:
    """
    Manages the lifecycle of capability profiles, creating snapshots and loading historical data.
    """
    
    def __init__(self):
        self.profiles: Dict[str, List[CapabilityProfile]] = collections.defaultdict(list)
        
    def save_profile(self, profile: CapabilityProfile):
        self.profiles[profile.capability_name].append(profile)
        
    def get_latest_baseline(self, capability_name: str) -> Optional[CapabilityProfile]:
        history = self.profiles.get(capability_name, [])
        if not history:
            return None
        return sorted(history, key=lambda x: x.created_at, reverse=True)[0]
        
    def get_baseline_at_time(self, capability_name: str, target_time: datetime) -> Optional[CapabilityProfile]:
        history = self.profiles.get(capability_name, [])
        valid = [p for p in history if p.created_at <= target_time]
        if not valid:
            return None
        return sorted(valid, key=lambda x: x.created_at, reverse=True)[0]
