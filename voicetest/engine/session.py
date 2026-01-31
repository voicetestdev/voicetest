"""Conversation session management.

Wraps the execution of conversations using DSPy modules.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from voicetest.engine.modules import ConversationModule, RunContext
from voicetest.llm import call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message, ToolCall
from voicetest.models.test_case import RunOptions
from voicetest.retry import OnErrorCallback


# Callback type for turn updates: receives transcript after each turn
OnTurnCallback = Callable[[list[Message]], Awaitable[None] | None]

# Callback type for token updates: receives token string and source ("agent" or "user")
OnTokenCallback = Callable[[str, str], Awaitable[None] | None]


async def _invoke_callback(callback: Callable, *args) -> None:
    """Invoke callback, handling both sync and async."""
    result = callback(*args)
    if result is not None and hasattr(result, "__await__"):
        await result


@dataclass
class ConversationState:
    """Tracks state during a conversation."""

    transcript: list[Message] = field(default_factory=list)
    nodes_visited: list[str] = field(default_factory=list)
    tools_called: list[ToolCall] = field(default_factory=list)
    turn_count: int = 0
    end_reason: str = ""
    end_call_invoked: bool = False


class NodeTracker:
    """Tracks node visits during conversation."""

    def __init__(self):
        self.visited: list[str] = []
        self.current_node: str | None = None

    def record(self, node_id: str) -> None:
        """Record a node visit."""
        self.visited.append(node_id)
        self.current_node = node_id


class ConversationRunner:
    """Runs simulated conversations.

    This class orchestrates the conversation loop, managing:
    - ConversationModule instantiation
    - Turn-by-turn execution
    - State tracking
    """

    def __init__(
        self,
        graph: AgentGraph,
        options: RunOptions | None = None,
        mock_mode: bool = False,
        dynamic_variables: dict | None = None,
        use_cot_transitions: bool = False,
    ):
        self.graph = graph
        self.options = options or RunOptions()
        self._mock_mode = mock_mode
        self._dynamic_variables = dynamic_variables or {}
        self._conversation_module = ConversationModule(
            graph, use_cot_transitions=use_cot_transitions
        )

    async def run(
        self,
        test_case: "TestCase",  # noqa: F821 - Forward reference
        user_simulator: "UserSimulator",  # noqa: F821 - Forward reference
        on_turn: OnTurnCallback | None = None,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> ConversationState:
        """Run a complete conversation.

        This method orchestrates the full conversation flow:
        1. Initialize state with entry node
        2. Loop: get user input -> process with agent -> record events
        3. Continue until end condition or max turns

        Args:
            test_case: The test case defining constraints.
            user_simulator: The user persona simulator.
            on_turn: Optional callback invoked after each turn with current transcript.
            on_token: Optional callback invoked for each token during streaming.
            on_error: Optional callback invoked on retryable errors (e.g., rate limits).

        Returns:
            ConversationState with transcript and tracking data.
        """
        state = ConversationState()
        node_tracker = NodeTracker()

        # Start at entry node
        node_tracker.record(self.graph.entry_node_id)
        current_node_id = self.graph.entry_node_id

        for _turn in range(self.options.max_turns):
            # Get simulated user input
            sim_response = await user_simulator.generate(
                state.transcript,
                on_token=on_token if self.options.streaming else None,
                on_error=on_error,
            )

            if sim_response.should_end:
                state.end_reason = "user_ended"
                break

            async def notify():
                if on_turn:
                    result = on_turn(state.transcript)
                    if result is not None:
                        await result

            # Record user message with current node
            state.transcript.append(
                Message(
                    role="user",
                    content=sim_response.message,
                    metadata={"node_id": node_tracker.current_node},
                )
            )
            await notify()

            # Process with current state module
            response, new_node_id = await self._process_turn(
                current_node_id,
                sim_response.message,
                state,
                node_tracker,
                on_token=on_token if self.options.streaming else None,
                on_error=on_error,
            )

            if response:
                state.transcript.append(
                    Message(
                        role="assistant",
                        content=response,
                        metadata={"node_id": node_tracker.current_node},
                    )
                )
                await notify()

            # Handle node transition
            if new_node_id is not None:
                current_node_id = new_node_id

            state.turn_count += 1

            # Check for agent-initiated end
            if state.end_call_invoked:
                state.end_reason = "agent_ended"
                break
        else:
            state.end_reason = "max_turns"

        state.nodes_visited = node_tracker.visited
        return state

    async def _process_turn(
        self,
        node_id: str,
        user_message: str,
        state: ConversationState,
        node_tracker: NodeTracker,
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> tuple[str, str | None]:
        """Process a single conversation turn.

        Uses the ConversationModule to generate responses and handle transitions.

        Args:
            node_id: The current node ID.
            user_message: The user's message to respond to.
            state: Current conversation state.
            node_tracker: Tracks visited nodes.
            on_token: Optional callback for streaming tokens.
            on_error: Optional callback for error handling.

        Returns:
            Tuple of (response text, new node ID if transition occurred).
        """
        # Mock mode for testing without LLM calls
        if self._mock_mode:
            return f"[Mock response from {node_id}]", None

        # Build context for state execution
        ctx = RunContext(
            conversation_history=self._format_transcript(state.transcript),
            user_message=user_message,
            dynamic_variables=self._dynamic_variables,
            available_transitions=self._conversation_module.format_transitions(node_id),
            general_instructions=self._conversation_module.instructions,
        )

        # Get the state module and its signature
        state_module = self._conversation_module.get_state_module(node_id)
        if state_module is None:
            raise ValueError(f"Unknown node: {node_id}")

        # Wrap on_token to add source="agent"
        async def agent_token_callback(token: str) -> None:
            if on_token:
                await _invoke_callback(on_token, token, "agent")

        # Call LLM with the state module's signature
        result = await call_llm(
            self.options.agent_model,
            state_module._response_signature,
            on_token=agent_token_callback if on_token else None,
            stream_field="response" if on_token else None,
            on_error=on_error,
            general_instructions=ctx.general_instructions,
            conversation_history=ctx.conversation_history,
            user_message=ctx.user_message,
            **(
                {"available_transitions": ctx.available_transitions}
                if state_module.transitions
                else {}
            ),
        )

        # Handle transition
        new_node_id = None
        transition_target = getattr(result, "transition_to", "none")
        if transition_target:
            transition_target = transition_target.strip().lower()

        if transition_target and transition_target != "none":
            # Check for end_call
            current_node = self.graph.nodes.get(node_id)
            has_end_call = current_node and any(
                t.name == "end_call" or getattr(t, "type", "") == "end_call"
                for t in current_node.tools
            )

            if transition_target == "end_call" and has_end_call:
                state.end_call_invoked = True
                state.tools_called.append(
                    ToolCall(
                        name="end_call",
                        arguments={},
                        result="call_ended",
                    )
                )
            elif transition_target in self.graph.nodes:
                node_tracker.record(transition_target)
                state.tools_called.append(
                    ToolCall(
                        name=f"route_to_{transition_target}",
                        arguments={},
                        result=transition_target,
                    )
                )
                new_node_id = transition_target

        return result.response, new_node_id

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        if not transcript:
            return "(conversation just started)"

        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)
