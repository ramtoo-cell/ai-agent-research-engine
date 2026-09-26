import asyncio
import heapq
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class TaskPriority(Enum):
    CRITICAL = 100
    HIGH = 75
    NORMAL = 50
    LOW = 25


class AgentCapability(BaseModel):
    """Capabilities and capacity for a single agent."""
    agent_id: str
    skill_scores: Dict[str, float] = Field(default_factory=dict, description="Map of skill to proficiency (0.0 to 1.0)")
    max_capacity: int = 1
    current_load: int = 0
    is_active: bool = True
    
    @property
    def available_capacity(self) -> int:
        return max(0, self.max_capacity - self.current_load)


class TaskDefinition(BaseModel):
    """Defines a piece of work to be routed to an agent."""
    id: UUID = Field(default_factory=uuid4)
    name: str
    priority: TaskPriority = TaskPriority.NORMAL
    required_skills: Dict[str, float] = Field(default_factory=dict, description="Skill name and minimum required score")
    deadline: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    
    def __lt__(self, other: "TaskDefinition") -> bool:
        # For priority queue: lower value means higher priority.
        # We invert priority enum value so CRITICAL(100) < NORMAL(50) for queue popping.
        if self.priority.value != other.priority.value:
            return self.priority.value > other.priority.value
        # Break ties with creation time (older is higher priority)
        return self.created_at < other.created_at


class RoutingDecision(BaseModel):
    """The result of the routing process."""
    task_id: UUID
    assigned_agent_id: Optional[str]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    justification: str
    is_successful: bool


class LoadBalancerStrategy(Enum):
    ROUND_ROBIN = "ROUND_ROBIN"
    LEAST_LOADED = "LEAST_LOADED"
    CAPABILITY_WEIGHTED = "CAPABILITY_WEIGHTED"


class TaskQueue:
    """A priority queue for tasks ensuring fairness and priority ordering."""
    
    def __init__(self) -> None:
        self._queue: List[TaskDefinition] = []
        self._lock = asyncio.Lock()

    async def push(self, task: TaskDefinition) -> None:
        async with self._lock:
            heapq.heappush(self._queue, task)

    async def pop(self) -> Optional[TaskDefinition]:
        async with self._lock:
            if not self._queue:
                return None
            return heapq.heappop(self._queue)
            
    async def size(self) -> int:
        async with self._lock:
            return len(self._queue)


class LoadBalancer:
    """Strategy implementation for selecting among capable agents."""
    
    def __init__(self, strategy: LoadBalancerStrategy = LoadBalancerStrategy.LEAST_LOADED):
        self.strategy = strategy
        self._round_robin_index = 0

    def select_agent(self, task: TaskDefinition, capable_agents: List[AgentCapability]) -> Optional[AgentCapability]:
        """Selects the best agent based on the configured strategy."""
        if not capable_agents:
            return None
            
        available_agents = [a for a in capable_agents if a.available_capacity > 0]
        if not available_agents:
            return None
            
        if self.strategy == LoadBalancerStrategy.LEAST_LOADED:
            # Sort by current load, then randomly or by ID for deterministic tie-breaking
            return min(available_agents, key=lambda a: (a.current_load, a.agent_id))
            
        elif self.strategy == LoadBalancerStrategy.ROUND_ROBIN:
            agent = available_agents[self._round_robin_index % len(available_agents)]
            self._round_robin_index += 1
            return agent
            
        elif self.strategy == LoadBalancerStrategy.CAPABILITY_WEIGHTED:
            # Score each agent based on how well they exceed the minimum required skills
            best_agent = None
            best_score = -1.0
            
            for agent in available_agents:
                score = 0.0
                for skill, min_val in task.required_skills.items():
                    agent_val = agent.skill_scores.get(skill, 0.0)
                    score += (agent_val - min_val)  # Surplus capability
                
                if score > best_score:
                    best_score = score
                    best_agent = agent
                    
            return best_agent or available_agents[0]
            
        return None


class TaskRouter:
    """Matches incoming tasks to the best fit agents dynamically."""
    
    def __init__(self) -> None:
        self.agents: Dict[str, AgentCapability] = {}
        self.queue = TaskQueue()
        self.balancer = LoadBalancer(LoadBalancerStrategy.LEAST_LOADED)
        self.routing_history: List[RoutingDecision] = []
        self._lock = asyncio.Lock()

    async def register_agent(self, agent: AgentCapability) -> None:
        """Registers a new agent or updates an existing one."""
        async with self._lock:
            self.agents[agent.agent_id] = agent

    async def submit_task(self, task: TaskDefinition) -> None:
        """Submits a task to be routed."""
        await self.queue.push(task)

    def _get_capable_agents(self, task: TaskDefinition) -> List[AgentCapability]:
        """Filters agents that meet the minimum skill requirements."""
        capable = []
        for agent in self.agents.values():
            if not agent.is_active:
                continue
                
            meets_requirements = True
            for skill, min_score in task.required_skills.items():
                if agent.skill_scores.get(skill, 0.0) < min_score:
                    meets_requirements = False
                    break
            
            if meets_requirements:
                capable.append(agent)
                
        return capable

    async def route_next_task(self) -> Optional[RoutingDecision]:
        """Pops the highest priority task and routes it to an agent."""
        task = await self.queue.pop()
        if not task:
            return None
            
        async with self._lock:
            capable_agents = self._get_capable_agents(task)
            
            if not capable_agents:
                decision = RoutingDecision(
                    task_id=task.id,
                    assigned_agent_id=None,
                    justification="No agents meet the required skills.",
                    is_successful=False
                )
                self.routing_history.append(decision)
                return decision
                
            assigned_agent = self.balancer.select_agent(task, capable_agents)
            
            if not assigned_agent:
                decision = RoutingDecision(
                    task_id=task.id,
                    assigned_agent_id=None,
                    justification="Capable agents found, but none have available capacity.",
                    is_successful=False
                )
                # Re-queue task or send to dead-letter queue depending on policy
                await self.queue.push(task)
                self.routing_history.append(decision)
                return decision
                
            # Update agent capacity
            assigned_agent.current_load += 1
            
            decision = RoutingDecision(
                task_id=task.id,
                assigned_agent_id=assigned_agent.agent_id,
                justification=f"Assigned via {self.balancer.strategy.name} strategy.",
                is_successful=True
            )
            self.routing_history.append(decision)
            return decision

    async def complete_task(self, agent_id: str, task_id: UUID) -> None:
        """Called when an agent finishes a task to free up capacity."""
        async with self._lock:
            if agent_id in self.agents:
                agent = self.agents[agent_id]
                agent.current_load = max(0, agent.current_load - 1)

# EOF
