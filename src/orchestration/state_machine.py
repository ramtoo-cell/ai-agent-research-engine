import asyncio
from typing import Dict, List, Optional, Any, Callable, Set, Coroutine
from datetime import datetime, timezone
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, ConfigDict


class StateHistoryEntry(BaseModel):
    """Record of a state transition for auditing and rollback."""
    id: UUID = Field(default_factory=uuid4)
    from_state: str
    to_state: str
    event: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    payload: Dict[str, Any] = Field(default_factory=dict)
    is_rollback: bool = False


class Transition(BaseModel):
    """Defines a valid state transition triggered by an event."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    source: str
    target: str
    event: str
    guard_condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    side_effects: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = Field(default_factory=list)


class State(BaseModel):
    """A distinct state in the finite state machine."""
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    name: str
    is_terminal: bool = False
    entry_actions: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = Field(default_factory=list)
    exit_actions: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]] = Field(default_factory=list)
    invariants: List[Callable[[Dict[str, Any]], bool]] = Field(default_factory=list)
    
    def check_invariants(self, context: Dict[str, Any]) -> bool:
        """Verifies all invariants hold true for the current context."""
        for inv in self.invariants:
            if not inv(context):
                return False
        return True


class StateMachineError(Exception):
    pass


class InvalidTransitionError(StateMachineError):
    pass


class InvariantViolationError(StateMachineError):
    pass


class StateMachine:
    """Definition of a finite state machine."""
    
    def __init__(self, name: str, initial_state: str) -> None:
        self.name = name
        self.initial_state = initial_state
        self.states: Dict[str, State] = {}
        self.transitions: List[Transition] = []

    def add_state(self, state: State) -> None:
        if state.name in self.states:
            raise StateMachineError(f"State {state.name} already exists.")
        self.states[state.name] = state

    def add_transition(self, transition: Transition) -> None:
        if transition.source not in self.states:
            raise StateMachineError(f"Source state {transition.source} not found.")
        if transition.target not in self.states:
            raise StateMachineError(f"Target state {transition.target} not found.")
        self.transitions.append(transition)

    def validate(self) -> None:
        """Validates the structure of the state machine."""
        if self.initial_state not in self.states:
            raise StateMachineError(f"Initial state {self.initial_state} not found.")
            
        # Check for dead states (non-terminal states with no outgoing transitions)
        for state_name, state in self.states.items():
            if not state.is_terminal:
                outgoing = [t for t in self.transitions if t.source == state_name]
                if not outgoing:
                    raise StateMachineError(f"Dead state detected: {state_name} is non-terminal but has no outgoing transitions.")
                    
        # Check reachability from initial state
        reachable = set()
        queue = [self.initial_state]
        
        while queue:
            curr = queue.pop(0)
            if curr not in reachable:
                reachable.add(curr)
                outgoing = [t for t in self.transitions if t.source == curr]
                queue.extend([t.target for t in outgoing])
                
        unreachable = [s for s in self.states if s not in reachable]
        if unreachable:
            raise StateMachineError(f"Unreachable states detected: {unreachable}")

    def export_mermaid(self) -> str:
        """Exports the state machine diagram to Mermaid format."""
        lines = ["stateDiagram-v2"]
        lines.append(f"    [*] --> {self.initial_state}")
        
        for state_name, state in self.states.items():
            if state.is_terminal:
                lines.append(f"    {state_name} --> [*]")
                
        for t in self.transitions:
            label = t.event
            if t.guard_condition:
                label += " [guard]"
            lines.append(f"    {t.source} --> {t.target} : {label}")
            
        return "\n".join(lines)


class StateMachineExecutor:
    """Executes a StateMachine, managing current state and transitions."""
    
    def __init__(self, machine: StateMachine, context: Optional[Dict[str, Any]] = None) -> None:
        machine.validate()
        self.machine = machine
        self.current_state = machine.initial_state
        self.context: Dict[str, Any] = context or {}
        self.history: List[StateHistoryEntry] = []
        self._lock = asyncio.Lock()

    async def _execute_actions(self, actions: List[Callable[[Dict[str, Any]], Coroutine[Any, Any, None]]]) -> None:
        for action in actions:
            await action(self.context)

    async def trigger(self, event: str, payload: Optional[Dict[str, Any]] = None) -> bool:
        """Triggers an event, potentially causing a state transition."""
        payload = payload or {}
        
        async with self._lock:
            # Find matching transitions
            valid_transitions = [
                t for t in self.machine.transitions 
                if t.source == self.current_state and t.event == event
            ]
            
            if not valid_transitions:
                raise InvalidTransitionError(f"No transition found for event '{event}' from state '{self.current_state}'.")
                
            # Find the first transition whose guard condition passes
            selected_transition = None
            for t in valid_transitions:
                if t.guard_condition is None or t.guard_condition(self.context):
                    selected_transition = t
                    break
                    
            if not selected_transition:
                raise InvalidTransitionError(f"Transitions exist for '{event}', but guard conditions prevented them.")
                
            source_state = self.machine.states[self.current_state]
            target_state = self.machine.states[selected_transition.target]
            
            # Execute exit actions
            await self._execute_actions(source_state.exit_actions)
            
            # Execute side effects
            await self._execute_actions(selected_transition.side_effects)
            
            # Update state
            prev_state = self.current_state
            self.current_state = selected_transition.target
            self.context.update(payload)
            
            # Execute entry actions
            await self._execute_actions(target_state.entry_actions)
            
            # Check invariants
            if not target_state.check_invariants(self.context):
                raise InvariantViolationError(f"Invariants failed for state '{self.current_state}' after transition.")
                
            # Record history
            self.history.append(StateHistoryEntry(
                from_state=prev_state,
                to_state=self.current_state,
                event=event,
                payload=payload
            ))
            
            return True

    async def rollback(self) -> bool:
        """Rolls back the last transition in the history."""
        async with self._lock:
            if not self.history:
                return False
                
            # Find the last valid non-rollback entry
            # In a real implementation, this would involve inverse side-effects, 
            # but for this simulation we just update the pointer.
            last_entry = self.history[-1]
            
            self.current_state = last_entry.from_state
            
            self.history.append(StateHistoryEntry(
                from_state=last_entry.to_state,
                to_state=last_entry.from_state,
                event="ROLLBACK",
                is_rollback=True
            ))
            
            return True

# EOF
