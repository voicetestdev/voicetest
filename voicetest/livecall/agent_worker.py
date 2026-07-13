"""Agent worker subprocess for live calls.

This module runs as a subprocess that connects to a LiveKit room and runs
the voice agent. Transcript updates are streamed to stdout as JSON lines.

IMPORTANT: This uses the same ConversationEngine as the test runner to
ensure tests and live calls behave identically.

Usage:
    python -m voicetest.livecall.agent_worker --room ROOM --url URL --token TOKEN
    python -m voicetest.livecall.agent_worker --room ROOM --url URL --token TOKEN --backend local
    # AgentGraph JSON is read from stdin
"""

import argparse
import asyncio
from collections.abc import Callable
import contextlib
import json
import os
import sys
import traceback

from livekit import rtc
from livekit.agents import stt as lk_stt
from livekit.agents.voice import Agent
from livekit.plugins import openai
from livekit.plugins import silero

from voicetest.engine.conversation import ConversationEngine
from voicetest.livecall.audio_observer import AudioObserver
from voicetest.livecall.livekit_adapter import VoicetestLLM
from voicetest.livecall.observer import ObserverTranscript
from voicetest.livecall.observer_mount import observe_participant
from voicetest.livecall.participant import CascadeParticipant
from voicetest.models.agent import AgentGraph
from voicetest.settings import resolve_model


# The agent participant joins with this identity (see CallManager.generate_token).
AGENT_IDENTITY = "agent"


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

    Each observed segment is tagged with the current turn id (the id of the most
    recent intended assistant turn) so the consumer can concatenate the STT
    segments of one turn onto that turn's message."""

    def __init__(self, current_turn_id):
        super().__init__()
        self._current_turn_id = current_turn_id

    def add_observed(self, role, heard, **kwargs):
        message = super().add_observed(role, heard, **kwargs)
        output_observed(role, heard, turn_id=self._current_turn_id())
        return message


def build_stt(args) -> lk_stt.STT:
    """Build the STT component for the selected backend."""
    if args.backend == "local":
        return openai.STT(
            base_url=args.whisper_url,
            api_key="not-needed",
            model="Systran/faster-whisper-base.en",
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
            base_url=args.kokoro_url,
            api_key="not-needed",
            model="kokoro",
            voice="af_heart",
        )
    if args.backend == "mlx":
        if not MLX_AVAILABLE:
            output_error("MLX backend requires mlx-audio: uv sync --extra macos")
            sys.exit(1)
        return MlxKokoroTTS()
    return openai.TTS()


def get_general_prompt(graph: AgentGraph) -> str:
    """Get the general prompt from the agent graph.

    Returns the general_prompt from source_metadata, or a default."""
    return graph.source_metadata.get("general_prompt", "You are a helpful voice assistant.")


async def opening_turn(
    engine: ConversationEngine, on_response: Callable[[str], None]
) -> str | None:
    """Produce the agent's opening turn from the graph entry node.

    Mirrors the text runner, which advances once before any user input
    (engine/session.py) so the agent always speaks first. Emits the intended
    transcript via on_response and returns the greeting to speak, or None when
    the entry node yields no response."""
    result = await engine.advance()
    if result.response:
        on_response(result.response)
        return result.response
    return None


def main() -> None:
    """Main entry point for the agent worker."""
    parser = argparse.ArgumentParser(description="Voicetest agent worker")
    parser.add_argument("--room", required=True, help="LiveKit room name")
    parser.add_argument("--url", required=True, help="LiveKit server URL")
    parser.add_argument("--token", required=True, help="LiveKit access token")
    parser.add_argument(
        "--backend",
        choices=["openai", "local", "mlx"],
        default=os.environ.get("VOICETEST_BACKEND", "openai"),
        help="Voice backend: 'openai' (OpenAI API), 'local' (Docker whisper+kokoro), 'mlx' (macOS)",
    )
    parser.add_argument(
        "--whisper-url",
        default=os.environ.get("WHISPER_URL", "http://localhost:8001/v1"),
        help="Whisper STT API URL (for local backend)",
    )
    parser.add_argument(
        "--kokoro-url",
        default=os.environ.get("KOKORO_URL", "http://localhost:8002/v1"),
        help="Kokoro TTS API URL (for local backend)",
    )
    parser.add_argument(
        "--agent-model",
        default=None,
        help="LLM model from global settings (overrides graph.default_model)",
    )
    parser.add_argument(
        "--dynamic-variables",
        default="{}",
        help="JSON string of dynamic variables for template substitution",
    )
    parser.add_argument(
        "--observer-token",
        default=None,
        help="LiveKit token for the observer participant that transcribes the agent's audio",
    )

    args = parser.parse_args()

    graph_json = sys.stdin.read()
    if not graph_json:
        output_error("No agent graph provided on stdin")
        sys.exit(1)

    try:
        graph = AgentGraph.model_validate_json(graph_json)
    except Exception as e:
        output_error(f"Invalid agent graph: {e}")
        sys.exit(1)

    async def run():
        output_status("connecting")

        room = rtc.Room()
        observer_room: rtc.Room | None = None
        observer_tasks: list[asyncio.Task] = []

        try:
            print(f"[agent-worker] connecting to {args.url}", file=sys.stderr, flush=True)
            await room.connect(args.url, args.token)
            output_status("connected")
            print("[agent-worker] connected to room", file=sys.stderr, flush=True)

            resolved = resolve_model(
                settings_value=args.agent_model,
                role_default=graph.default_model,
            )
            print(
                f"[agent-worker] backend={args.backend}, model={resolved}",
                file=sys.stderr,
                flush=True,
            )

            # Parse dynamic variables
            dynamic_variables = json.loads(args.dynamic_variables)

            # Create ConversationEngine - same logic as test runner
            engine = ConversationEngine(
                graph=graph, model=resolved, dynamic_variables=dynamic_variables or None
            )

            # Create VoicetestLLM that wraps the engine. Each intended response
            # advances the turn counter; the observer tags its heard segments with
            # the same id so they correlate regardless of STT segmentation.
            turn_counter = {"n": 0}
            voicetest_llm = VoicetestLLM(engine)

            def on_response(text: str) -> None:
                turn_counter["n"] += 1
                output_transcript("assistant", text, turn_id=turn_counter["n"])

            voicetest_llm.set_on_response(on_response)

            # Select the cascade STT/TTS components based on backend choice
            stt = build_stt(args)
            tts = build_tts(args)

            # One VAD instance, shared by the cascade session and the observer STT.
            vad = silero.VAD.load()
            session = CascadeParticipant(
                stt=stt,
                llm=voicetest_llm,
                tts=tts,
                vad=vad,
            ).build_session()

            # Get instructions from graph for Agent
            instructions = get_general_prompt(graph)
            agent = Agent(instructions=instructions)

            # Listen for user input transcriptions. Assistant transcripts are
            # emitted by VoicetestLLM via set_on_response (immediately, before TTS).
            @session.on("user_input_transcribed")
            def on_user_speech(event):
                if event.is_final and event.transcript:
                    output_transcript("user", event.transcript)

            # Register room disconnect handler BEFORE starting session
            disconnect_event = asyncio.Event()

            @room.on("disconnected")
            def on_disconnect():
                print("[agent-worker] room disconnected event", file=sys.stderr, flush=True)
                disconnect_event.set()

            output_status("active")
            print("[agent-worker] starting session", file=sys.stderr, flush=True)

            # Start the agent session
            await session.start(agent, room=room)
            print("[agent-worker] session.start() returned", file=sys.stderr, flush=True)

            # Observe the agent's own published audio from a second participant, so
            # the transcript records what was heard on the wire alongside intended text.
            if args.observer_token:
                observer_room = rtc.Room()
                observer = AudioObserver(
                    stt=streaming_stt(build_stt(args), vad),
                    transcript=EmittingObserverTranscript(lambda: turn_counter["n"]),
                )
                observe_participant(
                    observer_room, observer, AGENT_IDENTITY, "assistant", observer_tasks
                )

                await observer_room.connect(args.url, args.observer_token)
                print("[agent-worker] observer connected", file=sys.stderr, flush=True)

            # Agent speaks first, matching the text runner (the entry node's
            # opening turn advances before any user input). Emitted after the
            # observer connects so the greeting is transcribed on the wire too.
            opening = await opening_turn(engine, on_response)
            if opening:
                await session.say(opening)

            # Wait for room disconnect (session runs until room disconnects)
            print("[agent-worker] waiting for disconnect", file=sys.stderr, flush=True)
            await disconnect_event.wait()
            print("[agent-worker] disconnect event received", file=sys.stderr, flush=True)

        except Exception as e:
            print(f"[agent-worker] exception: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
            print(
                f"[agent-worker] traceback: {traceback.format_exc()}", file=sys.stderr, flush=True
            )
            output_error(f"Agent error: {e}")
        finally:
            for task in observer_tasks:
                task.cancel()
            if observer_tasks:
                # Let each observe_track run its cleanup (flush last final, aclose).
                await asyncio.gather(*observer_tasks, return_exceptions=True)
            # Best-effort disconnects: a failure tearing down one connection (e.g.
            # an observer room that never finished connecting) must not skip the other.
            if observer_room is not None:
                with contextlib.suppress(Exception):
                    await observer_room.disconnect()
            print("[agent-worker] disconnecting from room", file=sys.stderr, flush=True)
            with contextlib.suppress(Exception):
                await room.disconnect()
            output_status("disconnected")

    asyncio.run(run())


if __name__ == "__main__":
    main()
