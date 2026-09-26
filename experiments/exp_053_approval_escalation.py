"""
Experiment: Approval Escalation
Description: Tests runtime execution constraints, limits, and tool sandboxing.
"""

import asyncio
import logging
import time
from typing import Callable, Awaitable

# Mocking imports from src/
try:
    from src.runtime.executor import GovernedExecutor
    from src.runtime.limits import TokenBudget, TimeLimiter
    from src.runtime.sandbox import ToolSandbox
except ImportError:
    class GovernedExecutor: pass
    class TokenBudget: pass
    class ToolSandbox: pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

async def governed_task(task_id: int, duration: float) -> str:
    """A mock agent task that runs under governance constraints."""
    logger.info(f"Task {task_id} started. Expected duration: {duration}s")
    start = time.time()
    
    try:
        # Simulate work with timeout constraints
        await asyncio.wait_for(asyncio.sleep(duration), timeout=2.0)
        elapsed = time.time() - start
        logger.info(f"Task {task_id} completed successfully in {elapsed:.2f}s")
        return f"SUCCESS_{task_id}"
    except asyncio.TimeoutError:
        logger.error(f"Task {task_id} exceeded runtime limits and was TERMINATED.")
        return f"TIMEOUT_{task_id}"

async def apply_budget_constraints(tokens_used: int, limit: int) -> bool:
    """Simulate token budget deduction and enforcement."""
    logger.info(f"Checking budget: {tokens_used} / {limit} used.")
    if tokens_used > limit:
        logger.critical("TOKEN BUDGET EXCEEDED. Halting execution.")
        return False
    return True

async def main():
    """Entry point for Approval Escalation."""
    logger.info("Initializing Agent Runtime Environment...")
    
    # Run a batch of governed tasks
    tasks = [
        governed_task(1, 0.5),
        governed_task(2, 1.0),
        governed_task(3, 3.0), # Should timeout
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    budget_ok = await apply_budget_constraints(4500, 5000)
    
    logger.info(f"Execution Results: {results}")
    logger.info(f"Budget Status: {'OK' if budget_ok else 'EXHAUSTED'}")
    logger.info("Runtime experiment finished.")

if __name__ == '__main__':
    asyncio.run(main())
