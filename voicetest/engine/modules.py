"""DSPy modules for conversation state management.

Provides StateModule (per-node signature creation) and ConversationModule
(graph-wide state module registry and transition formatting).
"""

from typing import Any

import dspy

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionOption


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

    def create_response_signature(self, docstring: str) -> type[dspy.Signature]:
        """Create Signature for response generation.

        The node's state prompt is the signature docstring, giving it
        system-level weight in the LLM prompt rather than being just
        another input field.
        """
        attrs: dict[str, Any] = {
            "__doc__": docstring,
            "general_instructions": dspy.InputField(desc="Overall agent instructions and context"),
            "conversation_history": dspy.InputField(
                desc="Conversation so far — continue from where the conversation left off, "
                "do not repeat questions already asked or information already collected"
            ),
            "user_message": dspy.InputField(desc="Latest user message to respond to"),
            "response": dspy.OutputField(desc="Agent's spoken response to the user"),
        }

        return type(f"State_{self.node_id}", (dspy.Signature,), attrs)


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
        """Create Signature for transition evaluation.

        Transitions are evaluated based on conversation history alone
        (including the user's latest message). The agent has not yet
        responded — the transition determines which node the agent
        will respond FROM.

        Output fields are ordered to force completion reasoning before
        transition selection: the LLM must assess remaining objectives
        and whether the user addressed the agent's last message before
        it can pick a transition target.
        """
        docstring = (
            "Evaluate if the conversation should transition to a different state. "
            "First determine whether the current node's objectives are complete, "
            "then decide on a transition. If objectives remain, return 'none'."
        )

        attrs: dict[str, Any] = {
            "__doc__": docstring,
            "__annotations__": {"available_transitions": list[TransitionOption]},
            "current_state_prompt": dspy.InputField(
                desc="The instructions for the current conversation state"
            ),
            "conversation_history": dspy.InputField(
                desc="Conversation within the current state only"
            ),
            "last_agent_message": dspy.InputField(
                desc="The agent's most recent message in this state"
            ),
            "available_transitions": dspy.InputField(
                desc="Valid transitions with their conditions"
            ),
            "objectives_complete": dspy.OutputField(
                desc="Are ALL objectives in the state prompt met? "
                "If the agent asked a question or requested information and the user "
                "has not addressed it, objectives are NOT complete.",
                type=bool,
            ),
            "transition_to": dspy.OutputField(
                desc=(
                    "If objectives_complete is false, MUST be 'none'. "
                    "If true, select target from available_transitions whose "
                    "condition is satisfied, or 'none' if no condition matches."
                )
            ),
        }

        return type("TransitionEvaluator", (dspy.Signature,), attrs)

    def get_state_module(self, node_id: str) -> StateModule | None:
        """Get the state module for a given node ID."""
        return self._state_modules.get(node_id)

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
