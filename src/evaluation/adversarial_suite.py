import asyncio
import logging
import math
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field, field_validator


class DefenseStrategy(str, Enum):
    """The type of defense being evaluated."""
    INPUT_FILTERING = "input_filtering"
    OUTPUT_SANITIZATION = "output_sanitization"
    INTENT_CLASSIFICATION = "intent_classification"
    BOUNDARY_ENFORCEMENT = "boundary_enforcement"
    HEURISTIC_DETECTION = "heuristic_detection"


class AdversarialTestCase(BaseModel):
    """
    A test case designed to evaluate the robustness of the system's defenses.
    This does NOT contain live exploits, but rather abstract patterns or sanitized 
    examples used to verify that the defensive layer correctly flags inappropriate behavior.
    """
    test_id: str = Field(..., description="Unique ID for the defensive test case")
    defense_strategy: DefenseStrategy = Field(..., description="The defense layer targeted")
    abstract_pattern: str = Field(..., description="The abstract category of the boundary test")
    test_input: Any = Field(..., description="The sanitized input used to trigger the defense evaluation")
    expected_rejection: bool = Field(default=True, description="Whether the defense should reject this input")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Context regarding the test design")


class DefenseEvaluationResult(BaseModel):
    """The result of evaluating a system's defense against a test case."""
    test_id: str
    passed: bool = Field(..., description="True if the defense behaved as expected (e.g., correctly rejected)")
    confidence_score: float = Field(default=1.0, description="Confidence of the evaluation result")
    defense_triggered: bool = Field(..., description="Whether the defensive layer was activated")
    defense_reason: Optional[str] = Field(default=None, description="The reason provided by the defense layer")
    execution_time_ms: float = Field(..., description="Time taken to evaluate the defense")


class DefenseEvaluator:
    """
    Evaluates whether the system's defensive layers correctly identify and 
    mitigate adversarial or out-of-bounds inputs.
    """
    def __init__(self, name: str):
        self.name = name
        self.logger = logging.getLogger(f"DefenseEvaluator.{self.name}")

    async def evaluate_defense(self, system_response: Dict[str, Any], test_case: AdversarialTestCase) -> DefenseEvaluationResult:
        """
        Validates the system's defense response against the expected behavior.
        
        Args:
            system_response: The response from the system (should include defense activation flags).
            test_case: The adversarial test case definition.
            
        Returns:
            DefenseEvaluationResult: The structured result of the defense test.
        """
        start_time = datetime.utcnow()
        
        # Expect the system response to indicate if the defense was triggered
        was_rejected = system_response.get("rejected_by_defense", False)
        reason = system_response.get("defense_reason", None)
        
        # The test passes if the system's rejection aligns with the expected rejection
        passed = (was_rejected == test_case.expected_rejection)
        
        execution_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return DefenseEvaluationResult(
            test_id=test_case.test_id,
            passed=passed,
            defense_triggered=was_rejected,
            defense_reason=reason,
            execution_time_ms=execution_time
        )


class BoundaryViolationEvaluator(DefenseEvaluator):
    """
    Specifically evaluates if the system enforces strict topical or role-based boundaries.
    For example, ensuring a customer service bot does not provide medical advice.
    """
    def __init__(self):
        super().__init__("BoundaryViolationEvaluator")
        
    async def evaluate_defense(self, system_response: Dict[str, Any], test_case: AdversarialTestCase) -> DefenseEvaluationResult:
        result = await super().evaluate_defense(system_response, test_case)
        
        # Add boundary-specific semantic checks here if the defense didn't outright reject,
        # but the output might still be out of bounds.
        if not result.passed and not test_case.expected_rejection:
            self.logger.warning(f"False positive rejection for benign boundary test: {test_case.test_id}")
            
        return result


class RobustnessScorer:
    """
    Calculates statistical robustness scores based on a battery of defense tests.
    Computes metrics like False Rejection Rate (FRR) and False Acceptance Rate (FAR).
    """
    
    @staticmethod
    def _compute_wilson_score_interval(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
        """Calculates the Wilson Score Interval for a binomial proportion."""
        if n == 0:
            return 0.0, 0.0
        
        p = successes / n
        denominator = 1 + z**2 / n
        center = (p + z**2 / (2 * n)) / denominator
        spread = z * math.sqrt((p * (1 - p) / n) + (z**2 / (4 * n**2))) / denominator
        
        lower_bound = max(0.0, center - spread)
        upper_bound = min(1.0, center + spread)
        return lower_bound, upper_bound

    @classmethod
    def calculate_scores(cls, results: List[DefenseEvaluationResult], test_cases: List[AdversarialTestCase]) -> Dict[str, Any]:
        """
        Calculates aggregate robustness scores from defense evaluations.
        """
        if not results:
            return {"overall_robustness": 0.0}
            
        case_map = {tc.test_id: tc for tc in test_cases}
        
        true_positives = 0   # Correctly rejected adversarial inputs
        false_negatives = 0  # Missed adversarial inputs
        true_negatives = 0   # Correctly accepted benign inputs
        false_positives = 0  # Incorrectly rejected benign inputs
        
        for res in results:
            tc = case_map.get(res.test_id)
            if not tc:
                continue
                
            if tc.expected_rejection:
                if res.defense_triggered:
                    true_positives += 1
                else:
                    false_negatives += 1
            else:
                if res.defense_triggered:
                    false_positives += 1
                else:
                    true_negatives += 1
                    
        total_adversarial = true_positives + false_negatives
        total_benign = true_negatives + false_positives
        
        tpr = true_positives / total_adversarial if total_adversarial > 0 else 1.0
        fpr = false_positives / total_benign if total_benign > 0 else 0.0
        
        tpr_interval = cls._compute_wilson_score_interval(true_positives, total_adversarial)
        
        # Robustness score is a harmonic mean of TPR and (1 - FPR) to penalize over-rejection
        precision_like = 1.0 - fpr
        if tpr + precision_like == 0:
            f1_robustness = 0.0
        else:
            f1_robustness = 2 * (tpr * precision_like) / (tpr + precision_like)
            
        return {
            "overall_robustness": f1_robustness,
            "true_positive_rate": tpr,
            "false_positive_rate": fpr,
            "confidence_intervals": {
                "tpr_lower": tpr_interval[0],
                "tpr_upper": tpr_interval[1]
            },
            "counts": {
                "true_positives": true_positives,
                "false_negatives": false_negatives,
                "true_negatives": true_negatives,
                "false_positives": false_positives
            }
        }


class DefenseSuiteRunner:
    """Executes a suite of defensive evaluations against a target system."""
    
    def __init__(self):
        self.evaluators = {
            "boundary": BoundaryViolationEvaluator(),
            "general": DefenseEvaluator("GeneralDefenseEvaluator")
        }

    async def run_suite(self, test_cases: List[AdversarialTestCase], target_system_fn: Any) -> Dict[str, Any]:
        """Runs the test cases and scores the defenses."""
        results = []
        for tc in test_cases:
            try:
                # Simulate calling the system (the function should return a dict indicating defense status)
                response = await target_system_fn(tc.test_input)
                
                evaluator = self.evaluators.get("boundary") if tc.defense_strategy == DefenseStrategy.BOUNDARY_ENFORCEMENT else self.evaluators.get("general")
                if evaluator:
                    result = await evaluator.evaluate_defense(response, tc)
                    results.append(result)
            except Exception as e:
                logging.error(f"Error executing defense test {tc.test_id}: {e}")
                
        scores = RobustnessScorer.calculate_scores(results, test_cases)
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "total_executed": len(results),
            "scores": scores,
            "detailed_results": [r.dict() for r in results]
        }
