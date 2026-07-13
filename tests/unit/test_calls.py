"""Tests for live-call transcript helpers."""

from voicetest.web.calls import CallManager
from voicetest.web.calls import LiveKitConfig
from voicetest.web.calls import merge_observed_heard


def _add_intended(transcript, turn_messages, role, content, turn_id):
    """Mimic _monitor_agent_output appending an intended turn and indexing it."""
    message = {"role": role, "content": content}
    transcript.append(message)
    if turn_id is not None:
        turn_messages[(role, turn_id)] = message
    return message


class TestMergeObservedHeard:
    def test_correlates_heard_to_its_turn(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "hello there", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "hello thair", turn_id=1)

        assert transcript[0]["content"] == "hello there"
        assert transcript[0]["metadata"]["audio"]["heard"] == "hello thair"

    def test_multiple_finals_of_one_turn_concatenate(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "Hello. How can I help?", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "Hello.", turn_id=1)
        merge_observed_heard(transcript, turns, "assistant", "How can I help?", turn_id=1)

        assert len(transcript) == 1  # no phantom turn
        assert transcript[0]["metadata"]["audio"]["heard"] == "Hello. How can I help?"

    def test_distinct_turns_land_on_their_own_message(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "first", turn_id=1)
        _add_intended(transcript, turns, "assistant", "second", turn_id=2)

        merge_observed_heard(transcript, turns, "assistant", "second heard", turn_id=2)
        merge_observed_heard(transcript, turns, "assistant", "first heard", turn_id=1)

        assert transcript[0]["metadata"]["audio"]["heard"] == "first heard"
        assert transcript[1]["metadata"]["audio"]["heard"] == "second heard"

    def test_appends_standalone_when_turn_unknown(self):
        transcript, turns = [], {}

        merge_observed_heard(transcript, turns, "assistant", "orphan a", turn_id=7)
        merge_observed_heard(transcript, turns, "assistant", "orphan b", turn_id=7)

        assert len(transcript) == 1
        assert transcript[0]["role"] == "assistant"
        assert transcript[0]["metadata"]["audio"]["heard"] == "orphan a orphan b"

    def test_skips_empty_or_missing(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "hi", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "", turn_id=1)
        merge_observed_heard(transcript, turns, None, "x", turn_id=1)

        assert "metadata" not in transcript[0]
        assert len(transcript) == 1

    def test_preserves_other_metadata(self):
        transcript, turns = [], {}
        message = _add_intended(transcript, turns, "assistant", "hello", turn_id=1)
        message["metadata"] = {"foo": "bar"}

        merge_observed_heard(transcript, turns, "assistant", "hallo", turn_id=1)

        assert transcript[0]["metadata"]["foo"] == "bar"
        assert transcript[0]["metadata"]["audio"]["heard"] == "hallo"

    def test_same_turn_id_different_roles_do_not_collide(self):
        transcript, turns = [], {}
        _add_intended(transcript, turns, "assistant", "agent one", turn_id=1)
        _add_intended(transcript, turns, "user", "caller one", turn_id=1)

        merge_observed_heard(transcript, turns, "assistant", "agent heard", turn_id=1)
        merge_observed_heard(transcript, turns, "user", "caller heard", turn_id=1)

        assert transcript[0]["metadata"]["audio"]["heard"] == "agent heard"
        assert transcript[1]["metadata"]["audio"]["heard"] == "caller heard"


class TestCallerCommand:
    def _manager(self):
        return CallManager(settings_service=None, config=LiveKitConfig(voice_backend="local"))

    def test_caller_cmd_targets_caller_worker_with_persona(self):
        cm = self._manager()

        cmd = cm._caller_cmd("room1", "utok", "otok", "PERSONA TEXT", "model-x", max_turns=12)

        assert "voicetest.livecall.caller_worker" in cmd
        assert cmd[cmd.index("--token") + 1] == "utok"
        assert cmd[cmd.index("--observer-token") + 1] == "otok"
        assert cmd[cmd.index("--persona") + 1] == "PERSONA TEXT"
        assert cmd[cmd.index("--model") + 1] == "model-x"
        assert cmd[cmd.index("--max-turns") + 1] == "12"
        assert cmd[cmd.index("--backend") + 1] == "local"
