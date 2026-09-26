import hashlib
import json
import logging
import asyncio
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class AuditEntry(BaseModel):
    """A strictly structured record of a system event, designed for immutability."""
    entry_id: str = Field(..., description="Unique ID (e.g., UUID or sequential).")
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    actor: str = Field(..., description="System, User, or Agent initiating the action.")
    action: str = Field(..., description="The action performed (e.g., TOOL_EXECUTION).")
    resource: str = Field(..., description="Target of the action (e.g., 'bash', 's3').")
    outcome: str = Field(..., description="SUCCESS, FAILURE, REJECTED, etc.")
    context: Dict[str, Any] = Field(default_factory=dict, description="Additional context payload.")
    previous_hash: str = Field(..., description="Cryptographic link to the preceding entry.")

class HashChainBlock(BaseModel):
    """Wrapper that binds an AuditEntry to its cryptographic hash."""
    entry: AuditEntry
    block_hash: str = Field(..., description="SHA-256 hash of the entry and previous_hash.")

class LedgerVerificationReport(BaseModel):
    """Result of verifying the tamper-evident ledger integrity."""
    is_valid: bool
    total_blocks_verified: int
    failed_at_index: Optional[int] = None
    failure_reason: Optional[str] = None
    verification_time: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class MerkleNode(BaseModel):
    """Node in a Merkle Tree used for bulk verification."""
    hash_value: str
    left: Optional['MerkleNode'] = None
    right: Optional['MerkleNode'] = None

class MerkleTree:
    """Constructs a Merkle Tree from a list of hashes for efficient cryptographic proofs."""
    def __init__(self, leaves: List[str]):
        self.leaves = leaves
        self.root = self._build_tree([MerkleNode(hash_value=leaf) for leaf in leaves])

    def _build_tree(self, nodes: List[MerkleNode]) -> Optional[MerkleNode]:
        if not nodes:
            return None
        if len(nodes) == 1:
            return nodes[0]

        parents = []
        for i in range(0, len(nodes), 2):
            left = nodes[i]
            right = nodes[i + 1] if i + 1 < len(nodes) else left # Duplicate if odd
            
            combined = left.hash_value + right.hash_value
            parent_hash = hashlib.sha256(combined.encode('utf-8')).hexdigest()
            
            parents.append(MerkleNode(hash_value=parent_hash, left=left, right=right))
        
        return self._build_tree(parents)
        
    def get_root_hash(self) -> Optional[str]:
        return self.root.hash_value if self.root else None

class TamperEvidenceLedger:
    """
    An append-only, cryptographically linked chain of audit events.
    Guarantees that past audit logs cannot be modified without breaking the chain.
    """
    GENESIS_HASH = "0" * 64

    def __init__(self):
        self._chain: List[HashChainBlock] = []
        self._lock = asyncio.Lock()

    def _calculate_hash(self, entry: AuditEntry) -> str:
        """Deterministically serializes and hashes an AuditEntry."""
        # Convert to dict, sort keys to ensure deterministic JSON representation
        serialized = entry.model_dump_json(exclude={'previous_hash'})
        payload = f"{serialized}|{entry.previous_hash}"
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    async def append_entry(self, entry_data: Dict[str, Any]) -> HashChainBlock:
        """Safely appends a new event to the ledger."""
        async with self._lock:
            prev_hash = self._chain[-1].block_hash if self._chain else self.GENESIS_HASH
            
            # Construct Entry
            entry = AuditEntry(
                entry_id=entry_data.get("entry_id", ""),
                actor=entry_data.get("actor", "SYSTEM"),
                action=entry_data.get("action", "UNKNOWN"),
                resource=entry_data.get("resource", "NONE"),
                outcome=entry_data.get("outcome", "UNKNOWN"),
                context=entry_data.get("context", {}),
                previous_hash=prev_hash
            )
            
            block_hash = self._calculate_hash(entry)
            block = HashChainBlock(entry=entry, block_hash=block_hash)
            
            self._chain.append(block)
            logger.debug(f"Appended block to ledger. Hash: {block_hash[:8]}...")
            return block

    async def verify_integrity(self) -> LedgerVerificationReport:
        """Iterates through the chain to detect any tampering or broken links."""
        async with self._lock:
            if not self._chain:
                return LedgerVerificationReport(is_valid=True, total_blocks_verified=0)

            expected_prev_hash = self.GENESIS_HASH
            
            for index, block in enumerate(self._chain):
                # Check link
                if block.entry.previous_hash != expected_prev_hash:
                    return LedgerVerificationReport(
                        is_valid=False, 
                        total_blocks_verified=index,
                        failed_at_index=index,
                        failure_reason=f"Link broken: previous_hash mismatch at index {index}."
                    )
                
                # Check integrity
                recomputed_hash = self._calculate_hash(block.entry)
                if recomputed_hash != block.block_hash:
                    return LedgerVerificationReport(
                        is_valid=False, 
                        total_blocks_verified=index,
                        failed_at_index=index,
                        failure_reason=f"Tampering detected: block_hash invalid at index {index}."
                    )
                
                expected_prev_hash = block.block_hash

            return LedgerVerificationReport(is_valid=True, total_blocks_verified=len(self._chain))

    async def get_merkle_root(self) -> Optional[str]:
        """Returns the Merkle root hash of all blocks in the ledger."""
        async with self._lock:
            if not self._chain:
                return None
            leaves = [block.block_hash for block in self._chain]
            tree = MerkleTree(leaves)
            return tree.get_root_hash()

class LedgerExporter:
    """Exports the ledger into standard formats for external compliance auditors."""
    
    @staticmethod
    def export_to_json(ledger_chain: List[HashChainBlock]) -> str:
        """Exports the full cryptographically signed chain as JSON."""
        return json.dumps([block.model_dump(mode='json') for block in ledger_chain], indent=2)

    @staticmethod
    def export_to_csv(ledger_chain: List[HashChainBlock]) -> str:
        """Exports a flattened human-readable version (lossy, non-cryptographic)."""
        lines = ["entry_id,timestamp,actor,action,resource,outcome,block_hash"]
        for block in ledger_chain:
            entry = block.entry
            lines.append(f"{entry.entry_id},{entry.timestamp.isoformat()},{entry.actor},{entry.action},{entry.resource},{entry.outcome},{block.block_hash}")
        return "\n".join(lines)
