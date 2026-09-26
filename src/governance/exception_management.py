"""
Exception Management module for AI Governance & Safety Platform.

This module provides a structured workflow for handling policy exceptions,
including requesting, assessing, approving, and renewing exceptions. It
ensures that compensating controls are strictly applied when standard 
policies cannot be met, maintaining a secure, compliant, and auditable 
environment for AI operations.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import List, Dict, Optional, Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, field_validator


# Configure module logger
logger = logging.getLogger(__name__)


class ExceptionStatus(str, Enum):
    """Enumeration of possible statuses for an exception request."""
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVOKED = "revoked"
    EXPIRED = "expired"


class RiskLevel(str, Enum):
    """Enumeration of risk levels associated with an exception."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class CompensatingControl(BaseModel):
    """
    Defines a compensating control to mitigate the risk introduced by
    granting an exception to a standard AI safety or governance policy.
    """
    control_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the control.")
    name: str = Field(..., description="Name of the compensating control.")
    description: str = Field(..., description="Detailed description of how the control mitigates risk.")
    implemented_by: str = Field(..., description="ID of the user or system responsible for implementation.")
    verification_method: str = Field(..., description="How the control's effectiveness will be verified and audited.")
    is_active: bool = Field(default=False, description="Whether the control is currently active.")
    last_verified_at: Optional[datetime] = Field(None, description="Timestamp of the last successful verification.")
    
    async def activate(self) -> None:
        """Asynchronously activates the compensating control in external systems if necessary."""
        await asyncio.sleep(0.01)
        self.is_active = True
        logger.info(f"Compensating control {self.control_id} ({self.name}) activated.")
        
    async def deactivate(self) -> None:
        """Asynchronously deactivates the compensating control."""
        await asyncio.sleep(0.01)
        self.is_active = False
        logger.info(f"Compensating control {self.control_id} ({self.name}) deactivated.")
        
    async def verify(self, verifier_id: str) -> bool:
        """Simulates verification of the control's effectiveness."""
        await asyncio.sleep(0.05)
        self.last_verified_at = datetime.now(timezone.utc)
        logger.info(f"Control {self.control_id} verified by {verifier_id} at {self.last_verified_at}.")
        return True


class RiskAssessment(BaseModel):
    """
    Assessment of the risk associated with an exception request. 
    Usually performed by a dedicated security or risk officer.
    """
    assessment_id: UUID = Field(default_factory=uuid4)
    assessor_id: str = Field(..., description="ID of the user who performed the assessment.")
    assessed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    residual_risk_level: RiskLevel = Field(..., description="The remaining risk after compensating controls are applied.")
    findings: str = Field(..., description="Detailed findings of the risk assessment.")
    approved_duration_days: int = Field(default=30, description="Recommended duration for the exception before review.")


class ExceptionRequest(BaseModel):
    """
    Represents a formal request for an exception to an established governance policy.
    """
    request_id: UUID = Field(default_factory=uuid4, description="Unique identifier for the exception request.")
    policy_id: str = Field(..., description="ID of the policy for which an exception is requested.")
    requester_id: str = Field(..., description="ID of the user requesting the exception.")
    justification: str = Field(..., description="Detailed technical or business justification for why the exception is needed.")
    business_impact: str = Field(..., description="Impact on the business if the exception is not granted.")
    status: ExceptionStatus = Field(default=ExceptionStatus.DRAFT, description="Current lifecycle status of the request.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = Field(None, description="When the approved exception is scheduled to expire.")
    compensating_controls: List[CompensatingControl] = Field(default_factory=list, description="Controls applied to offset risk.")
    risk_assessment: Optional[RiskAssessment] = Field(None, description="Risk assessment generated for the exception.")
    
    @field_validator('justification')
    @classmethod
    def validate_justification_length(cls, v: str) -> str:
        """Ensures that justifications are detailed enough to warrant an exception."""
        if len(v.strip()) < 50:
            raise ValueError("Justification must be at least 50 characters long to provide sufficient context.")
        return v


class ApprovalStep(BaseModel):
    """
    Represents a single step in a multi-level approval chain.
    """
    step_order: int = Field(..., description="The sequence number of this approval step (1-indexed typically).")
    required_role: str = Field(..., description="The RBAC role required to approve this step (e.g., 'CISO', 'Data_Officer').")
    approver_id: Optional[str] = Field(None, description="ID of the user who approved this step.")
    approved_at: Optional[datetime] = Field(None, description="When the step was approved.")
    comments: Optional[str] = Field(None, description="Comments provided by the approver for auditing.")


class ApprovalChain(BaseModel):
    """
    Defines a multi-level approval chain required to authorize an exception request.
    """
    chain_id: UUID = Field(default_factory=uuid4)
    request_id: UUID = Field(..., description="The exception request this chain applies to.")
    steps: List[ApprovalStep] = Field(..., description="The ordered sequence of required approval steps.")
    current_step_index: int = Field(default=0, description="The index of the currently pending step.")
    is_complete: bool = Field(default=False, description="Whether the entire chain has been fully approved.")
    
    async def process_approval(self, user_id: str, role: str, comments: str = "") -> bool:
        """
        Processes an approval for the current step in the chain.
        Returns True if the entire chain is now complete and fully authorized.
        """
        await asyncio.sleep(0.05)
        if self.is_complete:
            logger.warning(f"Attempted to approve already complete chain {self.chain_id}.")
            raise ValueError("Approval chain is already complete.")
            
        current_step = self.steps[self.current_step_index]
        if current_step.required_role != role:
            logger.error(f"User {user_id} with role {role} attempted to approve step requiring {current_step.required_role}.")
            raise PermissionError(f"User role '{role}' does not match required role '{current_step.required_role}'.")
            
        current_step.approver_id = user_id
        current_step.approved_at = datetime.now(timezone.utc)
        current_step.comments = comments
        logger.info(f"Step {current_step.step_order} approved by {user_id} in chain {self.chain_id}.")
        
        self.current_step_index += 1
        if self.current_step_index >= len(self.steps):
            self.is_complete = True
            logger.info(f"Approval chain {self.chain_id} is now fully complete.")
            
        return self.is_complete


class ExceptionRegistry:
    """
    Central repository and orchestration engine for managing the entire 
    lifecycle of all policy exception requests.
    """
    def __init__(self):
        self.requests: Dict[UUID, ExceptionRequest] = {}
        self.approval_chains: Dict[UUID, ApprovalChain] = {}
        logger.info("Initialized ExceptionRegistry.")
        
    async def submit_request(self, request: ExceptionRequest, required_steps: List[ApprovalStep]) -> ApprovalChain:
        """Submits a draft exception request into the review pipeline."""
        await asyncio.sleep(0.1)
        if request.status != ExceptionStatus.DRAFT:
            raise ValueError("Only requests in DRAFT status can be submitted for review.")
            
        request.status = ExceptionStatus.PENDING_REVIEW
        self.requests[request.request_id] = request
        
        # Sort steps by step_order just to be safe
        required_steps.sort(key=lambda s: s.step_order)
        chain = ApprovalChain(request_id=request.request_id, steps=required_steps)
        self.approval_chains[request.request_id] = chain
        logger.info(f"Submitted exception request {request.request_id} for policy {request.policy_id}.")
        return chain
        
    async def add_risk_assessment(self, request_id: UUID, assessment: RiskAssessment) -> None:
        """Attaches a formalized risk assessment to a pending exception request."""
        await asyncio.sleep(0.05)
        request = self.requests.get(request_id)
        if not request:
            raise KeyError(f"Exception request {request_id} not found.")
            
        request.risk_assessment = assessment
        logger.info(f"Risk assessment {assessment.assessment_id} added to request {request_id}.")
        
    async def approve_request_step(self, request_id: UUID, user_id: str, role: str, comments: str = "") -> None:
        """Processes an approval for the current active step in the request's chain."""
        await asyncio.sleep(0.05)
        request = self.requests.get(request_id)
        chain = self.approval_chains.get(request_id)
        
        if not request or not chain:
            raise KeyError("Request or associated Approval Chain not found in registry.")
            
        if request.status != ExceptionStatus.PENDING_REVIEW:
            raise ValueError(f"Cannot approve step for request in status {request.status.value}.")
            
        chain_completed = await chain.process_approval(user_id, role, comments)
        
        if chain_completed:
            if not request.risk_assessment:
                logger.error(f"Cannot fully approve request {request_id} without a risk assessment.")
                raise ValueError("Cannot fully approve an exception request without an attached risk assessment.")
                
            request.status = ExceptionStatus.APPROVED
            duration = request.risk_assessment.approved_duration_days
            request.expires_at = datetime.now(timezone.utc) + timedelta(days=duration)
            logger.info(f"Request {request_id} fully approved. Expires at {request.expires_at}.")
            
            # Activate all compensating controls across integrated systems
            for control in request.compensating_controls:
                await control.activate()
                
    async def renew_exception(self, request_id: UUID, user_id: str, new_justification: str) -> ExceptionRequest:
        """Clones an existing exception to create a renewal request."""
        await asyncio.sleep(0.1)
        original = self.requests.get(request_id)
        if not original:
            raise KeyError(f"Original request {request_id} not found.")
            
        if original.status not in [ExceptionStatus.APPROVED, ExceptionStatus.EXPIRED]:
            raise ValueError(f"Cannot renew exception in status {original.status.value}.")
            
        renewal = ExceptionRequest(
            policy_id=original.policy_id,
            requester_id=user_id,
            justification=new_justification,
            business_impact=original.business_impact,
            compensating_controls=[c.copy(update={"is_active": False, "last_verified_at": None}) for c in original.compensating_controls]
        )
        self.requests[renewal.request_id] = renewal
        logger.info(f"Created renewal request {renewal.request_id} from original {request_id}.")
        return renewal
        
    async def evaluate_expirations(self) -> List[UUID]:
        """Background task method: Scans the registry to expire lapsed exceptions."""
        await asyncio.sleep(0.2)
        expired_ids = []
        now = datetime.now(timezone.utc)
        
        for req_id, request in self.requests.items():
            if request.status == ExceptionStatus.APPROVED and request.expires_at and request.expires_at < now:
                request.status = ExceptionStatus.EXPIRED
                expired_ids.append(req_id)
                logger.warning(f"Exception request {req_id} has expired.")
                
                # Deactivate compensating controls to trigger compliance alerts
                for control in request.compensating_controls:
                    await control.deactivate()
                    
        return expired_ids
