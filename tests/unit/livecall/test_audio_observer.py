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
