import uuid
import time
import asyncio
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class TraceContext(BaseModel):
    """Propagation context linking operations across distributed agent boundaries."""
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: Optional[str] = None
    sampled: bool = True
    baggage: Dict[str, str] = Field(default_factory=dict)

class TraceSpan(BaseModel):
    """A single logical unit of work within a distributed trace."""
    trace_id: str
    span_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_span_id: Optional[str] = None
    operation_name: str
    start_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    end_time: Optional[datetime] = None
    duration_ms: Optional[float] = None
    tags: Dict[str, Any] = Field(default_factory=dict)
    error: bool = False
    
    def finish(self, error: bool = False):
        self.end_time = datetime.now(timezone.utc)
        self.duration_ms = (self.end_time - self.start_time).total_seconds() * 1000.0
        self.error = error

class SpanRecorder:
    """Asynchronous buffer for trace spans to minimize latency impact on agents."""
    def __init__(self, batch_size: int = 50, flush_interval_seconds: float = 5.0):
        self.batch_size = batch_size
        self.flush_interval = flush_interval_seconds
        self._buffer: List[TraceSpan] = []
        self._lock = asyncio.Lock()
        self._flush_task = asyncio.create_task(self._periodic_flush())

    async def record(self, span: TraceSpan):
        """Append a span to the buffer."""
        async with self._lock:
            self._buffer.append(span)
            if len(self._buffer) >= self.batch_size:
                await self._flush_unlocked()

    async def _periodic_flush(self):
        """Background task to flush the buffer periodically."""
        while True:
            await asyncio.sleep(self.flush_interval)
            async with self._lock:
                await self._flush_unlocked()

    async def _flush_unlocked(self):
        if not self._buffer:
            return
        spans_to_export = self._buffer[:]
        self._buffer.clear()
        # In a real system, this would send to an exporter (Jaeger, OTLP)
        logger.debug(f"Flushed {len(spans_to_export)} spans.")
        
    async def shutdown(self):
        self._flush_task.cancel()
        async with self._lock:
            await self._flush_unlocked()

class TraceExporter:
    """Exports trace data to observability platforms (e.g., OpenTelemetry format)."""
    
    @staticmethod
    def export_to_jaeger_json(spans: List[TraceSpan]) -> Dict[str, Any]:
        """Mocks an export to Jaeger JSON format."""
        jaeger_spans = []
        for s in spans:
            jaeger_spans.append({
                "traceID": s.trace_id,
                "spanID": s.span_id,
                "operationName": s.operation_name,
                "references": [{"refType": "CHILD_OF", "traceID": s.trace_id, "spanID": s.parent_span_id}] if s.parent_span_id else [],
                "startTime": int(s.start_time.timestamp() * 1000000),
                "duration": int((s.duration_ms or 0) * 1000),
                "tags": [{"key": k, "type": "string", "value": str(v)} for k, v in s.tags.items()]
            })
        return {"data": [{"traceID": spans[0].trace_id if spans else "", "spans": jaeger_spans}]}

class TraceAnalyzer:
    """Analyzes a set of traces to identify latency bottlenecks and errors."""
    
    @staticmethod
    def analyze_bottlenecks(spans: List[TraceSpan], threshold_ms: float = 1000.0) -> List[TraceSpan]:
        """Finds spans that exceeded the acceptable latency threshold."""
        return [s for s in spans if s.duration_ms and s.duration_ms > threshold_ms]

    @staticmethod
    def calculate_error_rate(spans: List[TraceSpan]) -> float:
        """Calculates the percentage of operations that failed."""
        if not spans:
            return 0.0
        errors = sum(1 for s in spans if s.error)
        return (errors / len(spans)) * 100.0

    @staticmethod
    def breakdown_by_operation(spans: List[TraceSpan]) -> Dict[str, float]:
        """Averages latency by operation name."""
        totals = {}
        counts = {}
        for s in spans:
            if s.duration_ms:
                totals[s.operation_name] = totals.get(s.operation_name, 0.0) + s.duration_ms
                counts[s.operation_name] = counts.get(s.operation_name, 0) + 1
                
        return {op: (totals[op] / counts[op]) for op in totals}
