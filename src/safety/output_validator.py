"""
Output Validator Module for AI Governance & Safety Platform.

This module provides schema-enforced output validation, factual consistency checks
(hallucination detection), citation verification, and fallback strategies for AI
model outputs. It leverages Pydantic v2 for structured data validation and async
operations for efficient processing of large outputs or external API calls.
"""

import asyncio
import json
import logging
import re
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union

from pydantic import BaseModel, Field, ValidationError, field_validator

# Configure logging
logger = logging.getLogger(__name__)


class FallbackAction(str, Enum):
    """Actions to take when validation fails."""

    RETRY = "retry"
    DEGRADE = "degrade"
    REJECT = "reject"


class FallbackStrategy(BaseModel):
    """Defines the strategy to handle validation failures."""

    action: FallbackAction = Field(
        ..., description="The action to take upon validation failure."
    )
    max_retries: int = Field(
        default=3, ge=0, description="Maximum number of retries if action is RETRY."
    )
    degrade_message: Optional[str] = Field(
        default=None, description="Message to return if action is DEGRADE."
    )
    timeout_seconds: float = Field(
        default=10.0, ge=0.1, description="Timeout for retry operations."
    )


class OutputSchema(BaseModel):
    """Schema definition for structured output validation."""

    schema_name: str = Field(..., description="Name of the schema.")
    schema_version: str = Field(..., description="Version of the schema.")
    json_schema: Dict[str, Any] = Field(
        ..., description="JSON Schema definition for the expected output."
    )
    required_fields: List[str] = Field(
        default_factory=list, description="List of required fields in the output."
    )

    @field_validator("json_schema")
    def validate_json_schema(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validates that the provided dictionary is a valid JSON schema."""
        if "type" not in v or v["type"] != "object":
            raise ValueError("JSON schema must define an object type at the root.")
        return v


class ValidationReport(BaseModel):
    """Report detailing the results of the validation process."""

    is_valid: bool = Field(..., description="True if the output passed all validations.")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="Time of validation."
    )
    schema_errors: List[str] = Field(
        default_factory=list, description="Errors related to schema validation."
    )
    hallucination_score: float = Field(
        default=0.0, ge=0.0, le=1.0, description="Score indicating likelihood of hallucination (0=none, 1=high)."
    )
    unverified_citations: List[str] = Field(
        default_factory=list, description="List of citations that could not be verified."
    )
    applied_fallback: Optional[FallbackAction] = Field(
        default=None, description="The fallback action applied, if any."
    )
    final_output: Any = Field(..., description="The final processed output.")


class StructuredOutputValidator:
    """Validates AI outputs against predefined JSON schemas."""

    def __init__(self, schemas: Dict[str, OutputSchema]):
        self.schemas = schemas
        logger.info(f"Initialized StructuredOutputValidator with {len(schemas)} schemas.")

    async def validate(self, output: Union[str, Dict[str, Any]], schema_name: str) -> Tuple[bool, List[str], Any]:
        """
        Validates the output against the specified schema.
        
        Args:
            output: The AI output to validate (JSON string or dict).
            schema_name: The name of the schema to validate against.
            
        Returns:
            Tuple containing (is_valid, list_of_errors, parsed_output).
        """
        if schema_name not in self.schemas:
            return False, [f"Schema '{schema_name}' not found."], None

        schema = self.schemas[schema_name]
        
        # Parse if string
        parsed_output = output
        if isinstance(output, str):
            try:
                parsed_output = json.loads(output)
            except json.JSONDecodeError as e:
                return False, [f"Failed to parse JSON: {str(e)}"], None

        errors = []
        # Basic validation against required fields
        if isinstance(parsed_output, dict):
            for field in schema.required_fields:
                if field not in parsed_output:
                    errors.append(f"Missing required field: {field}")
                    
            # Basic type checking based on json_schema
            properties = schema.json_schema.get("properties", {})
            for key, value in parsed_output.items():
                if key in properties:
                    expected_type = properties[key].get("type")
                    if expected_type == "string" and not isinstance(value, str):
                        errors.append(f"Field '{key}' should be a string.")
                    elif expected_type == "number" and not isinstance(value, (int, float)):
                        errors.append(f"Field '{key}' should be a number.")
                    elif expected_type == "boolean" and not isinstance(value, bool):
                        errors.append(f"Field '{key}' should be a boolean.")
                    elif expected_type == "array" and not isinstance(value, list):
                        errors.append(f"Field '{key}' should be an array.")
                    elif expected_type == "object" and not isinstance(value, dict):
                        errors.append(f"Field '{key}' should be an object.")
        else:
            errors.append("Output must be a JSON object.")

        is_valid = len(errors) == 0
        return is_valid, errors, parsed_output


class HallucinationDetector:
    """Detects factual inconsistencies and hallucinations in AI outputs."""

    def __init__(self, sensitivity_threshold: float = 0.7):
        self.sensitivity_threshold = sensitivity_threshold
        logger.info(f"Initialized HallucinationDetector with threshold {sensitivity_threshold}.")

    async def analyze_consistency(self, text: str, context_documents: List[str]) -> Tuple[float, List[str]]:
        """
        Analyzes the text for factual consistency against provided context.
        
        Args:
            text: The AI generated text.
            context_documents: List of source documents for grounding.
            
        Returns:
            Tuple of (hallucination_score, list_of_flagged_statements).
        """
        # Simulated async analysis
        await asyncio.sleep(0.1)
        
        if not context_documents:
            # High risk if no context is provided for factual claims
            return 0.8, ["No context provided for grounding factual claims."]
            
        score = 0.0
        flagged = []
        
        # Simulated heuristic: Check for absolute statements that might be ungrounded
        absolute_words = ["always", "never", "everyone", "nobody", "proven", "impossible"]
        words = text.lower().split()
        for word in words:
            if word in absolute_words:
                score += 0.1
                flagged.append(f"Potentially ungrounded absolute term detected: '{word}'")
                
        # Normalize score
        score = min(1.0, score)
        return score, flagged


class CitationVerifier:
    """Verifies citations and references within AI generated content."""

    def __init__(self, strict_mode: bool = True):
        self.strict_mode = strict_mode
        # Regex to find citations like [1], (Author, 2023), etc.
        self.citation_pattern = re.compile(r'\[\d+\]|\([A-Za-z]+, \d{4}\)')

    async def verify_citations(self, text: str, reference_list: List[str]) -> List[str]:
        """
        Extracts citations from text and verifies them against the reference list.
        
        Args:
            text: The generated text containing citations.
            reference_list: Valid references to check against.
            
        Returns:
            List of unverified or invalid citations found in the text.
        """
        await asyncio.sleep(0.05)
        unverified = []
        
        found_citations = self.citation_pattern.findall(text)
        
        # Simple simulated verification logic
        for citation in found_citations:
            # Check if citation exists in reference list in some form
            is_valid = False
            for ref in reference_list:
                # Strip brackets/parentheses for loose matching
                clean_cit = re.sub(r'[\[\]\(\)]', '', citation)
                if clean_cit.lower() in ref.lower():
                    is_valid = True
                    break
                    
            if not is_valid:
                unverified.append(citation)
                
        return unverified


class OutputValidatorService:
    """Orchestrates the entire output validation pipeline."""

    def __init__(
        self,
        schema_validator: StructuredOutputValidator,
        hallucination_detector: HallucinationDetector,
        citation_verifier: CitationVerifier,
        fallback_strategy: FallbackStrategy
    ):
        self.schema_validator = schema_validator
        self.hallucination_detector = hallucination_detector
        self.citation_verifier = citation_verifier
        self.fallback_strategy = fallback_strategy
        logger.info("OutputValidatorService initialized.")

    async def process_output(
        self,
        raw_output: Union[str, Dict[str, Any]],
        schema_name: str,
        context_docs: List[str] = None,
        references: List[str] = None
    ) -> ValidationReport:
        """
        Runs the full validation pipeline on the AI output.
        """
        context_docs = context_docs or []
        references = references or []
        
        logger.info(f"Starting validation for schema: {schema_name}")
        
        # 1. Schema Validation
        is_schema_valid, schema_errors, parsed_output = await self.schema_validator.validate(
            raw_output, schema_name
        )
        
        # 2. Hallucination Detection
        text_to_analyze = str(parsed_output) if parsed_output else str(raw_output)
        hal_score, hal_flags = await self.hallucination_detector.analyze_consistency(
            text_to_analyze, context_docs
        )
        
        # 3. Citation Verification
        unverified_cits = await self.citation_verifier.verify_citations(
            text_to_analyze, references
        )
        
        # Determine overall validity
        is_valid = (
            is_schema_valid and
            hal_score < self.hallucination_detector.sensitivity_threshold and
            len(unverified_cits) == 0
        )
        
        applied_fallback = None
        final_output = parsed_output if parsed_output else raw_output
        
        # Handle failures using fallback strategy
        if not is_valid:
            logger.warning("Validation failed. Applying fallback strategy.")
            applied_fallback = self.fallback_strategy.action
            
            if self.fallback_strategy.action == FallbackAction.REJECT:
                final_output = None
            elif self.fallback_strategy.action == FallbackAction.DEGRADE:
                final_output = {"error": self.fallback_strategy.degrade_message or "Output degraded due to validation failure."}
            elif self.fallback_strategy.action == FallbackAction.RETRY:
                # In a real system, this would trigger a re-generation upstream.
                # Here we mark it as retry requested.
                logger.info(f"Retry requested. Max retries: {self.fallback_strategy.max_retries}")
                
        report = ValidationReport(
            is_valid=is_valid,
            schema_errors=schema_errors + hal_flags,
            hallucination_score=hal_score,
            unverified_citations=unverified_cits,
            applied_fallback=applied_fallback,
            final_output=final_output
        )
        
        logger.info(f"Validation complete. Valid: {is_valid}")
        return report

# End of output_validator.py
