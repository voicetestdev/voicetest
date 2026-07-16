"""Voice participant builders for live calls.

A VoiceParticipant produces a LiveKit AgentSession for one side of a call.
Cascade (STT -> LLM -> TTS) is the only implementation today.

The interface is shaped to admit a future RealtimeParticipant that wraps a
native speech-to-speech model in the llm slot: it does not assume a separable
LLM, and it treats intended text as an optional capability (a cascade exposes
the LLM's intended output; an S2S model has no separable text brain, so it
exposes only what the observer hears). A RealtimeParticipant is not built yet
and is expected to refine this contract when first implemented.
"""

from __future__ import annotations

from typing import Protocol
from typing import runtime_checkable

from livekit.agents import llm as lk_llm
from livekit.agents import stt as lk_stt
from livekit.agents import tts as lk_tts
from livekit.agents import vad as lk_vad
from livekit.agents.voice import AgentSession


@runtime_checkable
class VoiceParticipant(Protocol):
    """One side of a live call, capable of building its AgentSession."""

    intended_text_available: bool

    def build_session(self) -> AgentSession: ...


class CascadeParticipant:
    """Cascade pipeline participant: STT -> LLM -> TTS.

    White-box: the wrapped LLM exposes intended text, so
    intended_text_available is True."""

    intended_text_available = True

    def __init__(
        self,
        stt: lk_stt.STT,
        llm: lk_llm.LLM,
        tts: lk_tts.TTS,
        vad: lk_vad.VAD,
        allow_interruptions: bool = False,
    ):
        self.stt = stt
        self.llm = llm
        self.tts = tts
        self.vad = vad
        self.allow_interruptions = allow_interruptions

    def build_session(self) -> AgentSession:
        return AgentSession(
            stt=self.stt,
            llm=self.llm,
            tts=self.tts,
            vad=self.vad,
            allow_interruptions=self.allow_interruptions,
        )
