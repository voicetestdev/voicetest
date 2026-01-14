"""Integration tests for the complete voicetest flow."""

import pytest

from voicetest.models.agent import AgentGraph, AgentNode, Transition, TransitionCondition
from voicetest.models.results import Message, MetricResult
from voicetest.models.test_case import RunOptions, TestCase


@pytest.fixture
def simple_agent_graph() -> AgentGraph:
    """Create a simple agent graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the customer warmly and ask how you can help.",
                transitions=[
                    Transition(
                        target_node_id="help",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="Customer states their problem"
                        )
                    )
                ]
            ),
            "help": AgentNode(
                id="help",
                instructions="Help the customer with their request.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="Customer is satisfied"
                        )
                    )
                ]
            ),
            "end": AgentNode(
                id="end",
                instructions="Thank the customer and end the call politely.",
                transitions=[]
            )
        },
        entry_node_id="greeting",
        source_type="custom"
    )


@pytest.fixture
def simple_test_case() -> TestCase:
    """Create a simple test case."""
    return TestCase(
        id="greeting-test",
        name="Greeting test",
        user_prompt="""
## Identity
Your name is Test User.

## Goal
Say hello and see how the agent responds.

## Personality
Brief and polite.
""",
        metrics=["Agent greeted the user"],
        required_nodes=["greeting"],
        max_turns=3
    )


class TestEndToEndFlow:
    """End-to-end integration tests."""

    @pytest.mark.asyncio
    async def test_import_retell_config(self, sample_retell_config):
        from voicetest import api

        graph = await api.import_agent(sample_retell_config)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4

    @pytest.mark.asyncio
    async def test_run_test_returns_result(self, simple_agent_graph, simple_test_case):
        from voicetest import api
        from voicetest.models.results import TestResult

        # Use mock options for testing
        options = RunOptions(max_turns=2)

        result = await api.run_test(
            simple_agent_graph,
            simple_test_case,
            options=options,
            _mock_mode=True
        )

        assert isinstance(result, TestResult)
        assert result.test_id == "greeting-test"
        assert result.status in ("pass", "fail", "error")

    @pytest.mark.asyncio
    async def test_run_tests_returns_run(self, simple_agent_graph):
        from voicetest import api
        from voicetest.models.results import TestRun

        test_cases = [
            TestCase(
                id="t1",
                name="Test 1",
                user_prompt="## Identity\nJohn\n\n## Goal\nHello\n\n## Personality\nBrief",
                max_turns=2
            ),
            TestCase(
                id="t2",
                name="Test 2",
                user_prompt="## Identity\nJane\n\n## Goal\nBye\n\n## Personality\nPolite",
                max_turns=2
            )
        ]

        result = await api.run_tests(
            simple_agent_graph,
            test_cases,
            _mock_mode=True
        )

        assert isinstance(result, TestRun)
        assert len(result.results) == 2

    @pytest.mark.asyncio
    async def test_evaluate_transcript_returns_results(self):
        from voicetest import api

        transcript = [
            Message(role="assistant", content="Hello! How can I help you?"),
            Message(role="user", content="I need help with my bill"),
            Message(role="assistant", content="I'd be happy to help with your billing question."),
        ]

        results = await api.evaluate_transcript(
            transcript,
            metrics=["Agent greeted the user", "Agent acknowledged the request"],
            _mock_mode=True
        )

        assert len(results) == 2
        assert all(isinstance(r, MetricResult) for r in results)


class TestRunTestBehavior:
    """Tests for run_test behavior."""

    @pytest.mark.asyncio
    async def test_run_test_tracks_nodes(self, simple_agent_graph, simple_test_case):
        from voicetest import api

        result = await api.run_test(
            simple_agent_graph,
            simple_test_case,
            _mock_mode=True
        )

        # Should have visited at least the entry node
        assert "greeting" in result.nodes_visited

    @pytest.mark.asyncio
    async def test_run_test_evaluates_metrics(self, simple_agent_graph, simple_test_case):
        from voicetest import api

        result = await api.run_test(
            simple_agent_graph,
            simple_test_case,
            _mock_mode=True
        )

        # Should have evaluated the metrics
        assert len(result.metric_results) == len(simple_test_case.metrics)

    @pytest.mark.asyncio
    async def test_run_test_checks_flow_constraints(self, simple_agent_graph):
        from voicetest import api

        test_case = TestCase(
            id="flow-test",
            name="Flow test",
            user_prompt="## Identity\nTest\n\n## Goal\nTest\n\n## Personality\nTest",
            required_nodes=["greeting", "nonexistent"],
            max_turns=2
        )

        result = await api.run_test(
            simple_agent_graph,
            test_case,
            _mock_mode=True
        )

        # Should detect the missing required node
        assert len(result.constraint_violations) > 0
        assert any("nonexistent" in v for v in result.constraint_violations)


class TestExportAgent:
    """Tests for export_agent function."""

    @pytest.mark.asyncio
    async def test_export_mermaid(self, simple_agent_graph):
        from voicetest import api

        result = await api.export_agent(simple_agent_graph, format="mermaid")

        assert "flowchart" in result.lower()
        assert "greeting" in result
        assert "help" in result
        assert "end" in result

    @pytest.mark.asyncio
    async def test_export_livekit(self, simple_agent_graph):
        from voicetest import api

        result = await api.export_agent(simple_agent_graph, format="livekit")

        assert "class Agent_greeting" in result
        assert "def __init__" in result
