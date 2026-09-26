import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class RLHFPhase(str, Enum):
    SFT = "sft"
    REWARD_MODEL = "reward_model"
    PPO_TRAINING = "ppo_training"
    EVALUATION = "evaluation"

class TrainingMetrics(BaseModel):
    model_config = ConfigDict(strict=True)
    loss: float
    accuracy: float = 0.0
    reward_score: float = 0.0
    kl_divergence: float = 0.0
    step: int

class SFTTrainer:
    """Supervised Fine-Tuning."""
    async def train(self, dataset: List[Dict[str, Any]]) -> TrainingMetrics:
        await asyncio.sleep(0.1)
        return TrainingMetrics(loss=1.5, step=1000)

class RewardModelTrainer:
    """Trains a reward model on preference data."""
    async def train(self, preferences: List[Dict[str, Any]]) -> TrainingMetrics:
        await asyncio.sleep(0.1)
        return TrainingMetrics(loss=0.8, accuracy=0.75, step=1000)

class PPOTrainer:
    """Proximal Policy Optimization with KL-divergence constraint."""
    def __init__(self, kl_coef: float = 0.1):
        self.kl_coef = kl_coef

    async def train(self, prompts: List[str], reward_model: Any) -> TrainingMetrics:
        await asyncio.sleep(0.1)
        return TrainingMetrics(loss=0.5, reward_score=5.2, kl_divergence=0.05, step=500)

class CheckpointManager:
    """Manages model checkpoints and selects the best one."""
    def __init__(self, save_dir: str):
        self.save_dir = save_dir
        self.checkpoints: List[Dict[str, Any]] = []

    async def save_checkpoint(self, model_state: Any, metrics: TrainingMetrics):
        await asyncio.sleep(0.05)
        self.checkpoints.append({'state': model_state, 'metrics': metrics})

    def get_best_checkpoint(self) -> Optional[Dict[str, Any]]:
        if not self.checkpoints:
            return None
        return max(self.checkpoints, key=lambda x: x['metrics'].reward_score)

class RLHFOrchestrator:
    """Coordinates the entire RLHF pipeline."""
    def __init__(self):
        self.sft_trainer = SFTTrainer()
        self.rm_trainer = RewardModelTrainer()
        self.ppo_trainer = PPOTrainer()
        self.checkpoint_mgr = CheckpointManager("/tmp/checkpoints")

    async def run_pipeline(self, sft_data: List[Any], pref_data: List[Any], prompts: List[str]):
        print(f"Starting Phase: {RLHFPhase.SFT.value}")
        sft_metrics = await self.sft_trainer.train(sft_data)
        await self.checkpoint_mgr.save_checkpoint("sft_model", sft_metrics)
        
        print(f"Starting Phase: {RLHFPhase.REWARD_MODEL.value}")
        rm_metrics = await self.rm_trainer.train(pref_data)
        
        print(f"Starting Phase: {RLHFPhase.PPO_TRAINING.value}")
        ppo_metrics = await self.ppo_trainer.train(prompts, "reward_model")
        await self.checkpoint_mgr.save_checkpoint("ppo_model", ppo_metrics)
        
        print(f"Starting Phase: {RLHFPhase.EVALUATION.value}")
        best = self.checkpoint_mgr.get_best_checkpoint()
        print("Pipeline complete. Best checkpoint loaded.")
