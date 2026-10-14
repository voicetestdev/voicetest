"""Integration tests for the metric judge with structured event input.

TestJudgeEventsRoundTrip runs against the stack's Ollama model
(ollama pull qwen2.5:0.5b) and checks that events reach a real LLM and its
judgment parses. TestJudgeEventsVerdicts checks the judgments themselves, which
needs a capable model: set VOICETEST_JUDGE_TEST_MODEL to run it.

To run these tests:
    uv run pytest tests/integration/test_judge_events.py -m stack -v
    VOICETEST_JUDGE_TEST_MODEL=gemini/gemini-2.5-flash \\
        uv run pytest tests/integration/test_judge_events.py -m stack -v
"""

import json
import os

from click.testing import CliRunner
import pytest

from voicetest.cli import main
from voicetest.judges.metric import MetricJudge
from voicetest.models.events import JudgeEvent


pytestmark = pytest.mark.stack

VERDICT_MODEL = os.environ.get("VOICETEST_JUDGE_TEST_MODEL")
JUDGE_MODEL = VERDICT_MODEL or "ollama_chat/qwen2.5:0.5b"
KEYPAD_CRITERION = "The caller pressed 1 on the keypad."


@pytest.fixture
def keypad_events(fixtures_dir) -> list[JudgeEvent]:
    data = json.loads((fixtures_dir / "events" / "keypad_billing.json").read_text())
    return [JudgeEvent.model_validate(e) for e in data]


class TestJudgeEventsRoundTrip:
    @pytest.mark.asyncio
    async def test_judge_parses_result_for_events(self, keypad_events):
        result = await MetricJudge(JUDGE_MODEL).evaluate(keypad_events, KEYPAD_CRITERION)

        assert result.metric == KEYPAD_CRITERION
        assert result.reasoning
        assert 0.0 <= result.score <= 1.0
        assert 0.0 <= result.confidence <= 1.0

    def test_evaluate_command_reports_events_judgment(self, fixtures_dir):
        events_path = fixtures_dir / "events" / "keypad_billing.json"

        result = CliRunner().invoke(
            main,
            [
                "--json",
                "evaluate",
                "--events",
                str(events_path),
                "-m",
                KEYPAD_CRITERION,
                "--judge-model",
                JUDGE_MODEL,
            ],
        )

        payload = json.loads(result.output)
        assert payload[0]["metric"] == KEYPAD_CRITERION
        assert payload[0]["reasoning"]
        assert result.exit_code == (0 if payload[0]["passed"] else 1)


@pytest.mark.skipif(
    VERDICT_MODEL is None, reason="verdicts need a capable judge; set VOICETEST_JUDGE_TEST_MODEL"
)
class TestJudgeEventsVerdicts:
    @pytest.mark.asyncio
    async def test_keypad_event_satisfies_keypad_criterion(self, keypad_events):
        result = await MetricJudge(VERDICT_MODEL).evaluate(keypad_events, KEYPAD_CRITERION)

        assert result.passed is True

    @pytest.mark.asyncio
    async def test_spoken_digit_does_not_satisfy_keypad_criterion(self):
        events = [
            JudgeEvent(
                kind="speech",
                speaker="assistant",
                content="Press 1 for billing or 2 for support.",
            ),
            JudgeEvent(kind="speech", speaker="user", content="One."),
        ]

        result = await MetricJudge(VERDICT_MODEL).evaluate(events, KEYPAD_CRITERION)

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_tool_result_is_cited_as_evidence(self, keypad_events):
        result = await MetricJudge(VERDICT_MODEL).evaluate(
            keypad_events, "The agent looked up the caller's account before stating a balance."
        )

        assert result.passed is True
        assert "lookup_account" in result.reasoning
