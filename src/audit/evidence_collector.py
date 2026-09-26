import hashlib
import json
import logging
import uuid
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta
from enum import Enum
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class EvidenceType(str, Enum):
    """Categorization of evidence gathered during agent execution."""
    AGENT_TRACE = "AGENT_TRACE"
    POLICY_DECISION = "POLICY_DECISION"
    APPROVAL = "APPROVAL"
    TOOL_CALL = "TOOL_CALL"
    SYSTEM_METRIC = "SYSTEM_METRIC"
    DATA_ACCESS = "DATA_ACCESS"

class RetentionPolicy(BaseModel):
    """Policy for how long evidence must be retained for compliance."""
    retention_period_days: int = Field(default=365, description="Number of days to keep evidence.")
    archive_after_days: Optional[int] = Field(default=90, description="Move to cold storage after X days.")
    purge_on_expiry: bool = Field(default=True)

class EvidenceArtifact(BaseModel):
    """A strictly immutable snapshot of data collected for compliance."""
    artifact_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    evidence_type: EvidenceType
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    correlation_id: str
    metadata: Dict[str, str] = Field(default_factory=dict)
    raw_data: Any = Field(...)
    content_hash: str = Field(default="")
    chain_of_custody: List[str] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        if not self.content_hash:
            # Deterministically hash the raw_data
            data_str = json.dumps(self.raw_data, sort_keys=True, default=str)
            self.content_hash = hashlib.sha256(data_str.encode('utf-8')).hexdigest()
        if not self.chain_of_custody:
            self.chain_of_custody = [f"Generated locally at {self.timestamp.isoformat()}"]

class EvidencePackage(BaseModel):
    """A sealed bundle of related artifacts, typically tied to a single session or incident."""
    package_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    artifacts: List[EvidenceArtifact] = Field(default_factory=list)
    package_hash: str = Field(default="")
    sealed: bool = Field(default=False)

    def seal(self):
        """Seals the package, rendering it immutable and calculating a composite hash."""
        if self.sealed:
            return
        # Create composite hash of all artifact hashes
        artifact_hashes = "".join(sorted([a.content_hash for a in self.artifacts]))
        self.package_hash = hashlib.sha256(artifact_hashes.encode('utf-8')).hexdigest()
        self.sealed = True

class EvidenceCollectionPipeline:
    """
    Asynchronous pipeline that taps into the agent runtime to siphon evidence
    non-blockingly, batch it, and seal it into compliance packages.
    """
    def __init__(self, retention_policy: RetentionPolicy):
        self.policy = retention_policy
        self._buffer: Dict[str, EvidencePackage] = {}
        self._lock = asyncio.Lock()
        
    async def capture(self, evidence_type: EvidenceType, correlation_id: str, raw_data: Any, metadata: Optional[Dict[str, str]] = None):
        """Asynchronously ingest a piece of evidence."""
        artifact = EvidenceArtifact(
            evidence_type=evidence_type,
            correlation_id=correlation_id,
            raw_data=raw_data,
            metadata=metadata or {}
        )
        
        async with self._lock:
            if correlation_id not in self._buffer:
                self._buffer[correlation_id] = EvidencePackage(correlation_id=correlation_id)
            
            package = self._buffer[correlation_id]
            if package.sealed:
                logger.error(f"Cannot append artifact to sealed package {package.package_id}")
                return
            package.artifacts.append(artifact)
            logger.debug(f"Captured {evidence_type} artifact for correlation: {correlation_id}")

    async def finalize_session(self, correlation_id: str) -> Optional[EvidencePackage]:
        """Seals all evidence collected for a correlation ID and readies it for storage."""
        async with self._lock:
            package = self._buffer.get(correlation_id)
            if not package:
                return None
            
            package.seal()
            # Remove from active buffer (in a real system, send to Blob Storage / SIEM)
            del self._buffer[correlation_id]
            logger.info(f"Sealed EvidencePackage for {correlation_id} with {len(package.artifacts)} artifacts.")
            return package

    async def purge_expired_evidence(self, stored_packages: List[EvidencePackage]) -> List[str]:
        """Identifies packages that have exceeded their retention policy limits."""
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.policy.retention_period_days)
        expired_ids = []
        for pkg in stored_packages:
            if pkg.created_at < cutoff_date:
                expired_ids.append(pkg.package_id)
                logger.info(f"EvidencePackage {pkg.package_id} marked for purge (expired).")
        return expired_ids
