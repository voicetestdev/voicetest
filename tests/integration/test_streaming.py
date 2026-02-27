"""Integration tests for token streaming with real LLM calls."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.settings import DEFAULT_MODEL
from voicetest.settings import load_settings


# Load settings and apply env vars for API keys
_settings = load_settings()
_settings.apply_env()


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
        from voicetest.services.testing.execution import TestExecutionService

        tokens_received: list[tuple[str, str]] = []

        async def on_token(token: str, source: str) -> None:
            tokens_received.append((token, source))

        options = RunOptions(
            streaming=True,
            max_turns=2,
            agent_model=DEFAULT_MODEL,
            simulator_model=DEFAULT_MODEL,
            judge_model=DEFAULT_MODEL,
        )

        result = await TestExecutionService().run_test(
            simple_graph,
            simple_test_case,
            options=options,
            on_token=on_token,
        )

        # Handle rate limit errors gracefully - external API issue, not our code
        err = (result.error_message or "").lower()
        if result.status == "error" and "rate" in err and "limit" in err:
            import warnings

            warnings.warn(
                f"RATE LIMITED - Test skipped: {result.error_message[:100]}",
                UserWarning,
                stacklevel=1,
            )
            pytest.skip("Rate limited by external API")

        # Should complete without error
        assert result.status in ("pass", "fail"), f"Got error: {result.error_message}"
        assert len(result.transcript) > 0

        # If streaming worked, we should have received tokens
        print(f"Received {len(tokens_received)} tokens")


class TestStreamifyIntegration:
    """Direct tests for DSPy streamify usage."""

    @pytest.mark.asyncio
    async def test_streamify_basic(self):
        """Test basic DSPy streamify functionality."""
        import dspy
        from dspy.streaming import StreamListener
        from dspy.streaming import streamify

        lm = dspy.LM(DEFAULT_MODEL)

        class SimpleSignature(dspy.Signature):
            """Answer a simple question."""

            question: str = dspy.InputField()
            answer: str = dspy.OutputField()

        predictor = dspy.Predict(SimpleSignature)
        stream_listeners = [StreamListener(signature_field_name="answer")]

        streaming_predictor = streamify(
            predictor,
            stream_listeners=stream_listeners,
            is_async_program=False,
        )

        chunks_received = []
        result = None

        with dspy.context(lm=lm):
            async for chunk in streaming_predictor(question="What is 2+2?"):
                if isinstance(chunk, dspy.Prediction):
                    result = chunk
                elif hasattr(chunk, "chunk"):
                    chunks_received.append(chunk.chunk)

        assert result is not None
        assert "4" in result.answer or "four" in result.answer.lower()
        print(f"Received {len(chunks_received)} chunks")
