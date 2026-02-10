"""Conversation engine - single source of truth for turn processing.

This module provides ConversationEngine, used by BOTH the test runner AND live calls.
If tests pass, real calls behave the same.
"""

from dataclasses import dataclass, field

from voicetest.engine.modules import ConversationModule, RunContext
from voicetest.llm import OnTokenCallback, call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message, ToolCall
from voicetest.models.test_case import RunOptions
from voicetest.retry import OnErrorCallback
from voicetest.utils import substitute_variables


@dataclass
class TurnResult:
    """Result from processing a single turn."""

    response: str
    transitioned_to: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    end_call_invoked: bool = False


class ConversationEngine:
    """THE source of truth for turn processing. Used by tests AND live calls.

    This class encapsulates:
    - Graph structure and configuration
    - Turn-by-turn message processing
    - State tracking (current node, transcript, nodes visited)
    - Transition detection and handling
    """

    def __init__(
        self,
        graph: AgentGraph,
        model: str | None = None,
        options: RunOptions | None = None,
        dynamic_variables: dict | None = None,
    ):
        """Initialize the conversation engine.

        Args:
            graph: The agent graph defining conversation flow.
            model: LLM model identifier (e.g., "openai/gpt-4o-mini").
            options: Run options for configuration.
            dynamic_variables: Variables for template substitution.
        """
        self.graph = graph
        self.model = model or graph.default_model or "openai/gpt-4o-mini"
        self.options = options or RunOptions()
        self._dynamic_variables = dynamic_variables or {}

        use_cot = self.options.cot_transitions if self.options else False
        self._module = ConversationModule(graph, use_cot_transitions=use_cot)

        # State
        self._current_node = graph.entry_node_id
        self._transcript: list[Message] = []
        self._nodes_visited: list[str] = [graph.entry_node_id]
        self._tools_called: list[ToolCall] = []
        self._end_call_invoked = False

    @property
    def current_node(self) -> str:
        """Current node ID."""
        return self._current_node

    @property
    def transcript(self) -> list[Message]:
        """Conversation transcript (copy)."""
        return self._transcript.copy()

    @property
    def nodes_visited(self) -> list[str]:
        """List of node IDs visited during conversation (copy)."""
        return self._nodes_visited.copy()

    @property
    def tools_called(self) -> list[ToolCall]:
        """List of tool calls made during conversation (copy)."""
        return self._tools_called.copy()

    @property
    def end_call_invoked(self) -> bool:
        """Whether end_call was invoked."""
        return self._end_call_invoked

    def add_user_message(self, content: str) -> None:
        """Add a user message to the transcript.

        Args:
            content: The user's message content.
        """
        self._transcript.append(
            Message(
                role="user",
                content=content,
                metadata={"node_id": self._current_node},
            )
        )

    async def process_turn(
        self,
        user_message: str,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> TurnResult:
        """Process one turn. Same logic for tests and live calls.

        This method:
        1. Gets the state module for the current node
        2. Builds context with conversation history
        3. Calls the LLM
        4. Handles transitions
        5. Records the agent response

        Args:
            user_message: The user's message to respond to.
            on_token: Optional callback for streaming tokens.
            on_error: Optional callback for retryable errors.

        Returns:
            TurnResult with response and transition info.
        """
        # Get the state module for current node
        state_module = self._module.get_state_module(self._current_node)
        if state_module is None:
            raise ValueError(f"Unknown node: {self._current_node}")

        # Apply dynamic variable substitution to instructions
        general_instructions = substitute_variables(
            self._module.instructions, self._dynamic_variables
        )
        state_instructions = substitute_variables(
            state_module.instructions, self._dynamic_variables
        )

        # Build context for state execution
        ctx = RunContext(
            conversation_history=self._format_transcript(self._transcript),
            user_message=user_message,
            dynamic_variables=self._dynamic_variables,
            available_transitions=self._module.format_transitions(self._current_node),
            general_instructions=general_instructions,
            state_instructions=state_instructions,
        )

        # Call LLM with the state module's signature
        result = await call_llm(
            self.model,
            state_module._response_signature,
            on_token=on_token,
            stream_field="response" if on_token else None,
            on_error=on_error,
            general_instructions=ctx.general_instructions,
            state_instructions=ctx.state_instructions,
            conversation_history=ctx.conversation_history,
            user_message=ctx.user_message,
            **(
                {"available_transitions": ctx.available_transitions}
                if state_module.transitions
                else {}
            ),
        )

        # Build turn result
        turn_result = TurnResult(response=result.response)

        # Handle transition
        transition_target = getattr(result, "transition_to", "none")
        if transition_target:
            transition_target = transition_target.strip().lower()

        if transition_target and transition_target != "none":
            # Check for end_call
            current_node = self.graph.nodes.get(self._current_node)
            has_end_call = current_node and any(
                t.name == "end_call" or getattr(t, "type", "") == "end_call"
                for t in current_node.tools
            )

            if transition_target == "end_call" and has_end_call:
                self._end_call_invoked = True
                turn_result.end_call_invoked = True
                tool_call = ToolCall(
                    name="end_call",
                    arguments={},
                    result="call_ended",
                )
                self._tools_called.append(tool_call)
                turn_result.tool_calls.append(tool_call)
            elif transition_target in self.graph.nodes:
                self._current_node = transition_target
                self._nodes_visited.append(transition_target)
                turn_result.transitioned_to = transition_target
                tool_call = ToolCall(
                    name=f"route_to_{transition_target}",
                    arguments={},
                    result=transition_target,
                )
                self._tools_called.append(tool_call)
                turn_result.tool_calls.append(tool_call)

        # Record agent response
        self._transcript.append(
            Message(
                role="assistant",
                content=result.response,
                metadata={"node_id": self._current_node},
            )
        )

        return turn_result

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        if not transcript:
            return "(conversation just started)"

        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset the engine to initial state."""
        self._current_node = self.graph.entry_node_id
        self._transcript = []
        self._nodes_visited = [self.graph.entry_node_id]
        self._tools_called = []
        self._end_call_invoked = False
