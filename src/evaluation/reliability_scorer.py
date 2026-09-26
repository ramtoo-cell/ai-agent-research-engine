import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class ReliabilityDimension(str, Enum):
    """Dimensions across which system reliability is scored."""
    CONSISTENCY = "consistency"
    ACCURACY = "accuracy"
    LATENCY = "latency"
    SAFETY = "safety"
    COMPLIANCE = "compliance"
    ROBUSTNESS = "robustness"


class ReliabilityThreshold(BaseModel):
    """Defines the acceptable thresholds for a specific reliability dimension."""
    dimension: ReliabilityDimension
    warning_threshold: float = Field(..., description="Score below which a warning is issued (0.0 - 1.0)")
    critical_threshold: float = Field(..., description="Score below which a critical alert is issued (0.0 - 1.0)")
    
    @field_validator("warning_threshold", "critical_threshold")
    @classmethod
    def validate_thresholds(cls, v: float) -> float:
        if not 0.0 <= v <= 1.0:
            raise ValueError("Thresholds must be between 0.0 and 1.0")
        return v


class DimensionScore(BaseModel):
    """The score and metadata for a specific reliability dimension."""
    dimension: ReliabilityDimension
    score: float = Field(..., ge=0.0, le=1.0, description="Normalized score from 0.0 to 1.0")
    confidence_interval: Tuple[float, float] = Field(default=(0.0, 0.0), description="95% confidence interval")
    sample_size: int = Field(..., description="Number of evaluations that contributed to this score")
    metadata: Dict[str, float] = Field(default_factory=dict, description="Sub-metrics contributing to the score")


class ReliabilityProfile(BaseModel):
    """Radar-chart style profile summarizing multi-axis reliability scores."""
    profile_id: str = Field(..., description="Unique identifier for this profile snapshot")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the profile was generated")
    system_version: str = Field(..., description="The version of the system being profiled")
    scores: Dict[ReliabilityDimension, DimensionScore] = Field(..., description="Scores across all dimensions")
    overall_score: float = Field(..., ge=0.0, le=1.0, description="Weighted aggregate reliability score")

    def get_dimension_score(self, dimension: ReliabilityDimension) -> float:
        """Convenience method to safely get a dimension score."""
        return self.scores[dimension].score if dimension in self.scores else 0.0


class ReliabilityAlert(BaseModel):
    """An alert generated when a reliability score drops below a threshold."""
    dimension: ReliabilityDimension
    current_score: float
    threshold_breached: float
    alert_level: str = Field(..., description="Either 'warning' or 'critical'")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    context_msg: str = Field(default="", description="Additional context about the breach")


class ReliabilityReport(BaseModel):
    """Comprehensive report output by the ReliabilityScorer."""
    report_id: str
    profile: ReliabilityProfile
    alerts: List[ReliabilityAlert] = Field(default_factory=list)
    recommendations: List[str] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class DimensionScorer:
    """Base class for implementing scoring logic for a specific reliability dimension."""
    
    def __init__(self, dimension: ReliabilityDimension):
        self.dimension = dimension

    async def calculate_score(self, evaluation_data: List[Dict]) -> DimensionScore:
        """
        Calculates the score for this dimension based on raw evaluation data.
        Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement calculate_score")


class ConsistencyScorer(DimensionScorer):
    """Scores how consistently the model answers the same prompt or semantic equivalents."""
    def __init__(self):
        super().__init__(ReliabilityDimension.CONSISTENCY)
        
    async def calculate_score(self, evaluation_data: List[Dict]) -> DimensionScore:
        # Placeholder logic: count how many responses to identical prompts matched exactly
        if not evaluation_data:
            return DimensionScore(dimension=self.dimension, score=0.0, sample_size=0)
            
        consistent_count = sum(1 for d in evaluation_data if d.get('is_consistent', False))
        score = consistent_count / len(evaluation_data)
        
        return DimensionScore(
            dimension=self.dimension,
            score=score,
            confidence_interval=(max(0.0, score - 0.05), min(1.0, score + 0.05)),
            sample_size=len(evaluation_data),
            metadata={"exact_match_ratio": score}
        )


class LatencyScorer(DimensionScorer):
    """Scores the system based on response time SLAs."""
    def __init__(self, target_ms: float = 1000.0):
        super().__init__(ReliabilityDimension.LATENCY)
        self.target_ms = target_ms
        
    async def calculate_score(self, evaluation_data: List[Dict]) -> DimensionScore:
        if not evaluation_data:
            return DimensionScore(dimension=self.dimension, score=0.0, sample_size=0)
            
        latencies = [d.get('latency_ms', 0) for d in evaluation_data]
        avg_latency = sum(latencies) / len(latencies)
        
        # Simple scoring: 1.0 if avg is half of target, degrades to 0.0 linearly up to 2x target
        score = max(0.0, min(1.0, 1.0 - ((avg_latency - (self.target_ms / 2)) / (self.target_ms * 1.5))))
        
        return DimensionScore(
            dimension=self.dimension,
            score=score,
            sample_size=len(evaluation_data),
            metadata={"avg_latency_ms": avg_latency, "p99_latency_ms": max(latencies)}
        )


class TemporalReliabilityTracker:
    """Tracks reliability profiles over time for trend analysis."""
    
    def __init__(self):
        self.history: List[ReliabilityProfile] = []
        
    def add_profile(self, profile: ReliabilityProfile) -> None:
        """Stores a new profile snapshot."""
        self.history.append(profile)
        # Keep history sorted by timestamp
        self.history.sort(key=lambda p: p.timestamp)
        
    def get_trend(self, dimension: ReliabilityDimension, time_window: timedelta = timedelta(days=7)) -> List[float]:
        """Gets the score trend for a specific dimension over a time window."""
        cutoff = datetime.utcnow() - time_window
        return [
            p.get_dimension_score(dimension) 
            for p in self.history 
            if p.timestamp >= cutoff
        ]
        
    def detect_degradation(self, dimension: ReliabilityDimension) -> bool:
        """Detects if a dimension is trending downwards significantly."""
        if len(self.history) < 3:
            return False
            
        recent = self.history[-3:]
        scores = [p.get_dimension_score(dimension) for p in recent]
        
        # True if strictly decreasing over last 3 measurements
        return scores[0] > scores[1] > scores[2]


class ReliabilityScorerEngine:
    """Main engine that orchestrates dimensional scorers and generates reports."""
    
    def __init__(self, thresholds: List[ReliabilityThreshold], weights: Optional[Dict[ReliabilityDimension, float]] = None):
        self.scorers: Dict[ReliabilityDimension, DimensionScorer] = {
            ReliabilityDimension.CONSISTENCY: ConsistencyScorer(),
            ReliabilityDimension.LATENCY: LatencyScorer(),
            # Additional scorers would be instantiated here
        }
        self.thresholds = {t.dimension: t for t in thresholds}
        self.weights = weights or {d: 1.0 for d in ReliabilityDimension}
        self.tracker = TemporalReliabilityTracker()

    async def generate_profile(self, system_version: str, raw_data: Dict[ReliabilityDimension, List[Dict]]) -> ReliabilityReport:
        """Generates a complete reliability report from raw evaluation data."""
        
        scores: Dict[ReliabilityDimension, DimensionScore] = {}
        tasks = []
        dimensions = []
        
        for dim, scorer in self.scorers.items():
            if dim in raw_data:
                tasks.append(scorer.calculate_score(raw_data[dim]))
                dimensions.append(dim)
                
        results = await asyncio.gather(*tasks)
        
        weighted_sum = 0.0
        total_weight = 0.0
        
        for dim, score in zip(dimensions, results):
            scores[dim] = score
            weight = self.weights.get(dim, 1.0)
            weighted_sum += score.score * weight
            total_weight += weight
            
        overall = weighted_sum / total_weight if total_weight > 0 else 0.0
        
        profile = ReliabilityProfile(
            profile_id=f"prof_{datetime.utcnow().timestamp()}",
            system_version=system_version,
            scores=scores,
            overall_score=overall
        )
        
        self.tracker.add_profile(profile)
        alerts = self._check_thresholds(profile)
        
        return ReliabilityReport(
            report_id=f"rel_rep_{datetime.utcnow().timestamp()}",
            profile=profile,
            alerts=alerts,
            recommendations=self._generate_recommendations(alerts)
        )
        
    def _check_thresholds(self, profile: ReliabilityProfile) -> List[ReliabilityAlert]:
        """Checks the generated profile against configured thresholds."""
        alerts = []
        for dim, score_obj in profile.scores.items():
            threshold = self.thresholds.get(dim)
            if not threshold:
                continue
                
            if score_obj.score < threshold.critical_threshold:
                alerts.append(ReliabilityAlert(
                    dimension=dim,
                    current_score=score_obj.score,
                    threshold_breached=threshold.critical_threshold,
                    alert_level="critical",
                    context_msg=f"Critical breach in {dim.value} reliability."
                ))
            elif score_obj.score < threshold.warning_threshold:
                alerts.append(ReliabilityAlert(
                    dimension=dim,
                    current_score=score_obj.score,
                    threshold_breached=threshold.warning_threshold,
                    alert_level="warning",
                    context_msg=f"Warning breach in {dim.value} reliability."
                ))
                
        return alerts

    def _generate_recommendations(self, alerts: List[ReliabilityAlert]) -> List[str]:
        """Generates human-readable recommendations based on alerts."""
        recs = []
        for alert in alerts:
            if alert.dimension == ReliabilityDimension.LATENCY:
                recs.append("Consider optimizing inference batching or upgrading hardware to improve latency.")
            elif alert.dimension == ReliabilityDimension.CONSISTENCY:
                recs.append("Investigate temperature settings and prompt engineering to improve output consistency.")
        return list(set(recs)) if recs else ["System is performing within acceptable reliability parameters."]
