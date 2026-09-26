import asyncio
from typing import List, Dict, Any, Optional, AsyncGenerator
from pydantic import BaseModel, Field, ConfigDict

class SamplingConfig(BaseModel):
    model_config = ConfigDict(strict=True)
    temperature: float = Field(0.7, ge=0.0)
    top_p: float = Field(0.9, ge=0.0, le=1.0)
    top_k: int = Field(50, ge=0)
    repetition_penalty: float = Field(1.1, ge=1.0)

class TokenFilter:
    """Blocks dangerous token sequences."""
    def __init__(self, banned_sequences: List[List[int]]):
        self.banned_sequences = banned_sequences
        
    def is_safe(self, token_buffer: List[int]) -> bool:
        for seq in self.banned_sequences:
            if len(token_buffer) >= len(seq):
                if token_buffer[-len(seq):] == seq:
                    return False
        return True

class StreamingGuardrail:
    """Real-time content checking for streaming outputs."""
    async def check_chunk(self, chunk: str) -> bool:
        # Mock checking
        await asyncio.sleep(0.01)
        return "unsafe_keyword" not in chunk

class SamplingAnomalyDetector:
    """Detects unusual generation patterns (e.g. infinite loops)."""
    def __init__(self, max_repetitions: int = 5):
        self.max_repetitions = max_repetitions
        self.history: List[str] = []
        
    def update_and_check(self, token: str) -> bool:
        self.history.append(token)
        if len(self.history) >= self.max_repetitions:
            recent = self.history[-self.max_repetitions:]
            if len(set(recent)) == 1:
                return True # Anomaly detected
        return False

class SamplingReport(BaseModel):
    model_config = ConfigDict(strict=True)
    total_requests: int = 0
    blocked_requests: int = 0
    anomalies_detected: int = 0

class SafeSampler:
    """Coordinates safe sampling strategies."""
    def __init__(self, config: SamplingConfig):
        self.config = config
        self.token_filter = TokenFilter([[101, 102], [999]])
        self.guardrail = StreamingGuardrail()
        self.anomaly_detector = SamplingAnomalyDetector()
        self.report = SamplingReport()
        
    async def sample_stream(self, prompt: str) -> AsyncGenerator[str, None]:
        self.report.total_requests += 1
        mock_tokens = ["Hello", " world", "!", "unsafe_keyword", " aborting"]
        
        token_ids = []
        for i, token in enumerate(mock_tokens):
            token_ids.append(i)
            
            if not self.token_filter.is_safe(token_ids):
                self.report.blocked_requests += 1
                yield "[BLOCKED BY TOKEN FILTER]"
                break
                
            if self.anomaly_detector.update_and_check(token):
                self.report.anomalies_detected += 1
                yield "[ANOMALY DETECTED]"
                break
                
            is_chunk_safe = await self.guardrail.check_chunk(token)
            if not is_chunk_safe:
                self.report.blocked_requests += 1
                yield "[BLOCKED BY GUARDRAIL]"
                break
                
            yield token
