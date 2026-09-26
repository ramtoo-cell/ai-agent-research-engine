import asyncio
from enum import Enum
from typing import Dict, List, Optional, Any, Callable, Type, Set
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict, create_model


class NodeStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class AgentCapability(BaseModel):
    name: str
    version: str
    description: str


class AgentNode(BaseModel):
    """Represents an executable node in the agent graph."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    capabilities: List[AgentCapability] = Field(default_factory=list)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    output_schema: Dict[str, Any] = Field(default_factory=dict)
    
    # In a real implementation, this would point to the actual agent implementation
    executable_ref: str = ""


class EdgeCondition(BaseModel):
    """Condition that must be met for an edge to be traversed."""
    field_path: str
    operator: str  # e.g., "==", ">", "contains"
    value: Any


class Edge(BaseModel):
    """Directed connection between two agent nodes."""
    source_id: str
    target_id: str
    condition: Optional[EdgeCondition] = None
    priority: int = 0
    transformation_rules: Dict[str, str] = Field(default_factory=dict)
    
    def evaluate(self, state: Dict[str, Any]) -> bool:
        """Evaluates if the condition is met given the current state."""
        if not self.condition:
            return True
        # Simple evaluation logic for demonstration
        val = state.get(self.condition.field_path)
        if self.condition.operator == "==":
            return val == self.condition.value
        elif self.condition.operator == "!=":
            return val != self.condition.value
        elif self.condition.operator == ">":
            return val > self.condition.value
        return False


class ParallelFanOut(AgentNode):
    """Special node that broadcasts state to multiple targets simultaneously."""
    pass


class FanIn(AgentNode):
    """Special node that waits for multiple parallel branches to complete."""
    wait_for_all: bool = True


class ConditionalRouter(AgentNode):
    """Routes execution to specific branches based on state."""
    pass


class GraphExecutionError(Exception):
    pass


class GraphValidator:
    """Validates structural integrity of an AgentGraph."""
    
    @staticmethod
    def detect_cycles(nodes: Dict[str, AgentNode], edges: List[Edge]) -> bool:
        """Returns True if a cycle is detected, False otherwise."""
        adj_list: Dict[str, List[str]] = {n_id: [] for n_id in nodes}
        for e in edges:
            if e.source_id in adj_list:
                adj_list[e.source_id].append(e.target_id)
                
        visited = set()
        rec_stack = set()
        
        def visit(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in adj_list.get(node, []):
                if neighbor not in visited:
                    if visit(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
                    
            rec_stack.remove(node)
            return False
            
        for node_id in nodes:
            if node_id not in visited:
                if visit(node_id):
                    return True
        return False

    @staticmethod
    def check_reachability(nodes: Dict[str, AgentNode], edges: List[Edge], start_nodes: List[str]) -> List[str]:
        """Returns a list of node IDs that are unreachable from the start nodes."""
        adj_list: Dict[str, List[str]] = {n_id: [] for n_id in nodes}
        for e in edges:
            if e.source_id in adj_list:
                adj_list[e.source_id].append(e.target_id)
                
        reachable = set()
        queue = list(start_nodes)
        
        while queue:
            curr = queue.pop(0)
            if curr not in reachable:
                reachable.add(curr)
                queue.extend(adj_list.get(curr, []))
                
        unreachable = [n for n in nodes if n not in reachable]
        return unreachable


class AgentGraph(BaseModel):
    """Directed graph representing an orchestration of agent nodes."""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str
    nodes: Dict[str, AgentNode] = Field(default_factory=dict)
    edges: List[Edge] = Field(default_factory=list)
    start_nodes: List[str] = Field(default_factory=list)
    
    def validate(self) -> None:
        """Validates the graph for correctness."""
        if not self.nodes:
            raise GraphExecutionError("Graph has no nodes.")
        if not self.start_nodes:
            raise GraphExecutionError("Graph has no start nodes defined.")
            
        if GraphValidator.detect_cycles(self.nodes, self.edges):
            raise GraphExecutionError("Graph contains cycles, which is not supported in DAG mode.")
            
        unreachable = GraphValidator.check_reachability(self.nodes, self.edges, self.start_nodes)
        if unreachable:
            raise GraphExecutionError(f"Graph contains unreachable nodes: {unreachable}")


class GraphExecutor:
    """Executes an AgentGraph, handling data passing and parallel branches."""
    
    def __init__(self, graph: AgentGraph) -> None:
        self.graph = graph
        self.state: Dict[str, Any] = {}
        self.node_status: Dict[str, NodeStatus] = {n: NodeStatus.PENDING for n in graph.nodes}
        self._lock = asyncio.Lock()
        
    def _get_outgoing_edges(self, node_id: str) -> List[Edge]:
        """Get edges originating from a node, sorted by priority."""
        edges = [e for e in self.graph.edges if e.source_id == node_id]
        edges.sort(key=lambda e: e.priority, reverse=True)
        return edges

    def _get_incoming_edges(self, node_id: str) -> List[Edge]:
        """Get edges terminating at a node."""
        return [e for e in self.graph.edges if e.target_id == node_id]

    async def _execute_node(self, node_id: str) -> None:
        """Simulates the execution of a single agent node."""
        node = self.graph.nodes[node_id]
        
        async with self._lock:
            self.node_status[node_id] = NodeStatus.RUNNING
            
        try:
            # Simulate work
            await asyncio.sleep(0.1)
            
            # Simple state mutation simulation
            async with self._lock:
                self.state[f"{node.name}_completed"] = True
                self.node_status[node_id] = NodeStatus.COMPLETED
                
        except Exception as e:
            async with self._lock:
                self.node_status[node_id] = NodeStatus.FAILED
            raise e

    async def execute(self, initial_state: Dict[str, Any], timeout_seconds: int = 30) -> Dict[str, Any]:
        """Executes the graph using topological traversal."""
        self.graph.validate()
        self.state.update(initial_state)
        
        # Determine dependencies
        in_degree: Dict[str, int] = {n: 0 for n in self.graph.nodes}
        adj_list: Dict[str, List[str]] = {n: [] for n in self.graph.nodes}
        
        for edge in self.graph.edges:
            adj_list[edge.source_id].append(edge.target_id)
            in_degree[edge.target_id] += 1
            
        # Queue for nodes ready to run
        ready_queue = [n for n in self.graph.nodes if in_degree[n] == 0]
        
        active_tasks = set()
        
        async def run_and_notify(node_id: str):
            await self._execute_node(node_id)
            return node_id
            
        try:
            async with asyncio.timeout(timeout_seconds):
                while ready_queue or active_tasks:
                    # Launch all ready nodes
                    while ready_queue:
                        nxt = ready_queue.pop(0)
                        task = asyncio.create_task(run_and_notify(nxt))
                        active_tasks.add(task)
                        
                    if not active_tasks:
                        break
                        
                    # Wait for at least one task to finish
                    done, active_tasks = await asyncio.wait(active_tasks, return_when=asyncio.FIRST_COMPLETED)
                    
                    for task in done:
                        completed_node_id = task.result()
                        # Evaluate outgoing edges
                        for edge in self._get_outgoing_edges(completed_node_id):
                            if edge.evaluate(self.state):
                                target = edge.target_id
                                in_degree[target] -= 1
                                if in_degree[target] == 0:
                                    ready_queue.append(target)
                            else:
                                # Edge not taken, decrement in_degree and mark skipped if 0
                                target = edge.target_id
                                in_degree[target] -= 1
                                if in_degree[target] == 0:
                                    self.node_status[target] = NodeStatus.SKIPPED
                                    # Propagate skip down the chain recursively if needed (omitted for brevity)
                                    
        except asyncio.TimeoutError:
            raise GraphExecutionError("Graph execution timed out.")
            
        if any(s == NodeStatus.FAILED for s in self.node_status.values()):
            raise GraphExecutionError("One or more nodes failed during execution.")
            
        return self.state

# EOF
