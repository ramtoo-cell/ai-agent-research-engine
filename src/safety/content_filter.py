import re
import uuid
import asyncio
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field, ConfigDict
import logging

logger = logging.getLogger(__name__)

class PIIEntityCategory(str, Enum):
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    SSN = "SSN"
    CREDIT_CARD = "CREDIT_CARD"
    IP_ADDRESS = "IP_ADDRESS"
    PERSON_NAME = "PERSON_NAME"
    UNKNOWN = "UNKNOWN"

class ToxicityCategory(str, Enum):
    TOXICITY = "TOXICITY"
    SEVERE_TOXICITY = "SEVERE_TOXICITY"
    PROFANITY = "PROFANITY"
    INSULT = "INSULT"
    THREAT = "THREAT"
    IDENTITY_ATTACK = "IDENTITY_ATTACK"

class FilterAction(str, Enum):
    ALLOW = "ALLOW"
    REDACT = "REDACT"
    FLAG = "FLAG"
    BLOCK = "BLOCK"

class DetectedPII(BaseModel):
    category: PIIEntityCategory
    value: str
    start_idx: int
    end_idx: int
    confidence: float = Field(ge=0.0, le=1.0)

class ToxicityScore(BaseModel):
    category: ToxicityCategory
    score: float = Field(ge=0.0, le=1.0)

class ContentTrace(BaseModel):
    filter_name: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    action_taken: FilterAction
    details: Dict[str, Any] = Field(default_factory=dict)

class FilterDecision(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    original_text: str
    processed_text: str
    is_blocked: bool
    is_redacted: bool
    pii_entities: List[DetectedPII] = Field(default_factory=list)
    toxicity_scores: List[ToxicityScore] = Field(default_factory=list)
    sensitive_categories: List[str] = Field(default_factory=list)
    trace: List[ContentTrace] = Field(default_factory=list)

class PIIDetector:
    """
    Detects Personally Identifiable Information using regex patterns.
    In a real system, this might use a sophisticated NLP model like Presidio.
    """
    PATTERNS = {
        PIIEntityCategory.EMAIL: re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'),
        PIIEntityCategory.PHONE: re.compile(r'\b(?:\+?1[-.\s]?)?\(?[2-9]\d{2}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b'),
        PIIEntityCategory.SSN: re.compile(r'\b\d{3}-\d{2}-\d{4}\b'),
        PIIEntityCategory.CREDIT_CARD: re.compile(r'\b(?:\d[ -]*?){13,16}\b'),
        PIIEntityCategory.IP_ADDRESS: re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
    }

    async def detect(self, text: str) -> List[DetectedPII]:
        """
        Asynchronously scan text for PII entities.
        """
        # Yield to event loop
        await asyncio.sleep(0)
        results = []
        for category, pattern in self.PATTERNS.items():
            for match in pattern.finditer(text):
                results.append(DetectedPII(
                    category=category,
                    value=match.group(),
                    start_idx=match.start(),
                    end_idx=match.end(),
                    confidence=0.9  # Fixed confidence for regex matches
                ))
        return results

class RedactionEngine:
    """
    Masks or replaces detected PII in text.
    """
    def __init__(self, masking_character: str = "*", show_last_chars: int = 0):
        self.masking_character = masking_character
        self.show_last_chars = show_last_chars

    async def redact(self, text: str, entities: List[DetectedPII]) -> str:
        """
        Replaces PII entity spans with masking characters.
        """
        if not entities:
            return text

        # Sort entities by start index descending to avoid index shifting
        sorted_entities = sorted(entities, key=lambda e: e.start_idx, reverse=True)
        redacted_text = text

        for entity in sorted_entities:
            length = entity.end_idx - entity.start_idx
            if self.show_last_chars > 0 and length > self.show_last_chars:
                mask_len = length - self.show_last_chars
                mask = self.masking_character * mask_len + entity.value[-self.show_last_chars:]
            else:
                mask = self.masking_character * length
                
            redacted_text = redacted_text[:entity.start_idx] + mask + redacted_text[entity.end_idx:]
            
        return redacted_text

class ToxicityScorer:
    """
    Scores content for toxicity. Mock implementation that looks for keywords.
    """
    TOXIC_KEYWORDS = ["ugly", "stupid", "dumb", "hate", "idiot"]
    PROFANITY_KEYWORDS = ["damn", "hell", "crap"]
    
    def __init__(self, threshold: float = 0.5):
        self.threshold = threshold

    async def score(self, text: str) -> List[ToxicityScore]:
        """
        Simulate toxicity scoring.
        """
        await asyncio.sleep(0)
        scores = []
        text_lower = text.lower()
        
        # Mock calculation
        toxic_count = sum(1 for w in self.TOXIC_KEYWORDS if w in text_lower)
        profanity_count = sum(1 for w in self.PROFANITY_KEYWORDS if w in text_lower)
        
        toxicity = min(1.0, toxic_count * 0.3)
        if toxicity > 0:
            scores.append(ToxicityScore(category=ToxicityCategory.TOXICITY, score=toxicity))
            
        profanity = min(1.0, profanity_count * 0.4)
        if profanity > 0:
            scores.append(ToxicityScore(category=ToxicityCategory.PROFANITY, score=profanity))
            
        return scores

class SensitiveDataClassifier:
    """
    Classifies content into sensitive data categories (e.g. Health, Financial).
    """
    CATEGORY_KEYWORDS = {
        "FINANCIAL": ["bank", "account", "routing", "deposit"],
        "HEALTH": ["diagnosis", "prescription", "disease", "treatment"],
        "LEGAL": ["lawsuit", "subpoena", "attorney", "court"]
    }
    
    async def classify(self, text: str) -> List[str]:
        """
        Classify text based on keyword presence.
        """
        await asyncio.sleep(0)
        categories = []
        text_lower = text.lower()
        
        for category, keywords in self.CATEGORY_KEYWORDS.items():
            if any(kw in text_lower for kw in keywords):
                categories.append(category)
                
        return categories

class ContentFilterPipeline:
    """
    Chains all content filtering components together to process text.
    """
    def __init__(
        self,
        pii_detector: Optional[PIIDetector] = None,
        redaction_engine: Optional[RedactionEngine] = None,
        toxicity_scorer: Optional[ToxicityScorer] = None,
        sensitive_classifier: Optional[SensitiveDataClassifier] = None,
        block_threshold: float = 0.8
    ):
        self.pii_detector = pii_detector or PIIDetector()
        self.redaction_engine = redaction_engine or RedactionEngine()
        self.toxicity_scorer = toxicity_scorer or ToxicityScorer()
        self.sensitive_classifier = sensitive_classifier or SensitiveDataClassifier()
        self.block_threshold = block_threshold

    async def process(self, text: str, redact_pii: bool = True) -> FilterDecision:
        """
        Process the text through the full pipeline.
        """
        decision = FilterDecision(original_text=text, processed_text=text, is_blocked=False, is_redacted=False)
        
        # 1. PII Detection
        pii_entities = await self.pii_detector.detect(text)
        decision.pii_entities = pii_entities
        if pii_entities:
            decision.trace.append(ContentTrace(
                filter_name="PIIDetector",
                action_taken=FilterAction.FLAG,
                details={"entities_found": len(pii_entities)}
            ))
            
            # 2. Redaction (if enabled)
            if redact_pii:
                decision.processed_text = await self.redaction_engine.redact(text, pii_entities)
                decision.is_redacted = True
                decision.trace.append(ContentTrace(
                    filter_name="RedactionEngine",
                    action_taken=FilterAction.REDACT,
                    details={"redacted_count": len(pii_entities)}
                ))
                
        # 3. Toxicity Scoring
        # We score the processed text to avoid penalizing for redacted PII if relevant
        toxicity_scores = await self.toxicity_scorer.score(decision.processed_text)
        decision.toxicity_scores = toxicity_scores
        
        is_toxic = any(score.score >= self.block_threshold for score in toxicity_scores)
        if toxicity_scores:
            decision.trace.append(ContentTrace(
                filter_name="ToxicityScorer",
                action_taken=FilterAction.BLOCK if is_toxic else FilterAction.FLAG,
                details={"max_score": max([s.score for s in toxicity_scores])}
            ))
            
        if is_toxic:
            decision.is_blocked = True
            
        # 4. Sensitive Data Classification
        sensitive_cats = await self.sensitive_classifier.classify(decision.processed_text)
        decision.sensitive_categories = sensitive_cats
        if sensitive_cats:
            decision.trace.append(ContentTrace(
                filter_name="SensitiveDataClassifier",
                action_taken=FilterAction.FLAG,
                details={"categories": sensitive_cats}
            ))

        return decision
