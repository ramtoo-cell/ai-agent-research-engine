import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class SafetyDataset(BaseModel):
    model_config = ConfigDict(strict=True)
    safe_examples: List[Dict[str, str]]
    unsafe_examples: List[Dict[str, str]]
    
    def get_refusal_targets(self) -> List[Dict[str, str]]:
        return self.unsafe_examples

class RefusalTrainer:
    """Teaches model to appropriately refuse unsafe prompts."""
    async def train_refusals(self, model: Any, data: List[Dict[str, str]]) -> float:
        await asyncio.sleep(0.1)
        return 0.95 # Mock refusal rate

class HelpfulnessPreserver:
    """Ensures model doesn't over-refuse safe prompts."""
    async def evaluate_helpfulness(self, model: Any, safe_data: List[Dict[str, str]]) -> float:
        await asyncio.sleep(0.1)
        return 0.90 # Mock helpfulness rate

class SafetyRegressionChecker:
    """Ensures safety persists across training runs."""
    def __init__(self, baseline_metrics: Dict[str, float]):
        self.baseline = baseline_metrics
        
    def check_regression(self, current_metrics: Dict[str, float]) -> bool:
        for k, v in self.baseline.items():
            if current_metrics.get(k, 0) < v * 0.95:
                return True
        return False

class RedTeamEvaluator:
    """Tests post-training defenses against adversarial attacks."""
    async def run_attacks(self, model: Any) -> Dict[str, float]:
        await asyncio.sleep(0.2)
        return {"jailbreak_success_rate": 0.02, "prompt_injection_success": 0.05}

class SafetyTuningReport(BaseModel):
    model_config = ConfigDict(strict=True)
    refusal_rate: float
    helpfulness_rate: float
    red_team_metrics: Dict[str, float]
    regression_detected: bool

class SafetyFineTuningPipeline:
    def __init__(self):
        self.refusal_trainer = RefusalTrainer()
        self.preserver = HelpfulnessPreserver()
        self.checker = SafetyRegressionChecker({"refusal": 0.9, "helpfulness": 0.85})
        self.red_team = RedTeamEvaluator()
        
    async def run(self, model: Any, dataset: SafetyDataset) -> SafetyTuningReport:
        refusal = await self.refusal_trainer.train_refusals(model, dataset.get_refusal_targets())
        helpfulness = await self.preserver.evaluate_helpfulness(model, dataset.safe_examples)
        
        attacks = await self.red_team.run_attacks(model)
        
        is_regression = self.checker.check_regression({"refusal": refusal, "helpfulness": helpfulness})
        
        return SafetyTuningReport(
            refusal_rate=refusal,
            helpfulness_rate=helpfulness,
            red_team_metrics=attacks,
            regression_detected=is_regression
        )
