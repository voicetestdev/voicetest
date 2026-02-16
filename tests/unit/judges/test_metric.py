"""Tests for voicetest.judges.metric module."""

import pytest

from voicetest.models.results import Message


class TestMetricJudge:
    """Tests for MetricJudge."""

    def test_create_judge(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge("openai/gpt-4o-mini")

        assert judge is not None

    def test_create_judge_with_custom_model(self):
        from voicetest.judges.metric import MetricJudge

        judge = MetricJudge(model="openai/gpt-4o")

        assert judge.model == "openai/gpt-4o"

    @pytest.mark.asyncio
    async def test_evaluate_returns_metric_result(self):
        from voicetest.judges.metric import MetricJudge
        from voicetest.models.results import MetricResult

        judge = MetricJudge("openai/gpt-4o-mini")

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

        judge = MetricJudge("openai/gpt-4o-mini")

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

        judge = MetricJudge("openai/gpt-4o-mini")

        transcript = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
        ]

        formatted = judge._format_transcript(transcript)

        assert "USER: Hello" in formatted
        assert "ASSISTANT: Hi there!" in formatted

    @pytest.mark.asyncio
    async def test_evaluate_with_score_and_threshold(self):
        from voicetest.judges.metric import MetricJudge
        from voicetest.models.results import MetricResult

        judge = MetricJudge("openai/gpt-4o-mini")
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(
                metric="Test metric",
                score=0.85,
                passed=True,
                reasoning="High score",
                threshold=0.7,
                confidence=0.9,
            )
        ]

        transcript = [Message(role="user", content="Hello")]
        result = await judge.evaluate(transcript, "Test metric", threshold=0.7)

        assert result.score == 0.85
        assert result.threshold == 0.7
        assert result.passed is True

    @pytest.mark.asyncio
    async def test_evaluate_score_below_threshold_fails(self):
        from voicetest.judges.metric import MetricJudge
        from voicetest.models.results import MetricResult

        judge = MetricJudge("openai/gpt-4o-mini")
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(
                metric="Test metric",
                score=0.5,
                passed=False,
                reasoning="Below threshold",
                threshold=0.7,
                confidence=0.9,
            )
        ]

        transcript = [Message(role="user", content="Hello")]
        result = await judge.evaluate(transcript, "Test metric", threshold=0.7)

        assert result.score == 0.5
        assert result.threshold == 0.7
        assert result.passed is False

    @pytest.mark.asyncio
    async def test_evaluate_all_with_threshold(self):
        from voicetest.judges.metric import MetricJudge
        from voicetest.models.results import MetricResult

        judge = MetricJudge("openai/gpt-4o-mini")
        judge._mock_mode = True
        judge._mock_results = [
            MetricResult(metric="m1", score=0.9, passed=True, reasoning="Good", threshold=0.8),
            MetricResult(metric="m2", score=0.6, passed=False, reasoning="Bad", threshold=0.8),
        ]

        transcript = [Message(role="user", content="Hello")]
        results = await judge.evaluate_all(transcript, ["m1", "m2"], threshold=0.8)

        assert len(results) == 2
        assert results[0].passed is True
        assert results[1].passed is False
        assert all(r.threshold == 0.8 for r in results)
