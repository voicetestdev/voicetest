"""Integration tests using Ollama for local LLM execution.

These tests require Ollama to be running locally with the qwen2.5:0.5b model.
Run: ollama pull qwen2.5:0.5b

To run these tests:
    uv run pytest tests/integration -v
"""

import subprocess

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase


def ollama_available() -> bool:
    """Check if Ollama is running and has the required model."""
    try:
        result = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
        return "qwen2.5:0.5b" in result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(
    not ollama_available(), reason="Ollama not available or qwen2.5:0.5b not installed"
)


@pytest.fixture
def ollama_options() -> RunOptions:
    """Run options configured for Ollama."""
    return RunOptions(
        agent_model="ollama_chat/qwen2.5:0.5b",
        simulator_model="ollama_chat/qwen2.5:0.5b",
        judge_model="ollama_chat/qwen2.5:0.5b",
        max_turns=4,
        verbose=True,
    )


@pytest.fixture
def simple_graph() -> AgentGraph:
    """A simple customer service agent graph."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the customer warmly. Ask how you can help them today.",
                transitions=[
                    Transition(
                        target_node_id="help",
                        condition=TransitionCondition(
                            type="llm_prompt", value="Customer states what they need help with"
                        ),
                    )
                ],
            ),
            "help": AgentNode(
                id="help",
                state_prompt="Help the customer with their request. Be helpful and concise.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(
                            type="llm_prompt", value="Customer seems satisfied or says goodbye"
                        ),
                    )
                ],
            ),
            "end": AgentNode(
                id="end",
                state_prompt="Thank the customer and end the conversation politely.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


@pytest.fixture
def simple_test_case() -> TestCase:
    """A simple test case for greeting behavior."""
    return TestCase(
        name="Basic greeting test",
        user_prompt="When asked for name, say Alex. Say hello and ask about store hours.",
        metrics=["Agent greeted the user."],
    )


class TestOllamaExecution:
    """Integration tests for real LLM execution with Ollama."""

    @pytest.mark.asyncio
    async def test_run_single_test(self, simple_graph, simple_test_case, ollama_options):
        """Test running a single test case with Ollama."""
        from voicetest.services.testing.execution import TestExecutionService

        result = await TestExecutionService().run_test(
            simple_graph,
            simple_test_case,
            options=ollama_options,
        )

        assert result.test_id == "Basic greeting test"
        assert result.status in ("pass", "fail", "error")
        assert result.turn_count > 0
        assert len(result.transcript) > 0
        assert "greeting" in result.nodes_visited
        assert len(result.metric_results) > 0

    @pytest.mark.asyncio
    async def test_conversation_has_content(self, simple_graph, simple_test_case, ollama_options):
        """Test that the conversation actually produces meaningful content."""
        from voicetest.services.testing.execution import TestExecutionService

        result = await TestExecutionService().run_test(
            simple_graph,
            simple_test_case,
            options=ollama_options,
        )

        for msg in result.transcript:
            assert msg.content, f"Empty message from {msg.role}"
            assert len(msg.content) > 0

    @pytest.mark.asyncio
    async def test_user_simulator_responds_to_agent(
        self, simple_graph, simple_test_case, ollama_options
    ):
        """Test that the user simulator generates contextual responses."""
        from voicetest.services.testing.execution import TestExecutionService

        result = await TestExecutionService().run_test(
            simple_graph,
            simple_test_case,
            options=ollama_options,
        )

        user_messages = [m for m in result.transcript if m.role == "user"]
        assistant_messages = [m for m in result.transcript if m.role == "assistant"]

        assert len(user_messages) > 0, "No user messages in transcript"
        assert len(assistant_messages) > 0, "No assistant messages in transcript"

    @pytest.mark.asyncio
    async def test_metric_evaluation_has_reasoning(
        self, simple_graph, simple_test_case, ollama_options
    ):
        """Test that metric evaluation includes reasoning."""
        from voicetest.services.testing.execution import TestExecutionService

        result = await TestExecutionService().run_test(
            simple_graph,
            simple_test_case,
            options=ollama_options,
        )

        for metric_result in result.metric_results:
            assert metric_result.reasoning, f"No reasoning for metric: {metric_result.metric}"
            assert len(metric_result.reasoning) > 0


class TestOllamaMultipleTests:
    """Integration tests for running multiple tests."""

    @pytest.mark.asyncio
    async def test_run_multiple_tests(self, simple_graph, ollama_options):
        """Test running multiple test cases."""
        from voicetest.services.testing.execution import TestExecutionService

        test_cases = [
            TestCase(
                name="Greeting test",
                user_prompt="When asked for name, say Bob. Say hello.",
                metrics=["Agent greeted the user."],
            ),
            TestCase(
                name="Question test",
                user_prompt="When asked for name, say Alice. Ask about store hours.",
                metrics=["Agent responded to question."],
            ),
        ]

        run = await TestExecutionService().run_tests(
            simple_graph, test_cases, options=ollama_options
        )

        assert len(run.results) == 2
        assert run.results[0].test_id == "Greeting test"
        assert run.results[1].test_id == "Question test"
