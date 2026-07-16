"""Wire a room observer to transcribe one participant's published audio.

Generalizes the per-worker self-observer: given the identity of the participant
to watch and the role to attribute, subscribe to that participant's audio track
and run it through the observer. Reused by both the agent worker (watching the
agent's own track) and the caller worker (watching the caller's own track), so
each side records what it actually sounded like on the wire.
"""

from __future__ import annotations

import asyncio

from livekit import rtc

from voicetest.livecall.audio_observer import AudioObserver


def should_observe(track, participant, identity: str) -> bool:
    """Whether this subscribed track is the target participant's audio."""
    return track.kind == rtc.TrackKind.KIND_AUDIO and participant.identity == identity


def observe_participant(
    observer_room: rtc.Room,
    observer: AudioObserver,
    identity: str,
    role: str,
    tasks: list[asyncio.Task],
) -> None:
    """Observe the published audio of the participant with the given identity.

    Appends an observe_track task per matching track to tasks so the caller can
    cancel them on teardown. Observes each subscribed track once, so a duplicate
    subscribe does not spawn a second pipeline; an unsubscribe clears the guard so
    a genuine re-subscribe (reconnect/renegotiation) re-arms observation."""
    observed: set[str] = set()

    @observer_room.on("track_subscribed")
    def on_track(track, publication, participant):
        if should_observe(track, participant, identity) and participant.identity not in observed:
            observed.add(participant.identity)
            stream = rtc.AudioStream(track)
            tasks.append(asyncio.create_task(observer.observe_track(stream, role)))

    @observer_room.on("track_unsubscribed")
    def on_track_gone(track, publication, participant):
        if should_observe(track, participant, identity):
            observed.discard(participant.identity)
