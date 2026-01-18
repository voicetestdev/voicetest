"""Tests for the core API."""

import pytest


class TestImportAgent:
    """Tests for import_agent API function."""

    @pytest.mark.asyncio
    async def test_import_agent_from_dict(self, sample_retell_config):
        from voicetest import api

        graph = await api.import_agent(sample_retell_config)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4

    @pytest.mark.asyncio
    async def test_import_agent_from_path(self, sample_retell_config_path):
        from voicetest import api

        graph = await api.import_agent(sample_retell_config_path)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"

    @pytest.mark.asyncio
    async def test_import_agent_with_explicit_source(self, sample_retell_config):
        from voicetest import api

        graph = await api.import_agent(sample_retell_config, source="retell")

        assert graph.source_type == "retell"

    @pytest.mark.asyncio
    async def test_import_agent_custom_function(self):
        from voicetest import api
        from voicetest.models.agent import AgentGraph, AgentNode

        def create_agent() -> AgentGraph:
            return AgentGraph(
                nodes={"start": AgentNode(id="start", instructions="Hello")},
                entry_node_id="start",
                source_type="custom",
            )

        graph = await api.import_agent(create_agent, source="custom")

        assert graph.source_type == "custom"
        assert graph.entry_node_id == "start"

    @pytest.mark.asyncio
    async def test_import_agent_unknown_source_raises(self, sample_retell_config):
        from voicetest import api

        with pytest.raises(ValueError, match="Unknown importer"):
            await api.import_agent(sample_retell_config, source="nonexistent")

    @pytest.mark.asyncio
    async def test_import_agent_no_match_raises(self):
        from voicetest import api

        with pytest.raises(ValueError, match="Could not auto-detect"):
            await api.import_agent({"unknown": "config"})


class TestListImporters:
    """Tests for list_importers API function."""

    def test_list_importers_returns_list(self):
        from voicetest import api

        importers = api.list_importers()

        assert isinstance(importers, list)
        assert len(importers) >= 2  # At least retell and custom

    def test_list_importers_includes_retell(self):
        from voicetest import api

        importers = api.list_importers()
        types = [i.source_type for i in importers]

        assert "retell" in types

    def test_list_importers_includes_custom(self):
        from voicetest import api

        importers = api.list_importers()
        types = [i.source_type for i in importers]

        assert "custom" in types


class TestRunTest:
    """Tests for run_test function."""

    @pytest.mark.asyncio
    async def test_run_test_returns_result(self, sample_retell_config):
        from voicetest import api
        from voicetest.models.results import TestResult
        from voicetest.models.test_case import RunOptions, TestCase

        graph = await api.import_agent(sample_retell_config)
        test_case = TestCase(
            name="Test",
            user_prompt="When asked, say John. Say hi.",
        )

        result = await api.run_test(
            graph, test_case, options=RunOptions(max_turns=2), _mock_mode=True
        )

        assert isinstance(result, TestResult)
        assert result.test_id == "Test"


class TestRunTests:
    """Tests for run_tests function."""

    @pytest.mark.asyncio
    async def test_run_tests_returns_run(self, sample_retell_config):
        from voicetest import api
        from voicetest.models.results import TestRun
        from voicetest.models.test_case import RunOptions, TestCase

        graph = await api.import_agent(sample_retell_config)
        test_cases = [
            TestCase(
                name="T1",
                user_prompt="When asked, say A. Do X.",
            ),
        ]

        result = await api.run_tests(
            graph, test_cases, options=RunOptions(max_turns=2), _mock_mode=True
        )

        assert isinstance(result, TestRun)
        assert len(result.results) == 1


class TestExportAgent:
    """Tests for export_agent function."""

    @pytest.mark.asyncio
    async def test_export_mermaid(self, sample_retell_config):
        from voicetest import api

        graph = await api.import_agent(sample_retell_config)

        result = await api.export_agent(graph, format="mermaid")

        assert "flowchart" in result.lower()
        assert "greeting" in result

    @pytest.mark.asyncio
    async def test_export_livekit(self, sample_retell_config):
        from voicetest import api

        graph = await api.import_agent(sample_retell_config)

        result = await api.export_agent(graph, format="livekit")

        assert "class Agent_greeting" in result


class TestRunTestWithMetricsConfig:
    """Tests for run_test with MetricsConfig."""

    @pytest.mark.asyncio
    async def test_run_test_with_global_metrics(self, sample_retell_config):
        from voicetest import api
        from voicetest.models.agent import GlobalMetric, MetricsConfig
        from voicetest.models.test_case import RunOptions, TestCase

        graph = await api.import_agent(sample_retell_config)
        test_case = TestCase(
            name="Test",
            user_prompt="When asked, say John. Say hi.",
            metrics=["Agent greeted user"],
        )
        metrics_config = MetricsConfig(
            threshold=0.7,
            global_metrics=[
                GlobalMetric(name="HIPAA", criteria="Check HIPAA compliance"),
            ],
        )

        result = await api.run_test(
            graph,
            test_case,
            options=RunOptions(max_turns=2),
            metrics_config=metrics_config,
            _mock_mode=True,
        )

        # Should have test metrics + global metrics
        assert len(result.metric_results) == 2
        metric_names = [r.metric for r in result.metric_results]
        assert "Agent greeted user" in metric_names
        assert "[HIPAA]" in metric_names

    @pytest.mark.asyncio
    async def test_run_test_global_metric_disabled(self, sample_retell_config):
        from voicetest import api
        from voicetest.models.agent import GlobalMetric, MetricsConfig
        from voicetest.models.test_case import RunOptions, TestCase

        graph = await api.import_agent(sample_retell_config)
        test_case = TestCase(
            name="Test",
            user_prompt="When asked, say John. Say hi.",
            metrics=["Agent greeted user"],
        )
        metrics_config = MetricsConfig(
            threshold=0.7,
            global_metrics=[
                GlobalMetric(name="Disabled", criteria="Should not run", enabled=False),
            ],
        )

        result = await api.run_test(
            graph,
            test_case,
            options=RunOptions(max_turns=2),
            metrics_config=metrics_config,
            _mock_mode=True,
        )

        # Disabled global metric should not run
        assert len(result.metric_results) == 1
        assert result.metric_results[0].metric == "Agent greeted user"


class TestEvaluateTranscript:
    """Tests for evaluate_transcript function."""

    @pytest.mark.asyncio
    async def test_evaluate_transcript_returns_results(self):
        from voicetest import api
        from voicetest.models.results import Message, MetricResult

        transcript = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]

        results = await api.evaluate_transcript(
            transcript, metrics=["Greeted user"], _mock_mode=True
        )

        assert len(results) == 1
        assert isinstance(results[0], MetricResult)
