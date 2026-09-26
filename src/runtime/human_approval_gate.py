import asyncio
import logging
import uuid
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from enum import Enum

from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

class ApprovalDecision(str, Enum):
    """Possible outcomes of a human approval review."""
    APPROVED = "APPROVED"
    DENIED = "DENIED"
    ESCALATED = "ESCALATED"
    AUTO_DENIED = "AUTO_DENIED"

class RiskLevel(str, Enum):
    """Standardized risk categorization."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"

class ApprovalRequest(BaseModel):
    """Data object encapsulating a request that requires human review."""
    request_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = Field(..., description="Ties the request to an AgentExecutionContext.")
    action_description: str = Field(..., description="Human-readable description of what the agent intends to do.")
    risk_level: RiskLevel
    context: Dict[str, Any] = Field(default_factory=dict, description="Arbitrary JSON metadata for the reviewer.")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: datetime = Field(..., description="Timestamp after which the request auto-resolves.")
    requester_service: str = Field(default="AgentRuntime")

class ApprovalResponse(BaseModel):
    """The outcome of a human review."""
    request_id: str
    decision: ApprovalDecision
    reviewer_id: Optional[str] = Field(None, description="ID of the human who reviewed this. None if auto-resolved.")
    justification: Optional[str] = Field(None, description="Explanation for the decision, mandatory for DENIED.")
    reviewed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ApprovalPolicy(BaseModel):
    """Rules defining when an action requires human review."""
    model_config = ConfigDict(frozen=True)
    
    always_require_for_risk: List[RiskLevel] = Field(default_factory=lambda: [RiskLevel.HIGH, RiskLevel.CRITICAL])
    auto_deny_timeout_seconds: int = Field(default=3600, description="How long to wait before auto-denying.")
    require_justification_for_denial: bool = True

class EscalationChain(BaseModel):
    """Defines how a request escalates if not answered."""
    tiers: List[str] = Field(default_factory=list, description="Ordered list of reviewer groups/roles.")
    escalation_timeout_seconds: int = Field(default=900, description="Time per tier before escalating.")

class ApprovalAuditTrail:
    """Records the history of approval requests for compliance."""
    
    def __init__(self):
        self._history: List[ApprovalResponse] = []
        self._lock = asyncio.Lock()

    async def record_response(self, response: ApprovalResponse):
        async with self._lock:
            self._history.append(response)
            logger.info(f"AuditTrail recorded decision: {response.decision} for req {response.request_id}")

    async def get_history(self) -> List[ApprovalResponse]:
        async with self._lock:
            return list(self._history)

class ApprovalQueue:
    """Manages pending approval requests in memory, ordered by priority."""
    
    def __init__(self):
        self._pending: Dict[str, ApprovalRequest] = {}
        self._events: Dict[str, asyncio.Event] = {}
        self._responses: Dict[str, ApprovalResponse] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, request: ApprovalRequest) -> asyncio.Event:
        async with self._lock:
            self._pending[request.request_id] = request
            event = asyncio.Event()
            self._events[request.request_id] = event
            return event

    async def resolve(self, response: ApprovalResponse):
        async with self._lock:
            if response.request_id in self._pending:
                self._responses[response.request_id] = response
                del self._pending[response.request_id]
                event = self._events.get(response.request_id)
                if event:
                    event.set()

    async def get_response(self, request_id: str) -> Optional[ApprovalResponse]:
        async with self._lock:
            return self._responses.get(request_id)

    async def list_pending(self) -> List[ApprovalRequest]:
        async with self._lock:
            # In a real system, this might be sorted by risk_level or expiry
            return list(self._pending.values())

class AsyncApprovalGate:
    """
    A gateway that blocks agent execution execution until human approval is granted.
    Handles timeouts, auto-escalation, and integration with the ApprovalQueue.
    """
    
    def __init__(self, policy: ApprovalPolicy, queue: ApprovalQueue, audit_trail: ApprovalAuditTrail):
        self.policy = policy
        self.queue = queue
        self.audit_trail = audit_trail

    async def requires_approval(self, risk_level: RiskLevel) -> bool:
        """Determines if the given risk level mandates approval under current policy."""
        return risk_level in self.policy.always_require_for_risk

    async def request_approval(self, correlation_id: str, action_desc: str, risk: RiskLevel, context: Dict[str, Any]) -> ApprovalResponse:
        """
        Submits an approval request and asynchronously waits for the decision.
        """
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.policy.auto_deny_timeout_seconds)
        request = ApprovalRequest(
            correlation_id=correlation_id,
            action_description=action_desc,
            risk_level=risk,
            context=context,
            expires_at=expires_at
        )

        logger.info(f"[{correlation_id}] Human approval requested for action: {action_desc} (ReqID: {request.request_id})")
        
        # Enqueue and get event
        event = await self.queue.enqueue(request)
        
        # Wait for the event, bounded by the auto-deny timeout
        time_to_wait = (expires_at - datetime.now(timezone.utc)).total_seconds()
        
        if time_to_wait > 0:
            try:
                await asyncio.wait_for(event.wait(), timeout=time_to_wait)
                response = await self.queue.get_response(request.request_id)
                if response:
                    await self.audit_trail.record_response(response)
                    return response
            except asyncio.TimeoutError:
                logger.warning(f"[{correlation_id}] Approval request {request.request_id} timed out. Auto-denying.")
        
        # Auto-deny fallback
        auto_response = ApprovalResponse(
            request_id=request.request_id,
            decision=ApprovalDecision.AUTO_DENIED,
            justification="Request exceeded policy timeout without reviewer action."
        )
        
        # Cleanup queue and log
        await self.queue.resolve(auto_response)
        await self.audit_trail.record_response(auto_response)
        return auto_response
