import asyncio
import time
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

class MessageType(str, Enum):
    INFO = "INFO"
    REQUEST = "REQUEST"
    RESPONSE = "RESPONSE"
    ERROR = "ERROR"
    PROPOSAL = "PROPOSAL"

class AgentMessage(BaseModel):
    """A message sent between agents."""
    message_id: str
    sender: str
    receiver: str
    content: Any
    message_type: MessageType = MessageType.INFO
    priority: int = 1
    timestamp: float = Field(default_factory=time.time)
    topic: Optional[str] = None

class MessageBus:
    """Topic-based publish/subscribe message bus."""
    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[AgentMessage], None]]] = {}
        self.history: List[AgentMessage] = []

    def subscribe(self, topic: str, callback: Callable[[AgentMessage], None]):
        if topic not in self.subscribers:
            self.subscribers[topic] = []
        self.subscribers[topic].append(callback)

    def publish(self, message: AgentMessage):
        self.history.append(message)
        topic = message.topic or "general"
        for callback in self.subscribers.get(topic, []):
            # In a real system, this would queue tasks on an event loop
            callback(message)

class AgentProtocol(BaseModel):
    """Defines rules and contracts for agent communication."""
    protocol_id: str
    allowed_types: List[MessageType]
    timeout_ms: int = 5000
    retry_policy: str = "EXPONENTIAL_BACKOFF"

class NegotiationEngine:
    """Coordinates negotiations between agents."""
    def __init__(self, bus: MessageBus):
        self.bus = bus
        self.active_negotiations: Dict[str, Dict[str, Any]] = {}

    async def propose(self, sender: str, receivers: List[str], proposal: Any) -> bool:
        """Starts a negotiation by proposing an action."""
        msg_id = f"neg_{time.time()}"
        self.active_negotiations[msg_id] = {"proposal": proposal, "responses": {}}
        
        for receiver in receivers:
            msg = AgentMessage(
                message_id=msg_id,
                sender=sender,
                receiver=receiver,
                content=proposal,
                message_type=MessageType.PROPOSAL,
                topic=f"negotiation.{msg_id}"
            )
            self.bus.publish(msg)
            
        # Wait for responses (simulated)
        await asyncio.sleep(0.1)
        return True

class ConsensusProtocol:
    """Mechanisms for reaching agreement among multiple agents."""
    
    @staticmethod
    def majority_vote(votes: Dict[str, bool]) -> bool:
        """Requires > 50% approval."""
        if not votes:
            return False
        approvals = sum(1 for v in votes.values() if v)
        return approvals > len(votes) / 2

    @staticmethod
    def unanimous(votes: Dict[str, bool]) -> bool:
        """Requires 100% approval."""
        if not votes:
            return False
        return all(votes.values())
        
    @staticmethod
    def weighted_vote(votes: Dict[str, bool], weights: Dict[str, float]) -> bool:
        """Requires sum of approved weights to exceed 50% of total weights."""
        total_weight = sum(weights.values())
        approved_weight = sum(weights[agent] for agent, vote in votes.items() if vote)
        return approved_weight > total_weight / 2

class CommunicationAuditLog:
    """Logs all communications for debugging and analysis."""
    def __init__(self):
        self.logs: List[AgentMessage] = []

    def log_message(self, message: AgentMessage):
        self.logs.append(message)

    def search_by_sender(self, sender: str) -> List[AgentMessage]:
        return [msg for msg in self.logs if msg.sender == sender]
        
    def export_logs(self) -> str:
        """Exports logs to a string format (e.g., JSON or text)."""
        return "\n".join(f"[{m.timestamp}] {m.sender}->{m.receiver}: {m.content}" for m in self.logs)
