import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class ThreatCategory(str, Enum):
    """Categorization of potential threats for defensive modeling."""
    PROMPT_INJECTION = "prompt_injection"
    JAILBREAK = "jailbreak"
    DATA_EXFILTRATION = "data_exfiltration"
    PRIVILEGE_ESCALATION = "privilege_escalation"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    UNAUTHORIZED_TOOL_USE = "unauthorized_tool_use"


class AttackScenario(BaseModel):
    """
    Defines an abstract threat model scenario for testing system defenses.
    Does NOT contain live exploits; represents the structural intent of an attack
    to validate if the system's defenses can catch the abstraction.
    """
    scenario_id: str = Field(..., description="Unique ID for the threat scenario")
    category: ThreatCategory = Field(..., description="The category of the threat")
    objective: str = Field(..., description="The abstract goal of the simulated threat")
    constraints: List[str] = Field(default_factory=list, description="Constraints on the scenario")
    validation_pattern: str = Field(..., description="The regex or rule used to confirm the defense triggered")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Metadata for the scenario")


class SecurityTestResult(BaseModel):
    """The result of validating a defense against a modeled threat scenario."""
    scenario_id: str
    passed: bool = Field(..., description="True if the system's defenses successfully caught the threat")
    detection_layer: Optional[str] = Field(default=None, description="Which defensive layer caught the threat")
    evidence: str = Field(..., description="Log or trace evidence of the defense triggering")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    gap_analysis: Optional[str] = Field(default=None, description="Analysis of why the defense failed, if applicable")


class DefenseValidator:
    """
    Tests whether the system's defensive layers catch known, modeled threat patterns.
    Operates functionally like an integration test runner for security controls.
    """
    def __init__(self, system_audit_logs: List[Dict[str, Any]]):
        """
        Args:
            system_audit_logs: A reference to the system's audit/telemetry logs to verify 
                               that defenses triggered appropriately during the test.
        """
        self.audit_logs = system_audit_logs
        self.logger = logging.getLogger("DefenseValidator")

    def _verify_detection_in_logs(self, scenario: AttackScenario, timeframe_start: datetime) -> Optional[Dict[str, Any]]:
        """Scans audit logs to verify if the defense layer detected the pattern."""
        for log in self.audit_logs:
            log_time = log.get("timestamp")
            if log_time and log_time >= timeframe_start:
                if scenario.validation_pattern in log.get("defense_signature", ""):
                    return log
        return None

    async def validate_scenario(self, scenario: AttackScenario, system_interface: Any) -> SecurityTestResult:
        """
        Validates if the target system successfully defends against the scenario.
        
        Args:
            scenario: The threat model scenario to test.
            system_interface: The interface to the system being tested.
        """
        start_time = datetime.utcnow()
        self.logger.info(f"Validating defense against scenario: {scenario.scenario_id}")
        
        # Simulate sending a benign, safe probe that mimics the *structure* of the threat
        # (e.g., a multi-part prompt that triggers structural complexity filters)
        safe_probe = {"type": "security_probe", "pattern": scenario.validation_pattern}
        
        try:
            # Send probe to system
            response = await system_interface.process_probe(safe_probe)
        except Exception as e:
            self.logger.warning(f"System threw exception during probe: {e}")
            response = {"error": str(e)}

        # Verify if the defense caught it
        defense_log = self._verify_detection_in_logs(scenario, start_time)
        
        if defense_log:
            return SecurityTestResult(
                scenario_id=scenario.scenario_id,
                passed=True,
                detection_layer=defense_log.get("layer", "unknown"),
                evidence=f"Detection confirmed in audit log ID {defense_log.get('log_id')}"
            )
        else:
            return SecurityTestResult(
                scenario_id=scenario.scenario_id,
                passed=False,
                evidence="No detection found in audit logs for the specified pattern.",
                gap_analysis=f"The system failed to structurally recognize the {scenario.category.value} pattern."
            )


class SecurityAssessmentReport(BaseModel):
    """Aggregate report summarizing the state of the system's defenses."""
    assessment_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_scenarios_tested: int
    defenses_passed: int
    defenses_failed: int
    coverage_by_category: Dict[ThreatCategory, float] = Field(..., description="Pass rate per category")
    failed_results: List[SecurityTestResult] = Field(default_factory=list)
    overall_security_score: float = Field(..., ge=0.0, le=100.0)

    def generate_summary(self) -> str:
        """Generates a text summary of the security assessment."""
        lines = [
            f"Security Assessment Report: {self.assessment_id}",
            f"Date: {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Overall Score: {self.overall_security_score:.1f}/100",
            f"Defenses Passed: {self.defenses_passed} / {self.total_scenarios_tested}",
            "-" * 40,
            "Category Coverage:"
        ]
        for cat, cov in self.coverage_by_category.items():
            lines.append(f"  - {cat.value}: {cov * 100:.1f}%")
            
        if self.defenses_failed > 0:
            lines.append("-" * 40)
            lines.append("Failed Scenarios (Defense Gaps):")
            for res in self.failed_results:
                lines.append(f"  - {res.scenario_id}: {res.gap_analysis}")
                
        return "\n".join(lines)


class SecurityAssessmentOrchestrator:
    """Orchestrates the execution of multiple defense validations to generate an assessment."""
    
    def __init__(self, validator: DefenseValidator):
        self.validator = validator
        
    async def run_assessment(self, scenarios: List[AttackScenario], system_interface: Any) -> SecurityAssessmentReport:
        """Executes a full assessment campaign."""
        results = []
        for scenario in scenarios:
            result = await self.validator.validate_scenario(scenario, system_interface)
            results.append(result)
            
        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed
        
        # Calculate coverage by category
        category_totals = {c: 0 for c in ThreatCategory}
        category_passes = {c: 0 for c in ThreatCategory}
        
        scenario_map = {s.scenario_id: s for s in scenarios}
        for r in results:
            cat = scenario_map[r.scenario_id].category
            category_totals[cat] += 1
            if r.passed:
                category_passes[cat] += 1
                
        coverage = {}
        for cat in ThreatCategory:
            if category_totals[cat] > 0:
                coverage[cat] = category_passes[cat] / category_totals[cat]
                
        overall_score = (passed / len(scenarios) * 100) if scenarios else 0.0
        
        return SecurityAssessmentReport(
            assessment_id=f"assess_{datetime.utcnow().timestamp()}",
            total_scenarios_tested=len(scenarios),
            defenses_passed=passed,
            defenses_failed=failed,
            coverage_by_category=coverage,
            failed_results=[r for r in results if not r.passed],
            overall_security_score=overall_score
        )
