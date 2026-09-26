"""
Constitutional AI Module for AI Governance & Safety Platform.

This module implements Constitutional AI principles, evaluating and revising
AI outputs to ensure they adhere to predefined guidelines regarding harmlessness,
helpfulness, and honesty. It provides a robust, async-first architecture for
critiquing and automatically rewriting non-compliant outputs.
"""

import asyncio
import logging
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, validator, field_validator

# Configure logging
logger = logging.getLogger(__name__)


class PrincipleCategory(str, Enum):
    """Categories of constitutional principles."""
    HARMLESSNESS = "harmlessness"
    HELPFULNESS = "helpfulness"
    HONESTY = "honesty"
    FAIRNESS = "fairness"
    PRIVACY = "privacy"


class ConstitutionalPrinciple(BaseModel):
    """Represents a single constitutional rule or guideline."""

    id: str = Field(default_factory=lambda: str(uuid4())[:8], description="Unique identifier for the principle.")
    category: PrincipleCategory = Field(..., description="The category this principle belongs to.")
    name: str = Field(..., min_length=3, max_length=100, description="Short name of the principle.")
    description: str = Field(..., description="Detailed description of the principle.")
    critique_template: str = Field(
        ..., 
        description="Prompt template used to ask the model to critique an output based on this principle."
    )
    revision_template: str = Field(
        ...,
        description="Prompt template used to ask the model to revise an output based on the critique."
    )
    severity_weight: float = Field(
        default=1.0, ge=0.1, le=5.0, description="Weight indicating the importance of this principle."
    )


class PrincipleSet(BaseModel):
    """A collection of constitutional principles."""

    name: str = Field(..., description="Name of the principle set.")
    version: str = Field(..., description="Version of the principle set.")
    principles: List[ConstitutionalPrinciple] = Field(default_factory=list, description="List of principles.")

    def get_by_category(self, category: PrincipleCategory) -> List[ConstitutionalPrinciple]:
        """Returns principles filtered by category."""
        return [p for p in self.principles if p.category == category]

    @classmethod
    def default_harmlessness(cls) -> "PrincipleSet":
        """Factory method for default harmlessness principles."""
        return cls(
            name="Default Harmlessness",
            version="1.0.0",
            principles=[
                ConstitutionalPrinciple(
                    category=PrincipleCategory.HARMLESSNESS,
                    name="No Harmful Advice",
                    description="The AI should not give advice that could lead to physical or psychological harm.",
                    critique_template="Critique the following text to see if it gives advice that could lead to physical or psychological harm: {text}",
                    revision_template="Revise the following text to remove any advice that could lead to physical or psychological harm, while maintaining the helpful parts: {text}\nCritique: {critique}",
                    severity_weight=5.0
                ),
                ConstitutionalPrinciple(
                    category=PrincipleCategory.HARMLESSNESS,
                    name="No Hate Speech",
                    description="The AI must not generate hate speech, slurs, or discriminatory content.",
                    critique_template="Analyze this text for hate speech, slurs, or discriminatory language: {text}",
                    revision_template="Rewrite this text to completely remove any hate speech or discriminatory language: {text}\nCritique: {critique}",
                    severity_weight=5.0
                )
            ]
        )


class CritiqueResult(BaseModel):
    """The result of evaluating a text against a principle."""
    
    principle_id: str = Field(..., description="ID of the principle evaluated.")
    principle_name: str = Field(..., description="Name of the principle.")
    violation_found: bool = Field(..., description="True if a violation was detected.")
    critique_reasoning: str = Field(..., description="The model's reasoning for the critique.")
    severity_score: float = Field(default=0.0, ge=0.0, le=10.0, description="Severity of the violation if found.")


class ConstitutionalAuditLog(BaseModel):
    """Audit record of the constitutional evaluation and revision process."""

    log_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    original_text: str = Field(..., description="The original input text.")
    final_text: str = Field(..., description="The final text after any revisions.")
    was_revised: bool = Field(..., description="Whether the text was modified.")
    critiques: List[CritiqueResult] = Field(default_factory=list, description="All critiques performed.")
    revision_cycles: int = Field(default=0, description="Number of revision cycles executed.")
    processing_time_ms: float = Field(default=0.0, description="Total time taken for evaluation and revision.")


class ConstitutionalCritic:
    """Evaluates AI outputs against constitutional principles."""

    def __init__(self, model_client: Any = None):
        # model_client would be an async interface to an LLM for actual evaluation
        self.model_client = model_client
        logger.info("ConstitutionalCritic initialized.")

    async def evaluate(self, text: str, principle: ConstitutionalPrinciple) -> CritiqueResult:
        """
        Evaluates the text against a specific principle.
        In a real scenario, this calls an LLM with the principle's critique_template.
        """
        # Simulated evaluation logic
        await asyncio.sleep(0.1)
        
        # dummy logic
        harmful_keywords = ["kill", "steal", "hate", "destroy"]
        violation_found = any(keyword in text.lower() for keyword in harmful_keywords)
        
        reasoning = "Violation detected due to harmful keywords." if violation_found else "No violations detected."
        severity = principle.severity_weight * 2.0 if violation_found else 0.0
        
        return CritiqueResult(
            principle_id=principle.id,
            principle_name=principle.name,
            violation_found=violation_found,
            critique_reasoning=reasoning,
            severity_score=severity
        )

    async def evaluate_all(self, text: str, principle_set: PrincipleSet) -> List[CritiqueResult]:
        """Evaluates the text against all principles in the set concurrently."""
        tasks = [self.evaluate(text, p) for p in principle_set.principles]
        results = await asyncio.gather(*tasks)
        return list(results)


class RevisionEngine:
    """Rewrites AI outputs to satisfy constitutional principles based on critiques."""

    def __init__(self, model_client: Any = None):
        self.model_client = model_client
        logger.info("RevisionEngine initialized.")

    async def revise(self, text: str, principle: ConstitutionalPrinciple, critique: CritiqueResult) -> str:
        """
        Revises the text using the principle's revision template and the critique.
        """
        # Simulated revision logic
        await asyncio.sleep(0.15)
        
        if not critique.violation_found:
            return text
            
        # Dummy logic: replace harmful keywords
        revised_text = text
        harmful_keywords = ["kill", "steal", "hate", "destroy"]
        for kw in harmful_keywords:
            revised_text = revised_text.replace(kw, "[REDACTED]")
            
        logger.info(f"Text revised based on principle: {principle.name}")
        return revised_text


class ConstitutionalAIController:
    """Orchestrates the Constitutional AI process: critique, evaluation, and revision."""

    def __init__(
        self,
        critic: ConstitutionalCritic,
        revision_engine: RevisionEngine,
        max_revisions: int = 3
    ):
        self.critic = critic
        self.revision_engine = revision_engine
        self.max_revisions = max_revisions
        logger.info(f"ConstitutionalAIController initialized with max_revisions={max_revisions}.")

    async def process(self, text: str, principle_set: PrincipleSet) -> Tuple[str, ConstitutionalAuditLog]:
        """
        Processes text through the constitutional pipeline.
        Iteratively critiques and revises the text until no violations are found
        or the maximum number of revisions is reached.
        """
        import time
        start_time = time.time()
        
        current_text = text
        all_critiques = []
        revision_count = 0
        was_revised = False
        
        while revision_count < self.max_revisions:
            logger.debug(f"Starting critique cycle {revision_count + 1}")
            
            # 1. Critique
            critiques = await self.critic.evaluate_all(current_text, principle_set)
            all_critiques.extend(critiques)
            
            violations = [c for c in critiques if c.violation_found]
            
            if not violations:
                logger.info("No constitutional violations found.")
                break
                
            # 2. Revise (handle the most severe violation first)
            violations.sort(key=lambda x: x.severity_score, reverse=True)
            worst_violation = violations[0]
            
            principle = next(p for p in principle_set.principles if p.id == worst_violation.principle_id)
            
            logger.info(f"Revising text due to violation of: {principle.name}")
            current_text = await self.revision_engine.revise(current_text, principle, worst_violation)
            
            was_revised = True
            revision_count += 1
            
        if revision_count == self.max_revisions and violations:
            logger.warning("Maximum revisions reached, but violations still exist.")
            
        end_time = time.time()
        
        audit_log = ConstitutionalAuditLog(
            original_text=text,
            final_text=current_text,
            was_revised=was_revised,
            critiques=all_critiques,
            revision_cycles=revision_count,
            processing_time_ms=(end_time - start_time) * 1000.0
        )
        
        return current_text, audit_log

# End of constitutional_ai.py
