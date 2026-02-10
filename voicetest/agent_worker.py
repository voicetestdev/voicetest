"""Agent worker subprocess for live calls.

This module runs as a subprocess that connects to a LiveKit room and runs
the voice agent. Transcript updates are streamed to stdout as JSON lines.

IMPORTANT: This uses the same ConversationEngine as the test runner to
ensure tests and live calls behave identically.

Usage:
    python -m voicetest.agent_worker --room ROOM --url URL --token TOKEN
    python -m voicetest.agent_worker --room ROOM --url URL --token TOKEN --backend local
    # AgentGraph JSON is read from stdin
"""

import argparse
import asyncio
import json
import os
import sys
import traceback

from livekit import rtc
from livekit.agents.voice import Agent, AgentSession
from livekit.plugins import openai, silero

from voicetest.engine.conversation import ConversationEngine
from voicetest.engine.livekit_llm import VoicetestLLM
from voicetest.models.agent import AgentGraph


try:
    from voicetest.plugins.mlx import MlxKokoroTTS, MlxWhisperSTT

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


def get_general_prompt(graph: AgentGraph) -> str:
    """Get the general prompt from the agent graph.

    Returns the general_prompt from source_metadata, or a default.
    """
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
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434/v1"),
        help="Ollama API URL (for local backend)",
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

        try:
            print(f"[agent-worker] connecting to {args.url}", file=sys.stderr, flush=True)
            await room.connect(args.url, args.token)
            output_status("connected")
            print("[agent-worker] connected to room", file=sys.stderr, flush=True)

            model_name = graph.default_model or "gpt-4o-mini"
            print(
                f"[agent-worker] backend={args.backend}, model={model_name}",
                file=sys.stderr,
                flush=True,
            )

            # Create ConversationEngine - same logic as test runner
            engine = ConversationEngine(graph=graph, model=f"openai/{model_name}")

            # Create VoicetestLLM that wraps the engine
            voicetest_llm = VoicetestLLM(engine)

            # Configure the voice pipeline based on backend choice
            if args.backend == "local":
                # Local OSS stack via Docker: Whisper + Ollama + Kokoro
                ollama_model = model_name if ":" in model_name else "qwen2.5:0.5b"
                print(
                    f"[agent-worker] local backend: whisper={args.whisper_url},"
                    f" ollama={args.ollama_url}, kokoro={args.kokoro_url}",
                    file=sys.stderr,
                    flush=True,
                )
                # Update engine to use Ollama model
                engine.model = f"ollama/{ollama_model}"
                session = AgentSession(
                    stt=openai.STT(
                        base_url=args.whisper_url,
                        api_key="not-needed",
                        model="Systran/faster-whisper-base.en",
                    ),
                    llm=voicetest_llm,
                    tts=openai.TTS(
                        base_url=args.kokoro_url,
                        api_key="not-needed",
                        model="kokoro",
                        voice="af_heart",
                    ),
                    vad=silero.VAD.load(),
                )
            elif args.backend == "mlx":
                # macOS Metal-accelerated stack
                if not MLX_AVAILABLE:
                    output_error("MLX backend requires mlx-audio: uv sync --extra macos")
                    sys.exit(1)

                ollama_model = model_name if ":" in model_name else "qwen2.5:0.5b"
                engine.model = f"ollama/{ollama_model}"
                session = AgentSession(
                    stt=MlxWhisperSTT(),
                    llm=voicetest_llm,
                    tts=MlxKokoroTTS(),
                    vad=silero.VAD.load(),
                )
            else:
                # OpenAI backend
                session = AgentSession(
                    stt=openai.STT(),
                    llm=voicetest_llm,
                    tts=openai.TTS(),
                    vad=silero.VAD.load(),
                )

            # Get instructions from graph for Agent
            instructions = get_general_prompt(graph)
            agent = Agent(instructions=instructions)

            # Listen for user input transcriptions
            @session.on("user_input_transcribed")
            def on_user_speech(event):
                if event.is_final and event.transcript:
                    output_transcript("user", event.transcript)

            # Listen for agent speech to capture assistant responses
            @session.on("speech_created")
            def on_speech_created(event):
                handle = event.speech_handle

                # Add callback for when speech is done - chat_items will be populated
                def on_speech_done(h):
                    for item in h.chat_items:
                        text = getattr(item, "text_content", None)
                        if text:
                            output_transcript("assistant", text)

                handle.add_done_callback(on_speech_done)

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
            print("[agent-worker] disconnecting from room", file=sys.stderr, flush=True)
            await room.disconnect()
            output_status("disconnected")

    asyncio.run(run())


if __name__ == "__main__":
    main()
