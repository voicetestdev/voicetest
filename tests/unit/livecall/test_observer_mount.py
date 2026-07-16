"""Tests for the shared room-observer mount."""

import asyncio

from livekit import rtc
import pytest

from voicetest.livecall.observer_mount import observe_participant
from voicetest.livecall.observer_mount import should_observe


class FakeTrack:
    def __init__(self, kind=rtc.TrackKind.KIND_AUDIO):
        self.kind = kind


class FakeParticipant:
    def __init__(self, identity):
        self.identity = identity


class FakeRoom:
    """Captures event handlers registered via @room.on(event)."""

    def __init__(self):
        self.handlers = {}

    def on(self, event):
        def register(fn):
            self.handlers[event] = fn
            return fn

        return register

    def emit(self, event, *args):
        self.handlers[event](*args)


class FakeObserver:
    async def observe_track(self, stream, role):
        return None


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


class TestObserveParticipant:
    @pytest.mark.asyncio
    async def test_duplicate_subscribe_without_unsubscribe_is_deduped(self, monkeypatch):
        monkeypatch.setattr(rtc, "AudioStream", lambda track: track)
        room = FakeRoom()
        tasks = []
        observe_participant(room, FakeObserver(), "agent", "assistant", tasks)

        track, participant = FakeTrack(), FakeParticipant("agent")
        room.emit("track_subscribed", track, None, participant)
        room.emit("track_subscribed", track, None, participant)

        assert len(tasks) == 1
        await asyncio.gather(*tasks, return_exceptions=True)

    @pytest.mark.asyncio
    async def test_resubscribe_after_unsubscribe_spawns_new_pipeline(self, monkeypatch):
        monkeypatch.setattr(rtc, "AudioStream", lambda track: track)
        room = FakeRoom()
        tasks = []
        observe_participant(room, FakeObserver(), "agent", "assistant", tasks)

        track, participant = FakeTrack(), FakeParticipant("agent")
        room.emit("track_subscribed", track, None, participant)
        room.emit("track_unsubscribed", track, None, participant)
        room.emit("track_subscribed", track, None, participant)

        assert len(tasks) == 2
        await asyncio.gather(*tasks, return_exceptions=True)
