"""
Policy Engine Module for AI Governance & Safety Platform.

This module provides a deterministically evaluated policy engine that enforces
complex rule sets against runtime execution contexts. It supports recursive
logic trees, priority-based evaluation cascading, conflict resolution,
and comprehensive audit logging for AI agent operations.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Union, Callable
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ---------------------------------------------------------------------------
# Logging & Exceptions
# ---------------------------------------------------------------------------
logger = logging.getLogger(__name__)

class PolicyEngineError(Exception):
    """Base exception for policy engine errors."""
    pass

class InvalidConditionError(PolicyEngineError):
    """Raised when a policy condition is mathematically or logically invalid."""
    pass

class PolicyConflictError(PolicyEngineError):
    """Raised when policies conflict and cannot be deterministically resolved."""
    pass


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class PolicyDecision(str, Enum):
    """The definitive outcome of a policy evaluation."""
    ALLOW = "ALLOW"
    DENY = "DENY"
    ESCALATE = "ESCALATE"
    AUDIT = "AUDIT"

class ConditionOperator(str, Enum):
    """Supported logical and comparison operators."""
    EQ = "=="
    NEQ = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    IN = "IN"
    NOT_IN = "NOT_IN"
    CONTAINS = "CONTAINS"
    MATCHES_REGEX = "MATCHES_REGEX"

class RuleSeverity(int, Enum):
    """Severity levels for policy rules."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class Condition(BaseModel):
    """A single logical condition evaluating a field against a value."""
    field: str = Field(..., description="The key in the context to evaluate.")
    operator: ConditionOperator = Field(..., description="The comparison operator.")
    value: Any = Field(..., description="The value to compare against.")

    model_config = ConfigDict(frozen=True)

class LogicNode(BaseModel):
    """A recursive logic tree node supporting AND, OR, and NOT operations."""
    and_conditions: Optional[List[Union['LogicNode', Condition]]] = None
    or_conditions: Optional[List[Union['LogicNode', Condition]]] = None
    not_condition: Optional[Union['LogicNode', Condition]] = None

    @field_validator("not_condition")
    @classmethod
    def check_mutually_exclusive(cls, v: Any, info: Any) -> Any:
        # A node should generally only have one of AND, OR, or NOT defined,
        # but we allow combinations if strictly defined. Ideally, validate here.
        return v

class PolicyRule(BaseModel):
    """A distinct rule that produces a decision if conditions are met."""
    rule_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Human-readable name of the rule.")
    description: str = Field(default="", description="Detailed description.")
    conditions: LogicNode = Field(..., description="The logic tree to evaluate.")
    decision: PolicyDecision = Field(..., description="Outcome if conditions match.")
    priority: int = Field(default=100, description="Higher number means higher priority.")
    severity: RuleSeverity = Field(default=RuleSeverity.MEDIUM)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(frozen=True)

class PolicySet(BaseModel):
    """A grouping of policy rules that are evaluated together."""
    set_id: UUID = Field(default_factory=uuid4)
    name: str = Field(..., description="Name of the policy set.")
    rules: List[PolicyRule] = Field(default_factory=list)
    is_active: bool = Field(default=True)

class AuditTrailEntry(BaseModel):
    """An immutable record of a policy evaluation."""
    audit_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    policy_set_id: Optional[UUID] = None
    triggered_rules: List[UUID] = Field(default_factory=list)
    context_snapshot: Dict[str, Any] = Field(...)
    final_decision: PolicyDecision
    reasoning: str
    execution_time_ms: float

    model_config = ConfigDict(frozen=True)


# ---------------------------------------------------------------------------
# Engine Implementation
# ---------------------------------------------------------------------------
class PolicyEngine:
    """
    Evaluates execution contexts against defined PolicySets.
    Features async evaluation, recursive condition parsing, and caching.
    """

    def __init__(self, enable_caching: bool = True) -> None:
        self.policy_sets: Dict[UUID, PolicySet] = {}
        self.audit_log: List[AuditTrailEntry] = []
        self.enable_caching = enable_caching
        self._cache: Dict[str, PolicyDecision] = {}
        self._cache_lock = asyncio.Lock()

    def register_policy_set(self, policy_set: PolicySet) -> None:
        """Register a new policy set into the engine."""
        self.policy_sets[policy_set.set_id] = policy_set
        logger.info(f"Registered PolicySet: {policy_set.name} ({policy_set.set_id})")

    async def _evaluate_condition(self, condition: Condition, context: Dict[str, Any]) -> bool:
        """Evaluates a single condition leaf against the context."""
        context_value = context.get(condition.field)
        if context_value is None and condition.operator not in (ConditionOperator.NEQ, ConditionOperator.NOT_IN):
            return False

        op = condition.operator
        val = condition.value

        try:
            if op == ConditionOperator.EQ:
                return context_value == val
            elif op == ConditionOperator.NEQ:
                return context_value != val
            elif op == ConditionOperator.GT:
                return context_value > val
            elif op == ConditionOperator.LT:
                return context_value < val
            elif op == ConditionOperator.GTE:
                return context_value >= val
            elif op == ConditionOperator.LTE:
                return context_value <= val
            elif op == ConditionOperator.IN:
                return context_value in val
            elif op == ConditionOperator.NOT_IN:
                return context_value not in val
            elif op == ConditionOperator.CONTAINS:
                return val in context_value
            elif op == ConditionOperator.MATCHES_REGEX:
                return bool(re.search(str(val), str(context_value)))
            else:
                raise InvalidConditionError(f"Unknown operator: {op}")
        except TypeError as e:
            logger.warning(f"Type error evaluating condition {condition.field} {op} {val}: {e}")
            return False

    async def _evaluate_logic_node(self, node: Union[LogicNode, Condition], context: Dict[str, Any]) -> bool:
        """Recursively evaluates a LogicNode tree."""
        if isinstance(node, Condition):
            return await self._evaluate_condition(node, context)

        # It's a LogicNode
        if node.not_condition:
            return not await self._evaluate_logic_node(node.not_condition, context)

        if node.and_conditions:
            for child in node.and_conditions:
                if not await self._evaluate_logic_node(child, context):
                    return False
            return True if not node.or_conditions else False # If only ANDs existed

        if node.or_conditions:
            for child in node.or_conditions:
                if await self._evaluate_logic_node(child, context):
                    return True
            return False

        return False # Empty node resolves to False

    async def evaluate_rule(self, rule: PolicyRule, context: Dict[str, Any]) -> bool:
        """Evaluates a single rule."""
        try:
            match = await self._evaluate_logic_node(rule.conditions, context)
            if match:
                logger.debug(f"Rule '{rule.name}' ({rule.rule_id}) matched context.")
            return match
        except Exception as e:
            logger.error(f"Error evaluating rule {rule.rule_id}: {e}")
            return False

    def _resolve_conflicts(self, matched_rules: List[PolicyRule]) -> tuple[PolicyDecision, str]:
        """
        Resolves conflicts between multiple matched rules.
        Highest priority wins. If priorities are equal, highest severity wins.
        If still equal, DENY overrides ALLOW.
        """
        if not matched_rules:
            return PolicyDecision.ALLOW, "Default allow - no rules matched."

        # Sort rules: highest priority first, then highest severity first
        sorted_rules = sorted(
            matched_rules, 
            key=lambda r: (r.priority, r.severity), 
            reverse=True
        )

        top_rule = sorted_rules[0]
        # Check for ties at the top level
        top_ties = [r for r in sorted_rules if r.priority == top_rule.priority and r.severity == top_rule.severity]

        if len(top_ties) > 1:
            decisions = {r.decision for r in top_ties}
            if PolicyDecision.DENY in decisions:
                return PolicyDecision.DENY, f"Conflict resolved to DENY among ties: {[r.rule_id for r in top_ties]}"
            if PolicyDecision.ESCALATE in decisions:
                return PolicyDecision.ESCALATE, f"Conflict resolved to ESCALATE among ties: {[r.rule_id for r in top_ties]}"

        return top_rule.decision, f"Matched rule '{top_rule.name}' with priority {top_rule.priority}"

    async def evaluate(self, context: Dict[str, Any], policy_set_id: Optional[UUID] = None) -> AuditTrailEntry:
        """
        Main entrypoint to evaluate a context against policies.
        Can evaluate a specific set or all active sets.
        """
        start_time = asyncio.get_event_loop().time()
        
        # Caching logic
        cache_key = None
        if self.enable_caching:
            # Create a deterministically hashed key from the context dictionary
            cache_key = str(hash(frozenset(sorted([(k, str(v)) for k, v in context.items()])))) + str(policy_set_id)
            async with self._cache_lock:
                if cache_key in self._cache:
                    cached_decision = self._cache[cache_key]
                    logger.debug("Policy evaluation cache hit.")
                    # We still return an audit entry for the cached response, but note it's cached.
                    return AuditTrailEntry(
                        policy_set_id=policy_set_id,
                        triggered_rules=[],
                        context_snapshot=context,
                        final_decision=cached_decision,
                        reasoning="Returned from cache.",
                        execution_time_ms=(asyncio.get_event_loop().time() - start_time) * 1000
                    )

        target_sets = [self.policy_sets[policy_set_id]] if policy_set_id else self.policy_sets.values()
        
        matched_rules: List[PolicyRule] = []
        for p_set in target_sets:
            if not p_set.is_active:
                continue
            
            # Evaluate all rules in the set concurrently
            tasks = [self.evaluate_rule(rule, context) for rule in p_set.rules]
            results = await asyncio.gather(*tasks)
            
            for rule, matched in zip(p_set.rules, results):
                if matched:
                    matched_rules.append(rule)

        # Resolve conflicts and determine final decision
        final_decision, reasoning = self._resolve_conflicts(matched_rules)

        end_time = asyncio.get_event_loop().time()
        execution_time = (end_time - start_time) * 1000

        audit_entry = AuditTrailEntry(
            policy_set_id=policy_set_id,
            triggered_rules=[r.rule_id for r in matched_rules],
            context_snapshot=context,
            final_decision=final_decision,
            reasoning=reasoning,
            execution_time_ms=execution_time
        )
        
        self.audit_log.append(audit_entry)

        if self.enable_caching and cache_key:
            async with self._cache_lock:
                self._cache[cache_key] = final_decision

        return audit_entry

    async def clear_cache(self) -> None:
        """Clears the evaluation cache."""
        async with self._cache_lock:
            self._cache.clear()
            logger.info("Policy evaluation cache cleared.")
