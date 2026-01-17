"""Tests for voicetest.judges.metric module."""

import pytest

from voicetest.models.results import Message


class TestMetricJudge:
    """Tests for MetricJudge."""

    def test_create_judge(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge()

        assert judge is not None

    def test_create_judge_with_custom_model(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge(model="openai/gpt-4o")

        assert judge.model == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_evaluate_returns_metric_result(self):
        from voicetest.judges.metric import MetricJudge
        from voicetest.models.results import MetricResult

        judge = MetricJudge()

        transcript = [
            Message(role="assistant", content="Hello! How can I help you today?"),
            Message(role="user", content="I need help with my order"),
            Message(role="assistant", content="I'd be happy to help with your order."),
        ]

        # Use mock mode for testing
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(
                metric="Agent greeted the customer",
                passed=True,
                reasoning="Agent said 'Hello! How can I help you today?'",
                confidence=0.95,
            )
        ]

        result = await judge.evaluate(transcript, "Agent greeted the customer")

        assert isinstance(result, MetricResult)
        assert result.metric == "Agent greeted the customer"
        assert isinstance(result.passed, bool)
        assert isinstance(result.reasoning, str)

    @pytest.mark.asyncio
    async def test_evaluate_all_returns_list(self):
        from voicetest.judges.metric import MetricJudge
        from voicetest.models.results import MetricResult

        judge = MetricJudge()

        transcript = [
            Message(role="assistant", content="Hello!"),
            Message(role="user", content="Hi"),
        ]

        metrics = [
            "Agent greeted the customer",
            "Agent was professional",
            "Agent resolved the issue",
        ]

        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(metric=m, passed=True, reasoning="Test") for m in metrics
        ]

        results = await judge.evaluate_all(transcript, metrics)

        assert len(results) == 3
        assert all(isinstance(r, MetricResult) for r in results)

    def test_format_transcript(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge()

        transcript = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]

        formatted = judge._format_transcript(transcript)

        assert "USER: Hello" in formatted
        assert "ASSISTANT: Hi there!" in formatted
