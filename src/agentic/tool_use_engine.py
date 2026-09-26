import asyncio
from typing import Any, Callable, Dict, List, Optional, Set, Type, TypeVar, Generic
from pydantic import BaseModel, Field, ValidationError, create_model

T = TypeVar("T")

class ToolSchema(BaseModel):
    """Schema definition for tool parameters or return values."""
    schema_type: str = Field(description="The JSON schema type")
    properties: Dict[str, Any] = Field(default_factory=dict, description="Schema properties")
    required: List[str] = Field(default_factory=list, description="Required fields")

class ToolDefinition(BaseModel):
    """Definition of a tool available to the agent."""
    name: str = Field(description="Name of the tool")
    description: str = Field(description="Detailed description of what the tool does")
    version: str = Field(default="1.0.0", description="Tool version")
    parameters_schema: ToolSchema = Field(description="Schema for the tool's input parameters")
    return_schema: ToolSchema = Field(description="Schema for the tool's return value")
    side_effects: bool = Field(default=False, description="Whether the tool has side effects")
    cost_estimate: float = Field(default=0.0, description="Estimated cost of executing the tool")
    capabilities: List[str] = Field(default_factory=list, description="Capabilities this tool provides")

class ToolResult(BaseModel):
    """Result of a tool execution."""
    tool_name: str
    success: bool
    output: Any
    error: Optional[str] = None
    execution_time_ms: float
    cost: float = 0.0

class ToolSelector:
    """Selects the best tool for a given task based on capability and cost."""
    def __init__(self, tools: List[ToolDefinition]):
        self.tools = {tool.name: tool for tool in tools}

    def select_tools_by_capability(self, capability: str) -> List[ToolDefinition]:
        """Finds tools that provide a specific capability."""
        return [tool for tool in self.tools.values() if capability in tool.capabilities]

    def optimize_selection(self, candidates: List[ToolDefinition], max_cost: float) -> Optional[ToolDefinition]:
        """Selects the most cost-effective tool from candidates."""
        valid_candidates = [t for t in candidates if t.cost_estimate <= max_cost]
        if not valid_candidates:
            return None
        return min(valid_candidates, key=lambda t: t.cost_estimate)

class ToolExecutionStep(BaseModel):
    """A single step in a tool execution plan."""
    step_id: str
    tool_name: str
    arguments: Dict[str, Any]
    depends_on: List[str] = Field(default_factory=list)
    rollback_tool: Optional[str] = None
    rollback_arguments: Optional[Dict[str, Any]] = None

class ToolExecutionPlan(BaseModel):
    """An ordered plan of tool executions."""
    plan_id: str
    steps: List[ToolExecutionStep]
    max_parallelism: int = 1

class ToolResultValidator:
    """Validates tool outputs against their expected schemas."""
    
    @staticmethod
    def validate_output(tool_def: ToolDefinition, output: Any) -> bool:
        """Validates that the output matches the return_schema."""
        # A full implementation would compile the return_schema into a Pydantic model
        # and attempt to validate the output dictionary against it.
        try:
            if not isinstance(output, dict):
                return False
            for req in tool_def.return_schema.required:
                if req not in output:
                    return False
            return True
        except Exception:
            return False

class ToolCompositor:
    """Chains multiple tools into workflows."""
    def __init__(self, tools: Dict[str, ToolDefinition]):
        self.tools = tools

    def create_workflow(self, steps: List[ToolExecutionStep]) -> ToolExecutionPlan:
        """Creates an execution plan from a list of steps."""
        for step in steps:
            if step.tool_name not in self.tools:
                raise ValueError(f"Unknown tool: {step.tool_name}")
        return ToolExecutionPlan(plan_id="wf_" + str(id(steps)), steps=steps, max_parallelism=1)

class ParallelToolExecutor:
    """Executes tools in parallel while respecting dependencies."""
    def __init__(self, tool_implementations: Dict[str, Callable]):
        self.implementations = tool_implementations

    async def execute_plan(self, plan: ToolExecutionPlan) -> Dict[str, ToolResult]:
        """Executes the plan concurrently where possible."""
        results: Dict[str, ToolResult] = {}
        pending = {step.step_id: step for step in plan.steps}
        
        while pending:
            ready_steps = []
            for step_id, step in pending.items():
                if all(dep in results and results[dep].success for dep in step.depends_on):
                    ready_steps.append(step)
            
            if not ready_steps:
                # Deadlock or dependency failure
                break
                
            tasks = []
            for step in ready_steps:
                tasks.append(self._execute_step(step))
                del pending[step.step_id]
                
            step_results = await asyncio.gather(*tasks)
            for step_id, result in zip([s.step_id for s in ready_steps], step_results):
                results[step_id] = result
                if not result.success:
                    # Halt on failure, a real system would trigger rollback here
                    return results
                    
        return results

    async def _execute_step(self, step: ToolExecutionStep) -> ToolResult:
        """Executes a single step."""
        import time
        start = time.time()
        func = self.implementations.get(step.tool_name)
        if not func:
            return ToolResult(
                tool_name=step.tool_name, 
                success=False, 
                output=None, 
                error="Implementation not found", 
                execution_time_ms=0
            )
        try:
            # Assuming async functions for tools
            if asyncio.iscoroutinefunction(func):
                output = await func(**step.arguments)
            else:
                output = func(**step.arguments)
            duration = (time.time() - start) * 1000
            return ToolResult(
                tool_name=step.tool_name,
                success=True,
                output=output,
                execution_time_ms=duration
            )
        except Exception as e:
            duration = (time.time() - start) * 1000
            return ToolResult(
                tool_name=step.tool_name,
                success=False,
                output=None,
                error=str(e),
                execution_time_ms=duration
            )

class ToolVersionManager:
    """Manages different versions of tools."""
    def __init__(self):
        self._tools_by_version: Dict[str, Dict[str, ToolDefinition]] = {}

    def register_tool(self, tool: ToolDefinition):
        if tool.name not in self._tools_by_version:
            self._tools_by_version[tool.name] = {}
        self._tools_by_version[tool.name][tool.version] = tool

    def get_tool(self, name: str, version: Optional[str] = None) -> Optional[ToolDefinition]:
        if name not in self._tools_by_version:
            return None
        versions = self._tools_by_version[name]
        if version:
            return versions.get(version)
        # Return latest version based on simple string sorting (or semver in real impl)
        latest = sorted(versions.keys())[-1]
        return versions[latest]

class ToolDiscoveryService:
    """Dynamically discovers and registers tools."""
    def __init__(self, version_manager: ToolVersionManager):
        self.version_manager = version_manager

    async def discover_tools(self, source_url: str) -> List[ToolDefinition]:
        """Fetches tool definitions from a remote source."""
        # Simulated discovery
        discovered = []
        for tool in discovered:
            self.version_manager.register_tool(tool)
        return discovered
