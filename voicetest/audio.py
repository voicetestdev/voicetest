"""TTS→STT round-trip for evaluating spoken content fidelity.

Synthesizes agent messages to audio via TTS, then transcribes back via STT.
The resulting "heard" text reveals how a caller would actually perceive the
agent's output — catching pronunciation issues with phone numbers, addresses,
confirmation codes, etc.
"""

import copy
import logging

import httpx

from voicetest.models.results import Message
from voicetest.settings import Settings


logger = logging.getLogger(__name__)


class AudioRoundTrip:
    """TTS→STT round-trip using OpenAI-compatible APIs.

    Uses Kokoro (TTS) and faster-whisper-server (STT), both exposing
    OpenAI-compatible endpoints.
    """

    def __init__(
        self,
        tts_base_url: str = "http://localhost:8002/v1",
        stt_base_url: str = "http://localhost:8001/v1",
        tts_model: str = "kokoro",
        stt_model: str = "Systran/faster-whisper-small",
        voice: str = "af_heart",
    ):
        self.tts_base_url = tts_base_url.rstrip("/")
        self.stt_base_url = stt_base_url.rstrip("/")
        self.tts_model = tts_model
        self.stt_model = stt_model
        self.voice = voice
        self.client = httpx.AsyncClient(timeout=60.0)

    @classmethod
    def from_settings(cls, settings: Settings | None = None) -> "AudioRoundTrip":
        """Create an AudioRoundTrip from application settings."""
        if settings is None:
            settings = Settings()
        return cls(
            tts_base_url=settings.audio.tts_url,
            stt_base_url=settings.audio.stt_url,
        )

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
        """Round-trip all assistant messages, storing results in metadata["heard"].

        User messages pass through unchanged. The original message content
        is preserved — metadata["heard"] captures what was actually heard.
        """
        result = copy.deepcopy(transcript)
        for msg in result:
            if msg.role == "assistant" and msg.content.strip():
                try:
                    heard = await self.round_trip(msg.content)
                    msg.metadata["heard"] = heard
                except Exception:
                    logger.exception("Audio round-trip failed for message: %s", msg.content[:80])
        return result

    async def close(self) -> None:
        """Close the HTTP client."""
        await self.client.aclose()
