"""Conversation session management.

Wraps the execution of conversations using the ConversationEngine.
"""

import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field

from voicetest.engine.conversation import ConversationEngine
from voicetest.engine.modules import ConversationModule
from voicetest.llm import _invoke_callback
from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message
from voicetest.models.results import ToolCall
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
    ):
        self.graph = graph
        self.options = options or RunOptions()
        self._mock_mode = mock_mode
        self._dynamic_variables = dynamic_variables or {}

        self._conversation_module = ConversationModule(graph)

        # Engine for actual turn processing (not used in mock mode)
        self._engine: ConversationEngine | None = None
        if not mock_mode:
            self._engine = ConversationEngine(
                graph=graph,
                model=self.options.agent_model,
                options=self.options,
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
        1. Agent processes graph until it speaks (entry preamble)
        2. Loop: get user input -> agent processes graph until speech
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
        if self._mock_mode:
            return await self._run_mock(test_case, user_simulator, on_turn, on_token, on_error)

        state = ConversationState()

        # Wrap on_token to add source="agent"
        agent_token_cb = None
        if on_token and self.options.streaming:

            async def agent_token_cb(token: str) -> None:
                await _invoke_callback(on_token, token, "agent")

        # Entry: agent processes graph until it speaks
        await self._engine.advance(
            on_token=agent_token_cb,
            on_error=on_error,
        )
        if on_turn:
            await _invoke_callback(on_turn, self._engine.transcript)

        turn_timeout = self.options.turn_timeout_seconds

        for _turn in range(self.options.max_turns):
            try:
                # Get simulated user input
                sim_response = await asyncio.wait_for(
                    user_simulator.generate(
                        self._engine.transcript,
                        on_token=on_token if self.options.streaming else None,
                        on_error=on_error,
                    ),
                    timeout=turn_timeout,
                )
            except TimeoutError:
                state.end_reason = "turn_timeout"
                break

            if sim_response.should_end:
                state.end_reason = "user_ended"
                break

            self._engine.add_user_message(sim_response.message)
            if on_turn:
                await _invoke_callback(on_turn, self._engine.transcript)

            try:
                await asyncio.wait_for(
                    self._engine.advance(
                        on_token=agent_token_cb,
                        on_error=on_error,
                    ),
                    timeout=turn_timeout,
                )
            except TimeoutError:
                state.end_reason = "turn_timeout"
                break

            if on_turn:
                await _invoke_callback(on_turn, self._engine.transcript)

            state.turn_count += 1

            if self._engine.end_call_invoked:
                state.end_reason = "agent_ended"
                break
        else:
            state.end_reason = "max_turns"

        state.transcript = self._engine.transcript
        state.nodes_visited = self._engine.nodes_visited
        state.tools_called = self._engine.tools_called
        state.end_call_invoked = self._engine.end_call_invoked
        return state

    async def _run_mock(
        self,
        test_case,
        user_simulator,
        on_turn=None,
        on_token=None,
        on_error=None,
    ) -> ConversationState:
        """Run a conversation in mock mode (no LLM calls)."""
        state = ConversationState()
        node_tracker = NodeTracker()
        node_tracker.record(self.graph.entry_node_id)
        current_node_id = self.graph.entry_node_id

        for _turn in range(self.options.max_turns):
            sim_response = await user_simulator.generate(
                state.transcript,
                on_token=on_token if self.options.streaming else None,
                on_error=on_error,
            )

            if sim_response.should_end:
                state.end_reason = "user_ended"
                break

            state.transcript.append(
                Message(
                    role="user",
                    content=sim_response.message,
                    metadata={"node_id": node_tracker.current_node},
                )
            )

            response = f"[Mock response from {current_node_id}]"
            state.transcript.append(
                Message(
                    role="assistant",
                    content=response,
                    metadata={"node_id": node_tracker.current_node},
                )
            )

            if on_turn:
                await _invoke_callback(on_turn, state.transcript)

            state.turn_count += 1
        else:
            state.end_reason = "max_turns"

        state.nodes_visited = node_tracker.visited
        return state
