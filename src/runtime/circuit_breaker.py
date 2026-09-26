import time
import asyncio
import logging
from typing import Dict, Any, Callable, Awaitable, Optional
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class CircuitState(str, Enum):
    """Represents the finite state machine of the circuit breaker."""
    CLOSED = "CLOSED"      # Normal operation. Requests flow freely.
    OPEN = "OPEN"          # Failure threshold breached. Requests fail fast.
    HALF_OPEN = "HALF_OPEN"# Trial phase. Allowing limited requests to probe recovery.

class CircuitBreakerMetrics(BaseModel):
    """Counters and timers for observability."""
    service_name: str
    successful_requests: int = 0
    failed_requests: int = 0
    fallback_invocations: int = 0
    short_circuited_requests: int = 0
    last_state_change: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class CircuitBreakerConfig(BaseModel):
    """Configuration for circuit breaking thresholds."""
    failure_threshold: int = Field(default=5, description="Consecutive failures before opening.")
    recovery_timeout_seconds: float = Field(default=60.0, description="Time to wait before transitioning OPEN -> HALF_OPEN.")
    success_threshold: int = Field(default=3, description="Consecutive successes in HALF_OPEN to transition to CLOSED.")

class CircuitBreaker:
    """
    Prevents catastrophic cascading failures across agent infrastructure by
    failing fast when a downstream dependency (LLM API, Database) is degraded.
    """
    def __init__(self, service_name: str, config: CircuitBreakerConfig):
        self.service_name = service_name
        self.config = config
        
        self.state = CircuitState.CLOSED
        self.metrics = CircuitBreakerMetrics(service_name=service_name)
        
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time = 0.0
        self._lock = asyncio.Lock()

    async def _evaluate_state(self):
        """Internal FSM transition logic based on time and counts."""
        now = time.monotonic()
        
        if self.state == CircuitState.OPEN:
            elapsed = now - self._last_failure_time
            if elapsed >= self.config.recovery_timeout_seconds:
                logger.info(f"CircuitBreaker[{self.service_name}] transition: OPEN -> HALF_OPEN")
                self._transition_to(CircuitState.HALF_OPEN)
                self._success_count = 0

    def _transition_to(self, new_state: CircuitState):
        self.state = new_state
        self.metrics.last_state_change = datetime.now(timezone.utc)

    async def execute(self, operation: Callable[..., Awaitable[Any]], fallback: Optional[Callable[..., Awaitable[Any]]] = None, *args, **kwargs) -> Any:
        """
        Wraps an async operation with circuit-breaking logic.
        """
        async with self._lock:
            await self._evaluate_state()
            
            if self.state == CircuitState.OPEN:
                self.metrics.short_circuited_requests += 1
                logger.warning(f"CircuitBreaker[{self.service_name}] is OPEN. Short-circuiting request.")
                if fallback:
                    self.metrics.fallback_invocations += 1
                    return await fallback(*args, **kwargs)
                raise Exception(f"Service {self.service_name} is unavailable (Circuit OPEN).")

        try:
            result = await operation(*args, **kwargs)
            await self.record_success()
            return result
        except Exception as e:
            await self.record_failure()
            if fallback:
                logger.warning(f"CircuitBreaker[{self.service_name}] executing fallback due to error: {e}")
                self.metrics.fallback_invocations += 1
                return await fallback(*args, **kwargs)
            raise e

    async def record_success(self):
        async with self._lock:
            self.metrics.successful_requests += 1
            if self.state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    logger.info(f"CircuitBreaker[{self.service_name}] transition: HALF_OPEN -> CLOSED")
                    self._transition_to(CircuitState.CLOSED)
                    self._failure_count = 0
            elif self.state == CircuitState.CLOSED:
                self._failure_count = 0

    async def record_failure(self):
        async with self._lock:
            self.metrics.failed_requests += 1
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            
            if self.state == CircuitState.CLOSED and self._failure_count >= self.config.failure_threshold:
                logger.error(f"CircuitBreaker[{self.service_name}] threshold breached. CLOSED -> OPEN")
                self._transition_to(CircuitState.OPEN)
            elif self.state == CircuitState.HALF_OPEN:
                logger.error(f"CircuitBreaker[{self.service_name}] failure in trial. HALF_OPEN -> OPEN")
                self._transition_to(CircuitState.OPEN)


class CircuitBreakerRegistry:
    """Central registry to manage and retrieve circuit breakers for multiple dependencies."""
    def __init__(self):
        self._breakers: Dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()

    async def get_or_create(self, service_name: str, config: Optional[CircuitBreakerConfig] = None) -> CircuitBreaker:
        async with self._lock:
            if service_name not in self._breakers:
                self._breakers[service_name] = CircuitBreaker(
                    service_name, 
                    config or CircuitBreakerConfig()
                )
            return self._breakers[service_name]

class HealthCheck:
    """Probes services to proactively check health and feed into the CircuitBreaker."""
    def __init__(self, name: str, probe_func: Callable[..., Awaitable[bool]], interval_seconds: float):
        self.name = name
        self.probe = probe_func
        self.interval = interval_seconds
        self._task: Optional[asyncio.Task] = None

    async def start(self, cb_registry: CircuitBreakerRegistry):
        self._task = asyncio.create_task(self._run_loop(cb_registry))

    async def _run_loop(self, cb_registry: CircuitBreakerRegistry):
        breaker = await cb_registry.get_or_create(self.name)
        while True:
            try:
                is_healthy = await self.probe()
                if is_healthy:
                    await breaker.record_success()
                else:
                    await breaker.record_failure()
            except Exception:
                await breaker.record_failure()
            await asyncio.sleep(self.interval)

    def stop(self):
        if self._task:
            self._task.cancel()
