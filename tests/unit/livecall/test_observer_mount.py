"""Tests for the shared room-observer mount."""

from livekit import rtc

from voicetest.livecall.observer_mount import should_observe


class FakeTrack:
    def __init__(self, kind):
        self.kind = kind


class FakeParticipant:
    def __init__(self, identity):
        self.identity = identity


class TestShouldObserve:
    def test_matches_audio_track_of_target_identity(self):
        assert (
            should_observe(FakeTrack(rtc.TrackKind.KIND_AUDIO), FakeParticipant("agent"), "agent")
            is True
        )

    def test_rejects_other_identity(self):
        assert (
            should_observe(FakeTrack(rtc.TrackKind.KIND_AUDIO), FakeParticipant("user"), "agent")
            is False
        )

    def test_rejects_non_audio_track(self):
        assert (
            should_observe(FakeTrack(rtc.TrackKind.KIND_VIDEO), FakeParticipant("agent"), "agent")
            is False
        )
