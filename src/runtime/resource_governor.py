import time
import asyncio
import logging
from typing import Dict, Optional, List, Callable, Awaitable
from datetime import datetime, timezone
from enum import Enum
from pydantic import BaseModel, Field, ConfigDict

logger = logging.getLogger(__name__)

class QuotaExhaustedStrategy(str, Enum):
    """Behavior when a resource quota is exceeded."""
    REJECT = "REJECT"        # Fail immediately
    QUEUE = "QUEUE"          # Wait until capacity is available
    DEGRADE = "DEGRADE"      # Fallback to lower-cost model or mode

class TokenBudget(BaseModel):
    """Tracks token consumption vs budget allocation."""
    model_config = ConfigDict(frozen=False)

    max_tokens_per_request: int = Field(default=4096)
    max_tokens_per_session: int = Field(default=32768)
    consumed_request: int = Field(default=0)
    consumed_session: int = Field(default=0)
    
    def can_consume(self, amount: int) -> bool:
        """Checks if budget permits consuming 'amount' tokens."""
        if self.consumed_request + amount > self.max_tokens_per_request:
            return False
        if self.consumed_session + amount > self.max_tokens_per_session:
            return False
        return True

    def consume(self, amount: int):
        self.consumed_request += amount
        self.consumed_session += amount

class CostCeiling(BaseModel):
    """Monetary cost limits for an entity (User/Org)."""
    max_usd_per_day: float = Field(default=10.0)
    current_spend_usd: float = Field(default=0.0)
    
    def can_spend(self, amount_usd: float) -> bool:
        return (self.current_spend_usd + amount_usd) <= self.max_usd_per_day
        
    def record_spend(self, amount_usd: float):
        self.current_spend_usd += amount_usd

class ResourceQuota(BaseModel):
    """Aggregates all quotas applied to an entity."""
    entity_id: str
    tokens: TokenBudget = Field(default_factory=TokenBudget)
    cost: CostCeiling = Field(default_factory=CostCeiling)
    max_concurrent_requests: int = Field(default=5)
    current_concurrent_requests: int = Field(default=0)

class ResourceUsageReport(BaseModel):
    """Periodic report of resource consumption."""
    entity_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    tokens_consumed: int
    cost_incurred: float
    throttled_requests: int

class RateLimiter:
    """Token Bucket algorithm for rate limiting API/Agent requests."""
    
    def __init__(self, bucket_capacity: int, refill_rate_per_second: float):
        self.capacity = bucket_capacity
        self.refill_rate = refill_rate_per_second
        self.tokens = float(bucket_capacity)
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self, amount: int = 1, timeout: Optional[float] = None) -> bool:
        """Attempts to acquire tokens from the bucket."""
        start_time = time.monotonic()
        
        while True:
            async with self._lock:
                now = time.monotonic()
                elapsed = now - self.last_refill
                
                # Refill
                self.tokens = min(float(self.capacity), self.tokens + elapsed * self.refill_rate)
                self.last_refill = now
                
                if self.tokens >= amount:
                    self.tokens -= amount
                    return True

            if timeout is not None:
                elapsed_wait = time.monotonic() - start_time
                if elapsed_wait >= timeout:
                    return False
            
            # Wait a bit before checking again
            await asyncio.sleep(0.1)

class ResourceGovernor:
    """
    Orchestrates resource management, rate limiting, and budgeting across the system.
    """
    def __init__(self, exhaustion_strategy: QuotaExhaustedStrategy = QuotaExhaustedStrategy.REJECT):
        self.strategy = exhaustion_strategy
        self._quotas: Dict[str, ResourceQuota] = {}
        self._rate_limiters: Dict[str, RateLimiter] = {}
        self._lock = asyncio.Lock()

    async def register_entity(self, entity_id: str, quota: ResourceQuota, rate_limit_cap: int = 10, rate_refill: float = 1.0):
        async with self._lock:
            self._quotas[entity_id] = quota
            self._rate_limiters[entity_id] = RateLimiter(rate_limit_cap, rate_refill)
            logger.info(f"Registered quotas for entity: {entity_id}")

    async def request_execution(self, entity_id: str, estimated_tokens: int, estimated_cost: float) -> bool:
        """
        Pre-flight check: determines if an execution can proceed based on quotas and rate limits.
        """
        async with self._lock:
            if entity_id not in self._quotas:
                logger.error(f"Entity {entity_id} has no registered quotas.")
                return False

            quota = self._quotas[entity_id]
            limiter = self._rate_limiters[entity_id]

        # 1. Rate Limiting Check
        if self.strategy == QuotaExhaustedStrategy.QUEUE:
            acquired = await limiter.acquire(amount=1, timeout=30.0)
        else:
            acquired = await limiter.acquire(amount=1, timeout=0.0)

        if not acquired:
            logger.warning(f"Rate limit exceeded for entity {entity_id}.")
            return False

        # 2. Concurrency Check
        async with self._lock:
            if quota.current_concurrent_requests >= quota.max_concurrent_requests:
                logger.warning(f"Concurrency limit exceeded for entity {entity_id}.")
                return False
            
            # 3. Budget & Cost Check
            if not quota.tokens.can_consume(estimated_tokens) or not quota.cost.can_spend(estimated_cost):
                logger.warning(f"Budget/Cost limit exceeded for entity {entity_id}.")
                return False
            
            # Commit pre-flight
            quota.current_concurrent_requests += 1

        return True

    async def finalize_execution(self, entity_id: str, actual_tokens: int, actual_cost: float):
        """
        Post-flight update: applies actual consumption to budgets.
        """
        async with self._lock:
            quota = self._quotas.get(entity_id)
            if quota:
                quota.current_concurrent_requests = max(0, quota.current_concurrent_requests - 1)
                quota.tokens.consume(actual_tokens)
                quota.cost.record_spend(actual_cost)

    async def generate_report(self, entity_id: str) -> Optional[ResourceUsageReport]:
        """Generates a point-in-time usage report for an entity."""
        async with self._lock:
            quota = self._quotas.get(entity_id)
            if not quota:
                return None
            return ResourceUsageReport(
                entity_id=entity_id,
                tokens_consumed=quota.tokens.consumed_session,
                cost_incurred=quota.cost.current_spend_usd,
                throttled_requests=0 # Tracked via metrics in a real system
            )
