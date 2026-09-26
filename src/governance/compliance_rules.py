"""
Compliance Rules Module for AI Governance & Safety Platform.

Defines the core data models and assessment logic for regulatory and industry 
compliance frameworks (e.g., NIST AI RMF, ISO 42001, GDPR, SOX). Provides
automated gap analysis and control mapping for AI systems.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class FrameworkType(str, Enum):
    """Supported regulatory and compliance frameworks."""
    NIST_AI_RMF = "NIST_AI_RMF"
    ISO_42001 = "ISO_42001"
    EU_AI_ACT = "EU_AI_ACT"
    GDPR = "GDPR"
    SOX = "SOX"
    CUSTOM = "CUSTOM"

class ControlStatus(str, Enum):
    """The operational status of a specific control."""
    IMPLEMENTED = "IMPLEMENTED"
    PARTIALLY_IMPLEMENTED = "PARTIALLY_IMPLEMENTED"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class AssessmentStatus(str, Enum):
    """Status of an overarching assessment."""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class CriticalityLevel(str, Enum):
    """Criticality of a control or gap."""
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class EvidenceRequirement(BaseModel):
    """Defines what evidence must be supplied to prove a control is met."""
    requirement_id: str = Field(..., description="Unique identifier for the requirement.")
    description: str = Field(..., description="Description of the evidence needed.")
    data_type: str = Field(..., description="Expected data type (e.g., 'LOGS', 'DOCUMENT', 'METRIC').")
    is_mandatory: bool = Field(default=True)

class ControlObjective(BaseModel):
    """A specific objective that must be met to satisfy a framework requirement."""
    control_id: str = Field(..., description="Standardized control ID (e.g., 'MAP-1.1').")
    title: str = Field(..., description="Short title of the control.")
    description: str = Field(..., description="Detailed description of what must be achieved.")
    criticality: CriticalityLevel = Field(default=CriticalityLevel.MODERATE)
    test_procedures: List[str] = Field(default_factory=list, description="Steps to verify compliance.")
    evidence_requirements: List[EvidenceRequirement] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class ComplianceFramework(BaseModel):
    """A full compliance framework comprising many control objectives."""
    framework_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Human-readable name of the framework.")
    type: FrameworkType = Field(...)
    version: str = Field(..., description="Version of the framework standard.")
    controls: List[ControlObjective] = Field(default_factory=list)

class RemediationRecommendation(BaseModel):
    """Actionable steps to remediate a identified compliance gap."""
    action_items: List[str] = Field(..., description="Specific steps to take.")
    estimated_effort_hours: Optional[float] = None
    target_completion_date: Optional[datetime] = None
    assigned_role: Optional[str] = None

class ComplianceGap(BaseModel):
    """Identified deficiency where a system does not meet a control objective."""
    gap_id: UUID = Field(default_factory=uuid4)
    control_id: str = Field(...)
    description: str = Field(..., description="Detailed explanation of the gap.")
    criticality: CriticalityLevel = Field(...)
    remediation: RemediationRecommendation = Field(...)
    discovered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ComplianceAssessment(BaseModel):
    """The result of evaluating a system against a compliance framework."""
    assessment_id: UUID = Field(default_factory=uuid4)
    framework_id: UUID = Field(...)
    target_system: str = Field(..., description="The system or component assessed.")
    status: AssessmentStatus = Field(default=AssessmentStatus.PENDING)
    assessor_id: str = Field(...)
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    control_results: Dict[str, ControlStatus] = Field(default_factory=dict)
    gaps: List[ComplianceGap] = Field(default_factory=list)
    overall_score: Optional[float] = Field(None, description="0.0 to 1.0 compliance score.")

    model_config = ConfigDict(frozen=False)


# ---------------------------------------------------------------------------
# Engine Implementation
# ---------------------------------------------------------------------------
class ComplianceEngine:
    """
    Manages compliance frameworks and automated assessments.
    Performs gap analysis by comparing provided evidence against requirements.
    """
    
    def __init__(self) -> None:
        self.frameworks: Dict[UUID, ComplianceFramework] = {}
        self.assessments: Dict[UUID, ComplianceAssessment] = {}

    def register_framework(self, framework: ComplianceFramework) -> None:
        """Register a new compliance framework into the engine."""
        self.frameworks[framework.framework_id] = framework
        logger.info(f"Registered framework: {framework.name} ({framework.type})")

    async def assess_control(
        self, 
        control: ControlObjective, 
        provided_evidence: Dict[str, Any]
    ) -> tuple[ControlStatus, Optional[ComplianceGap]]:
        """
        Evaluates a single control objective against provided evidence.
        Returns the status and a gap if one is identified.
        """
        missing_mandatory = []
        for req in control.evidence_requirements:
            if req.is_mandatory and req.requirement_id not in provided_evidence:
                missing_mandatory.append(req.requirement_id)
        
        if not missing_mandatory:
            return ControlStatus.IMPLEMENTED, None

        if len(missing_mandatory) < len([r for r in control.evidence_requirements if r.is_mandatory]):
            status = ControlStatus.PARTIALLY_IMPLEMENTED
        else:
            status = ControlStatus.NOT_IMPLEMENTED

        gap = ComplianceGap(
            control_id=control.control_id,
            description=f"Missing mandatory evidence: {', '.join(missing_mandatory)}",
            criticality=control.criticality,
            remediation=RemediationRecommendation(
                action_items=[f"Provide evidence for {req_id}" for req_id in missing_mandatory],
                estimated_effort_hours=2.0
            )
        )
        return status, gap

    async def run_comprehensive_assessment(
        self,
        framework_id: UUID,
        target_system: str,
        assessor_id: str,
        evidence_bundle: Dict[str, Dict[str, Any]]
    ) -> ComplianceAssessment:
        """
        Runs a full assessment of a target system against a framework.
        Evidence bundle is a mapping of control_id -> {requirement_id: evidence_data}.
        """
        if framework_id not in self.frameworks:
            raise ValueError(f"Framework {framework_id} not found.")
            
        framework = self.frameworks[framework_id]
        
        assessment = ComplianceAssessment(
            framework_id=framework_id,
            target_system=target_system,
            assessor_id=assessor_id,
            status=AssessmentStatus.IN_PROGRESS
        )
        self.assessments[assessment.assessment_id] = assessment
        
        tasks = []
        for control in framework.controls:
            evidence = evidence_bundle.get(control.control_id, {})
            tasks.append(self.assess_control(control, evidence))
            
        results = await asyncio.gather(*tasks)
        
        implemented_count = 0
        for control, (status, gap) in zip(framework.controls, results):
            assessment.control_results[control.control_id] = status
            if gap:
                assessment.gaps.append(gap)
            if status == ControlStatus.IMPLEMENTED:
                implemented_count += 1
                
        # Calculate overall score
        total_controls = len(framework.controls)
        assessment.overall_score = implemented_count / total_controls if total_controls > 0 else 1.0
        
        assessment.status = AssessmentStatus.COMPLETED
        assessment.end_time = datetime.now(timezone.utc)
        
        logger.info(f"Assessment {assessment.assessment_id} completed. Score: {assessment.overall_score:.2f}")
        return assessment

    def export_report(self, assessment_id: UUID) -> Dict[str, Any]:
        """Exports the assessment to a standard JSON report format."""
        if assessment_id not in self.assessments:
            raise ValueError(f"Assessment {assessment_id} not found.")
            
        assessment = self.assessments[assessment_id]
        framework = self.frameworks[assessment.framework_id]
        
        return {
            "report_generated_at": datetime.now(timezone.utc).isoformat(),
            "target_system": assessment.target_system,
            "framework": framework.name,
            "version": framework.version,
            "overall_score": assessment.overall_score,
            "status": assessment.status,
            "total_controls_assessed": len(assessment.control_results),
            "gaps_identified": len(assessment.gaps),
            "critical_gaps": len([g for g in assessment.gaps if g.criticality == CriticalityLevel.CRITICAL]),
            "details": assessment.model_dump(mode="json")
        }
