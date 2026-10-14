"""Integration tests for the metric judge with structured event input.

Uses Ollama by default (ollama pull qwen2.5:0.5b). Set VOICETEST_JUDGE_TEST_MODEL
to judge with a different model.

To run these tests:
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

JUDGE_MODEL = os.environ.get("VOICETEST_JUDGE_TEST_MODEL", "ollama_chat/qwen2.5:0.5b")
KEYPAD_CRITERION = "The caller pressed 1 on the keypad."


@pytest.fixture
def keypad_events(fixtures_dir) -> list[JudgeEvent]:
    data = json.loads((fixtures_dir / "events" / "keypad_billing.json").read_text())
    return [JudgeEvent.model_validate(e) for e in data]


class TestJudgeEvents:
    @pytest.mark.asyncio
    async def test_keypad_event_satisfies_keypad_criterion(self, keypad_events):
        result = await MetricJudge(JUDGE_MODEL).evaluate(keypad_events, KEYPAD_CRITERION)

        assert result.passed is True
        assert result.reasoning

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

        result = await MetricJudge(JUDGE_MODEL).evaluate(events, KEYPAD_CRITERION)

        assert result.passed is False

    @pytest.mark.asyncio
    async def test_tool_result_is_cited_as_evidence(self, keypad_events):
        result = await MetricJudge(JUDGE_MODEL).evaluate(
            keypad_events, "The agent looked up the caller's account before stating a balance."
        )

        assert result.passed is True
        assert "lookup_account" in result.reasoning


class TestEvaluateCommandWithEvents:
    def test_evaluate_events_file(self, fixtures_dir):
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

        assert result.exit_code == 0, result.output
        payload = json.loads(result.output)
        assert payload[0]["metric"] == KEYPAD_CRITERION
        assert payload[0]["passed"] is True
