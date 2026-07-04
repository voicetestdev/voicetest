"""End-to-end: AudioObserver transcribes real published audio over a LiveKit room.

Requires the local service stack (scripts/services.sh up):
  - LiveKit dev server   ws://localhost:7880
  - faster-whisper STT   http://localhost:8001
  - Kokoro TTS           http://localhost:8002

A publisher participant publishes Kokoro-synthesized speech into a room; the
AudioObserver subscribes to that track via rtc.AudioStream, transcribes it with
a VAD-wrapped whisper STT, and records what it heard. Assertions are tolerant
(real STT is nondeterministic): the observed transcript must be non-empty and
contain at least one expected word.
"""

import asyncio

import httpx
from livekit import api as livekit_api
from livekit import rtc
from livekit.agents import stt as lk_stt
from livekit.plugins import openai
from livekit.plugins import silero
import pytest

from voicetest.livecall.audio_observer import AudioObserver
from voicetest.livecall.observer import ObserverTranscript


LIVEKIT_URL = "ws://localhost:7880"
WHISPER_URL = "http://localhost:8001/v1"
KOKORO_URL = "http://localhost:8002/v1"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1
ROOM = "observer-e2e"

pytestmark = pytest.mark.stack


def _token(identity: str) -> str:
    return (
        livekit_api.AccessToken("devkey", "secret")
        .with_identity(identity)
        .with_grants(livekit_api.VideoGrants(room_join=True, room=ROOM))
        .to_jwt()
    )


async def _synthesize_pcm(text: str) -> bytes:
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{KOKORO_URL}/audio/speech",
            json={
                "model": "kokoro",
                "input": text,
                "voice": "af_heart",
                "response_format": "pcm",
            },
        )
        resp.raise_for_status()
        return resp.content


@pytest.mark.asyncio
async def test_observer_transcribes_published_audio():
    phrase = "the quick brown fox jumps over the lazy dog"
    pcm = await _synthesize_pcm(phrase)

    transcript = ObserverTranscript()
    whisper = openai.STT(
        base_url=WHISPER_URL,
        api_key="not-needed",
        model="Systran/faster-whisper-base.en",
    )
    stream_stt = lk_stt.StreamAdapter(stt=whisper, vad=silero.VAD.load())
    observer = AudioObserver(stt=stream_stt, transcript=transcript)

    pub_room = rtc.Room()
    obs_room = rtc.Room()
    observe_task: asyncio.Task | None = None
    holder: dict[str, rtc.AudioStream] = {}
    subscribed = asyncio.Event()

    @obs_room.on("track_subscribed")
    def _on_subscribed(track, publication, participant):
        if track.kind == rtc.TrackKind.KIND_AUDIO:
            holder["stream"] = rtc.AudioStream(track)
            subscribed.set()

    try:
        await obs_room.connect(LIVEKIT_URL, _token("observer"))
        await pub_room.connect(LIVEKIT_URL, _token("publisher"))

        source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
        track = rtc.LocalAudioTrack.create_audio_track("speech", source)
        await pub_room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        )

        await asyncio.wait_for(subscribed.wait(), timeout=15)
        observe_task = asyncio.create_task(observer.observe_track(holder["stream"], "assistant"))

        samples_per_frame = SAMPLE_RATE // 100  # 10ms frames
        bytes_per_frame = samples_per_frame * 2
        for offset in range(0, len(pcm), bytes_per_frame):
            chunk = pcm[offset : offset + bytes_per_frame]
            if len(chunk) < bytes_per_frame:
                chunk = chunk + b"\x00" * (bytes_per_frame - len(chunk))
            await source.capture_frame(
                rtc.AudioFrame(chunk, SAMPLE_RATE, NUM_CHANNELS, samples_per_frame)
            )

        # Trailing silence so the VAD marks end-of-speech and the STT finalizes.
        silence = b"\x00" * bytes_per_frame
        for _ in range(100):
            await source.capture_frame(
                rtc.AudioFrame(silence, SAMPLE_RATE, NUM_CHANNELS, samples_per_frame)
            )

        # Generous window so a cold VAD/STT (first request in CI) can finalize.
        for _ in range(300):
            if transcript.messages:
                break
            if observe_task.done() and observe_task.exception() is not None:
                raise observe_task.exception()
            await asyncio.sleep(0.1)
    finally:
        if observe_task is not None:
            observe_task.cancel()
        await pub_room.disconnect()
        await obs_room.disconnect()

    assert transcript.messages, "observer produced no transcript"
    heard = " ".join(m.audio().heard.lower() for m in transcript.messages)
    assert any(word in heard for word in ["fox", "quick", "brown", "dog", "lazy"]), heard
