import json
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

class ControlStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    PARTIAL = "PARTIAL"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class ControlTestResult(BaseModel):
    """Result of a specific compliance control test."""
    control_id: str
    control_name: str
    status: ControlStatus
    evidence_links: List[str] = Field(default_factory=list)
    findings: str = ""
    recommendations: str = ""

class ComplianceReportTemplate(BaseModel):
    """Template schema for frameworks like SOC2, ISO27001, AI Risk Management Framework."""
    framework_name: str
    version: str
    controls_required: List[str]

class ComplianceScorecard(BaseModel):
    """Aggregate metrics of a compliance evaluation."""
    total_controls: int
    passed: int
    failed: int
    partial: int
    not_applicable: int
    overall_score_percentage: float = 0.0

    def calculate(self):
        active_controls = self.total_controls - self.not_applicable
        if active_controls > 0:
            self.overall_score_percentage = ((self.passed + (self.partial * 0.5)) / active_controls) * 100.0

class GapAnalysisReport(BaseModel):
    """Actionable report detailing compliance gaps."""
    report_id: str
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    framework: str
    scorecard: ComplianceScorecard
    critical_failures: List[ControlTestResult]
    remediation_plan: List[str]

class ReportRenderer:
    """Translates Python objects into standard human-readable compliance formats."""
    
    @staticmethod
    def render_markdown(report: GapAnalysisReport) -> str:
        """Generates a GitHub-flavored Markdown report."""
        md = []
        md.append(f"# Compliance Gap Analysis: {report.framework}")
        md.append(f"**Date:** {report.generated_at.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        md.append(f"**Report ID:** `{report.report_id}`\n")
        
        md.append("## Executive Summary")
        s = report.scorecard
        md.append(f"- **Overall Score:** {s.overall_score_percentage:.2f}%")
        md.append(f"- **Passed:** {s.passed} | **Failed:** {s.failed} | **Partial:** {s.partial}")
        md.append("")
        
        md.append("## Critical Failures")
        if not report.critical_failures:
            md.append("No critical failures detected. ✅")
        else:
            for failure in report.critical_failures:
                md.append(f"### ❌ {failure.control_id}: {failure.control_name}")
                md.append(f"**Findings:** {failure.findings}")
                md.append(f"**Recommendation:** {failure.recommendations}")
                md.append("")

        md.append("## Remediation Plan")
        for idx, step in enumerate(report.remediation_plan, 1):
            md.append(f"{idx}. {step}")

        return "\n".join(md)

    @staticmethod
    def render_html(report: GapAnalysisReport) -> str:
        """Generates an HTML report for email/web distribution."""
        md_text = ReportRenderer.render_markdown(report)
        # simplistic conversion for illustration
        html = md_text.replace("\n", "<br>").replace("# ", "<h1>").replace("## ", "<h2>").replace("### ", "<h3>")
        return f"<html><body>{html}</body></html>"

    @staticmethod
    def render_json(report: GapAnalysisReport) -> str:
        """Generates a machine-readable JSON report."""
        return report.model_dump_json(indent=2)
