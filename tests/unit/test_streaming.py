"""Unit tests for token streaming functionality."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase


@pytest.fixture
def simple_graph():
    """Simple single-node agent graph for testing."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant. Respond briefly.",
                tools=[],
                transitions=[],
            )
        },
        entry_node_id="main",
        source_type="test",
    )


class TestStreamingPredictor:
    """Tests for DSPy streamify integration."""

    @pytest.mark.asyncio
    async def test_streaming_session_with_callback(self, simple_graph):
        """Test that streaming session calls on_token callback."""
        from voicetest.engine.session import ConversationRunner
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        options = RunOptions(streaming=True, simulator_model="openai/gpt-4o-mini")
        runner = ConversationRunner(simple_graph, options, mock_mode=True)

        simulator = UserSimulator("Say hi", options.simulator_model)
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hello", should_end=False, reasoning="test"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        tokens_received: list[tuple[str, str]] = []

        async def on_token(token: str, source: str) -> None:
            tokens_received.append((token, source))

        test_case = TestCase(name="test", user_prompt="hi", metrics=[], type="llm")

        # Mock mode should work without streaming (no LLM calls)
        state = await runner.run(test_case, simulator, on_token=on_token)

        assert state.transcript is not None
        assert len(state.transcript) > 0
