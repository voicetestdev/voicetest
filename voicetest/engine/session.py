"""Conversation session management.

Wraps the execution of conversations using generated agents.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import dspy

from voicetest.engine.agent_gen import GeneratedAgent, generate_agent_classes
from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message, ToolCall
from voicetest.models.test_case import RunOptions
from voicetest.utils import DSPyAdapterMixin, substitute_variables


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


class NodeTracker:
    """Tracks node visits during conversation."""

    def __init__(self):
        self.visited: list[str] = []
        self.current_node: str | None = None

    def record(self, node_id: str) -> None:
        """Record a node visit."""
        self.visited.append(node_id)
        self.current_node = node_id


class ConversationRunner(DSPyAdapterMixin):
    """Runs simulated conversations.

    This class orchestrates the conversation loop, managing:
    - Agent class instantiation
    - Turn-by-turn execution
    - State tracking
    """

    def __init__(
        self,
        graph: AgentGraph,
        options: RunOptions | None = None,
        mock_mode: bool = False,
        dynamic_variables: dict | None = None,
        adapter: dspy.Adapter | None = None,
    ):
        self.graph = graph
        self.options = options or RunOptions()
        self.agent_classes = generate_agent_classes(graph)
        self._mock_mode = mock_mode
        self._dynamic_variables = dynamic_variables or {}
        self._adapter = adapter

    async def run(
        self,
        test_case: "TestCase",  # noqa: F821 - Forward reference
        user_simulator: "UserSimulator",  # noqa: F821 - Forward reference
        on_turn: OnTurnCallback | None = None,
        on_token: OnTokenCallback | None = None,
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

        Returns:
            ConversationState with transcript and tracking data.
        """
        state = ConversationState()
        node_tracker = NodeTracker()

        # Start at entry node
        node_tracker.record(self.graph.entry_node_id)
        current_agent = self.agent_classes[self.graph.entry_node_id]()

        for _turn in range(self.options.max_turns):
            # Get simulated user input
            sim_response = await user_simulator.generate(
                state.transcript,
                on_token=on_token if self.options.streaming else None,
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

            # Process with current agent
            response, new_agent = await self._process_turn(
                current_agent,
                sim_response.message,
                state,
                node_tracker,
                on_token=on_token if self.options.streaming else None,
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
            if new_agent is not None:
                current_agent = new_agent

            state.turn_count += 1

            # Check for agent-initiated end
            if self._should_end_conversation(current_agent, state):
                state.end_reason = "agent_ended"
                break
        else:
            state.end_reason = "max_turns"

        state.nodes_visited = node_tracker.visited
        return state

    async def _process_turn(
        self,
        agent: GeneratedAgent,
        user_message: str,
        state: ConversationState,
        node_tracker: NodeTracker,
        on_token: OnTokenCallback | None = None,
    ) -> tuple[str, GeneratedAgent | None]:
        """Process a single conversation turn.

        Uses DSPy to generate agent responses and handle transitions.

        Args:
            agent: The current agent instance.
            user_message: The user's message to respond to.
            state: Current conversation state.
            node_tracker: Tracks visited nodes.
            on_token: Optional callback for streaming tokens.

        Returns:
            Tuple of (response text, new agent if transition occurred).
        """
        # Mock mode for testing without LLM calls
        if self._mock_mode:
            return self._mock_response(agent, user_message), None

        lm = dspy.LM(self.options.agent_model)

        # Build available tools description
        tools_desc = self._format_tools(agent)

        class AgentResponseSignature(dspy.Signature):
            """Generate agent response in a voice conversation."""

            agent_instructions: str = dspy.InputField(desc="System instructions for the agent")
            available_transitions: str = dspy.InputField(
                desc="Available transitions to other agents/nodes"
            )
            conversation_history: str = dspy.InputField(desc="Conversation so far")
            user_message: str = dspy.InputField(desc="Latest user message to respond to")

            response: str = dspy.OutputField(desc="Agent's spoken response to the user")
            transition_to: str = dspy.OutputField(
                desc="Node ID to transition to, or 'none' to stay"
            )

        agent_instructions = substitute_variables(agent.instructions, self._dynamic_variables)
        conversation_history = self._format_transcript(state.transcript)

        if on_token:
            # Streaming mode: use streamify to get tokens as they're generated
            result = await self._process_turn_streaming(
                lm,
                AgentResponseSignature,
                agent_instructions,
                tools_desc,
                conversation_history,
                user_message,
                on_token,
            )
        else:
            # Non-streaming mode: blocking call in thread pool
            ctx = self._dspy_context(lm)

            def run_predictor():
                with ctx:
                    predictor = dspy.Predict(AgentResponseSignature)
                    return predictor(
                        agent_instructions=agent_instructions,
                        available_transitions=tools_desc,
                        conversation_history=conversation_history,
                        user_message=user_message,
                    )

            result = await asyncio.to_thread(run_predictor)

        # Handle transition
        new_agent = None
        transition_target = result.transition_to.strip().lower()
        if transition_target and transition_target != "none":
            # Find matching transition
            for tool in agent._transition_tools:
                if tool.__name__ == f"route_to_{transition_target}":
                    node_tracker.record(transition_target)
                    state.tools_called.append(
                        ToolCall(
                            name=tool.__name__,
                            arguments={},
                            result=transition_target,
                        )
                    )
                    if transition_target in self.agent_classes:
                        new_agent = self.agent_classes[transition_target]()
                    break

        return result.response, new_agent

    async def _process_turn_streaming(
        self,
        lm: dspy.LM,
        signature_class: type,
        agent_instructions: str,
        tools_desc: str,
        conversation_history: str,
        user_message: str,
        on_token: OnTokenCallback,
    ) -> dspy.Prediction:
        """Process turn with streaming, yielding tokens via callback.

        Uses DSPy's streamify to get tokens as they're generated.
        """
        from dspy.streaming import StreamListener, streamify

        predictor = dspy.Predict(signature_class)
        stream_listeners = [StreamListener(signature_field_name="response")]

        streaming_predictor = streamify(
            predictor,
            stream_listeners=stream_listeners,
            is_async_program=False,
        )

        result = None
        with self._dspy_context(lm):
            async for chunk in streaming_predictor(
                agent_instructions=agent_instructions,
                available_transitions=tools_desc,
                conversation_history=conversation_history,
                user_message=user_message,
            ):
                if isinstance(chunk, dspy.Prediction):
                    result = chunk
                elif (
                    hasattr(chunk, "chunk")
                    and hasattr(chunk, "signature_field_name")
                    and chunk.signature_field_name == "response"
                ):
                    # StreamResponse with token data for response field
                    await _invoke_callback(on_token, chunk.chunk, "agent")

        if result is None:
            raise RuntimeError("Streaming predictor did not return a Prediction")

        return result

    def _format_tools(self, agent: GeneratedAgent) -> str:
        """Format available transition tools for LLM."""
        if not agent._transition_tools:
            return "(no transitions available - this is a terminal node)"

        lines = []
        for tool in agent._transition_tools:
            target = tool.__name__.replace("route_to_", "")
            condition = tool.__doc__ or "No condition specified"
            lines.append(f"- {target}: {condition}")
        return "\n".join(lines)

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        if not transcript:
            return "(conversation just started)"

        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)

    def _mock_response(self, agent: GeneratedAgent, user_message: str) -> str:
        """Generate mock response for testing."""
        return f"[Mock response from {agent._node_id}]"

    def _should_end_conversation(
        self,
        agent: GeneratedAgent,
        state: ConversationState,
    ) -> bool:
        """Check if the agent has signaled conversation end."""
        # Terminal node (no transitions) means conversation should end
        return len(agent._transition_tools) == 0
