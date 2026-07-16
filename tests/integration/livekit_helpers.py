"""Shared helpers for the LiveKit-backed stack integration tests."""

import httpx
from livekit import rtc


KOKORO_URL = "http://localhost:8002/v1"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1


async def synthesize_pcm(text: str, kokoro_url: str = KOKORO_URL) -> bytes:
    """Synthesize speech to raw PCM via the local Kokoro TTS."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{kokoro_url}/audio/speech",
            json={
                "model": "kokoro",
                "input": text,
                "voice": "af_heart",
                "response_format": "pcm",
            },
        )
        resp.raise_for_status()
        return resp.content


async def capture_pcm_frames(source: rtc.AudioSource, pcm: bytes) -> None:
    """Feed PCM into an audio source as 10ms frames, then trailing silence so the
    VAD marks end-of-speech and the STT finalizes."""
    samples_per_frame = SAMPLE_RATE // 100
    bytes_per_frame = samples_per_frame * 2
    for offset in range(0, len(pcm), bytes_per_frame):
        chunk = pcm[offset : offset + bytes_per_frame]
        if len(chunk) < bytes_per_frame:
            chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))
        await source.capture_frame(
            rtc.AudioFrame(chunk, SAMPLE_RATE, NUM_CHANNELS, samples_per_frame)
        )

    silence = b"\x00" * bytes_per_frame
    for _ in range(100):
        await source.capture_frame(
            rtc.AudioFrame(silence, SAMPLE_RATE, NUM_CHANNELS, samples_per_frame)
        )
