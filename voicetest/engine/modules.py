"""DSPy modules for conversation state management.

Provides proper dspy.Module subclasses for state execution and conversation flow,
enabling DSPy optimization (e.g., BootstrapFewShot) on agent behavior.
"""

from dataclasses import dataclass
from typing import Any

import dspy

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import Transition
from voicetest.utils import create_template_filler


@dataclass
class RunContext:
    """Context for state execution (LiveKit-aligned naming).

    Contains all the information a state needs to generate a response
    and decide on transitions.
    """

    conversation_history: str
    user_message: str
    dynamic_variables: dict[str, Any]
    available_transitions: str
    general_instructions: str
    state_instructions: str


@dataclass
class StateResult:
    """Result from state execution.

    Contains the agent's response and optional transition information.
    """

    response: str
    handoff_to: str | None  # Node ID or None to stay
    transition_reasoning: str | None = None  # Reasoning from split transition evaluation


class StateModule(dspy.Module):
    """DSPy module for a single conversation state.

    Each StateModule encapsulates the logic for one node in the conversation
    flow. It handles response generation and optionally transition decisions.

    The module supports two modes:
    - Combined (default): Single LLM call for both response and transition
    - Response-only (split): Just generate response, transitions handled separately
    """

    def __init__(
        self,
        node_id: str,
        instructions: str,
        transitions: list[Transition],
        use_split_transitions: bool = False,
    ):
        super().__init__()
        self.node_id = node_id
        self.instructions = instructions  # state_prompt, LiveKit naming
        self.transitions = transitions
        self.use_split_transitions = use_split_transitions
        self._template_filler = create_template_filler(instructions)

        # Create appropriate signature based on mode
        if use_split_transitions:
            # Response-only mode - transitions handled by ConversationModule
            self._response_signature = self._create_response_signature(include_transitions=False)
        else:
            # Combined mode - include transitions if they exist
            self._response_signature = self._create_response_signature(
                include_transitions=bool(transitions)
            )

        self.response_predictor = dspy.Predict(self._response_signature)

    def _create_response_signature(self, include_transitions: bool) -> type[dspy.Signature]:
        """Create Signature for response generation.

        Args:
            include_transitions: Whether to include transition fields in the signature
        """
        docstring = "Generate a natural spoken response as a voice agent."

        attrs: dict[str, Any] = {
            "__doc__": docstring,
            "general_instructions": dspy.InputField(desc="Overall agent instructions and context"),
            "state_instructions": dspy.InputField(
                desc="Current state-specific instructions for this conversation node"
            ),
            "conversation_history": dspy.InputField(desc="Conversation so far"),
            "user_message": dspy.InputField(desc="Latest user message to respond to"),
            "response": dspy.OutputField(desc="Agent's spoken response to the user"),
        }

        if include_transitions:
            valid_targets = [t.target_node_id for t in self.transitions] + ["none"]
            attrs["available_transitions"] = dspy.InputField(
                desc="Available transitions to other states"
            )
            attrs["transition_to"] = dspy.OutputField(
                desc=f"State to transition to. One of: {valid_targets}"
            )

        suffix = "_combined" if include_transitions else "_response_only"
        return type(f"State_{self.node_id}{suffix}", (dspy.Signature,), attrs)

    def forward(self, ctx: RunContext) -> StateResult:
        """Execute state - generates response and optionally determines transition.

        This is the main DSPy-optimizable method.
        """
        if self.use_split_transitions:
            return self._forward_response_only(ctx)
        else:
            return self._forward_combined(ctx)

    def _forward_combined(self, ctx: RunContext) -> StateResult:
        """Combined mode: single call for response and transition."""
        if self.transitions:
            result = self.response_predictor(
                general_instructions=ctx.general_instructions,
                state_instructions=ctx.state_instructions,
                conversation_history=ctx.conversation_history,
                user_message=ctx.user_message,
                available_transitions=ctx.available_transitions,
            )
            transition_to = getattr(result, "transition_to", "none")
            transition_to = transition_to.strip().lower() if transition_to else "none"
            handoff = transition_to if transition_to != "none" else None
        else:
            result = self.response_predictor(
                general_instructions=ctx.general_instructions,
                state_instructions=ctx.state_instructions,
                conversation_history=ctx.conversation_history,
                user_message=ctx.user_message,
            )
            handoff = None

        return StateResult(
            response=result.response,
            handoff_to=handoff,
        )

    def _forward_response_only(self, ctx: RunContext) -> StateResult:
        """Response-only mode: just generate response, no transition detection."""
        result = self.response_predictor(
            general_instructions=ctx.general_instructions,
            state_instructions=ctx.state_instructions,
            conversation_history=ctx.conversation_history,
            user_message=ctx.user_message,
        )

        return StateResult(
            response=result.response,
            handoff_to=None,  # Transition handled by ConversationModule
        )


class ConversationModule(dspy.Module):
    """DSPy module for full conversation flow.

    Wraps all state modules and manages conversation execution.
    State modules are registered as submodules for DSPy optimization.

    When use_split_transitions is True, transition detection happens in a
    separate LLM call after getting the agent's response.
    """

    def __init__(self, graph: AgentGraph, use_split_transitions: bool = False):
        super().__init__()
        self.instructions = graph.source_metadata.get("general_prompt", "")
        self.entry_node_id = graph.entry_node_id
        self.graph = graph
        self.use_split_transitions = use_split_transitions

        # Build and register state modules as proper submodules
        self._state_modules: dict[str, StateModule] = {}
        for node_id, node in graph.nodes.items():
            # Force split to False if node has no transitions
            effective_split = use_split_transitions and bool(node.transitions)

            state_module = StateModule(
                node_id=node_id,
                instructions=node.state_prompt,
                transitions=node.transitions,
                use_split_transitions=effective_split,
            )
            # Register as attribute for DSPy optimization
            setattr(self, f"state_{node_id}", state_module)
            self._state_modules[node_id] = state_module

        # Create transition predictor for split mode
        if use_split_transitions:
            self._transition_signature = self._create_transition_signature()
            self.transition_predictor = dspy.ChainOfThought(self._transition_signature)

    def _create_transition_signature(self) -> type[dspy.Signature]:
        """Create Signature for split transition evaluation."""
        docstring = (
            "Evaluate if conversation should transition to a different state "
            "based on the conversation and agent's response."
        )

        attrs: dict[str, Any] = {
            "__doc__": docstring,
            "conversation_history": dspy.InputField(desc="Full conversation so far"),
            "agent_response": dspy.InputField(desc="The response just generated"),
            "available_transitions": dspy.InputField(
                desc="Valid transitions with their conditions"
            ),
            "transition_to": dspy.OutputField(
                desc="State to transition to, or 'none' to stay in current state"
            ),
        }

        return type("TransitionEvaluator", (dspy.Signature,), attrs)

    def get_state_module(self, node_id: str) -> StateModule | None:
        """Get the state module for a given node ID."""
        return self._state_modules.get(node_id)

    def forward(
        self,
        node_id: str,
        ctx: RunContext,
    ) -> StateResult:
        """Execute a single state - returns response and transition.

        This method is called by ConversationRunner for each turn.
        The runner manages the conversation loop and state.

        In split mode, this method handles transition detection after
        getting the response from the state module.
        """
        state_module = self._state_modules.get(node_id)
        if state_module is None:
            raise ValueError(f"Unknown node: {node_id}")

        # Get response from state module
        result = state_module(ctx)

        # In split mode with transitions, evaluate transition separately
        if state_module.use_split_transitions:
            transition_result = self.transition_predictor(
                conversation_history=ctx.conversation_history,
                agent_response=result.response,
                available_transitions=ctx.available_transitions,
            )

            transition_to = transition_result.transition_to.strip().lower()
            handoff = transition_to if transition_to != "none" else None
            reasoning = getattr(transition_result, "rationale", None)

            return StateResult(
                response=result.response,
                handoff_to=handoff,
                transition_reasoning=reasoning,
            )

        return result

    def format_transitions(self, node_id: str) -> str:
        """Format available transitions for a node as a string for LLM input."""
        node = self.graph.nodes.get(node_id)
        if not node or not node.transitions:
            return "(no transitions available - stay in current state)"

        lines = []
        for transition in node.transitions:
            condition = transition.condition.value or "No condition specified"
            lines.append(f"- {transition.target_node_id}: {condition}")

        # Check for end_call tool
        for tool in node.tools:
            if tool.name == "end_call" or getattr(tool, "type", "") == "end_call":
                desc = tool.description or "End the call"
                lines.append(f"- end_call: {desc}")
                break

        return "\n".join(lines) if lines else "(no transitions available)"
