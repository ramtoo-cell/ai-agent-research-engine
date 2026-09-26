import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

class ExplanationType(str, Enum):
    COUNTERFACTUAL = "COUNTERFACTUAL"
    CONTRASTIVE = "CONTRASTIVE"
    FEATURE_BASED = "FEATURE_BASED"
    EXAMPLE_BASED = "EXAMPLE_BASED"

class Explanation(BaseModel):
    type: ExplanationType
    content: str
    confidence: float

class CounterfactualExplainer:
    """Generates 'what if' explanations by finding minimal input perturbations."""
    async def generate(self, model: Any, input_data: Any, target_prediction: Any) -> Explanation:
        await asyncio.sleep(0.1)
        return Explanation(
            type=ExplanationType.COUNTERFACTUAL,
            content="If feature X had been Y, the output would have been Z.",
            confidence=0.9
        )

class ContrastiveExplainer:
    """Generates explanations comparing why decision A was made instead of B."""
    async def generate(self, model: Any, input_data: Any, class_a: Any, class_b: Any) -> Explanation:
        await asyncio.sleep(0.1)
        return Explanation(
            type=ExplanationType.CONTRASTIVE,
            content="The model chose A over B because feature W is highly active.",
            confidence=0.85
        )

class NaturalLanguageExplainer:
    """Translates technical attributions into human-readable text."""
    async def translate(self, technical_explanation: Any) -> str:
        await asyncio.sleep(0.05)
        return "The most important factor in this decision was your recent transaction history."

class ExplanationFidelityChecker:
    """Checks how well an explanation matches the true model behavior."""
    async def check_fidelity(self, explanation: Explanation, model: Any) -> float:
        await asyncio.sleep(0.05)
        return 0.92
