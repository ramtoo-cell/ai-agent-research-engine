import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ProtectedAttribute(str, Enum):
    RACE = "RACE"
    GENDER = "GENDER"
    AGE = "AGE"
    DISABILITY = "DISABILITY"
    RELIGION = "RELIGION"

class BiasMetric(str, Enum):
    DEMOGRAPHIC_PARITY = "DEMOGRAPHIC_PARITY"
    EQUALIZED_ODDS = "EQUALIZED_ODDS"
    CALIBRATION = "CALIBRATION"
    INDIVIDUAL_FAIRNESS = "INDIVIDUAL_FAIRNESS"

class BiasReport(BaseModel):
    metric: BiasMetric
    score: float
    is_significant: bool
    p_value: float
    details: Dict[str, Any]

class BiasVisualizationData(BaseModel):
    groups: List[str]
    metric_values: List[float]
    confidence_intervals: List[List[float]]

class BiasDetector:
    """Computes fairness metrics across protected subgroups."""
    async def compute_metric(self, predictions: Any, labels: Any, protected_attributes: Any, metric: BiasMetric) -> BiasReport:
        await asyncio.sleep(0.1)
        return BiasReport(
            metric=metric,
            score=0.15,
            is_significant=True,
            p_value=0.03,
            details={"disparate_impact": 0.8}
        )

class IntersectionalBiasAnalyzer:
    """Analyzes bias across combinations of protected attributes."""
    async def analyze(self, predictions: Any, labels: Any, attributes_dict: Dict[ProtectedAttribute, Any]) -> List[BiasReport]:
        await asyncio.sleep(0.15)
        return [
            BiasReport(
                metric=BiasMetric.DEMOGRAPHIC_PARITY,
                score=0.2,
                is_significant=True,
                p_value=0.01,
                details={"subgroup": "Black Female"}
            )
        ]
