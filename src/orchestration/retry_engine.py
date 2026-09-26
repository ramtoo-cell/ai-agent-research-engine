import asyncio
import random
import logging
from enum import Enum
from typing import Callable, Any, Dict, Optional, Coroutine, Type
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)


class BackoffStrategy(Enum):
    FIXED = "FIXED"
    LINEAR = "LINEAR"
    EXPONENTIAL = "EXPONENTIAL"
    DECORRELATED_JITTER = "DECORRELATED_JITTER"


class RetryPolicy(BaseModel):
    """Configuration for retry behavior."""
    max_retries: int = Field(default=3, ge=0)
    base_delay_seconds: float = Field(default=1.0, gt=0.0)
    max_delay_seconds: float = Field(default=60.0, gt=0.0)
    backoff_strategy: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    jitter_factor: float = Field(default=0.1, ge=0.0, le=1.0, description="Used in EXPONENTIAL backoff")
    retryable_exceptions: tuple = Field(default=(Exception,), exclude=True)


class DeadLetter(BaseModel):
    """Record of a permanently failed task."""
    id: UUID = Field(default_factory=uuid4)
    task_name: str
    error_message: str
    traceback: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    failed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    attempts: int


class CircuitBreakerState(Enum):
    CLOSED = "CLOSED"      # Normal operation
    OPEN = "OPEN"          # Failing, fast-reject
    HALF_OPEN = "HALF_OPEN"  # Testing recovery


class CircuitBreakerIntegration:
    """Simple circuit breaker to prevent cascading failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout_seconds: float = 30.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds
        
        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self._lock = asyncio.Lock()

    async def record_failure(self) -> None:
        async with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now(timezone.utc)
            if self.failure_count >= self.failure_threshold:
                self.state = CircuitBreakerState.OPEN
                logger.warning("Circuit breaker opened due to successive failures.")

    async def record_success(self) -> None:
        async with self._lock:
            if self.state == CircuitBreakerState.HALF_OPEN:
                self.state = CircuitBreakerState.CLOSED
                self.failure_count = 0
                logger.info("Circuit breaker closed after successful recovery.")
            elif self.state == CircuitBreakerState.CLOSED:
                self.failure_count = 0

    async def can_execute(self) -> bool:
        """Determines if a request should be allowed through."""
        async with self._lock:
            if self.state == CircuitBreakerState.CLOSED:
                return True
                
            if self.state == CircuitBreakerState.OPEN:
                if self.last_failure_time:
                    elapsed = (datetime.now(timezone.utc) - self.last_failure_time).total_seconds()
                    if elapsed > self.recovery_timeout:
                        self.state = CircuitBreakerState.HALF_OPEN
                        logger.info("Circuit breaker entering half-open state for testing.")
                        return True
                return False
                
            # HALF_OPEN allows 1 request through to test
            return True


class DeadLetterQueue:
    """Storage for permanently failed tasks."""
    
    def __init__(self) -> None:
        self.queue: List[DeadLetter] = []
        self._lock = asyncio.Lock()

    async def push(self, dl: DeadLetter) -> None:
        async with self._lock:
            self.queue.append(dl)
            logger.error(f"Task moved to DLQ: {dl.task_name}, Error: {dl.error_message}")

    async def list_items(self) -> List[DeadLetter]:
        async with self._lock:
            return list(self.queue)


class RetryBudget:
    """Token bucket style budget to prevent system overload from retries."""
    
    def __init__(self, max_tokens: int = 100, refill_rate_per_sec: float = 10.0):
        self.max_tokens = float(max_tokens)
        self.tokens = float(max_tokens)
        self.refill_rate = refill_rate_per_sec
        self.last_refill = datetime.now(timezone.utc)
        self._lock = asyncio.Lock()

    async def consume(self) -> bool:
        """Consumes a retry token. Returns True if successful, False if budget exhausted."""
        async with self._lock:
            now = datetime.now(timezone.utc)
            elapsed = (now - self.last_refill).total_seconds()
            
            # Refill
            self.tokens = min(self.max_tokens, self.tokens + elapsed * self.refill_rate)
            self.last_refill = now
            
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class RetryExecutor:
    """Executes asynchronous callables with robust retry policies."""
    
    def __init__(self, dlq: Optional[DeadLetterQueue] = None, budget: Optional[RetryBudget] = None, circuit_breaker: Optional[CircuitBreakerIntegration] = None):
        self.dlq = dlq or DeadLetterQueue()
        self.budget = budget or RetryBudget()
        self.circuit_breaker = circuit_breaker or CircuitBreakerIntegration()

    def _calculate_delay(self, attempt: int, policy: RetryPolicy, last_delay: float = 0.0) -> float:
        """Calculates the delay before the next attempt based on the strategy."""
        if policy.backoff_strategy == BackoffStrategy.FIXED:
            delay = policy.base_delay_seconds
            
        elif policy.backoff_strategy == BackoffStrategy.LINEAR:
            delay = policy.base_delay_seconds * attempt
            
        elif policy.backoff_strategy == BackoffStrategy.EXPONENTIAL:
            delay = policy.base_delay_seconds * (2 ** (attempt - 1))
            # Add basic jitter
            jitter = delay * policy.jitter_factor
            delay = random.uniform(delay - jitter, delay + jitter)
            
        elif policy.backoff_strategy == BackoffStrategy.DECORRELATED_JITTER:
            if attempt == 1:
                delay = policy.base_delay_seconds
            else:
                delay = random.uniform(policy.base_delay_seconds, last_delay * 3)
        else:
            delay = policy.base_delay_seconds
            
        return min(delay, policy.max_delay_seconds)

    async def execute(self, task_name: str, func: Callable[..., Coroutine[Any, Any, Any]], policy: RetryPolicy, *args: Any, **kwargs: Any) -> Any:
        """Executes the function with retries."""
        
        attempt = 0
        last_delay = 0.0
        last_exception = None
        
        while attempt <= policy.max_retries:
            attempt += 1
            
            # Check circuit breaker
            if not await self.circuit_breaker.can_execute():
                logger.error(f"Execution of {task_name} rejected by circuit breaker.")
                raise Exception(f"Circuit Breaker OPEN for task {task_name}")
                
            try:
                result = await func(*args, **kwargs)
                await self.circuit_breaker.record_success()
                return result
                
            except policy.retryable_exceptions as e:
                last_exception = e
                await self.circuit_breaker.record_failure()
                
                if attempt > policy.max_retries:
                    break
                    
                # Check retry budget
                if not await self.budget.consume():
                    logger.warning(f"Retry budget exhausted for {task_name}.")
                    break
                    
                # Calculate delay and sleep
                last_delay = self._calculate_delay(attempt, policy, last_delay)
                logger.info(f"Task {task_name} failed. Retrying in {last_delay:.2f}s (Attempt {attempt}/{policy.max_retries}). Error: {str(e)}")
                await asyncio.sleep(last_delay)
                
            except Exception as e:
                # Non-retryable exception
                last_exception = e
                await self.circuit_breaker.record_failure()
                break

        # If we reach here, it's a permanent failure
        dl = DeadLetter(
            task_name=task_name,
            error_message=str(last_exception),
            attempts=attempt,
            payload={"args": str(args), "kwargs": str(kwargs)}
        )
        await self.dlq.push(dl)
        
        raise last_exception or Exception(f"Task {task_name} failed unexpectedly.")

# EOF
