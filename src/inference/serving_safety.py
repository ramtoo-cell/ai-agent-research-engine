import asyncio
import time
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class ServingConfig(BaseModel):
    model_config = ConfigDict(strict=True)
    rate_limit_rpm: int = Field(60, description="Requests per minute limit")
    timeout_ms: int = Field(5000, description="Timeout in milliseconds")
    max_tokens: int = Field(4096, description="Max input+output tokens")

class RequestValidator:
    """Validates incoming requests before processing."""
    def validate(self, prompt: str, max_tokens: int) -> bool:
        if len(prompt) > max_tokens * 4: # rough character estimation
            return False
        return True

class ResponseSanitizer:
    """Cleans outputs before delivery."""
    def sanitize(self, response: str) -> str:
        return response.replace("<|endoftext|>", "").strip()

class LoadShedder:
    """Graceful degradation under load."""
    def __init__(self, max_concurrent: int):
        self.max_concurrent = max_concurrent
        self.current_requests = 0
        
    def should_shed(self) -> bool:
        return self.current_requests >= self.max_concurrent
        
    def enter(self):
        self.current_requests += 1
        
    def exit(self):
        self.current_requests = max(0, self.current_requests - 1)

class ServingCircuitBreaker:
    """Prevents cascading failures."""
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = 0.0
        self.is_open = False
        
    def record_failure(self):
        self.failures += 1
        self.last_failure_time = time.time()
        if self.failures >= self.failure_threshold:
            self.is_open = True
            
    def record_success(self):
        self.failures = 0
        self.is_open = False
        
    def allow_request(self) -> bool:
        if self.is_open:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.is_open = False
                self.failures = 0
                return True
            return False
        return True

class ServingMetrics(BaseModel):
    model_config = ConfigDict(strict=True)
    latency_ms: List[float] = []
    throughput_rps: float = 0.0
    error_rate: float = 0.0
    safety_violations: int = 0

class HealthEndpoint:
    def __init__(self, circuit_breaker: ServingCircuitBreaker, load_shedder: LoadShedder):
        self.cb = circuit_breaker
        self.ls = load_shedder
        
    def get_status(self) -> Dict[str, Any]:
        return {
            "status": "UNHEALTHY" if self.cb.is_open else "HEALTHY",
            "circuit_breaker_open": self.cb.is_open,
            "load_shedding": self.ls.should_shed()
        }
