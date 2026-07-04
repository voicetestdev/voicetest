"""Tests for live-call transcript helpers."""

from voicetest.web.calls import merge_observed_heard


class TestMergeObservedHeard:
    def test_attaches_heard_to_matching_role(self):
        transcript = [{"role": "assistant", "content": "hello there"}]

        merge_observed_heard(transcript, "assistant", "hello thair")

        assert transcript[0]["metadata"]["audio"]["heard"] == "hello thair"
        assert transcript[0]["content"] == "hello there"

    def test_ignores_other_roles(self):
        transcript = [
            {"role": "user", "content": "hi"},
            {"role": "assistant", "content": "hello there"},
        ]

        merge_observed_heard(transcript, "assistant", "hello thair")

        assert "audio" not in transcript[0].get("metadata", {})
        assert transcript[1]["metadata"]["audio"]["heard"] == "hello thair"

    def test_fills_earliest_unheard_turn_in_order(self):
        transcript = [
            {"role": "assistant", "content": "first"},
            {"role": "assistant", "content": "second"},
        ]

        merge_observed_heard(transcript, "assistant", "first heard")
        merge_observed_heard(transcript, "assistant", "second heard")

        assert transcript[0]["metadata"]["audio"]["heard"] == "first heard"
        assert transcript[1]["metadata"]["audio"]["heard"] == "second heard"

    def test_appends_standalone_when_no_intended_turn(self):
        transcript = [
            {"role": "assistant", "content": "only", "metadata": {"audio": {"heard": "h"}}}
        ]

        merge_observed_heard(transcript, "assistant", "extra")

        assert len(transcript) == 2
        assert transcript[1]["content"] == "extra"
        assert transcript[1]["metadata"]["audio"]["heard"] == "extra"

    def test_preserves_existing_metadata(self):
        transcript = [{"role": "assistant", "content": "hello", "metadata": {"latency_ms": 10}}]

        merge_observed_heard(transcript, "assistant", "hallo")

        assert transcript[0]["metadata"]["latency_ms"] == 10
        assert transcript[0]["metadata"]["audio"]["heard"] == "hallo"
