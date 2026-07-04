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


def output_transcript(role: str, content: str) -> None:
    """Output a transcript message to stdout as JSON."""
    msg = {
        "type": "transcript",
        "message": {
            "role": role,
            "content": content,
        },
    }
    print(json.dumps(msg), flush=True)


def output_error(message: str) -> None:
    """Output an error message to stdout as JSON."""
    msg = {"type": "error", "message": message}
    print(json.dumps(msg), flush=True)


def output_status(status: str) -> None:
    """Output a status update to stdout as JSON."""
    msg = {"type": "status", "status": status}
    print(json.dumps(msg), flush=True)


def output_observed(role: str, heard: str) -> None:
    """Output an observed (heard-on-the-wire) transcript line to stdout as JSON."""
    print(json.dumps({"type": "observed", "role": role, "heard": heard}), flush=True)


class EmittingObserverTranscript(ObserverTranscript):
    """ObserverTranscript that streams each observed turn to stdout as it lands."""

    def add_observed(self, role, heard, **kwargs):
        message = super().add_observed(role, heard, **kwargs)
        output_observed(role, heard)
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


def streaming_stt(stt: lk_stt.STT) -> lk_stt.STT:
    """Wrap a non-streaming STT so AudioObserver can call .stream() on it."""
    if stt.capabilities.streaming:
        return stt
    return lk_stt.StreamAdapter(stt=stt, vad=silero.VAD.load())


def get_general_prompt(graph: AgentGraph) -> str:
    """Get the general prompt from the agent graph.

    Returns the general_prompt from source_metadata, or a default."""
    return graph.source_metadata.get("general_prompt", "You are a helpful voice assistant.")


def main() -> None:
    """Main entry point for the agent worker."""
    parser = argparse.ArgumentParser(description="Voicetest agent worker")
    parser.add_argument("--room", required=True, help="LiveKit room name")
    parser.add_argument("--url", required=True, help="LiveKit server URL")
    parser.add_argument("--token", required=True, help="LiveKit access token")
    parser.add_argument(
        "--backend",
        choices=["openai", "local"],
        default=os.environ.get("VOICETEST_BACKEND", "openai"),
        help="Voice backend: 'openai' for OpenAI API, 'local' for Ollama+MLX",
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

            # Create VoicetestLLM that wraps the engine
            voicetest_llm = VoicetestLLM(engine)
            voicetest_llm.set_on_response(lambda text: output_transcript("assistant", text))

            # Select the cascade STT/TTS components based on backend choice
            stt = build_stt(args)
            if args.backend == "local":
                # Local OSS stack via Docker: Whisper + local TTS + Kokoro
                print(
                    f"[agent-worker] local backend: whisper={args.whisper_url},"
                    f" kokoro={args.kokoro_url}",
                    file=sys.stderr,
                    flush=True,
                )
                tts = openai.TTS(
                    base_url=args.kokoro_url,
                    api_key="not-needed",
                    model="kokoro",
                    voice="af_heart",
                )
            elif args.backend == "mlx":
                # macOS Metal-accelerated stack
                tts = MlxKokoroTTS()
            else:
                # OpenAI backend
                tts = openai.TTS()

            session = CascadeParticipant(
                stt=stt,
                llm=voicetest_llm,
                tts=tts,
                vad=silero.VAD.load(),
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
                    stt=streaming_stt(build_stt(args)),
                    transcript=EmittingObserverTranscript(),
                )

                @observer_room.on("track_subscribed")
                def on_agent_track(track, publication, participant):
                    if (
                        track.kind == rtc.TrackKind.KIND_AUDIO
                        and participant.identity == AGENT_IDENTITY
                    ):
                        stream = rtc.AudioStream(track)
                        observer_tasks.append(
                            asyncio.create_task(observer.observe_track(stream, "assistant"))
                        )

                await observer_room.connect(args.url, args.observer_token)
                print("[agent-worker] observer connected", file=sys.stderr, flush=True)

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
            if observer_room is not None:
                await observer_room.disconnect()
            print("[agent-worker] disconnecting from room", file=sys.stderr, flush=True)
            await room.disconnect()
            output_status("disconnected")

    asyncio.run(run())


if __name__ == "__main__":
    main()
