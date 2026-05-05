"""Tests for the Retell transcript adapter."""

import json

import pytest

from voicetest.importers.transcripts.retell import parse_retell
from voicetest.importers.transcripts.retell import parse_retell_file


# A 4-turn transcript used by the parsing tests below — overrides the
# 2-turn default in the shared retell_call fixture.
_FOUR_TURN_TRANSCRIPT = [
    {"role": "agent", "content": "Hi, how can I help?"},
    {"role": "user", "content": "I need to cancel my appointment."},
    {"role": "agent", "content": "Sure — what's your account number?"},
    {"role": "user", "content": "12345."},
]


class TestParseRetell:
    def test_single_call_object(self, retell_call):
        result = parse_retell(retell_call(transcript_object=_FOUR_TURN_TRANSCRIPT))

        assert len(result) == 1
        tr = result[0]
        assert tr.status == "imported"
        assert tr.test_name == "call_001"
        assert tr.test_id == "call_001"
        assert len(tr.transcript) == 4
        assert tr.transcript[0].role == "assistant"
        assert tr.transcript[0].content == "Hi, how can I help?"
        assert tr.transcript[1].role == "user"
        assert tr.turn_count == 4
        assert tr.duration_ms == 60000

    def test_role_mapping_agent_to_assistant(self, retell_call):
        result = parse_retell(retell_call(transcript_object=_FOUR_TURN_TRANSCRIPT))

        roles = [m.role for m in result[0].transcript]
        assert roles == ["assistant", "user", "assistant", "user"]

    def test_array_of_calls(self, retell_call):
        payload = [retell_call("call_a"), retell_call("call_b")]

        result = parse_retell(payload)

        assert len(result) == 2
        assert result[0].test_name == "call_a"
        assert result[1].test_name == "call_b"

    def test_webhook_envelope(self, retell_call):
        payload = {"event": "call_ended", "call": retell_call("call_wh")}

        result = parse_retell(payload)

        assert len(result) == 1
        assert result[0].test_name == "call_wh"

    def test_array_of_webhook_envelopes(self, retell_call):
        payload = [
            {"event": "call_ended", "call": retell_call("call_a")},
            {"event": "call_ended", "call": retell_call("call_b")},
        ]

        result = parse_retell(payload)

        assert len(result) == 2
        assert {tr.test_name for tr in result} == {"call_a", "call_b"}

    def test_skips_turns_with_empty_content(self, retell_call):
        transcript = _FOUR_TURN_TRANSCRIPT + [
            {"role": "user", "content": ""},
            {"role": "agent", "content": None},
        ]
        call = retell_call(transcript_object=transcript)

        result = parse_retell(call)

        # Only the original 4 turns survive — the empty/null ones are skipped
        assert len(result[0].transcript) == 4
        assert result[0].turn_count == 4

    def test_derives_duration_from_timestamps_if_missing(self, retell_call):
        call = retell_call()
        del call["duration_ms"]

        result = parse_retell(call)

        assert result[0].duration_ms == 60000

    def test_duration_zero_when_neither_field_present(self):
        call = {"call_id": "no_timing", "transcript_object": []}

        result = parse_retell(call)

        assert result[0].duration_ms == 0

    def test_uses_disconnection_reason_for_end_reason(self, retell_call):
        call = retell_call(disconnection_reason="user_hangup")

        result = parse_retell(call)

        assert result[0].end_reason == "user_hangup"

    def test_falls_back_to_call_status_for_end_reason(self, retell_call):
        result = parse_retell(retell_call())

        assert result[0].end_reason == "ended"

    def test_raises_when_no_calls_found(self):
        with pytest.raises(ValueError, match="No Retell call objects"):
            parse_retell({"unrelated": "payload"})

    def test_raises_when_payload_is_garbage(self):
        with pytest.raises(ValueError, match="No Retell call objects"):
            parse_retell([1, 2, 3])

    def test_handles_call_without_transcript_object(self):
        # A call that ended before any transcript was generated — still valid,
        # just produces zero messages.
        call = {"call_id": "empty", "transcript_object": []}

        result = parse_retell(call)

        assert len(result) == 1
        assert result[0].transcript == []
        assert result[0].turn_count == 0
        assert result[0].test_name == "empty"

    def test_falls_back_to_default_test_name_when_no_call_id(self):
        call = {"transcript_object": [{"role": "user", "content": "hi"}]}

        result = parse_retell(call)

        assert result[0].test_name == "imported call"
        assert result[0].test_id is None


class TestParseRetellFile:
    def test_reads_file(self, tmp_path, retell_call):
        path = tmp_path / "call.json"
        path.write_text(json.dumps(retell_call()), encoding="utf-8")

        result = parse_retell_file(path)

        assert len(result) == 1
        assert result[0].test_name == "call_001"

    def test_invalid_json_raises_value_error(self, tmp_path):
        path = tmp_path / "broken.json"
        path.write_text("not json at all", encoding="utf-8")

        with pytest.raises(ValueError, match="Not valid JSON"):
            parse_retell_file(path)
