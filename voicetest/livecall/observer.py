"""Observer transcript: what was actually heard on the wire.

The observer transcribes each participant's actually-published audio via STT
and records canonical Messages. A cascade turn carries both content (the
intended LLM text) and heard (the observed STT text); a turn with no separable
intended text (a native speech-to-speech model) carries heard only, which also
becomes its content so the transcript stays readable.

ObserverTranscript is the architecture-independent core. Wiring it to a live
LiveKit room (subscribing to audio tracks, running STT, timing latency) is the
caller's responsibility and is exercised end-to-end, not here.
"""

from __future__ import annotations

from voicetest.models.results import AudioMetadata
from voicetest.models.results import Message


class ObserverTranscript:
    """Accumulates canonical Messages from observed audio."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def add_observed(
        self,
        role: str,
        heard: str,
        *,
        intended: str | None = None,
        latency_ms: int | None = None,
        audio_ref: str | None = None,
        turn_id: int | None = None,
    ) -> Message:
        """Record an observed turn.

        content is the intended text when available (cascade), else the heard
        text (speech-to-speech). heard always holds the observed STT text.
        turn_id is a streaming-correlation hint for emitting subclasses; it is
        not stored on the canonical Message."""
        content = intended if intended is not None else heard
        msg = Message(role=role, content=content)
        msg.set_audio(AudioMetadata(heard=heard, latency_ms=latency_ms, audio_ref=audio_ref))
        self._messages.append(msg)
        return msg

    @property
    def messages(self) -> list[Message]:
        """A snapshot copy of the observed transcript."""
        return list(self._messages)
