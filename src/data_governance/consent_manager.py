import asyncio
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime, timedelta

class ConsentRecord(BaseModel):
    model_config = ConfigDict(strict=True)
    user_id: str
    purpose: str
    scope: List[str]
    granted_at: datetime = Field(default_factory=datetime.utcnow)
    expiry: datetime
    
    def is_valid(self) -> bool:
        return datetime.utcnow() < self.expiry

class ConsentAuditTrail:
    def __init__(self):
        self.logs: List[Dict[str, Any]] = []
        
    def log_action(self, user_id: str, action: str, purpose: str):
        self.logs.append({
            "user_id": user_id,
            "action": action,
            "purpose": purpose,
            "timestamp": datetime.utcnow()
        })

class ConsentRegistry:
    """CRUD operations for consent."""
    def __init__(self, audit_trail: ConsentAuditTrail):
        self.records: Dict[str, List[ConsentRecord]] = {}
        self.audit = audit_trail
        
    def grant(self, record: ConsentRecord):
        if record.user_id not in self.records:
            self.records[record.user_id] = []
        self.records[record.user_id].append(record)
        self.audit.log_action(record.user_id, "GRANT", record.purpose)
        
    def revoke(self, user_id: str, purpose: str):
        if user_id in self.records:
            self.records[user_id] = [
                r for r in self.records[user_id] if r.purpose != purpose
            ]
            self.audit.log_action(user_id, "REVOKE", purpose)

class PurposeLimitation:
    """Enforces consent purposes."""
    def __init__(self, registry: ConsentRegistry):
        self.registry = registry
        
    def can_process(self, user_id: str, purpose: str) -> bool:
        records = self.registry.records.get(user_id, [])
        for r in records:
            if r.purpose == purpose and r.is_valid():
                return True
        return False

class DataSubjectRights:
    """Handles GDPR/CCPA rights."""
    async def request_access(self, user_id: str) -> Dict[str, Any]:
        await asyncio.sleep(0.1)
        return {"data": "user_data_dump"}
        
    async def request_deletion(self, user_id: str) -> bool:
        await asyncio.sleep(0.1)
        return True

class ConsentReport(BaseModel):
    model_config = ConfigDict(strict=True)
    active_consents: int
    expired_consents: int
    revoked_consents: int
