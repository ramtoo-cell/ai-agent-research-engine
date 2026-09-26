import asyncio
import math
from enum import Enum
from typing import Dict, List, Optional, Any, Union
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class DriftSeverity(Enum):
    """Severity levels for detected drift."""
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class DriftMetric(BaseModel):
    """A tracked metric for drift detection."""
    metric_name: str
    baseline_value: float
    current_value: float
    warning_threshold: float
    critical_threshold: float
    is_higher_better: bool = True
    
    @property
    def drift_magnitude(self) -> float:
        return abs(self.current_value - self.baseline_value)
        
    @property
    def percentage_change(self) -> float:
        if self.baseline_value == 0:
            return float('inf') if self.current_value > 0 else 0.0
        return (self.current_value - self.baseline_value) / self.baseline_value


class DriftAlert(BaseModel):
    """Alert triggered when drift thresholds are breached."""
    id: UUID = Field(default_factory=uuid4)
    model_id: str
    metric_name: str
    severity: DriftSeverity
    detected_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    details: str
    auto_remediation_suggestions: List[str] = Field(default_factory=list)


class DriftDashboardData(BaseModel):
    """Aggregated data for drift monitoring dashboard visualization."""
    model_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    performance_metrics: List[DriftMetric]
    distribution_metrics: List[DriftMetric]
    active_alerts: List[DriftAlert]
    overall_status: DriftSeverity


class DistributionDriftDetector:
    """Detects statistical drift in data distributions (e.g., PSI, Wasserstein)."""
    
    def __init__(self, warning_threshold: float = 0.1, critical_threshold: float = 0.2) -> None:
        self.warning_threshold = warning_threshold
        self.critical_threshold = critical_threshold

    def calculate_psi(self, expected_proportions: List[float], actual_proportions: List[float]) -> float:
        """
        Calculates the Population Stability Index (PSI).
        PSI = sum((Actual_% - Expected_%) * ln(Actual_% / Expected_%))
        """
        if len(expected_proportions) != len(actual_proportions):
            raise ValueError("Proportions lists must have the same length.")
            
        psi = 0.0
        for exp, act in zip(expected_proportions, actual_proportions):
            # Avoid division by zero and log(0)
            exp = max(exp, 0.0001)
            act = max(act, 0.0001)
            psi += (act - exp) * math.log(act / exp)
        return psi

    def evaluate_drift(self, metric_name: str, psi_value: float) -> Optional[DriftSeverity]:
        """Evaluates severity based on PSI."""
        if psi_value >= self.critical_threshold:
            return DriftSeverity.CRITICAL
        elif psi_value >= self.warning_threshold:
            return DriftSeverity.WARNING
        return DriftSeverity.NORMAL


class PerformanceDriftDetector:
    """Monitors model performance metrics like accuracy, latency, error rate."""
    
    def __init__(self) -> None:
        self._baselines: Dict[str, Dict[str, float]] = {}

    def set_baseline(self, model_id: str, metrics: Dict[str, float]) -> None:
        """Sets the baseline performance metrics for a model."""
        self._baselines[model_id] = metrics.copy()

    def evaluate(self, model_id: str, current_metrics: Dict[str, float], thresholds: Dict[str, tuple]) -> List[DriftMetric]:
        """
        Evaluates current metrics against baselines.
        thresholds maps metric_name to (warning_delta, critical_delta, is_higher_better).
        """
        baselines = self._baselines.get(model_id, {})
        results = []
        
        for metric_name, current_val in current_metrics.items():
            if metric_name not in baselines or metric_name not in thresholds:
                continue
                
            baseline_val = baselines[metric_name]
            warn_th, crit_th, is_higher_better = thresholds[metric_name]
            
            results.append(DriftMetric(
                metric_name=metric_name,
                baseline_value=baseline_val,
                current_value=current_val,
                warning_threshold=warn_th,
                critical_threshold=crit_th,
                is_higher_better=is_higher_better
            ))
            
        return results


class ConceptDriftDetector:
    """Detects shifts in the underlying relationship between inputs and outputs."""
    
    def __init__(self, window_size: int = 1000) -> None:
        self.window_size = window_size
        self._error_rates: Dict[str, List[int]] = {}  # 0 for correct, 1 for error
        
    def add_feedback(self, model_id: str, is_error: bool) -> None:
        if model_id not in self._error_rates:
            self._error_rates[model_id] = []
        
        self._error_rates[model_id].append(1 if is_error else 0)
        
        # Maintain window size
        if len(self._error_rates[model_id]) > self.window_size:
            self._error_rates[model_id].pop(0)

    def detect(self, model_id: str) -> Optional[float]:
        """Simple concept drift detection based on moving average error rate."""
        window = self._error_rates.get(model_id, [])
        if len(window) < min(100, self.window_size):
            return None  # Not enough data
            
        return sum(window) / len(window)


class RealTimeDriftMonitor:
    """Orchestrates drift detection across distribution, performance, and concept."""
    
    def __init__(self) -> None:
        self.distribution_detector = DistributionDriftDetector()
        self.performance_detector = PerformanceDriftDetector()
        self.concept_detector = ConceptDriftDetector()
        self.active_alerts: List[DriftAlert] = []
        self._lock = asyncio.Lock()

    def _generate_remediation(self, metric: str, severity: DriftSeverity) -> List[str]:
        if severity == DriftSeverity.CRITICAL:
            return ["Trigger automated model retraining pipeline.", "Halt traffic to current model version.", "Alert MLOps on-call."]
        return ["Schedule review of data distribution.", "Log feature importance shift.", "Prepare shadowing for new model candidate."]

    async def check_performance(self, model_id: str, current_metrics: Dict[str, float], thresholds: Dict[str, tuple]) -> List[DriftAlert]:
        """Checks for performance degradation and generates alerts."""
        async with self._lock:
            metrics = self.performance_detector.evaluate(model_id, current_metrics, thresholds)
            new_alerts = []
            
            for metric in metrics:
                delta = metric.baseline_value - metric.current_value if metric.is_higher_better else metric.current_value - metric.baseline_value
                
                severity = DriftSeverity.NORMAL
                if delta >= metric.critical_threshold:
                    severity = DriftSeverity.CRITICAL
                elif delta >= metric.warning_threshold:
                    severity = DriftSeverity.WARNING
                    
                if severity != DriftSeverity.NORMAL:
                    alert = DriftAlert(
                        model_id=model_id,
                        metric_name=metric.metric_name,
                        severity=severity,
                        details=f"Metric {metric.metric_name} drifted by {delta:.4f} (Threshold: {metric.critical_threshold})",
                        auto_remediation_suggestions=self._generate_remediation(metric.metric_name, severity)
                    )
                    new_alerts.append(alert)
                    self.active_alerts.append(alert)
                    
            return new_alerts

    async def get_dashboard_data(self, model_id: str) -> DriftDashboardData:
        """Assembles the drift status for the dashboard view."""
        async with self._lock:
            model_alerts = [a for a in self.active_alerts if a.model_id == model_id]
            overall = DriftSeverity.NORMAL
            if any(a.severity == DriftSeverity.CRITICAL for a in model_alerts):
                overall = DriftSeverity.CRITICAL
            elif any(a.severity == DriftSeverity.WARNING for a in model_alerts):
                overall = DriftSeverity.WARNING
                
            return DriftDashboardData(
                model_id=model_id,
                performance_metrics=[],
                distribution_metrics=[],
                active_alerts=model_alerts,
                overall_status=overall
            )

# EOF
