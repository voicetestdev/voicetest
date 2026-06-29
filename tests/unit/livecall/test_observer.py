"""Tests for the observer transcript builder."""

from voicetest.livecall.observer import ObserverTranscript


class TestObserverTranscript:
    """The observer records what was heard on the wire as canonical Messages."""

    def test_cascade_turn_carries_content_and_heard(self):
        observer = ObserverTranscript()

        msg = observer.add_observed(
            "assistant", heard="hello thair", intended="hello there", latency_ms=240, audio_ref="r1"
        )

        assert msg.content == "hello there"
        assert msg.audio().heard == "hello thair"
        assert msg.audio().latency_ms == 240
        assert msg.audio().audio_ref == "r1"

    def test_s2s_turn_carries_heard_only(self):
        observer = ObserverTranscript()

        msg = observer.add_observed("assistant", heard="hello thair")

        assert msg.content == "hello thair"
        assert msg.audio().heard == "hello thair"

    def test_messages_accumulate_in_order(self):
        observer = ObserverTranscript()

        observer.add_observed("user", heard="hi")
        observer.add_observed("assistant", heard="hello")

        messages = observer.messages
        assert [m.role for m in messages] == ["user", "assistant"]
        assert messages[0].audio().heard == "hi"

    def test_messages_returns_a_copy(self):
        observer = ObserverTranscript()
        observer.add_observed("user", heard="hi")

        snapshot = observer.messages
        observer.add_observed("assistant", heard="hello")

        assert len(snapshot) == 1
