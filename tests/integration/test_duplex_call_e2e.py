"""End-to-end: a fully-simulated audio call (no human) records both sides' heard.

Requires the local service stack (scripts/services.sh up). Both the agent's and
the caller's spoken turns come from the local ollama model in that stack, so no
external LLM key is needed:
  - LiveKit dev server   ws://localhost:7880
  - faster-whisper STT   http://localhost:8001
  - Kokoro TTS           http://localhost:8002
  - ollama LLM           http://localhost:11434

CallManager.start_call with a persona launches both the agent worker and the
simulated caller worker into one room, each observing its own published audio.
The conversation runs over real STT/TTS/WebRTC with no human. Assertions tolerate
STT/LLM nondeterminism: at least one assistant turn and one caller turn must carry
non-empty heard text.
"""

import asyncio
from unittest.mock import MagicMock

import pytest

from tests.integration.livekit_helpers import KOKORO_URL
from voicetest.models.agent import AgentGraph
from voicetest.settings import Settings
from voicetest.web.calls import CallManager
from voicetest.web.calls import LiveKitConfig


LIVEKIT_URL = "ws://localhost:7880"
WHISPER_URL = "http://localhost:8001/v1"
MODEL = "ollama_chat/qwen2.5:0.5b"
PERSONA = "## Goal\nAsk the assistant what time the store opens, then say thanks."

pytestmark = pytest.mark.stack


def _greeting_graph() -> AgentGraph:
    return AgentGraph(
        source_type="custom",
        entry_node_id="greeting",
        nodes={
            "greeting": {
                "id": "greeting",
                "node_type": "conversation",
                "state_prompt": "You are a store assistant. Greet the caller and help.",
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


def _heard(transcript: list[dict], role: str) -> list[dict]:
    return [
        m
        for m in transcript
        if m.get("role") == role and m.get("metadata", {}).get("audio", {}).get("heard")
    ]


@pytest.mark.asyncio
async def test_simulated_audio_call_records_both_sides_heard():
    call_repo = MagicMock()
    call_repo.create.return_value = {
        "id": "duplex-call",
        "room_name": "",
        "status": "connecting",
    }

    manager = CallManager(_Settings(), _config())
    call_id: str | None = None

    try:
        call_info = await manager.start_call(
            agent_id="duplex-agent",
            graph=_greeting_graph(),
            call_repo=call_repo,
            agent_model=MODEL,
            persona=PERSONA,
            simulator_model=MODEL,
            max_turns=3,
        )
        call_id = call_info["call_id"]
        active_call = manager.get_active_call(call_id)

        # Generous window: both cascades cold-start whisper + LLM + kokoro, plus
        # two observer STT passes, across several turns with no human driving.
        agent_heard: list[dict] = []
        caller_heard: list[dict] = []
        for _ in range(2400):
            agent_heard = _heard(active_call.transcript, "assistant")
            caller_heard = _heard(active_call.transcript, "user")
            if agent_heard and caller_heard:
                break
            await asyncio.sleep(0.1)

        assert agent_heard, f"no assistant heard; transcript={active_call.transcript}"
        assert caller_heard, f"no caller heard; transcript={active_call.transcript}"
    finally:
        if call_id is not None:
            await manager.end_call(call_id, call_repo)
