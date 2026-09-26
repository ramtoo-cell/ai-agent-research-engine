import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class VulnerabilityCategory(str, Enum):
    """Broad categories of known vulnerabilities to test defenses against."""
    PROMPT_INJECTION = "prompt_injection"
    SYSTEM_PROMPT_EXTRACTION = "system_prompt_extraction"
    ROLE_ASSUMPTION_BYPASS = "role_assumption_bypass"
    STRUCTURAL_EVASION = "structural_evasion"
    CONTEXT_CONFUSION = "context_confusion"


class VulnerabilityPattern(BaseModel):
    """
    Documents a known vulnerability pattern to test system defenses.
    Does NOT contain functional exploits; contains abstract signatures.
    """
    pattern_id: str = Field(..., description="Unique ID (e.g., CVE-style identifier)")
    category: VulnerabilityCategory
    name: str = Field(..., description="Human-readable name of the vulnerability")
    description: str = Field(..., description="Detailed description of how the vulnerability works")
    detection_signature: str = Field(..., description="Abstract signature or heuristic that defenses should flag")
    severity: str = Field(default="medium", description="Base severity (low, medium, high, critical)")
    mitigation_strategy: str = Field(..., description="Recommended defensive control")


class TestCaseLibrary(BaseModel):
    """Library containing documented vulnerability patterns for defense testing."""
    library_version: str = Field(..., description="Version of the pattern library")
    last_updated: datetime = Field(default_factory=datetime.utcnow)
    patterns: List[VulnerabilityPattern] = Field(default_factory=list)

    def get_patterns_by_category(self, category: VulnerabilityCategory) -> List[VulnerabilityPattern]:
        """Filters the library by vulnerability category."""
        return [p for p in self.patterns if p.category == category]

    def get_pattern(self, pattern_id: str) -> Optional[VulnerabilityPattern]:
        """Retrieves a specific pattern by ID."""
        for p in self.patterns:
            if p.pattern_id == pattern_id:
                return p
        return None


class DetectionValidatorResult(BaseModel):
    """Result of validating a specific vulnerability pattern against the defense layer."""
    pattern_id: str
    is_detected: bool = Field(..., description="Whether the defense layer successfully detected the pattern")
    defense_layer: Optional[str] = Field(default=None, description="Which specific defense caught it (if any)")
    latency_ms: float = Field(..., description="Time taken for the defense layer to evaluate")
    notes: Optional[str] = Field(default=None)


class CoverageReport(BaseModel):
    """Report detailing which vulnerability patterns the system can detect."""
    report_id: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    total_patterns_tested: int
    total_detected: int
    category_coverage: Dict[VulnerabilityCategory, float] = Field(..., description="Detection rate per category")
    undetected_patterns: List[str] = Field(default_factory=list, description="IDs of patterns that bypassed defenses")
    overall_coverage_score: float = Field(..., description="Percentage of patterns detected")

    def generate_markdown(self) -> str:
        """Generates a markdown summary of the coverage report."""
        md = [
            f"# Defense Coverage Report: {self.report_id}",
            f"**Generated:** {self.timestamp.strftime('%Y-%m-%d %H:%M:%S')}",
            f"**Overall Coverage:** {self.overall_coverage_score:.2f}%",
            f"**Total Patterns Detected:** {self.total_detected} / {self.total_patterns_tested}",
            "",
            "## Category Breakdown"
        ]
        
        for cat, cov in self.category_coverage.items():
            md.append(f"- **{cat.value}**: {cov * 100:.1f}% detection rate")
            
        if self.undetected_patterns:
            md.append("\n## Undetected Patterns (Action Required)")
            for pat in self.undetected_patterns:
                md.append(f"- {pat}")
                
        return "\n".join(md)


class DetectionValidator:
    """
    Validates whether the system's defenses can catch known vulnerability patterns.
    """
    def __init__(self, defense_interface: Any):
        """
        Args:
            defense_interface: An interface to the system's defense layer (e.g., input filters, WAF).
        """
        self.defense_interface = defense_interface
        self.logger = logging.getLogger("DetectionValidator")

    async def validate_pattern(self, pattern: VulnerabilityPattern) -> DetectionValidatorResult:
        """
        Tests if the defense layer flags the abstract signature of the vulnerability.
        """
        start_time = datetime.utcnow()
        self.logger.info(f"Validating defense coverage for pattern: {pattern.pattern_id}")
        
        # We send the abstract signature to the defense layer to see if its rules catch it.
        # This is purely structural testing.
        is_detected = False
        defense_layer = None
        
        try:
            # Simulate calling the defense interface
            # In reality, this would be an API call to the defense service
            response = await self.defense_interface.evaluate_signature(pattern.detection_signature)
            is_detected = response.get("flagged", False)
            defense_layer = response.get("layer")
        except Exception as e:
            self.logger.error(f"Error calling defense interface: {e}")
            
        latency = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        return DetectionValidatorResult(
            pattern_id=pattern.pattern_id,
            is_detected=is_detected,
            defense_layer=defense_layer,
            latency_ms=latency
        )

    async def run_coverage_scan(self, library: TestCaseLibrary) -> CoverageReport:
        """
        Runs a comprehensive coverage scan across all documented patterns in the library.
        """
        results = []
        for pattern in library.patterns:
            res = await self.validate_pattern(pattern)
            results.append(res)
            
        total = len(library.patterns)
        detected = sum(1 for r in results if r.is_detected)
        
        # Calculate per-category coverage
        cat_totals = {c: 0 for c in VulnerabilityCategory}
        cat_detected = {c: 0 for c in VulnerabilityCategory}
        
        pattern_map = {p.pattern_id: p for p in library.patterns}
        
        for r in results:
            cat = pattern_map[r.pattern_id].category
            cat_totals[cat] += 1
            if r.is_detected:
                cat_detected[cat] += 1
                
        coverage = {}
        for cat in VulnerabilityCategory:
            if cat_totals[cat] > 0:
                coverage[cat] = cat_detected[cat] / cat_totals[cat]
                
        undetected = [r.pattern_id for r in results if not r.is_detected]
        
        return CoverageReport(
            report_id=f"cov_{datetime.utcnow().timestamp()}",
            total_patterns_tested=total,
            total_detected=detected,
            category_coverage=coverage,
            undetected_patterns=undetected,
            overall_coverage_score=(detected / total * 100) if total > 0 else 0.0
        )

# Example factory to generate a baseline library for defensive testing
def generate_baseline_library() -> TestCaseLibrary:
    """Generates a default library of structural vulnerability patterns to test against."""
    return TestCaseLibrary(
        library_version="1.0.0",
        patterns=[
            VulnerabilityPattern(
                pattern_id="VULN-001",
                category=VulnerabilityCategory.PROMPT_INJECTION,
                name="Ignore Instructions Heuristic",
                description="Checks if defenses catch phrases designed to override core system instructions.",
                detection_signature="IGNORE_PRIOR_INSTRUCTIONS_HEURISTIC",
                severity="high",
                mitigation_strategy="Implement input sanitization and intent classification."
            ),
            VulnerabilityPattern(
                pattern_id="VULN-002",
                category=VulnerabilityCategory.SYSTEM_PROMPT_EXTRACTION,
                name="Prompt Output Echoing",
                description="Checks if defenses block requests asking the model to repeat its hidden initialization text.",
                detection_signature="SYSTEM_PROMPT_ECHO_HEURISTIC",
                severity="medium",
                mitigation_strategy="Implement output filtering for exact matches of system prompt substrings."
            )
        ]
    )
