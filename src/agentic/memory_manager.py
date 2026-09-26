import time
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

class MemoryItem(BaseModel):
    """Base class for memory entries."""
    id: str
    content: Any
    timestamp: float = Field(default_factory=time.time)
    importance: float = 1.0
    access_count: int = 0

class WorkingMemory:
    """Short-term memory with capacity limits."""
    def __init__(self, capacity: int = 100):
        self.capacity = capacity
        self.items: Dict[str, MemoryItem] = {}

    def add(self, item: MemoryItem):
        if len(self.items) >= self.capacity:
            self._evict()
        self.items[item.id] = item

    def get(self, item_id: str) -> Optional[MemoryItem]:
        item = self.items.get(item_id)
        if item:
            item.access_count += 1
            item.timestamp = time.time()  # update access time
        return item
        
    def _evict(self):
        """Evicts the least important/recently used item."""
        if not self.items:
            return
        # Evict item with lowest (importance * access_count) as a heuristic
        worst_item_id = min(self.items.keys(), key=lambda k: self.items[k].importance * (self.items[k].access_count + 1))
        del self.items[worst_item_id]

class EpisodicMemory:
    """Memory of conversation and interaction history."""
    def __init__(self):
        self.episodes: List[MemoryItem] = []

    def record_episode(self, episode: MemoryItem):
        self.episodes.append(episode)

    def retrieve_recent(self, limit: int = 10) -> List[MemoryItem]:
        return self.episodes[-limit:]

class SemanticMemory:
    """Long-term knowledge storage."""
    def __init__(self):
        self.knowledge_base: Dict[str, MemoryItem] = {}

    def store_fact(self, key: str, fact: MemoryItem):
        self.knowledge_base[key] = fact

    def query(self, key: str) -> Optional[MemoryItem]:
        return self.knowledge_base.get(key)

class MemoryRetriever:
    """Retrieves relevant memories based on a query."""
    def __init__(self, semantic: SemanticMemory, episodic: EpisodicMemory):
        self.semantic = semantic
        self.episodic = episodic

    def retrieve(self, query: str, top_k: int = 5) -> List[MemoryItem]:
        """Scores and retrieves relevant memories."""
        # Simulated retrieval logic, e.g., using vector embeddings
        results = []
        for item in self.semantic.knowledge_base.values():
            if query in str(item.content):
                results.append(item)
        return sorted(results, key=lambda x: x.importance, reverse=True)[:top_k]

class MemoryConsolidator:
    """Optimizes short-term memories into long-term storage."""
    def __init__(self, working: WorkingMemory, semantic: SemanticMemory):
        self.working = working
        self.semantic = semantic

    def consolidate(self):
        """Moves important items from working to semantic memory."""
        for item_id, item in list(self.working.items.items()):
            if item.importance > 0.8 and item.access_count > 5:
                self.semantic.store_fact(item_id, item)
                del self.working.items[item_id]

class MemoryDecayPolicy:
    """Automatically cleans up old or unimportant memories."""
    def __init__(self, threshold_days: int = 30):
        self.threshold_seconds = threshold_days * 86400

    def apply_decay(self, memory_store: List[MemoryItem]):
        """Reduces importance of older memories and removes obsolete ones."""
        current_time = time.time()
        for item in memory_store[:]:
            age = current_time - item.timestamp
            if age > self.threshold_seconds and item.importance < 0.5:
                memory_store.remove(item)
            else:
                # Decay importance linearly over time
                decay_factor = max(0.1, 1.0 - (age / self.threshold_seconds))
                item.importance *= decay_factor

class ContextWindowManager:
    """Optimizes token usage for LLM prompts."""
    def __init__(self, max_tokens: int = 4096):
        self.max_tokens = max_tokens

    def build_context(self, current_prompt: str, memories: List[MemoryItem]) -> str:
        """Selects memories that fit within the context window."""
        # Simplified token counting heuristic (1 token ~ 4 chars)
        current_tokens = len(current_prompt) // 4
        context_parts = [current_prompt]
        
        for mem in sorted(memories, key=lambda x: x.importance, reverse=True):
            mem_str = str(mem.content)
            mem_tokens = len(mem_str) // 4
            if current_tokens + mem_tokens < self.max_tokens:
                context_parts.append(mem_str)
                current_tokens += mem_tokens
            else:
                break
                
        return "\n".join(context_parts)
