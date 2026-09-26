import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class ContentFilter(BaseModel):
    model_config = ConfigDict(strict=True)
    name: str = Field(..., description="Name of the filter")
    enabled: bool = Field(True, description="Whether filter is enabled")

    async def apply(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Apply filter to data and return cleaned data."""
        if not self.enabled:
            return data
        return await self._filter_logic(data)
    
    async def _filter_logic(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        raise NotImplementedError

class ToxicContentFilter(ContentFilter):
    """Removes toxic or harmful content."""
    toxicity_threshold: float = 0.8
    
    async def _filter_logic(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        # Mock logic
        return [d for d in data if d.get('toxicity', 0.0) < self.toxicity_threshold]

class LowQualityFilter(ContentFilter):
    """Filters based on perplexity and length."""
    min_length: int = 10
    max_perplexity: float = 100.0
    
    async def _filter_logic(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        # Mock logic
        return [d for d in data if len(d.get('text', '')) >= self.min_length]

class PIIFilter(ContentFilter):
    """Removes personal identifiable information."""
    redact: bool = True
    
    async def _filter_logic(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        # Mock logic
        return data

class LicenseComplianceFilter(ContentFilter):
    """Checks data licensing."""
    allowed_licenses: List[str] = Field(default_factory=lambda: ["MIT", "Apache-2.0"])
    
    async def _filter_logic(self, data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        await asyncio.sleep(0.05)
        return [d for d in data if d.get('license') in self.allowed_licenses]

class FilteringReport(BaseModel):
    model_config = ConfigDict(strict=True)
    initial_count: int
    final_count: int
    filtered_by_rule: Dict[str, int]
    
    @property
    def retention_rate(self) -> float:
        return self.final_count / self.initial_count if self.initial_count > 0 else 0.0

class ContentFilteringPipeline:
    def __init__(self, filters: List[ContentFilter]):
        self.filters = filters

    async def process(self, data: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], FilteringReport]:
        initial_count = len(data)
        current_data = data
        filtered_stats = {}
        
        for f in self.filters:
            if not f.enabled:
                continue
            prev_count = len(current_data)
            current_data = await f.apply(current_data)
            filtered_stats[f.name] = prev_count - len(current_data)
            
        report = FilteringReport(
            initial_count=initial_count,
            final_count=len(current_data),
            filtered_by_rule=filtered_stats
        )
        return current_data, report
