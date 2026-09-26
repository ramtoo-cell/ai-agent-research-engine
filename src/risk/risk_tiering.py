import asyncio
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class RiskTier(Enum):
    """Classification of overall risk levels for AI models."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    MINIMAL = "MINIMAL"


class AutonomyLevel(Enum):
    """The degree to which the model acts independently."""
    FULL_AUTONOMY = "FULL_AUTONOMY"
    HUMAN_IN_THE_LOOP = "HUMAN_IN_THE_LOOP"
    HUMAN_ON_THE_LOOP = "HUMAN_ON_THE_LOOP"
    DECISION_SUPPORT = "DECISION_SUPPORT"
    INFORMATION_ONLY = "INFORMATION_ONLY"


class DataSensitivity(Enum):
    """The sensitivity classification of the data processed by the model."""
    RESTRICTED = "RESTRICTED"
    CONFIDENTIAL = "CONFIDENTIAL"
    INTERNAL = "INTERNAL"
    PUBLIC = "PUBLIC"


class UseCaseImpact(Enum):
    """Potential impact of the model's use case on individuals or systems."""
    LIFE_OR_DEATH = "LIFE_OR_DEATH"
    FINANCIAL_RUIN = "FINANCIAL_RUIN"
    MODERATE_HARM = "MODERATE_HARM"
    MINOR_INCONVENIENCE = "MINOR_INCONVENIENCE"
    NO_DIRECT_IMPACT = "NO_DIRECT_IMPACT"


class TieringCriteria(BaseModel):
    """Scoring rubric used to determine the risk tier."""
    model_config = ConfigDict(frozen=True)

    use_case_impact: UseCaseImpact
    data_sensitivity: DataSensitivity
    autonomy_level: AutonomyLevel
    regulatory_exposure: bool = Field(default=False, description="Is the model subject to specific regulations?")
    external_facing: bool = Field(default=False, description="Is the model directly accessible by external users?")


class GovernanceRequirement(BaseModel):
    """Defines the governance expectations for a specific risk tier."""
    tier: RiskTier
    approval_level: str = Field(..., description="Role required for approval (e.g., C-Level, Director, Manager)")
    monitoring_frequency_days: int = Field(..., description="How often the model must be reviewed")
    audit_depth: str = Field(..., description="Description of the audit rigorousness")
    requires_external_audit: bool = Field(default=False)
    documentation_requirements: List[str] = Field(default_factory=list)


class TieringDecisionAudit(BaseModel):
    """Audit record for a tiering decision."""
    id: UUID = Field(default_factory=uuid4)
    model_id: str
    previous_tier: Optional[RiskTier]
    assigned_tier: RiskTier
    criteria: TieringCriteria
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    justification: str
    approver: Optional[str] = None


class TierEscalation(BaseModel):
    """Record of a model escalating to a higher risk tier."""
    id: UUID = Field(default_factory=uuid4)
    model_id: str
    from_tier: RiskTier
    to_tier: RiskTier
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: str


class AutomatedTieringEngine:
    """Engine that classifies models into risk tiers based on criteria."""

    def __init__(self) -> None:
        self.governance_map: Dict[RiskTier, GovernanceRequirement] = self._initialize_governance_map()
        self.audit_log: List[TieringDecisionAudit] = []
        self.escalations: List[TierEscalation] = []
        self.current_tiers: Dict[str, RiskTier] = {}

    def _initialize_governance_map(self) -> Dict[RiskTier, GovernanceRequirement]:
        """Sets up default governance requirements per tier."""
        return {
            RiskTier.CRITICAL: GovernanceRequirement(
                tier=RiskTier.CRITICAL,
                approval_level="Board/C-Level",
                monitoring_frequency_days=7,
                audit_depth="Comprehensive algorithmic and security audit",
                requires_external_audit=True,
                documentation_requirements=["Model Architecture", "Data Lineage", "Red Team Report", "Bias Assessment"]
            ),
            RiskTier.HIGH: GovernanceRequirement(
                tier=RiskTier.HIGH,
                approval_level="VP/Director",
                monitoring_frequency_days=30,
                audit_depth="Detailed internal audit",
                requires_external_audit=False,
                documentation_requirements=["Model Architecture", "Data Lineage", "Bias Assessment"]
            ),
            RiskTier.MEDIUM: GovernanceRequirement(
                tier=RiskTier.MEDIUM,
                approval_level="Manager",
                monitoring_frequency_days=90,
                audit_depth="Standard compliance check",
                requires_external_audit=False,
                documentation_requirements=["Model Architecture", "Performance Metrics"]
            ),
            RiskTier.LOW: GovernanceRequirement(
                tier=RiskTier.LOW,
                approval_level="Peer Review",
                monitoring_frequency_days=180,
                audit_depth="Basic validation",
                requires_external_audit=False,
                documentation_requirements=["Performance Metrics"]
            ),
            RiskTier.MINIMAL: GovernanceRequirement(
                tier=RiskTier.MINIMAL,
                approval_level="Self-Approval",
                monitoring_frequency_days=365,
                audit_depth="None",
                requires_external_audit=False,
                documentation_requirements=["Basic Description"]
            )
        }

    def _score_criteria(self, criteria: TieringCriteria) -> int:
        """Calculates a numerical risk score based on the criteria."""
        score = 0
        
        # Impact scoring
        impact_scores = {
            UseCaseImpact.LIFE_OR_DEATH: 100,
            UseCaseImpact.FINANCIAL_RUIN: 80,
            UseCaseImpact.MODERATE_HARM: 40,
            UseCaseImpact.MINOR_INCONVENIENCE: 10,
            UseCaseImpact.NO_DIRECT_IMPACT: 0,
        }
        score += impact_scores.get(criteria.use_case_impact, 0)
        
        # Sensitivity scoring
        sensitivity_scores = {
            DataSensitivity.RESTRICTED: 50,
            DataSensitivity.CONFIDENTIAL: 30,
            DataSensitivity.INTERNAL: 10,
            DataSensitivity.PUBLIC: 0,
        }
        score += sensitivity_scores.get(criteria.data_sensitivity, 0)
        
        # Autonomy scoring
        autonomy_scores = {
            AutonomyLevel.FULL_AUTONOMY: 40,
            AutonomyLevel.HUMAN_ON_THE_LOOP: 20,
            AutonomyLevel.HUMAN_IN_THE_LOOP: 10,
            AutonomyLevel.DECISION_SUPPORT: 5,
            AutonomyLevel.INFORMATION_ONLY: 0,
        }
        score += autonomy_scores.get(criteria.autonomy_level, 0)
        
        if criteria.regulatory_exposure:
            score += 30
        if criteria.external_facing:
            score += 20
            
        return score

    def _determine_tier(self, score: int) -> RiskTier:
        """Maps a numerical score to a RiskTier."""
        if score >= 150:
            return RiskTier.CRITICAL
        elif score >= 100:
            return RiskTier.HIGH
        elif score >= 50:
            return RiskTier.MEDIUM
        elif score >= 20:
            return RiskTier.LOW
        return RiskTier.MINIMAL

    async def classify_model(self, model_id: str, criteria: TieringCriteria, approver: Optional[str] = None) -> RiskTier:
        """
        Classifies a model based on provided criteria and records the decision.
        """
        score = self._score_criteria(criteria)
        assigned_tier = self._determine_tier(score)
        
        previous_tier = self.current_tiers.get(model_id)
        
        audit_record = TieringDecisionAudit(
            model_id=model_id,
            previous_tier=previous_tier,
            assigned_tier=assigned_tier,
            criteria=criteria,
            justification=f"Calculated criteria score: {score}. Assigned tier: {assigned_tier.name}",
            approver=approver
        )
        
        self.audit_log.append(audit_record)
        self.current_tiers[model_id] = assigned_tier
        
        # Check for escalation
        if previous_tier:
            tier_ranks = {
                RiskTier.MINIMAL: 1,
                RiskTier.LOW: 2,
                RiskTier.MEDIUM: 3,
                RiskTier.HIGH: 4,
                RiskTier.CRITICAL: 5
            }
            if tier_ranks[assigned_tier] > tier_ranks[previous_tier]:
                escalation = TierEscalation(
                    model_id=model_id,
                    from_tier=previous_tier,
                    to_tier=assigned_tier,
                    reason=f"Criteria re-evaluation resulted in higher risk score ({score})"
                )
                self.escalations.append(escalation)
                
        return assigned_tier

    def get_governance_requirements(self, tier: RiskTier) -> GovernanceRequirement:
        """Retrieves governance requirements for a given tier."""
        return self.governance_map[tier]

    def get_audit_history(self, model_id: str) -> List[TieringDecisionAudit]:
        """Retrieves the tiering audit history for a model."""
        return [log for log in self.audit_log if log.model_id == model_id]

# EOF
