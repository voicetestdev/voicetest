"""Shared IO and component builders for the live-call worker subprocesses.

The agent worker and the caller worker are separate subprocess entry points that
speak the same JSON line protocol to stdout and build their STT/TTS from the same
backend flags. Those shared pieces live here so neither worker reaches into the
other's module.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from livekit.agents import stt as lk_stt
from livekit.plugins import openai

from voicetest.livecall.observer import ObserverTranscript
from voicetest.settings import AudioSettings


try:
    from voicetest.plugins.mlx import MlxKokoroTTS
    from voicetest.plugins.mlx import MlxWhisperSTT

    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False
    MlxKokoroTTS = None
    MlxWhisperSTT = None


def output_transcript(role: str, content: str, turn_id: int | None = None) -> None:
    """Output a transcript message to stdout as JSON.

    turn_id ties an intended assistant turn to the observer's heard segments of
    the same turn so they can be correlated regardless of STT segmentation."""
    msg = {
        "type": "transcript",
        "message": {
            "role": role,
            "content": content,
        },
    }
    if turn_id is not None:
        msg["turn_id"] = turn_id
    print(json.dumps(msg), flush=True)


def output_error(message: str) -> None:
    """Output an error message to stdout as JSON."""
    msg = {"type": "error", "message": message}
    print(json.dumps(msg), flush=True)


def output_status(status: str) -> None:
    """Output a status update to stdout as JSON."""
    msg = {"type": "status", "status": status}
    print(json.dumps(msg), flush=True)


def output_observed(role: str, heard: str, turn_id: int | None = None) -> None:
    """Output an observed (heard-on-the-wire) transcript line to stdout as JSON."""
    msg = {"type": "observed", "role": role, "heard": heard}
    if turn_id is not None:
        msg["turn_id"] = turn_id
    print(json.dumps(msg), flush=True)


class EmittingObserverTranscript(ObserverTranscript):
    """ObserverTranscript that streams each observed turn to stdout as it lands.

    The turn id is supplied by the AudioObserver (captured at speech-start) so
    each observed segment carries the id of the turn it belongs to, letting the
    consumer concatenate the STT segments of one turn onto that turn's message."""

    def add_observed(self, role, heard, *, turn_id=None, **kwargs):
        message = super().add_observed(role, heard, turn_id=turn_id, **kwargs)
        output_observed(role, heard, turn_id=turn_id)
        return message


def add_voice_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        choices=["openai", "local", "mlx"],
        default=os.environ.get("VOICETEST_BACKEND", "openai"),
        help="Voice backend: 'openai' (OpenAI API), 'local' (Docker whisper+kokoro), 'mlx' (macOS)",
    )
    parser.add_argument(
        "--audio-settings",
        type=AudioSettings.model_validate_json,
        default=AudioSettings(),
        help="AudioSettings JSON: STT/TTS URLs, models and voice (for local and mlx backends)",
    )


def build_stt(args) -> lk_stt.STT:
    """Build the STT component for the selected backend."""
    if args.backend == "local":
        return openai.STT(
            base_url=args.audio_settings.stt_url,
            api_key="not-needed",
            model=args.audio_settings.stt_model,
        )
    if args.backend == "mlx":
        if not MLX_AVAILABLE:
            output_error("MLX backend requires mlx-audio: uv sync --extra macos")
            sys.exit(1)
        return MlxWhisperSTT()
    return openai.STT()


def streaming_stt(stt: lk_stt.STT, vad) -> lk_stt.STT:
    """Wrap a non-streaming STT so AudioObserver can call .stream() on it."""
    if stt.capabilities.streaming:
        return stt
    return lk_stt.StreamAdapter(stt=stt, vad=vad)


def build_tts(args):
    """Build the TTS component for the selected backend."""
    if args.backend == "local":
        return openai.TTS(
            base_url=args.audio_settings.tts_url,
            api_key="not-needed",
            model=args.audio_settings.tts_model,
            voice=args.audio_settings.voice,
        )
    if args.backend == "mlx":
        if not MLX_AVAILABLE:
            output_error("MLX backend requires mlx-audio: uv sync --extra macos")
            sys.exit(1)
        return MlxKokoroTTS(voice=args.audio_settings.voice)
    return openai.TTS()
