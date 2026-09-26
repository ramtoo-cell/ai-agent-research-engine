import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolAbusePattern(BaseModel):
    """Defines a signature or pattern of tool misuse."""
    pattern_id: str
    name: str
    description: str
    detection_logic: str = Field(..., description="Abstract representation of the detection rule")
    risk_level: str = Field(default="high", description="Risk level (low, medium, high, critical)")


class ToolInvocation(BaseModel):
    """Represents a single invocation of a tool by the AI system."""
    invocation_id: str
    tool_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    arguments: Dict[str, Any]
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    result_status: str = Field(default="pending", description="pending, success, error")


class AnomalyEvent(BaseModel):
    """An event triggered when tool usage deviates from normal patterns."""
    event_id: str = Field(..., description="Unique anomaly identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    session_id: Optional[str]
    tool_name: Optional[str]
    description: str = Field(..., description="Human readable reason for the anomaly")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence in the anomaly detection")


class AbusePreventionReport(BaseModel):
    """Aggregate report of tool abuse detections over a period."""
    report_id: str
    start_time: datetime
    end_time: datetime
    total_invocations_analyzed: int
    anomalies_detected: int
    pattern_matches: int
    events: List[AnomalyEvent] = Field(default_factory=list)
    action_taken: str = Field(default="logged", description="What systemic action was taken (e.g., rate_limited)")


class UsageAnomalyDetector:
    """
    Detects statistical outliers in tool usage, such as:
    - Excessive call frequency (rate limiting)
    - Unusually large payload sizes
    - Chained tool exploits (calling Tool A then Tool B in rapid, unexpected succession)
    """
    
    def __init__(self, rate_limit_per_minute: int = 60):
        self.rate_limit = rate_limit_per_minute
        self.invocation_history: Dict[str, deque] = {}  # session_id -> deque of timestamps
        self.logger = logging.getLogger("UsageAnomalyDetector")

    def _clean_history(self, session_id: str, current_time: datetime):
        """Removes invocations older than 1 minute for the rate limit check."""
        if session_id not in self.invocation_history:
            return
            
        history = self.invocation_history[session_id]
        cutoff = current_time - timedelta(minutes=1)
        
        while history and history[0] < cutoff:
            history.popleft()

    async def analyze_invocation(self, invocation: ToolInvocation) -> Optional[AnomalyEvent]:
        """
        Analyzes a single invocation in real-time to detect statistical anomalies (e.g., velocity).
        """
        session = invocation.session_id or "global"
        current_time = invocation.timestamp
        
        if session not in self.invocation_history:
            self.invocation_history[session] = deque()
            
        self.invocation_history[session].append(current_time)
        self._clean_history(session, current_time)
        
        # Velocity Anomaly (Rate Limiting)
        current_rate = len(self.invocation_history[session])
        if current_rate > self.rate_limit:
            self.logger.warning(f"Velocity anomaly detected for session {session}. Rate: {current_rate}/min")
            return AnomalyEvent(
                event_id=f"vel_{current_time.timestamp()}_{session}",
                session_id=session,
                tool_name=invocation.tool_name,
                description=f"Tool invocation rate ({current_rate}/min) exceeded limit ({self.rate_limit}/min)",
                confidence=1.0
            )
            
        # Payload Size Anomaly (Heuristic)
        payload_size = len(str(invocation.arguments))
        if payload_size > 50000: # 50KB arbitrary heuristic limit
            return AnomalyEvent(
                event_id=f"size_{current_time.timestamp()}_{session}",
                session_id=session,
                tool_name=invocation.tool_name,
                description=f"Unusually large payload size detected: {payload_size} bytes",
                confidence=0.85
            )
            
        return None


class AbuseDetector:
    """
    Monitors tool usage against known abuse patterns (e.g., privilege escalation attempts).
    """
    def __init__(self, patterns: List[ToolAbusePattern], anomaly_detector: UsageAnomalyDetector):
        self.patterns = patterns
        self.anomaly_detector = anomaly_detector
        self.logger = logging.getLogger("AbuseDetector")
        
    async def evaluate_invocation(self, invocation: ToolInvocation) -> List[AnomalyEvent]:
        """
        Evaluates an invocation against known patterns AND statistical anomalies.
        """
        events = []
        
        # 1. Statistical Anomaly Check
        anomaly = await self.anomaly_detector.analyze_invocation(invocation)
        if anomaly:
            events.append(anomaly)
            
        # 2. Pattern Matching Check (Structural)
        for pattern in self.patterns:
            # Example heuristic: checking if arguments contain dangerous shell metacharacters
            # when the pattern logic specifies "SHELL_INJECTION_HEURISTIC"
            if pattern.detection_logic == "SHELL_INJECTION_HEURISTIC" and invocation.tool_name in ["run_command", "execute_script"]:
                args_str = str(invocation.arguments)
                if any(char in args_str for char in [";", "|", "&", "$(", "`"]):
                    events.append(AnomalyEvent(
                        event_id=f"pat_{datetime.utcnow().timestamp()}_{pattern.pattern_id}",
                        session_id=invocation.session_id,
                        tool_name=invocation.tool_name,
                        description=f"Matched abuse pattern: {pattern.name}",
                        confidence=0.95
                    ))
                    
            elif pattern.detection_logic == "PRIVILEGE_ESCALATION_HEURISTIC":
                if "sudo" in str(invocation.arguments) or "root" in str(invocation.arguments):
                    events.append(AnomalyEvent(
                        event_id=f"pat_{datetime.utcnow().timestamp()}_{pattern.pattern_id}",
                        session_id=invocation.session_id,
                        tool_name=invocation.tool_name,
                        description=f"Matched privilege escalation heuristic: {pattern.name}",
                        confidence=0.90
                    ))
                    
        return events

    async def generate_report(self, invocations: List[ToolInvocation], start_time: datetime, end_time: datetime) -> AbusePreventionReport:
        """
        Processes a batch of historical invocations and generates a comprehensive report.
        """
        all_events = []
        pattern_matches = 0
        anomalies = 0
        
        for inv in invocations:
            events = await self.evaluate_invocation(inv)
            for e in events:
                if e.event_id.startswith("pat_"):
                    pattern_matches += 1
                else:
                    anomalies += 1
                all_events.append(e)
                
        action = "logged"
        if len(all_events) > (len(invocations) * 0.1):  # If more than 10% of invocations are abusive
            action = "rate_limited_global"
            
        return AbusePreventionReport(
            report_id=f"abuse_rep_{datetime.utcnow().timestamp()}",
            start_time=start_time,
            end_time=end_time,
            total_invocations_analyzed=len(invocations),
            anomalies_detected=anomalies,
            pattern_matches=pattern_matches,
            events=all_events,
            action_taken=action
        )
