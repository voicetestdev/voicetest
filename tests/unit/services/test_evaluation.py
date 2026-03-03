"""Tests for voicetest.services.evaluation module."""

import pytest

from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.services.evaluation import EvaluationService
from voicetest.services.testing.execution import TestExecutionService


@pytest.fixture
def svc():
    """EvaluationService with a real TestExecutionService."""
    return EvaluationService(TestExecutionService())


@pytest.fixture
def transcript():
    return [
        Message(role="assistant", content="Hello, how can I help you?"),
        Message(role="user", content="I need help with billing."),
        Message(role="assistant", content="I'd be happy to help with billing."),
    ]


class TestEvaluateTranscript:
    @pytest.mark.asyncio
    async def test_returns_metric_results(self, svc, transcript):
        results = await svc.evaluate_transcript(
            transcript=transcript,
            metrics=["Was the agent polite?", "Did the agent address billing?"],
            _mock_mode=True,
        )
        assert len(results) == 2
        assert all(isinstance(r, MetricResult) for r in results)

    @pytest.mark.asyncio
    async def test_mock_results_pass(self, svc, transcript):
        results = await svc.evaluate_transcript(
            transcript=transcript,
            metrics=["Check politeness"],
            _mock_mode=True,
        )
        assert results[0].passed is True

    @pytest.mark.asyncio
    async def test_empty_metrics(self, svc, transcript):
        results = await svc.evaluate_transcript(
            transcript=transcript,
            metrics=[],
            _mock_mode=True,
        )
        assert results == []
