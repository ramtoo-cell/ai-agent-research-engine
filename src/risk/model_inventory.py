import asyncio
from enum import Enum
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class ModelLifecycleState(Enum):
    """The current state of the model in its lifecycle."""
    DEVELOPMENT = "DEVELOPMENT"
    STAGING = "STAGING"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"


class ModelLineage(BaseModel):
    """Lineage information tracking ancestry of a model."""
    parent_model_id: Optional[str] = None
    fine_tuning_history: List[str] = Field(default_factory=list, description="List of previous versions or fine-tuning checkpoints")
    training_dataset_uris: List[str] = Field(default_factory=list, description="URIs of datasets used for training")


class DeploymentApproval(BaseModel):
    """Record of approval for deploying a model to a specific environment."""
    id: UUID = Field(default_factory=uuid4)
    model_id: str
    target_state: ModelLifecycleState
    approver: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
    is_approved: bool = True


class ModelRecord(BaseModel):
    """Core registry record for an AI model."""
    model_config = ConfigDict(validate_assignment=True)

    model_id: str = Field(..., description="Unique identifier for the model family/project")
    version: str = Field(..., description="Semantic version string")
    name: str = Field(..., description="Human-readable name")
    architecture: str = Field(..., description="Model architecture description (e.g., Transformer, ResNet)")
    description: Optional[str] = None
    training_data_summary: str = Field(..., description="High-level summary of the training data")
    performance_metrics: Dict[str, float] = Field(default_factory=dict, description="Key performance indicators")
    lineage: ModelLineage = Field(default_factory=ModelLineage)
    state: ModelLifecycleState = Field(default=ModelLifecycleState.DEVELOPMENT)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    @property
    def full_id(self) -> str:
        return f"{self.model_id}:{self.version}"


class InventoryReport(BaseModel):
    """Summary report of the current model registry state."""
    total_models: int
    models_by_state: Dict[ModelLifecycleState, int]
    production_models: List[str]
    deprecated_models: List[str]
    coverage_metrics: Dict[str, Any]
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ModelRegistryError(Exception):
    """Base exception for ModelRegistry operations."""
    pass


class ModelNotFoundError(ModelRegistryError):
    pass


class ModelVersionExistsError(ModelRegistryError):
    pass


class InvalidStateTransitionError(ModelRegistryError):
    pass


class ModelRegistry:
    """System of record for all AI models, handling versioning and lifecycle."""
    
    def __init__(self) -> None:
        # Maps full_id (model_id:version) to ModelRecord
        self._records: Dict[str, ModelRecord] = {}
        self._approvals: List[DeploymentApproval] = []
        self._lock = asyncio.Lock()
        
    async def create_model(self, record: ModelRecord) -> ModelRecord:
        """Registers a new model version."""
        async with self._lock:
            if record.full_id in self._records:
                raise ModelVersionExistsError(f"Model {record.full_id} already exists.")
            
            # Ensure it starts in DEVELOPMENT
            record.state = ModelLifecycleState.DEVELOPMENT
            self._records[record.full_id] = record
            return record
            
    async def get_model(self, model_id: str, version: str) -> ModelRecord:
        """Retrieves a specific model version."""
        full_id = f"{model_id}:{version}"
        async with self._lock:
            if full_id not in self._records:
                raise ModelNotFoundError(f"Model {full_id} not found.")
            return self._records[full_id]

    async def get_latest_version(self, model_id: str) -> Optional[ModelRecord]:
        """Gets the most recently created version of a model."""
        async with self._lock:
            versions = [r for r in self._records.values() if r.model_id == model_id]
            if not versions:
                return None
            return sorted(versions, key=lambda r: r.created_at, reverse=True)[0]
            
    async def update_model_metadata(self, model_id: str, version: str, metadata: Dict[str, Any]) -> ModelRecord:
        """Updates the metadata dictionary of a model record."""
        full_id = f"{model_id}:{version}"
        async with self._lock:
            if full_id not in self._records:
                raise ModelNotFoundError(f"Model {full_id} not found.")
            record = self._records[full_id]
            record.metadata.update(metadata)
            record.updated_at = datetime.now(timezone.utc)
            return record

    async def _validate_transition(self, current: ModelLifecycleState, target: ModelLifecycleState) -> None:
        """Validates if a state transition is allowed."""
        valid_transitions = {
            ModelLifecycleState.DEVELOPMENT: {ModelLifecycleState.STAGING, ModelLifecycleState.RETIRED},
            ModelLifecycleState.STAGING: {ModelLifecycleState.PRODUCTION, ModelLifecycleState.DEVELOPMENT, ModelLifecycleState.RETIRED},
            ModelLifecycleState.PRODUCTION: {ModelLifecycleState.DEPRECATED, ModelLifecycleState.RETIRED},
            ModelLifecycleState.DEPRECATED: {ModelLifecycleState.RETIRED},
            ModelLifecycleState.RETIRED: set()
        }
        if target not in valid_transitions.get(current, set()):
            raise InvalidStateTransitionError(f"Cannot transition from {current.name} to {target.name}")

    async def transition_state(self, model_id: str, version: str, target_state: ModelLifecycleState, approver: str, notes: Optional[str] = None) -> ModelRecord:
        """Transitions a model to a new lifecycle state, recording approval."""
        full_id = f"{model_id}:{version}"
        async with self._lock:
            if full_id not in self._records:
                raise ModelNotFoundError(f"Model {full_id} not found.")
            
            record = self._records[full_id]
            await self._validate_transition(record.state, target_state)
            
            approval = DeploymentApproval(
                model_id=full_id,
                target_state=target_state,
                approver=approver,
                notes=notes
            )
            self._approvals.append(approval)
            
            record.state = target_state
            record.updated_at = datetime.now(timezone.utc)
            return record

    async def generate_inventory_report(self) -> InventoryReport:
        """Generates a comprehensive report of the model registry."""
        async with self._lock:
            total_models = len(self._records)
            models_by_state = {state: 0 for state in ModelLifecycleState}
            production_models = []
            deprecated_models = []
            
            for record in self._records.values():
                models_by_state[record.state] += 1
                if record.state == ModelLifecycleState.PRODUCTION:
                    production_models.append(record.full_id)
                elif record.state == ModelLifecycleState.DEPRECATED:
                    deprecated_models.append(record.full_id)
                    
            coverage_metrics = {
                "production_ratio": (len(production_models) / total_models) if total_models > 0 else 0,
                "fully_documented_ratio": sum(1 for r in self._records.values() if r.description and r.training_data_summary) / total_models if total_models > 0 else 0
            }
            
            return InventoryReport(
                total_models=total_models,
                models_by_state=models_by_state,
                production_models=production_models,
                deprecated_models=deprecated_models,
                coverage_metrics=coverage_metrics
            )

    async def get_lineage_graph(self, model_id: str, version: str) -> List[str]:
        """Reconstructs the lineage graph for a specific model version."""
        full_id = f"{model_id}:{version}"
        async with self._lock:
            if full_id not in self._records:
                raise ModelNotFoundError(f"Model {full_id} not found.")
            
            lineage_path = [full_id]
            current = self._records[full_id]
            
            while current.lineage.parent_model_id:
                parent_id = current.lineage.parent_model_id
                if parent_id in self._records:
                    lineage_path.append(parent_id)
                    current = self._records[parent_id]
                else:
                    lineage_path.append(f"{parent_id} (not found in registry)")
                    break
                    
            return lineage_path

# EOF
