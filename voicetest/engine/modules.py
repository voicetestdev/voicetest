"""DSPy modules for conversation state management.

Provides proper dspy.Module subclasses for state execution and conversation flow,
enabling DSPy optimization (e.g., BootstrapFewShot) on agent behavior.
"""

from dataclasses import dataclass
from typing import Any

import dspy

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionOption
from voicetest.templating import create_template_filler


@dataclass
class RunContext:
    """Context for state execution (LiveKit-aligned naming).

    Contains all the information a state needs to generate a response
    and decide on transitions.
    """

    conversation_history: str
    user_message: str
    dynamic_variables: dict[str, Any]
    available_transitions: list[TransitionOption]
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
    flow. It generates a response; transition decisions are handled separately
    by a dedicated LLM call in ConversationEngine.
    """

    def __init__(
        self,
        node_id: str,
        instructions: str,
        transitions: list[Transition],
    ):
        super().__init__()
        self.node_id = node_id
        self.instructions = instructions  # state_prompt, LiveKit naming
        self.transitions = transitions
        self._template_filler = create_template_filler(instructions)

        self._response_signature = self._create_response_signature()
        self.response_predictor = dspy.Predict(self._response_signature)

    def _create_response_signature(self) -> type[dspy.Signature]:
        """Create Signature for response generation (no transition fields)."""
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

        return type(f"State_{self.node_id}", (dspy.Signature,), attrs)

    def forward(self, ctx: RunContext) -> StateResult:
        """Execute state - generates response only.

        This is the main DSPy-optimizable method.
        """
        result = self.response_predictor(
            general_instructions=ctx.general_instructions,
            state_instructions=ctx.state_instructions,
            conversation_history=ctx.conversation_history,
            user_message=ctx.user_message,
        )

        return StateResult(
            response=result.response,
            handoff_to=None,
        )


class ConversationModule(dspy.Module):
    """DSPy module for full conversation flow.

    Wraps all state modules and manages conversation execution.
    State modules are registered as submodules for DSPy optimization.
    Transition detection happens in a separate LLM call after getting
    the agent's response.
    """

    def __init__(self, graph: AgentGraph):
        super().__init__()
        self.instructions = graph.source_metadata.get("general_prompt", "")
        self.entry_node_id = graph.entry_node_id
        self.graph = graph

        # Build and register state modules as proper submodules
        self._state_modules: dict[str, StateModule] = {}
        for node_id, node in graph.nodes.items():
            state_module = StateModule(
                node_id=node_id,
                instructions=node.state_prompt,
                transitions=node.transitions,
            )
            # Register as attribute for DSPy optimization
            setattr(self, f"state_{node_id}", state_module)
            self._state_modules[node_id] = state_module

        self._transition_signature = self._create_transition_signature()

    def _create_transition_signature(self) -> type[dspy.Signature]:
        """Create Signature for split transition evaluation."""
        docstring = (
            "Evaluate if conversation should transition to a different state "
            "based on the conversation and agent's response."
        )

        attrs: dict[str, Any] = {
            "__doc__": docstring,
            "__annotations__": {"available_transitions": list[TransitionOption]},
            "conversation_history": dspy.InputField(desc="Full conversation so far"),
            "agent_response": dspy.InputField(desc="The response just generated"),
            "available_transitions": dspy.InputField(
                desc="Valid transitions with their conditions"
            ),
            "transition_to": dspy.OutputField(
                desc=(
                    "Target from available_transitions to transition to, or 'none' to stay in "
                    "current state"
                )
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
        """Execute a single state - returns response only.

        This method is called by ConversationRunner for each turn.
        The runner manages the conversation loop and state.
        Transition detection is handled separately by ConversationEngine.
        """
        state_module = self._state_modules.get(node_id)
        if state_module is None:
            raise ValueError(f"Unknown node: {node_id}")

        return state_module(ctx)

    def format_transitions(self, node_id: str) -> list[TransitionOption]:
        """Format available transitions for a node as structured objects for LLM input.

        Excludes always-type transitions from conversation nodes since those
        fire automatically after the LLM responds (not LLM-decided).
        """
        node = self.graph.nodes.get(node_id)
        if not node or not node.transitions:
            return []

        return [
            TransitionOption(
                target=t.target_node_id,
                condition=t.condition.value or "No condition specified",
                condition_type=t.condition.type,
                description=t.description,
            )
            for t in node.transitions
            if t.condition.type != "always"
        ]
