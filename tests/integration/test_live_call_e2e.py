"""End-to-end: a live cascade call records heard audio back into the transcript.

Requires the local service stack (scripts/services.sh up). The agent's spoken
reply comes from the local ollama model in that stack, so no external LLM key is
needed and this runs unconditionally wherever the stack is up (including CI).
  - LiveKit dev server   ws://localhost:7880
  - faster-whisper STT   http://localhost:8001
  - Kokoro TTS           http://localhost:8002
  - ollama LLM           http://localhost:11434

A caller participant publishes a synthesized utterance into a real call started
by CallManager. The agent worker (cascade STT -> ConversationEngine -> TTS) plus
its observer participant transcribe the agent's spoken reply, and the observed
'heard' text is merged into the call transcript. Assertions are tolerant of
STT/LLM nondeterminism: at least one assistant turn must carry non-empty heard.
"""

import asyncio
from unittest.mock import MagicMock

import httpx
from livekit import rtc
import pytest

from voicetest.models.agent import AgentGraph
from voicetest.settings import Settings
from voicetest.web.calls import CallManager
from voicetest.web.calls import LiveKitConfig


LIVEKIT_URL = "ws://localhost:7880"
WHISPER_URL = "http://localhost:8001/v1"
KOKORO_URL = "http://localhost:8002/v1"
AGENT_MODEL = "ollama_chat/qwen2.5:0.5b"
SAMPLE_RATE = 24000
NUM_CHANNELS = 1

pytestmark = pytest.mark.stack


def _greeting_graph() -> AgentGraph:
    return AgentGraph(
        source_type="custom",
        entry_node_id="greeting",
        nodes={
            "greeting": {
                "id": "greeting",
                "node_type": "conversation",
                "state_prompt": "You are a helpful assistant. Greet the caller and say hello.",
                "transitions": [],
                "tools": [],
                "metadata": {},
            }
        },
    )


def _config() -> LiveKitConfig:
    return LiveKitConfig(
        url=LIVEKIT_URL,
        public_url=LIVEKIT_URL,
        api_key="devkey",
        api_secret="secret",
        voice_backend="local",
        whisper_url=WHISPER_URL,
        kokoro_url=KOKORO_URL,
    )


class _Settings:
    def get_settings(self) -> Settings:
        return Settings()


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


async def _publish_caller_audio(room: rtc.Room, pcm: bytes) -> None:
    source = rtc.AudioSource(SAMPLE_RATE, NUM_CHANNELS)
    track = rtc.LocalAudioTrack.create_audio_track("caller", source)
    await room.local_participant.publish_track(
        track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
    )

    samples_per_frame = SAMPLE_RATE // 100  # 10ms frames
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


def _heard_turns(transcript: list[dict]) -> list[dict]:
    return [
        m
        for m in transcript
        if m.get("role") == "assistant" and m.get("metadata", {}).get("audio", {}).get("heard")
    ]


@pytest.mark.asyncio
async def test_live_call_records_heard_transcript():
    call_repo = MagicMock()
    call_repo.create.return_value = {
        "id": "smoke-call",
        "room_name": "",
        "status": "connecting",
    }

    manager = CallManager(_Settings(), _config())
    caller_room = rtc.Room()
    call_id: str | None = None

    try:
        call_info = await manager.start_call(
            agent_id="smoke-agent",
            graph=_greeting_graph(),
            call_repo=call_repo,
            agent_model=AGENT_MODEL,
        )
        call_id = call_info["call_id"]
        active_call = manager.get_active_call(call_id)

        await caller_room.connect(call_info["livekit_url"], call_info["token"])
        # Let the agent worker and its observer join and subscribe before speaking.
        await asyncio.sleep(3)

        pcm = await _synthesize_pcm("Hello, can you hear me?")
        await _publish_caller_audio(caller_room, pcm)

        # Generous window: cold whisper STT + LLM turn + kokoro TTS + observer STT.
        heard: list[dict] = []
        for _ in range(1200):
            heard = _heard_turns(active_call.transcript)
            if heard:
                break
            if active_call.process is not None and active_call.process.poll() is not None:
                break
            await asyncio.sleep(0.1)

        assert heard, f"no assistant turn carried heard audio; transcript={active_call.transcript}"
        assert heard[0]["metadata"]["audio"]["heard"].strip()
    finally:
        await caller_room.disconnect()
        if call_id is not None:
            await manager.end_call(call_id, call_repo)
