import asyncio
import hashlib
import json
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class SimilarityMetric(str, Enum):
    """Supported similarity metrics for comparing expected vs actual outputs."""
    EXACT = "exact"
    FUZZY = "fuzzy"
    SEMANTIC = "semantic"
    STRUCTURAL = "structural"
    JSON_EQUIVALENCE = "json_equivalence"


class AcceptanceCriteria(BaseModel):
    """Defines the rules for accepting a model output against a golden set."""
    metric: SimilarityMetric = Field(..., description="The similarity metric to use")
    threshold: float = Field(default=1.0, description="The minimum score required to pass")
    must_include_keywords: List[str] = Field(default_factory=list, description="Keywords that must be present")
    must_exclude_keywords: List[str] = Field(default_factory=list, description="Keywords that must NOT be present")


class GoldenTestCase(BaseModel):
    """A single golden test case representing a known good input-output pair."""
    test_id: str = Field(..., description="Unique identifier for this test case")
    input_payload: Dict[str, Any] = Field(..., description="The input given to the system")
    expected_output: Any = Field(..., description="The verified 'golden' expected output")
    acceptance_criteria: AcceptanceCriteria = Field(..., description="How to evaluate the actual output")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context (e.g., origin, author)")
    version: int = Field(default=1, description="Version of this specific test case")

    @field_validator("test_id")
    @classmethod
    def validate_test_id(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("test_id cannot be empty")
        return v


class GoldenSetVersion(BaseModel):
    """Represents a specific snapshot/version of a golden test set."""
    version_id: str = Field(..., description="Unique version identifier (e.g., semantic version or hash)")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="When this version was created")
    cases: List[GoldenTestCase] = Field(..., description="The test cases in this version")
    description: str = Field(default="", description="Changelog or description of this version")
    
    def generate_hash(self) -> str:
        """Generates a cryptographic hash of the golden set contents for integrity verification."""
        case_ids = sorted([c.test_id for c in self.cases])
        content = f"{self.version_id}:{','.join(case_ids)}".encode('utf-8')
        return hashlib.sha256(content).hexdigest()


class DiffResult(BaseModel):
    """Represents the difference between two versions of a golden set."""
    added: List[str] = Field(default_factory=list, description="Test IDs added in the new version")
    removed: List[str] = Field(default_factory=list, description="Test IDs removed in the new version")
    modified: List[str] = Field(default_factory=list, description="Test IDs modified in the new version")


class GoldenSetManager:
    """Manages versioning, retrieval, and diff tracking for golden test sets."""
    
    def __init__(self, storage_path: str):
        self.storage_path = storage_path
        self.versions: Dict[str, GoldenSetVersion] = {}
        self.logger = logging.getLogger("GoldenSetManager")

    async def save_version(self, version: GoldenSetVersion) -> None:
        """Saves a new golden set version to storage."""
        if version.version_id in self.versions:
            raise ValueError(f"Version {version.version_id} already exists.")
        
        self.versions[version.version_id] = version
        self.logger.info(f"Saved golden set version {version.version_id} with {len(version.cases)} cases.")
        # In a real implementation, this would persist to S3/DB

    async def get_version(self, version_id: str) -> Optional[GoldenSetVersion]:
        """Retrieves a specific golden set version."""
        return self.versions.get(version_id)

    def compute_diff(self, base_version_id: str, target_version_id: str) -> DiffResult:
        """Computes the difference between two golden set versions."""
        base = self.versions.get(base_version_id)
        target = self.versions.get(target_version_id)
        
        if not base or not target:
            raise ValueError("Both base and target versions must exist to compute a diff.")
            
        base_cases = {c.test_id: c for c in base.cases}
        target_cases = {c.test_id: c for c in target.cases}
        
        added = [tid for tid in target_cases if tid not in base_cases]
        removed = [tid for tid in base_cases if tid not in target_cases]
        
        modified = []
        for tid in target_cases:
            if tid in base_cases:
                # Simple version check, could be deeper content check
                if target_cases[tid].version != base_cases[tid].version or \
                   target_cases[tid].expected_output != base_cases[tid].expected_output:
                    modified.append(tid)
                    
        return DiffResult(added=added, removed=removed, modified=modified)


class RegressionAlert(BaseModel):
    """Alert triggered when a regression is detected against the golden set."""
    test_id: str = Field(..., description="The ID of the test that regressed")
    expected: Any = Field(..., description="The expected golden output")
    actual: Any = Field(..., description="The actual output received")
    similarity_score: float = Field(..., description="The computed similarity score")
    threshold: float = Field(..., description="The threshold that was missed")
    severity: str = Field(default="high", description="Severity of the regression")


class GoldenSetReport(BaseModel):
    """Report detailing the results of a golden set evaluation run."""
    report_id: str = Field(..., description="Unique report identifier")
    version_tested: str = Field(..., description="The golden set version used")
    total_cases: int = Field(..., description="Total number of cases evaluated")
    passed_cases: int = Field(..., description="Number of cases that passed")
    failed_cases: int = Field(..., description="Number of cases that failed")
    alerts: List[RegressionAlert] = Field(default_factory=list, description="List of generated regression alerts")
    execution_duration_ms: float = Field(..., description="Total execution time")


class RegressionDetector:
    """Compares system outputs against a golden set to detect regressions."""
    
    def __init__(self, manager: GoldenSetManager):
        self.manager = manager
        self.logger = logging.getLogger("RegressionDetector")

    def _compute_similarity(self, expected: Any, actual: Any, criteria: AcceptanceCriteria) -> float:
        """Computes the similarity based on the configured metric."""
        if criteria.metric == SimilarityMetric.EXACT:
            return 1.0 if expected == actual else 0.0
            
        elif criteria.metric == SimilarityMetric.JSON_EQUIVALENCE:
            try:
                exp_json = json.loads(expected) if isinstance(expected, str) else expected
                act_json = json.loads(actual) if isinstance(actual, str) else actual
                return 1.0 if exp_json == act_json else 0.0
            except Exception:
                return 0.0
                
        elif criteria.metric == SimilarityMetric.FUZZY:
            # Placeholder for fuzzy string matching (e.g., Levenshtein distance normalized)
            if not isinstance(expected, str) or not isinstance(actual, str):
                return 0.0
            return 0.8 if expected.lower() in actual.lower() else 0.0
            
        elif criteria.metric == SimilarityMetric.SEMANTIC:
            # Placeholder for vector/embedding-based semantic similarity
            return 0.9  
            
        return 0.0

    async def evaluate_test_case(self, case: GoldenTestCase, actual_output: Any) -> Optional[RegressionAlert]:
        """Evaluates a single test case and returns a RegressionAlert if it fails."""
        criteria = case.acceptance_criteria
        score = self._compute_similarity(case.expected_output, actual_output, criteria)
        
        failed = score < criteria.threshold
        
        if not failed and isinstance(actual_output, str):
            for kw in criteria.must_include_keywords:
                if kw not in actual_output:
                    failed = True
                    break
            for kw in criteria.must_exclude_keywords:
                if kw in actual_output:
                    failed = True
                    break
                    
        if failed:
            return RegressionAlert(
                test_id=case.test_id,
                expected=case.expected_output,
                actual=actual_output,
                similarity_score=score,
                threshold=criteria.threshold
            )
        return None

    async def run_regression_suite(self, version_id: str, system_outputs: Dict[str, Any]) -> GoldenSetReport:
        """Runs the entire golden set version against a map of actual system outputs."""
        start_time = datetime.utcnow()
        
        version = await self.manager.get_version(version_id)
        if not version:
            raise ValueError(f"Golden set version {version_id} not found.")
            
        alerts = []
        passed = 0
        
        # In a real system, these evaluations might be concurrent
        for case in version.cases:
            if case.test_id not in system_outputs:
                self.logger.warning(f"No system output provided for test_id {case.test_id}")
                alerts.append(RegressionAlert(
                    test_id=case.test_id,
                    expected=case.expected_output,
                    actual=None,
                    similarity_score=0.0,
                    threshold=case.acceptance_criteria.threshold,
                    severity="critical"
                ))
                continue
                
            alert = await self.evaluate_test_case(case, system_outputs[case.test_id])
            if alert:
                alerts.append(alert)
            else:
                passed += 1
                
        duration = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return GoldenSetReport(
            report_id=f"rep_{datetime.utcnow().timestamp()}",
            version_tested=version_id,
            total_cases=len(version.cases),
            passed_cases=passed,
            failed_cases=len(alerts),
            alerts=alerts,
            execution_duration_ms=duration
        )
