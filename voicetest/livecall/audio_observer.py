"""LiveKit audio observer.

Transcribes a participant's actually-published audio track into an
ObserverTranscript via STT. record_speech_events is the architecture- and
transport-independent core (it consumes any SpeechEvent stream); observe_track
wires a live rtc.AudioStream to an STT stream and is exercised end-to-end
against a running LiveKit server.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterable

from livekit import rtc
from livekit.agents import stt as lk_stt

from voicetest.livecall.observer import ObserverTranscript


class AudioObserver:
    """Records final STT transcripts of published audio as observed Messages."""

    def __init__(self, stt: lk_stt.STT, transcript: ObserverTranscript):
        self._stt = stt
        self._transcript = transcript

    async def record_speech_events(
        self, events: AsyncIterable[lk_stt.SpeechEvent], role: str
    ) -> None:
        """Record each final transcript from a SpeechEvent stream."""
        async for event in events:
            if event.type == lk_stt.SpeechEventType.FINAL_TRANSCRIPT and event.alternatives:
                self._transcript.add_observed(role, event.alternatives[0].text)

    async def observe_track(self, audio_stream: rtc.AudioStream, role: str) -> None:
        """Pump a published audio track through STT, recording observed turns."""
        stream = self._stt.stream()

        async def _pump() -> None:
            try:
                async for frame_event in audio_stream:
                    stream.push_frame(frame_event.frame)
            finally:
                stream.end_input()

        pump_task = asyncio.create_task(_pump())
        try:
            await self.record_speech_events(stream, role)
        finally:
            await pump_task
            await stream.aclose()
