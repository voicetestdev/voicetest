"""Tests for voicetest.services.evaluation module."""

import pytest

from voicetest.models.events import JudgeEvent
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.services.evaluation import EvaluationService
from voicetest.services.settings import SettingsService
from voicetest.services.testing.execution import TestExecutionService


@pytest.fixture
def svc():
    """EvaluationService with a real TestExecutionService."""
    settings_svc = SettingsService()
    return EvaluationService(TestExecutionService(settings_svc), settings_svc)


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
    async def test_judges_events(self, svc, judge_prompts):
        events = [
            JudgeEvent(kind="speech", speaker="assistant", content="Press 1 for billing"),
            JudgeEvent(kind="keypad_input", speaker="user", payload={"digits": "1"}),
        ]

        results = await svc.evaluate_transcript(
            transcript=events, metrics=["Caller pressed 1"], judge_model="openai/gpt-4o-mini"
        )

        assert [r.metric for r in results] == ["Caller pressed 1"]
        assert results[0].passed is True
        assert "[[ ## events ## ]]" in judge_prompts()[0]

    @pytest.mark.asyncio
    async def test_empty_metrics(self, svc, transcript):
        results = await svc.evaluate_transcript(
            transcript=transcript,
            metrics=[],
            _mock_mode=True,
        )
        assert results == []
