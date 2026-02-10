"""Conversation session management.

Wraps the execution of conversations using the ConversationEngine.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from voicetest.engine.conversation import ConversationEngine
from voicetest.engine.modules import ConversationModule
from voicetest.llm import _invoke_callback
from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message, ToolCall
from voicetest.models.test_case import RunOptions
from voicetest.retry import OnErrorCallback


# Callback type for turn updates: receives transcript after each turn
OnTurnCallback = Callable[[list[Message]], Awaitable[None] | None]

# Callback type for token updates: receives token string and source ("agent" or "user")
OnTokenCallback = Callable[[str, str], Awaitable[None] | None]


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

    This class orchestrates the conversation loop, delegating turn processing
    to ConversationEngine for consistent behavior between tests and live calls.
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

        # Keep _conversation_module for backward compatibility with tests
        # that access it directly
        self._conversation_module = ConversationModule(
            graph, use_cot_transitions=use_cot_transitions
        )

        # Engine for actual turn processing (not used in mock mode)
        self._engine: ConversationEngine | None = None
        if not mock_mode:
            # Apply cot_transitions setting to options
            effective_options = RunOptions(
                **{
                    **self.options.model_dump(),
                    "cot_transitions": use_cot_transitions,
                }
            )
            self._engine = ConversationEngine(
                graph=graph,
                model=self.options.agent_model,
                options=effective_options,
                dynamic_variables=dynamic_variables,
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

        Delegates to ConversationEngine for consistent behavior with live calls.

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

        # Wrap on_token to add source="agent"
        async def agent_token_callback(token: str) -> None:
            if on_token:
                await _invoke_callback(on_token, token, "agent")

        # Use the engine for turn processing (same logic as live calls)
        # But we need to sync the engine's state with our state tracking
        # The engine manages its own transcript, so we need to sync carefully

        # Sync engine to current node if needed
        if self._engine._current_node != node_id:
            self._engine._current_node = node_id

        # Sync transcript to engine (excluding the user message we just added to state)
        # The engine maintains its own transcript, but we need to keep them in sync
        # for the context to be correct
        self._engine._transcript = [
            msg for msg in state.transcript if msg.role != "user" or msg.content != user_message
        ]

        # Process turn through engine
        result = await self._engine.process_turn(
            user_message,
            on_token=agent_token_callback if on_token else None,
            on_error=on_error,
        )

        # Sync state from engine result
        new_node_id = None
        if result.transitioned_to:
            node_tracker.record(result.transitioned_to)
            new_node_id = result.transitioned_to

        if result.end_call_invoked:
            state.end_call_invoked = True

        # Add tool calls from engine to state
        state.tools_called.extend(result.tool_calls)

        return result.response, new_node_id
