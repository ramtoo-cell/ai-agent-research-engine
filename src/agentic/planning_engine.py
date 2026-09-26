import asyncio
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

class PlanStep(BaseModel):
    """A single step in a plan."""
    step_id: str
    action: str
    parameters: Dict[str, Any] = Field(default_factory=dict)
    preconditions: List[str] = Field(default_factory=list)
    postconditions: List[str] = Field(default_factory=list)
    estimated_cost: float = 0.0

class SubGoal(BaseModel):
    """A subgoal within a larger plan."""
    subgoal_id: str
    description: str
    steps: List[PlanStep] = Field(default_factory=list)
    is_completed: bool = False

class Plan(BaseModel):
    """A hierarchical plan."""
    plan_id: str
    main_goal: str
    subgoals: List[SubGoal] = Field(default_factory=list)
    status: str = "DRAFT"
    total_estimated_cost: float = 0.0

class HierarchicalPlanner:
    """Decomposes goals into subgoals and steps."""
    async def create_plan(self, goal: str, context: Dict[str, Any]) -> Plan:
        """Generates a hierarchical plan for a given goal."""
        # In a real implementation, this would invoke an LLM or reasoning engine
        plan = Plan(
            plan_id=f"plan_{id(goal)}",
            main_goal=goal,
            subgoals=[
                SubGoal(
                    subgoal_id="sg_1",
                    description="Analyze requirements",
                    steps=[
                        PlanStep(step_id="st_1", action="GatherContext", preconditions=[], postconditions=["context_gathered"])
                    ]
                )
            ]
        )
        return plan

class PlanValidator:
    """Validates plans against feasibility and safety constraints."""
    def __init__(self, safety_rules: List[str]):
        self.safety_rules = safety_rules

    def validate(self, plan: Plan) -> bool:
        """Checks if a plan is safe and feasible."""
        for subgoal in plan.subgoals:
            for step in subgoal.steps:
                if step.action in self.safety_rules:
                    return False
        return True

class PlanOptimizer:
    """Optimizes plans for cost, latency, or quality."""
    def optimize(self, plan: Plan, objective: str = "cost") -> Plan:
        """Rearranges or alters steps to optimize the plan."""
        if objective == "cost":
            plan.subgoals.sort(key=lambda sg: sum(step.estimated_cost for step in sg.steps))
        return plan

class PlanExecutor:
    """Executes plans step-by-step with replanning capabilities."""
    def __init__(self, executor_functions: Dict[str, Any], contingency_planner: 'ContingencyPlanner'):
        self.executor_functions = executor_functions
        self.contingency_planner = contingency_planner

    async def execute(self, plan: Plan) -> bool:
        """Executes a plan."""
        plan.status = "EXECUTING"
        for subgoal in plan.subgoals:
            if subgoal.is_completed:
                continue
            
            for step in subgoal.steps:
                func = self.executor_functions.get(step.action)
                if not func:
                    plan.status = "FAILED"
                    await self.contingency_planner.handle_failure(plan, step)
                    return False
                
                try:
                    if asyncio.iscoroutinefunction(func):
                        await func(**step.parameters)
                    else:
                        func(**step.parameters)
                except Exception as e:
                    plan.status = "FAILED"
                    await self.contingency_planner.handle_failure(plan, step, error=str(e))
                    return False
            
            subgoal.is_completed = True
            
        plan.status = "COMPLETED"
        return True

class ContingencyPlanner:
    """Handles failure scenarios by generating fallback plans."""
    async def handle_failure(self, plan: Plan, failed_step: PlanStep, error: Optional[str] = None) -> Plan:
        """Generates a contingency plan for a failed step."""
        # Real implementation would re-evaluate the state and generate new subgoals
        fallback_step = PlanStep(
            step_id=f"{failed_step.step_id}_fallback",
            action="FallbackAction",
            parameters={"original_error": error}
        )
        plan.subgoals.append(
            SubGoal(
                subgoal_id="sg_fallback",
                description=f"Fallback for {failed_step.step_id}",
                steps=[fallback_step]
            )
        )
        plan.status = "REPLANNING"
        return plan

class PlanExplainer:
    """Generates human-readable descriptions of plans."""
    def explain(self, plan: Plan) -> str:
        """Returns a formatted string explaining the plan."""
        explanation = [f"Plan: {plan.main_goal}", f"Status: {plan.status}", ""]
        for i, sg in enumerate(plan.subgoals):
            explanation.append(f"Subgoal {i+1}: {sg.description} (Completed: {sg.is_completed})")
            for j, step in enumerate(sg.steps):
                explanation.append(f"  Step {i+1}.{j+1}: {step.action}")
        return "\n".join(explanation)
