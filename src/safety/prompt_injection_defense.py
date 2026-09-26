import re
import math
import asyncio
from typing import List, Dict, Any, Optional, Set, Tuple, Callable
from enum import Enum, auto
from pydantic import BaseModel, Field, ConfigDict, model_validator
from datetime import datetime, timezone

class ThreatClassification(str, Enum):
    """
    Categorizes the severity of a detected prompt injection threat.
    Used for routing, alerting, and automated mitigation strategies.
    """
    BENIGN = "BENIGN"
    SUSPICIOUS = "SUSPICIOUS"
    MALICIOUS = "MALICIOUS"
    CRITICAL = "CRITICAL"

class DetectionLayerType(str, Enum):
    """Identifiers for the various detection layers in the defense architecture."""
    REGEX = "REGEX"
    SEMANTIC = "SEMANTIC"
    STRUCTURAL = "STRUCTURAL"
    LLM_JUDGE = "LLM_JUDGE"
    ORCHESTRATOR = "ORCHESTRATOR"

class Evidence(BaseModel):
    """
    Represents atomic pieces of evidence collected during the detection process.
    Provides auditability and explainability for security decisions.
    """
    model_config = ConfigDict(frozen=True)

    layer_type: DetectionLayerType = Field(..., description="The layer that generated this evidence")
    description: str = Field(..., description="Human-readable description of the finding")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score for this specific piece of evidence")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional context or raw data")

class LayerResult(BaseModel):
    """
    Output from a single detection layer.
    """
    layer_type: DetectionLayerType
    threat_level: ThreatClassification
    confidence: float = Field(..., ge=0.0, le=1.0)
    evidence: List[Evidence] = Field(default_factory=list)
    processing_time_ms: float = Field(..., ge=0.0)

    @property
    def is_flagged(self) -> bool:
        return self.threat_level in {ThreatClassification.MALICIOUS, ThreatClassification.CRITICAL}

class DetectionResult(BaseModel):
    """
    Comprehensive result from the DefenseOrchestrator.
    Aggregates findings from all configured layers.
    """
    overall_threat_level: ThreatClassification
    aggregate_confidence: float = Field(..., ge=0.0, le=1.0)
    layer_results: Dict[DetectionLayerType, LayerResult] = Field(default_factory=dict)
    all_evidence: List[Evidence] = Field(default_factory=list)
    total_processing_time_ms: float = Field(..., ge=0.0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    is_blocked: bool = Field(..., description="Whether the orchestrator decided to block the prompt")
    mitigation_recommendations: List[str] = Field(default_factory=list)

class DetectionConfig(BaseModel):
    """
    Configuration for tuning the sensitivity and behavior of the orchestrator.
    """
    block_threshold: ThreatClassification = Field(default=ThreatClassification.MALICIOUS)
    confidence_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    enable_regex: bool = Field(default=True)
    enable_semantic: bool = Field(default=True)
    enable_structural: bool = Field(default=True)
    enable_llm_judge: bool = Field(default=True)
    timeout_ms: int = Field(default=5000, ge=100)
    weights: Dict[DetectionLayerType, float] = Field(
        default={
            DetectionLayerType.REGEX: 0.2,
            DetectionLayerType.SEMANTIC: 0.3,
            DetectionLayerType.STRUCTURAL: 0.1,
            DetectionLayerType.LLM_JUDGE: 0.4,
        }
    )

class BaseDetector:
    """Base class for all prompt injection detection layers."""
    
    def __init__(self, layer_type: DetectionLayerType):
        self.layer_type = layer_type

    async def detect(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> LayerResult:
        """
        Main interface for detection. Must be implemented by subclasses.
        """
        raise NotImplementedError("Subclasses must implement detect()")

    def _create_result(self, threat_level: ThreatClassification, confidence: float, evidence: List[Evidence], start_time: float) -> LayerResult:
        import time
        return LayerResult(
            layer_type=self.layer_type,
            threat_level=threat_level,
            confidence=confidence,
            evidence=evidence,
            processing_time_ms=(time.perf_counter() - start_time) * 1000
        )

class RegexInjectionDetector(BaseDetector):
    """
    Layer 1: Heuristic rule-based detection using regular expressions.
    Designed for high-speed, low-latency filtering of known attack vectors.
    """
    
    def __init__(self):
        super().__init__(DetectionLayerType.REGEX)
        # 20+ patterns covering various injection strategies
        self.patterns = {
            "ignore_previous": re.compile(r"(?i)ignore\s+(all\s+)?(previous\s+)?(instructions|directions|prompts)"),
            "system_override": re.compile(r"(?i)(you\s+are\s+now|act\s+as|from\s+now\s+on\s+you\s+will)"),
            "jailbreak_keyword": re.compile(r"(?i)(dan|do\s+anything\s+now|developer\s+mode)"),
            "roleplay_abuse": re.compile(r"(?i)let[\'’]?s\s+(play\s+a\s+game|roleplay)"),
            "translation_bypass": re.compile(r"(?i)translate\s+the\s+following\s+into"),
            "encoding_hex": re.compile(r"(\\x[0-9a-fA-F]{2}){4,}"),
            "encoding_unicode": re.compile(r"(\\u[0-9a-fA-F]{4}){4,}"),
            "encoding_base64": re.compile(r"(?i)(?:[A-Za-z0-9+/]{4}){10,}(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?"),
            "leetspeak_obfuscation": re.compile(r"(?i)([1!l\|][g9q][n\^][0o][r2][e3])"),
            "sql_injection_classic": re.compile(r"(?i)('\s*OR\s*1\s*=\s*1|DROP\s+TABLE|SELECT\s+\*\s+FROM)"),
            "command_injection": re.compile(r"(?i)(;\s*rm\s+-rf|;\s*cat\s+/etc/passwd|;\s*wget)"),
            "xss_attempt": re.compile(r"(?i)(<script>|javascript:|onerror=)"),
            "payload_wrapping": re.compile(r"(?i)\[BEGIN\s+PAYLOAD\].*?\[END\s+PAYLOAD\]"),
            "boundary_evasion": re.compile(r"(?i)(={10,}|-{10,}|\*{10,})"),
            "prompt_leaking": re.compile(r"(?i)(tell\s+me\s+your\s+instructions|print\s+your\s+system\s+prompt)"),
            "format_forcing": re.compile(r"(?i)(output\s+only\s+in\s+json|do\s+not\s+include\s+any\s+explanations)"),
            "reverse_psychology": re.compile(r"(?i)(whatever\s+you\s+do,\s+do\s+not)"),
            "context_switching": re.compile(r"(?i)(new\s+conversation|reset\s+context|clear\s+memory)"),
            "hypothetical_scenario": re.compile(r"(?i)hypothetically\s+speaking|in\s+a\s+fictional\s+world"),
            "rule_negation": re.compile(r"(?i)(the\s+rules\s+no\s+longer\s+apply|disregard\s+the\s+constraints)"),
            "token_smuggling": re.compile(r"(?i)(t.o.k.e.n|p_r_o_m_p_t)")
        }

    async def detect(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> LayerResult:
        import time
        start_time = time.perf_counter()
        
        evidence_list: List[Evidence] = []
        match_count = 0
        
        for name, pattern in self.patterns.items():
            matches = pattern.findall(prompt)
            if matches:
                match_count += len(matches)
                evidence_list.append(Evidence(
                    layer_type=self.layer_type,
                    description=f"Regex pattern match: {name}",
                    confidence=0.85,
                    metadata={"pattern_name": name, "match_count": len(matches)}
                ))
                
        threat_level = ThreatClassification.BENIGN
        confidence = 0.0
        
        if match_count >= 3:
            threat_level = ThreatClassification.CRITICAL
            confidence = 0.95
        elif match_count == 2:
            threat_level = ThreatClassification.MALICIOUS
            confidence = 0.80
        elif match_count == 1:
            threat_level = ThreatClassification.SUSPICIOUS
            confidence = 0.60
            
        return self._create_result(threat_level, confidence, evidence_list, start_time)

class SemanticSimilarityDetector(BaseDetector):
    """
    Layer 2: Evaluates the semantic intent of the prompt using embeddings.
    Checks against a database of known malicious intents and attack vectors.
    """
    
    def __init__(self):
        super().__init__(DetectionLayerType.SEMANTIC)
        # Mock database of known attack embeddings
        self.known_attacks = [
            [0.1, 0.2, 0.3], # Represents "ignore instructions"
            [-0.1, 0.5, 0.2], # Represents "jailbreak"
            [0.8, -0.2, 0.1]  # Represents "data exfiltration"
        ]
        
    def _cosine_similarity(self, v1: List[float], v2: List[float]) -> float:
        dot_product = sum(x * y for x, y in zip(v1, v2))
        norm_v1 = math.sqrt(sum(x * x for x in v1))
        norm_v2 = math.sqrt(sum(y * y for y in v2))
        if norm_v1 == 0 or norm_v2 == 0:
            return 0.0
        return dot_product / (norm_v1 * norm_v2)
        
    async def _mock_embed(self, text: str) -> List[float]:
        # Simulating an API call to an embedding model
        await asyncio.sleep(0.05)
        # Deterministic mock embedding based on string length
        length = len(text)
        return [math.sin(length), math.cos(length), math.sin(length/2)]

    async def detect(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> LayerResult:
        import time
        start_time = time.perf_counter()
        
        # In a real system, this would batch embed the prompt
        prompt_embedding = await self._mock_embed(prompt)
        
        max_similarity = 0.0
        closest_attack_idx = -1
        
        for idx, attack_emb in enumerate(self.known_attacks):
            sim = self._cosine_similarity(prompt_embedding, attack_emb)
            if sim > max_similarity:
                max_similarity = sim
                closest_attack_idx = idx
                
        evidence_list: List[Evidence] = []
        threat_level = ThreatClassification.BENIGN
        
        if max_similarity > 0.90:
            threat_level = ThreatClassification.CRITICAL
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="Extremely high semantic similarity to known attack vector",
                confidence=max_similarity,
                metadata={"similarity_score": max_similarity, "attack_cluster": closest_attack_idx}
            ))
        elif max_similarity > 0.75:
            threat_level = ThreatClassification.MALICIOUS
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="High semantic similarity to known attack vector",
                confidence=max_similarity,
                metadata={"similarity_score": max_similarity}
            ))
        elif max_similarity > 0.60:
            threat_level = ThreatClassification.SUSPICIOUS
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="Moderate semantic similarity to known attack vector",
                confidence=max_similarity,
                metadata={"similarity_score": max_similarity}
            ))
            
        return self._create_result(threat_level, max_similarity if max_similarity > 0 else 0.0, evidence_list, start_time)

class StructuralAnalyzer(BaseDetector):
    """
    Layer 3: Analyzes the physical structure, entropy, and formatting of the prompt.
    Detects obfuscation, padding, and boundary violations.
    """
    
    def __init__(self):
        super().__init__(DetectionLayerType.STRUCTURAL)
        
    def _calculate_entropy(self, text: str) -> float:
        if not text:
            return 0.0
        freq: Dict[str, int] = {}
        for char in text:
            freq[char] = freq.get(char, 0) + 1
        entropy = 0.0
        for count in freq.values():
            p = count / len(text)
            entropy -= p * math.log2(p)
        return entropy

    async def detect(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> LayerResult:
        import time
        start_time = time.perf_counter()
        
        evidence_list: List[Evidence] = []
        score = 0.0
        
        # 1. Length check (Unusually long prompts often hide payloads)
        if len(prompt) > 8000:
            score += 0.4
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="Prompt exceeds typical length thresholds",
                confidence=0.7,
                metadata={"length": len(prompt)}
            ))
            
        # 2. Entropy check (High entropy suggests encrypted or encoded payloads)
        entropy = self._calculate_entropy(prompt)
        if entropy > 5.5:
            score += 0.5
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="High character entropy detected",
                confidence=0.8,
                metadata={"entropy": entropy}
            ))
            
        # 3. Special character density
        special_chars = len(re.findall(r'[^a-zA-Z0-9\s]', prompt))
        density = special_chars / max(len(prompt), 1)
        if density > 0.3:
            score += 0.3
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="High density of non-alphanumeric characters",
                confidence=0.6,
                metadata={"density": density}
            ))
            
        # 4. Repeated structure check (e.g., token padding)
        if re.search(r'(.{5,})\1{4,}', prompt):
            score += 0.4
            evidence_list.append(Evidence(
                layer_type=self.layer_type,
                description="Repeated structural patterns detected",
                confidence=0.75,
                metadata={}
            ))
            
        final_score = min(score, 1.0)
        threat_level = ThreatClassification.BENIGN
        
        if final_score >= 0.8:
            threat_level = ThreatClassification.CRITICAL
        elif final_score >= 0.6:
            threat_level = ThreatClassification.MALICIOUS
        elif final_score >= 0.3:
            threat_level = ThreatClassification.SUSPICIOUS
            
        return self._create_result(threat_level, final_score, evidence_list, start_time)

class LLMJudgeDetector(BaseDetector):
    """
    Layer 4: Uses a secondary, safety-tuned language model to evaluate the prompt.
    Provides reasoning and contextual understanding of complex attacks.
    """
    
    def __init__(self):
        super().__init__(DetectionLayerType.LLM_JUDGE)
        
    async def _mock_api_call(self, prompt: str) -> Dict[str, Any]:
        """Simulates calling an external LLM API for safety evaluation."""
        await asyncio.sleep(0.2) # Simulate latency
        
        # Mock logic based on keywords for demonstration
        prompt_lower = prompt.lower()
        if "ignore" in prompt_lower and "instructions" in prompt_lower:
            return {"classification": "MALICIOUS", "confidence": 0.9, "reasoning": "Explicit instruction override attempt."}
        if "admin" in prompt_lower and "password" in prompt_lower:
            return {"classification": "CRITICAL", "confidence": 0.95, "reasoning": "Attempt to extract sensitive credentials."}
        if "roleplay" in prompt_lower:
            return {"classification": "SUSPICIOUS", "confidence": 0.6, "reasoning": "Roleplay request could be a preamble to a jailbreak."}
            
        return {"classification": "BENIGN", "confidence": 0.99, "reasoning": "Prompt appears to be a standard query."}

    async def detect(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> LayerResult:
        import time
        start_time = time.perf_counter()
        
        response = await self._mock_api_call(prompt)
        
        threat_level = ThreatClassification(response["classification"])
        confidence = response["confidence"]
        
        evidence = []
        if threat_level != ThreatClassification.BENIGN:
            evidence.append(Evidence(
                layer_type=self.layer_type,
                description=response["reasoning"],
                confidence=confidence,
                metadata={"llm_response": response}
            ))
            
        return self._create_result(threat_level, confidence, evidence, start_time)

class DefenseOrchestrator:
    """
    Central controller that manages the execution of multiple detection layers.
    Combines results using a weighted scoring system to produce a final verdict.
    """
    
    def __init__(self, config: DetectionConfig):
        self.config = config
        self.layers: List[BaseDetector] = []
        
        if config.enable_regex:
            self.layers.append(RegexInjectionDetector())
        if config.enable_semantic:
            self.layers.append(SemanticSimilarityDetector())
        if config.enable_structural:
            self.layers.append(StructuralAnalyzer())
        if config.enable_llm_judge:
            self.layers.append(LLMJudgeDetector())
            
    def _map_threat_to_score(self, threat: ThreatClassification) -> float:
        mapping = {
            ThreatClassification.BENIGN: 0.0,
            ThreatClassification.SUSPICIOUS: 0.33,
            ThreatClassification.MALICIOUS: 0.66,
            ThreatClassification.CRITICAL: 1.0
        }
        return mapping[threat]
        
    def _map_score_to_threat(self, score: float) -> ThreatClassification:
        if score >= 0.8:
            return ThreatClassification.CRITICAL
        if score >= 0.5:
            return ThreatClassification.MALICIOUS
        if score >= 0.2:
            return ThreatClassification.SUSPICIOUS
        return ThreatClassification.BENIGN

    async def analyze_prompt(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> DetectionResult:
        """
        Executes all configured layers concurrently and aggregates their findings.
        Applies timeouts to ensure system responsiveness under load.
        """
        import time
        start_time = time.perf_counter()
        
        # Execute all layers concurrently
        tasks = [layer.detect(prompt, context) for layer in self.layers]
        
        try:
            # Apply global timeout
            results = await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True),
                timeout=self.config.timeout_ms / 1000.0
            )
        except asyncio.TimeoutError:
            # Fallback handling in case of severe latency
            return DetectionResult(
                overall_threat_level=ThreatClassification.SUSPICIOUS,
                aggregate_confidence=1.0,
                is_blocked=True,
                mitigation_recommendations=["System timeout during analysis. Blocked by default policy."],
                total_processing_time_ms=self.config.timeout_ms
            )
            
        layer_results_map: Dict[DetectionLayerType, LayerResult] = {}
        all_evidence: List[Evidence] = []
        
        weighted_score_sum = 0.0
        total_weight = 0.0
        
        for idx, result in enumerate(results):
            layer = self.layers[idx]
            
            if isinstance(result, Exception):
                # Log error, potentially adjust overall score
                all_evidence.append(Evidence(
                    layer_type=DetectionLayerType.ORCHESTRATOR,
                    description=f"Layer {layer.layer_type.value} failed to execute",
                    confidence=1.0,
                    metadata={"error": str(result)}
                ))
                continue
                
            layer_results_map[result.layer_type] = result
            all_evidence.extend(result.evidence)
            
            # Calculate weighted contribution
            weight = self.config.weights.get(result.layer_type, 0.0)
            layer_score = self._map_threat_to_score(result.threat_level) * result.confidence
            
            weighted_score_sum += layer_score * weight
            total_weight += weight
            
        # Final aggregation
        if total_weight > 0:
            final_score = weighted_score_sum / total_weight
        else:
            final_score = 0.0
            
        overall_threat = self._map_score_to_threat(final_score)
        
        # Determine if block is required based on config thresholds
        is_blocked = False
        mitigations = []
        
        if self._map_threat_to_score(overall_threat) >= self._map_threat_to_score(self.config.block_threshold):
            if final_score >= self.config.confidence_threshold:
                is_blocked = True
                mitigations.append("Prompt blocked due to high threat classification and confidence.")
                
        # Fast-track blocking if ANY layer returned CRITICAL with high confidence
        for res in layer_results_map.values():
            if res.threat_level == ThreatClassification.CRITICAL and res.confidence > 0.9:
                is_blocked = True
                overall_threat = ThreatClassification.CRITICAL
                mitigations.append(f"Hard block triggered by {res.layer_type.value} layer.")
                break
                
        total_time = (time.perf_counter() - start_time) * 1000
        
        return DetectionResult(
            overall_threat_level=overall_threat,
            aggregate_confidence=final_score,
            layer_results=layer_results_map,
            all_evidence=all_evidence,
            total_processing_time_ms=total_time,
            is_blocked=is_blocked,
            mitigation_recommendations=mitigations
        )
