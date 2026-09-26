"""
Authorization Module for AI Governance & Safety Platform.

Implements a hybrid authorization model combining Role-Based Access Control (RBAC),
Attribute-Based Access Control (ABAC), and Cryptographic Capability-Based Authorization.
Supports hierarchical role resolution, token signing, and deep audit contexts.
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ActionType(str, Enum):
    """Standardized actions that can be performed."""
    CREATE = "CREATE"
    READ = "READ"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"
    TRAIN = "TRAIN"
    DEPLOY = "DEPLOY"
    INVOKE = "INVOKE"

class ResourceType(str, Enum):
    """Standardized resource types in the AI Governance ecosystem."""
    MODEL = "MODEL"
    DATASET = "DATASET"
    AGENT = "AGENT"
    POLICY = "POLICY"
    AUDIT_LOG = "AUDIT_LOG"
    SYSTEM = "SYSTEM"

class DecisionType(str, Enum):
    """The result of an authorization request."""
    PERMIT = "PERMIT"
    DENY = "DENY"
    INDETERMINATE = "INDETERMINATE"
    NOT_APPLICABLE = "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Subject(BaseModel):
    """The entity (User, Agent, System) requesting access."""
    subject_id: str = Field(..., description="Unique identifier for the subject.")
    subject_type: str = Field(..., description="E.g., 'USER', 'AGENT', 'SERVICE'.")
    roles: List[str] = Field(default_factory=list, description="RBAC roles assigned.")
    attributes: Dict[str, Any] = Field(default_factory=dict, description="ABAC attributes.")

class Resource(BaseModel):
    """The target entity being accessed."""
    resource_id: str = Field(...)
    resource_type: ResourceType = Field(...)
    attributes: Dict[str, Any] = Field(default_factory=dict, description="ABAC attributes (e.g., sensitivity).")

class Permission(BaseModel):
    """A distinct permission granting an action on a resource type."""
    action: ActionType
    resource_type: ResourceType
    conditions: Dict[str, Any] = Field(default_factory=dict, description="ABAC condition constraints.")
    
    model_config = ConfigDict(frozen=True)

class Role(BaseModel):
    """RBAC Role supporting inheritance."""
    name: str = Field(..., description="Unique role name.")
    permissions: List[Permission] = Field(default_factory=list)
    parent_roles: List[str] = Field(default_factory=list, description="Roles from which this role inherits.")

class CapabilityToken(BaseModel):
    """A cryptographic capability token granting specific, time-bound access."""
    token_id: str = Field(default_factory=lambda: str(uuid4()))
    subject_id: str = Field(...)
    target_resource_id: str = Field(...)
    allowed_actions: List[ActionType] = Field(...)
    issued_at: int = Field(default_factory=lambda: int(time.time()))
    expires_at: int = Field(...)
    signature: str = Field(default="", description="HMAC-SHA256 signature.")

class AuthorizationDecision(BaseModel):
    """The fully auditable result of an authorization check."""
    decision_id: UUID = Field(default_factory=uuid4)
    timestamp: float = Field(default_factory=time.time)
    subject_id: str
    resource_id: str
    action: ActionType
    decision: DecisionType
    reasoning: str
    matched_roles: List[str] = Field(default_factory=list)
    capability_used: bool = Field(default=False)

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Engine Implementation
# ---------------------------------------------------------------------------
class AuthorizationEngine:
    """
    Hybrid authorization engine supporting RBAC, ABAC, and Capabilities.
    """
    
    def __init__(self, secret_key: Optional[str] = None) -> None:
        self.roles: Dict[str, Role] = {}
        # Use provided key or generate a strong random one for tokens
        self._secret_key = secret_key.encode() if secret_key else secrets.token_bytes(32)

    def register_role(self, role: Role) -> None:
        """Register an RBAC role."""
        self.roles[role.name] = role
        logger.info(f"Registered role: {role.name}")

    def _resolve_roles(self, role_names: List[str]) -> Set[str]:
        """Recursively resolves role inheritance (DFS)."""
        resolved = set()
        stack = list(role_names)
        
        while stack:
            current = stack.pop()
            if current not in resolved and current in self.roles:
                resolved.add(current)
                role_obj = self.roles[current]
                stack.extend(role_obj.parent_roles)
                
        return resolved

    def _evaluate_abac(self, subject: Subject, resource: Resource, conditions: Dict[str, Any]) -> bool:
        """
        Evaluates Attribute-Based Access Control conditions.
        Simple matching: condition keys must exist in subject or resource attributes,
        and values must match.
        """
        if not conditions:
            return True
            
        for key, expected_val in conditions.items():
            # Check subject attributes first, then resource attributes
            if key.startswith("subject."):
                attr_key = key.split("subject.", 1)[1]
                if subject.attributes.get(attr_key) != expected_val:
                    return False
            elif key.startswith("resource."):
                attr_key = key.split("resource.", 1)[1]
                if resource.attributes.get(attr_key) != expected_val:
                    return False
            else:
                # Ambiguous key, deny by default
                return False
                
        return True

    def _sign_token(self, payload: str) -> str:
        """Generates an HMAC-SHA256 signature."""
        return hmac.new(self._secret_key, payload.encode(), hashlib.sha256).hexdigest()

    def generate_capability_token(
        self, subject_id: str, resource_id: str, actions: List[ActionType], ttl_seconds: int = 3600
    ) -> CapabilityToken:
        """Generates a cryptographically signed capability token."""
        now = int(time.time())
        token = CapabilityToken(
            subject_id=subject_id,
            target_resource_id=resource_id,
            allowed_actions=actions,
            issued_at=now,
            expires_at=now + ttl_seconds
        )
        
        # Serialize payload without signature for signing
        payload_dict = token.model_dump(exclude={"signature"})
        # Ensure deterministic JSON serialization
        payload_str = json.dumps(payload_dict, sort_keys=True)
        token.signature = self._sign_token(payload_str)
        
        return token

    def verify_capability_token(self, token: CapabilityToken) -> bool:
        """Verifies the cryptographic signature and expiration of a token."""
        if int(time.time()) > token.expires_at:
            logger.warning(f"Capability token expired: {token.token_id}")
            return False
            
        payload_dict = token.model_dump(exclude={"signature"})
        payload_str = json.dumps(payload_dict, sort_keys=True)
        expected_sig = self._sign_token(payload_str)
        
        # Use compare_digest to prevent timing attacks
        return hmac.compare_digest(expected_sig, token.signature)

    async def authorize(
        self, 
        subject: Subject, 
        resource: Resource, 
        action: ActionType,
        capability_token: Optional[CapabilityToken] = None
    ) -> AuthorizationDecision:
        """
        Main entrypoint for authorization.
        Checks capabilities first, then falls back to RBAC + ABAC.
        """
        # 1. Check Capability Token (Fast Path)
        if capability_token:
            if self.verify_capability_token(capability_token):
                if capability_token.subject_id == subject.subject_id and \
                   capability_token.target_resource_id == resource.resource_id and \
                   action in capability_token.allowed_actions:
                    
                    return AuthorizationDecision(
                        subject_id=subject.subject_id,
                        resource_id=resource.resource_id,
                        action=action,
                        decision=DecisionType.PERMIT,
                        reasoning="Valid capability token presented.",
                        capability_used=True
                    )
            else:
                return AuthorizationDecision(
                    subject_id=subject.subject_id,
                    resource_id=resource.resource_id,
                    action=action,
                    decision=DecisionType.DENY,
                    reasoning="Invalid or expired capability token.",
                    capability_used=True
                )

        # 2. RBAC + ABAC Evaluation
        effective_roles = self._resolve_roles(subject.roles)
        matched_roles = []
        
        for role_name in effective_roles:
            role = self.roles.get(role_name)
            if not role:
                continue
                
            for perm in role.permissions:
                if perm.action == action and perm.resource_type == resource.resource_type:
                    # Found RBAC match, now check ABAC conditions
                    if self._evaluate_abac(subject, resource, perm.conditions):
                        matched_roles.append(role_name)

        if matched_roles:
            return AuthorizationDecision(
                subject_id=subject.subject_id,
                resource_id=resource.resource_id,
                action=action,
                decision=DecisionType.PERMIT,
                reasoning="RBAC and ABAC conditions satisfied.",
                matched_roles=matched_roles
            )

        # 3. Default Deny
        return AuthorizationDecision(
            subject_id=subject.subject_id,
            resource_id=resource.resource_id,
            action=action,
            decision=DecisionType.DENY,
            reasoning="No matching roles or valid capabilities found."
        )
