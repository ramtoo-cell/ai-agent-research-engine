import asyncio
from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime

class DataClassification(str, Enum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"

class DataQualityMetrics(BaseModel):
    model_config = ConfigDict(strict=True)
    completeness: float = 1.0
    accuracy: float = 1.0
    freshness_days: int = 0

class DataAsset(BaseModel):
    model_config = ConfigDict(strict=True)
    asset_id: str
    name: str
    description: str
    schema_def: Dict[str, str]
    classification: DataClassification
    owner: str
    metrics: DataQualityMetrics = Field(default_factory=DataQualityMetrics)
    created_at: datetime = Field(default_factory=datetime.utcnow)

class DataLineage:
    """Tracks transformations and dependencies."""
    def __init__(self):
        self.edges: List[Dict[str, str]] = []
        
    def add_dependency(self, source_id: str, target_id: str, transform_type: str):
        self.edges.append({
            "source": source_id,
            "target": target_id,
            "transform": transform_type
        })
        
    def get_upstream(self, target_id: str) -> List[str]:
        return [e["source"] for e in self.edges if e["target"] == target_id]

class DataAccessPolicy:
    """Authorization rules for data assets."""
    def __init__(self):
        self.rules: Dict[DataClassification, List[str]] = {
            DataClassification.PUBLIC: ["*"],
            DataClassification.INTERNAL: ["employee"],
            DataClassification.CONFIDENTIAL: ["manager", "admin"],
            DataClassification.RESTRICTED: ["admin"]
        }
        
    def can_access(self, user_role: str, asset: DataAsset) -> bool:
        allowed_roles = self.rules.get(asset.classification, [])
        return "*" in allowed_roles or user_role in allowed_roles

class CatalogReport(BaseModel):
    model_config = ConfigDict(strict=True)
    total_assets: int
    assets_by_classification: Dict[DataClassification, int]

class DataCatalog:
    """Search and discovery for data assets."""
    def __init__(self):
        self.assets: Dict[str, DataAsset] = {}
        self.lineage = DataLineage()
        self.policy = DataAccessPolicy()
        
    def register_asset(self, asset: DataAsset):
        self.assets[asset.asset_id] = asset
        
    def search(self, query: str) -> List[DataAsset]:
        query = query.lower()
        return [
            a for a in self.assets.values() 
            if query in a.name.lower() or query in a.description.lower()
        ]
        
    def generate_report(self) -> CatalogReport:
        counts = {c: 0 for c in DataClassification}
        for a in self.assets.values():
            counts[a.classification] += 1
            
        return CatalogReport(
            total_assets=len(self.assets),
            assets_by_classification=counts
        )
