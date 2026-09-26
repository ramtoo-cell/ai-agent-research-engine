"""
Segregation of Duties (SoD) module for AI Governance & Safety Platform.

This module provides comprehensive mechanisms to enforce maker-checker patterns,
detect conflicts of interest, and manage segregation of duties to prevent fraud
and ensure rigorous oversight of AI system deployments and configuration changes.
By utilizing async operations and Pydantic v2 models, the module scales efficiently
while maintaining strict type enforcement and data validation.
"""

import asyncio
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import List, Dict, Set, Optional, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator, model_validator


# Configure module logger
logger = logging.getLogger(__name__)


class DutyType(str, Enum):
    """
    Enumeration of various duty types within the governance platform.
    These types correspond to distinct roles that are often mutually exclusive.
    """
    DEVELOPMENT = "development"
    TESTING = "testing"
    SECURITY_REVIEW = "security_review"
    DEPLOYMENT_APPROVAL = "deployment_approval"
    AUDIT = "audit"
    POLICY_DEFINITION = "policy_definition"
    DATA_MANAGEMENT = "data_management"
    SYSTEM_ADMINISTRATION = "system_administration"


class WorkflowStatus(str, Enum):
    """Status of a maker-checker workflow."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELED = "canceled"


class DutyDefinition(BaseModel):
    """
    Defines a specific duty or role and the list of duties that are
    computationally and organizationally incompatible with it.
    """
    duty_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the duty definition.")
    name: str = Field(..., description="Human-readable name of the duty.")
    duty_type: DutyType = Field(..., description="Categorization of the duty.")
    incompatible_duties: List[DutyType] = Field(
        default_factory=list,
        description="List of duty types that cannot be performed by the same individual."
    )
    description: str = Field(..., description="Detailed description of what the duty entails.")
    is_active: bool = Field(default=True, description="Whether this duty definition is currently enforced.")

    @field_validator('incompatible_duties')
    @classmethod
    def self_incompatibility_check(cls, v: List[DutyType], info: Any) -> List[DutyType]:
        """Ensures that a duty is not marked as incompatible with itself."""
        if 'duty_type' in info.data and info.data['duty_type'] in v:
            raise ValueError("A duty cannot be incompatible with itself.")
        return v


class SoDViolation(BaseModel):
    """Record of a segregation of duties violation or attempted violation."""
    violation_id: UUID = Field(default_factory=uuid4)
    user_id: str = Field(..., description="The user involved in the violation.")
    attempted_duty: DutyType = Field(..., description="The duty the user attempted to perform.")
    conflicting_duties: List[DutyType] = Field(..., description="The conflicting duties already held by the user.")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    severity: str = Field("HIGH", description="Severity level of the violation (e.g., LOW, MEDIUM, HIGH, CRITICAL).")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional contextual metadata about the violation.")
    resolved: bool = Field(default=False, description="Whether the violation has been reviewed and resolved by an auditor.")
    resolution_notes: Optional[str] = Field(None, description="Notes from the auditor resolving the violation.")


class ConflictOfInterestDetector:
    """
    Service to analyze and detect conflicts of interest based on assigned duties
    and requested operations. Maintains state of user duties and violation logs.
    """
    def __init__(self, duty_definitions: List[DutyDefinition]):
        self.duty_definitions = {d.duty_type: d for d in duty_definitions if d.is_active}
        self.user_duties: Dict[str, Set[DutyType]] = {}
        self.violations_log: List[SoDViolation] = []
        logger.info(f"Initialized ConflictOfInterestDetector with {len(self.duty_definitions)} active duty definitions.")

    async def assign_duty(self, user_id: str, duty: DutyType) -> None:
        """Assigns a duty to a user, strictly checking for any SoD conflicts."""
        logger.debug(f"Attempting to assign duty {duty.value} to user {user_id}.")
        await asyncio.sleep(0.01)  # Simulate async database check
        
        current_duties = self.user_duties.get(user_id, set())
        
        conflicts = await self.check_conflicts(user_id, duty, current_duties)
        if conflicts:
            violation = SoDViolation(
                user_id=user_id,
                attempted_duty=duty,
                conflicting_duties=conflicts,
                context={"action": "assign_duty", "current_duties": [d.value for d in current_duties]}
            )
            self.violations_log.append(violation)
            logger.warning(f"SoD violation detected for user {user_id}. Attempted: {duty.value}, Conflicts: {conflicts}")
            raise ValueError(f"SoD Conflict Detected for user {user_id}. Conflicting duties: {conflicts}")
        
        if user_id not in self.user_duties:
            self.user_duties[user_id] = set()
        self.user_duties[user_id].add(duty)
        logger.info(f"Successfully assigned duty {duty.value} to user {user_id}.")

    async def check_conflicts(self, user_id: str, requested_duty: DutyType, current_duties: Set[DutyType]) -> List[DutyType]:
        """Asynchronously cross-checks a requested duty against an existing set of duties."""
        await asyncio.sleep(0.01) # Simulate network latency
        conflicts = []
        duty_def = self.duty_definitions.get(requested_duty)
        if not duty_def:
            logger.warning(f"Duty definition for {requested_duty.value} not found.")
            return conflicts
        
        for existing_duty in current_duties:
            # Direct check
            if existing_duty in duty_def.incompatible_duties:
                conflicts.append(existing_duty)
                
            # Bidirectional/Reverse check
            existing_def = self.duty_definitions.get(existing_duty)
            if existing_def and requested_duty in existing_def.incompatible_duties:
                if existing_duty not in conflicts:
                    conflicts.append(existing_duty)
                    
        return conflicts

    async def get_violations(self, unresolved_only: bool = False) -> List[SoDViolation]:
        """Returns the list of recorded SoD violations, optionally filtering for unresolved ones."""
        await asyncio.sleep(0.01)
        if unresolved_only:
            return [v for v in self.violations_log if not v.resolved]
        return self.violations_log


class MakerCheckerWorkflow(BaseModel):
    """
    Represents a Maker-Checker workflow ensuring that the person who initiates
    an action (maker) is not the same person who approves it (checker).
    Critical for financial, infrastructural, or security-sensitive AI operations.
    """
    workflow_id: UUID = Field(default_factory=uuid4)
    target_resource_id: str = Field(..., description="ID of the resource being modified, deployed, or altered.")
    maker_id: str = Field(..., description="ID of the user who initiated the workflow (Maker).")
    checker_id: Optional[str] = Field(None, description="ID of the user who approved or rejected the workflow (Checker).")
    status: WorkflowStatus = Field(default=WorkflowStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    resolved_at: Optional[datetime] = None
    operation_details: Dict[str, Any] = Field(..., description="JSON-serializable details of the operation to be performed.")

    async def approve(self, checker_id: str, comments: str = "") -> None:
        """Approves the workflow, ensuring the checker is not the maker."""
        await asyncio.sleep(0.05)
        if checker_id == self.maker_id:
            raise ValueError("Maker and Checker cannot be the same individual.")
        if self.status != WorkflowStatus.PENDING:
            raise ValueError(f"Workflow cannot be approved from status {self.status.value}")
        
        self.checker_id = checker_id
        self.status = WorkflowStatus.APPROVED
        self.resolved_at = datetime.now(timezone.utc)
        self.operation_details["approval_comments"] = comments
        logger.info(f"Workflow {self.workflow_id} approved by Checker {checker_id}.")

    async def reject(self, checker_id: str, reason: str) -> None:
        """Rejects the workflow, storing the reason for rejection."""
        await asyncio.sleep(0.05)
        if checker_id == self.maker_id:
            raise ValueError("Maker and Checker cannot be the same individual.")
        if self.status != WorkflowStatus.PENDING:
            raise ValueError(f"Workflow cannot be rejected from status {self.status.value}")
            
        self.checker_id = checker_id
        self.status = WorkflowStatus.REJECTED
        self.resolved_at = datetime.now(timezone.utc)
        self.operation_details["rejection_reason"] = reason
        logger.info(f"Workflow {self.workflow_id} rejected by Checker {checker_id}.")


class DualControlEnforcer:
    """
    Enforces dual control for high-risk operations, requiring multiple distinct
    approvals before an action is executed. Integrates tightly with ConflictOfInterestDetector.
    """
    def __init__(self, detector: ConflictOfInterestDetector):
        self.detector = detector
        self.active_workflows: Dict[UUID, MakerCheckerWorkflow] = {}
        logger.info("Initialized DualControlEnforcer.")

    async def initiate_operation(self, maker_id: str, resource_id: str, details: Dict[str, Any]) -> MakerCheckerWorkflow:
        """Initiates a high-risk operation requiring dual control."""
        await asyncio.sleep(0.02)
        
        # Verify maker has the right duty to initiate
        maker_duties = self.detector.user_duties.get(maker_id, set())
        if DutyType.DEVELOPMENT not in maker_duties and DutyType.POLICY_DEFINITION not in maker_duties:
            logger.error(f"User {maker_id} attempted to initiate an operation without appropriate duties.")
            raise PermissionError(f"User {maker_id} does not have permission to initiate operations.")
            
        workflow = MakerCheckerWorkflow(
            target_resource_id=resource_id,
            maker_id=maker_id,
            operation_details=details
        )
        self.active_workflows[workflow.workflow_id] = workflow
        logger.info(f"Workflow {workflow.workflow_id} initiated by Maker {maker_id} for resource {resource_id}.")
        return workflow

    async def approve_operation(self, workflow_id: UUID, checker_id: str, comments: str = "") -> None:
        """Approves a high-risk operation after ensuring appropriate SoD constraints."""
        await asyncio.sleep(0.02)
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            raise KeyError(f"Workflow {workflow_id} not found.")
            
        # Verify checker has the right duty to approve
        checker_duties = self.detector.user_duties.get(checker_id, set())
        if DutyType.SECURITY_REVIEW not in checker_duties and DutyType.DEPLOYMENT_APPROVAL not in checker_duties:
            logger.error(f"User {checker_id} attempted to approve workflow {workflow_id} without appropriate duties.")
            raise PermissionError(f"User {checker_id} does not have permission to approve operations.")
            
        # Check SoD dynamically to prevent self-approval even if roles changed mid-flight
        if checker_id == workflow.maker_id:
            violation = SoDViolation(
                user_id=checker_id,
                attempted_duty=DutyType.SECURITY_REVIEW,
                conflicting_duties=[DutyType.DEVELOPMENT],
                context={"workflow_id": str(workflow_id), "reason": "Maker attempted self-approval"}
            )
            self.detector.violations_log.append(violation)
            logger.critical(f"Critical SoD violation: Maker {checker_id} attempted to self-approve workflow {workflow_id}.")
            raise ValueError("Maker cannot be Checker.")
            
        await workflow.approve(checker_id, comments)

    async def execute_operation(self, workflow_id: UUID) -> Any:
        """Executes the operation if it has been fully approved."""
        await asyncio.sleep(0.1)
        workflow = self.active_workflows.get(workflow_id)
        if not workflow:
            raise KeyError(f"Workflow {workflow_id} not found.")
            
        if workflow.status != WorkflowStatus.APPROVED:
            raise ValueError(f"Cannot execute workflow in status {workflow.status.value}")
            
        logger.info(f"Executing workflow {workflow_id} for resource {workflow.target_resource_id}.")
        # Simulated execution logic wrapping external integrations
        result = {
            "status": "executed",
            "resource_id": workflow.target_resource_id,
            "execution_timestamp": datetime.now(timezone.utc).isoformat(),
            "maker_id": workflow.maker_id,
            "checker_id": workflow.checker_id
        }
        return result
