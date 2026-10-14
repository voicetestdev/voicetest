"""Integration tests for token streaming with real LLM calls."""

import dspy
import pytest

from voicetest.llm import call_llm
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import NodeType
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.services.settings import SettingsService
from voicetest.services.testing.execution import TestExecutionService


# The agent's turns run against the local ollama model in the service stack, so
# these stream real tokens without any external LLM key.
MODEL = "ollama_chat/qwen2.5:0.5b"

pytestmark = pytest.mark.stack


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
                node_type=NodeType.CONVERSATION,
            )
        },
        entry_node_id="main",
        source_type="test",
    )


@pytest.fixture
def simple_test_case():
    """Simple test case for streaming tests."""
    return TestCase(
        name="streaming_test",
        user_prompt="Say hello and ask how you can help.",
        metrics=["Agent greeted the user"],
        type="llm",
    )


class TestStreamingWithLLM:
    """Streaming tests that require a configured LLM provider."""

    @pytest.mark.asyncio
    async def test_streaming_with_real_llm(self, simple_graph, simple_test_case):
        """Test streaming with actual LLM call."""

        tokens_received: list[tuple[str, str]] = []

        async def on_token(token: str, source: str) -> None:
            tokens_received.append((token, source))

        options = RunOptions(
            streaming=True,
            max_turns=2,
            agent_model=MODEL,
            simulator_model=MODEL,
            judge_model=MODEL,
        )

        result = await TestExecutionService(SettingsService()).run_test(
            simple_graph,
            simple_test_case,
            options=options,
            on_token=on_token,
        )

        assert result.status in ("pass", "fail"), f"Got error: {result.error_message}"
        assert len(result.transcript) > 0

        print(f"Received {len(tokens_received)} tokens")


class TestCallLlmStreamingIntegration:
    """Streaming through call_llm against a real model."""

    @pytest.mark.asyncio
    async def test_call_llm_streaming_basic(self):
        """call_llm streams tokens and returns a parsed Prediction."""

        class SimpleSignature(dspy.Signature):
            """Answer a simple question."""

            question: str = dspy.InputField()
            answer: str = dspy.OutputField()

        tokens_received: list[str] = []

        result = await call_llm(
            MODEL,
            SimpleSignature,
            on_token=tokens_received.append,
            stream_field="answer",
            predictor_class=dspy.Predict,
            question="What is 2+2?",
        )

        assert "4" in result.answer or "four" in result.answer.lower()
        assert "".join(tokens_received)
