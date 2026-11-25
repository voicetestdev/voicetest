"""TTS→STT round-trip for evaluating spoken content fidelity."""

import copy
import logging

import httpx

from voicetest.models.results import AudioMetadata
from voicetest.models.results import Message
from voicetest.settings import AudioSettings
from voicetest.settings import Settings


logger = logging.getLogger(__name__)


class AudioRoundTrip:
    """TTS→STT round-trip using OpenAI-compatible APIs."""

    def __init__(self, audio: AudioSettings | None = None):
        audio = audio or AudioSettings()
        self.tts_base_url = audio.tts_url.rstrip("/")
        self.stt_base_url = audio.stt_url.rstrip("/")
        self.tts_model = audio.tts_model
        self.stt_model = audio.stt_model
        self.voice = audio.voice
        self.client = httpx.AsyncClient(timeout=60.0)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "AudioRoundTrip":
        """Create an AudioRoundTrip from application settings."""
        if settings is None:
            settings = Settings()
        return cls(settings.audio)

    async def round_trip(self, text: str) -> str:
        """Synthesize text to audio, transcribe audio back to text."""
        audio = await self._synthesize(text)
        return await self._transcribe(audio)

    async def _synthesize(self, text: str) -> bytes:
        """Synthesize text to audio via OpenAI-compatible TTS API."""
        response = await self.client.post(
            f"{self.tts_base_url}/audio/speech",
            json={
                "model": self.tts_model,
                "input": text,
                "voice": self.voice,
            },
        )
        response.raise_for_status()
        return response.content

    async def _transcribe(self, audio: bytes) -> str:
        """Transcribe audio to text via OpenAI-compatible STT API."""
        response = await self.client.post(
            f"{self.stt_base_url}/audio/transcriptions",
            files={"file": ("audio.mp3", audio, "audio/mpeg")},
            data={"model": self.stt_model},
        )
        response.raise_for_status()
        return response.json()["text"]

    async def transform_transcript(self, transcript: list[Message]) -> list[Message]:
        """Round-trip all assistant messages, storing results in the audio sub-model."""
        result = copy.deepcopy(transcript)
        for msg in result:
            if msg.role == "assistant" and msg.content.strip():
                try:
                    heard = await self.round_trip(msg.content)
                    msg.set_audio(AudioMetadata(heard=heard))
                except Exception:
                    logger.exception("Audio round-trip failed for message: %s", msg.content[:80])
        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
