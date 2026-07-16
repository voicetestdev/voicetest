"""Tests for the LiveKit audio observer's STT-event consumption."""

from collections.abc import AsyncIterable

from livekit.agents.stt import SpeechData
from livekit.agents.stt import SpeechEvent
from livekit.agents.stt import SpeechEventType
import pytest

from voicetest.livecall.audio_observer import AudioObserver
from voicetest.livecall.observer import ObserverTranscript


async def _aiter(events: list[SpeechEvent]) -> AsyncIterable[SpeechEvent]:
    for event in events:
        yield event


def _final(text: str) -> SpeechEvent:
    return SpeechEvent(
        type=SpeechEventType.FINAL_TRANSCRIPT,
        alternatives=[SpeechData(language="en", text=text)],
    )


def _interim(text: str) -> SpeechEvent:
    return SpeechEvent(
        type=SpeechEventType.INTERIM_TRANSCRIPT,
        alternatives=[SpeechData(language="en", text=text)],
    )


class TestRecordSpeechEvents:
    @pytest.mark.asyncio
    async def test_records_only_final_transcripts(self):
        transcript = ObserverTranscript()
        observer = AudioObserver(stt=object(), transcript=transcript)

        await observer.record_speech_events(
            _aiter([_interim("hel"), _final("hello"), _interim("the"), _final("there")]),
            "assistant",
        )

        messages = transcript.messages
        assert [m.audio().heard for m in messages] == ["hello", "there"]
        assert all(m.role == "assistant" for m in messages)

    @pytest.mark.asyncio
    async def test_ignores_finals_with_no_alternatives(self):
        transcript = ObserverTranscript()
        observer = AudioObserver(stt=object(), transcript=transcript)

        empty_final = SpeechEvent(type=SpeechEventType.FINAL_TRANSCRIPT, alternatives=[])
        await observer.record_speech_events(_aiter([empty_final]), "user")

        assert transcript.messages == []

    @pytest.mark.asyncio
    async def test_role_is_attributed(self):
        transcript = ObserverTranscript()
        observer = AudioObserver(stt=object(), transcript=transcript)

        await observer.record_speech_events(_aiter([_final("hi")]), "user")

        assert transcript.messages[0].role == "user"


class _RecordingTranscript:
    def __init__(self):
        self.calls = []

    def add_observed(self, role, heard, *, turn_id=None, **kwargs):
        self.calls.append((role, heard, turn_id))


def _start() -> SpeechEvent:
    return SpeechEvent(type=SpeechEventType.START_OF_SPEECH, alternatives=[])


class TestTurnIdCapture:
    @pytest.mark.asyncio
    async def test_turn_id_captured_at_speech_start_not_final(self):
        transcript = _RecordingTranscript()
        turn = {"n": 1}
        observer = AudioObserver(
            stt=object(), transcript=transcript, turn_id_provider=lambda: turn["n"]
        )

        async def events():
            yield _start()
            turn["n"] = 2
            yield _final("hello")

        await observer.record_speech_events(events(), "assistant")

        assert transcript.calls == [("assistant", "hello", 1)]

    @pytest.mark.asyncio
    async def test_turn_id_falls_back_to_final_when_no_speech_start(self):
        transcript = _RecordingTranscript()
        observer = AudioObserver(stt=object(), transcript=transcript, turn_id_provider=lambda: 5)

        await observer.record_speech_events(_aiter([_final("hi")]), "user")

        assert transcript.calls == [("user", "hi", 5)]
