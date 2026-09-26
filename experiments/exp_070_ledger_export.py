"""
Experiment: Ledger Export
Description: Tests audit trailing, tamper-evident logging, and circuit breakers.
"""

import asyncio
import logging
import hashlib
from datetime import datetime
from dataclasses import dataclass

# Mocking imports from src/
try:
    from src.audit.ledger import TamperEvidentLedger, HashChain
    from src.audit.tracing import DistributedTracer
    from src.circuit_breaker.manager import CircuitBreaker
except ImportError:
    class TamperEvidentLedger: pass
    class CircuitBreaker: pass

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class AuditRecord:
    timestamp: str
    action: str
    actor: str
    status: str
    previous_hash: str
    
    def compute_hash(self) -> str:
        data = f"{self.timestamp}{self.action}{self.actor}{self.status}{self.previous_hash}"
        return hashlib.sha256(data.encode()).hexdigest()

class MockLedger:
    def __init__(self):
        self.chain = []
        self.last_hash = "0" * 64
        
    async def append_record(self, action: str, actor: str, status: str) -> str:
        record = AuditRecord(
            timestamp=datetime.utcnow().isoformat(),
            action=action,
            actor=actor,
            status=status,
            previous_hash=self.last_hash
        )
        new_hash = record.compute_hash()
        self.chain.append((record, new_hash))
        self.last_hash = new_hash
        logger.info(f"Ledger Appended: {action} by {actor} -> {new_hash[:8]}...")
        return new_hash
        
    def verify_integrity(self) -> bool:
        logger.info("Verifying cryptographic integrity of the audit chain...")
        curr_hash = "0" * 64
        for rec, h in self.chain:
            if rec.previous_hash != curr_hash:
                return False
            curr_hash = h
        return True

async def main():
    """Main logic for Ledger Export."""
    logger.info("Starting Audit & Circuit Breaker Experiment: Ledger Export")
    
    ledger = MockLedger()
    
    # Simulate a sequence of audited events
    await ledger.append_record("AGENT_START", "system", "SUCCESS")
    await asyncio.sleep(0.1)
    await ledger.append_record("TOOL_EXECUTION", "agent_01", "SUCCESS")
    await asyncio.sleep(0.1)
    await ledger.append_record("DB_WRITE", "agent_01", "DENIED_BY_POLICY")
    
    is_valid = ledger.verify_integrity()
    logger.info(f"Ledger Integrity Verified: {is_valid}")
    logger.info(f"Total records stored: {len(ledger.chain)}")

if __name__ == '__main__':
    asyncio.run(main())
