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

from livekit import api as livekit_api
from livekit import rtc
from livekit.agents import stt as lk_stt
from livekit.plugins import openai
from livekit.plugins import silero
import pytest

from tests.integration.livekit_helpers import NUM_CHANNELS
from tests.integration.livekit_helpers import SAMPLE_RATE
from tests.integration.livekit_helpers import capture_pcm_frames
from tests.integration.livekit_helpers import synthesize_pcm
from voicetest.livecall.audio_observer import AudioObserver
from voicetest.livecall.observer import ObserverTranscript


LIVEKIT_URL = "ws://localhost:7880"
WHISPER_URL = "http://localhost:8001/v1"
ROOM = "observer-e2e"

pytestmark = pytest.mark.stack


def _token(identity: str) -> str:
    return (
        livekit_api.AccessToken("devkey", "secret")
        .with_identity(identity)
        .with_grants(livekit_api.VideoGrants(room_join=True, room=ROOM))
        .to_jwt()
    )


@pytest.mark.asyncio
async def test_observer_transcribes_published_audio():
    phrase = "the quick brown fox jumps over the lazy dog"
    pcm = await synthesize_pcm(phrase)

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

        await capture_pcm_frames(source, pcm)

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
