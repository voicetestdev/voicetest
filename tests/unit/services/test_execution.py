"""Tests for voicetest.services.testing.execution module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import GlobalMetric
from voicetest.models.agent import MetricsConfig
from voicetest.models.results import TestResult
from voicetest.models.results import TestRun
from voicetest.models.test_case import TestCase
from voicetest.services.testing.execution import TestExecutionService


@pytest.fixture
def svc():
    return TestExecutionService()


@pytest.fixture
def graph():
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="custom",
        source_metadata={"general_prompt": "Be helpful."},
    )


@pytest.fixture
def test_case():
    return TestCase(
        name="basic_test",
        user_prompt="I need help with my account.",
        metrics=["Was the agent helpful?"],
    )


class TestRunTest:
    @pytest.mark.asyncio
    async def test_returns_test_result(self, svc, graph, test_case):
        result = await svc.run_test(graph, test_case, _mock_mode=True)
        assert isinstance(result, TestResult)

    @pytest.mark.asyncio
    async def test_pass_status(self, svc, graph, test_case):
        result = await svc.run_test(graph, test_case, _mock_mode=True)
        assert result.status == "pass"

    @pytest.mark.asyncio
    async def test_has_transcript(self, svc, graph, test_case):
        result = await svc.run_test(graph, test_case, _mock_mode=True)
        assert len(result.transcript) > 0

    @pytest.mark.asyncio
    async def test_has_metric_results(self, svc, graph, test_case):
        result = await svc.run_test(graph, test_case, _mock_mode=True)
        assert len(result.metric_results) >= 1

    @pytest.mark.asyncio
    async def test_tracks_nodes_visited(self, svc, graph, test_case):
        result = await svc.run_test(graph, test_case, _mock_mode=True)
        assert "main" in result.nodes_visited

    @pytest.mark.asyncio
    async def test_models_used_populated(self, svc, graph, test_case):
        result = await svc.run_test(graph, test_case, _mock_mode=True)
        assert result.models_used is not None
        assert result.models_used.agent is not None


class TestRunTests:
    @pytest.mark.asyncio
    async def test_returns_test_run(self, svc, graph, test_case):
        run = await svc.run_tests(graph, [test_case], _mock_mode=True)
        assert isinstance(run, TestRun)

    @pytest.mark.asyncio
    async def test_multiple_test_cases(self, svc, graph):
        cases = [
            TestCase(name="test1", user_prompt="Help me", metrics=["Was it helpful?"]),
            TestCase(name="test2", user_prompt="Billing question", metrics=["Billing resolved?"]),
        ]
        run = await svc.run_tests(graph, cases, _mock_mode=True)
        assert len(run.results) == 2

    @pytest.mark.asyncio
    async def test_empty_test_cases(self, svc, graph):
        run = await svc.run_tests(graph, [], _mock_mode=True)
        assert len(run.results) == 0


class TestEvaluateGlobalMetrics:
    @pytest.mark.asyncio
    async def test_no_enabled_global_metrics(self, svc):
        """evaluate_global_metrics returns empty when no metrics are enabled."""
        from voicetest.models.results import Message

        transcript = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        config = MetricsConfig(
            threshold=0.7,
            global_metrics=[
                GlobalMetric(name="Off", criteria="Unused", enabled=False),
            ],
        )
        results = await svc.evaluate_global_metrics(transcript, config, judge_model="mock/model")
        assert results == []

    @pytest.mark.asyncio
    async def test_empty_global_metrics(self, svc):
        """evaluate_global_metrics returns empty for empty global_metrics list."""
        from voicetest.models.results import Message

        transcript = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]
        config = MetricsConfig(threshold=0.7, global_metrics=[])
        results = await svc.evaluate_global_metrics(transcript, config, judge_model="mock/model")
        assert results == []
