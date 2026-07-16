"""Caller worker subprocess for live calls.

Runs as a subprocess that joins a LiveKit room as the simulated user and drives
the caller side of a live call from a UserSimulator, so a test call runs fully
over audio with no human. Mirror of agent_worker: the agent runs the graph,
this runs the persona.

The agent speaks first (see agent_worker.opening_turn), so the caller reacts to
the agent's turns rather than initiating. The call ends when the room
disconnects or the caller reaches its max-turns cap.

Usage:
    python -m voicetest.livecall.caller_worker --room ROOM --url URL --token TOKEN \
        --persona PERSONA --model MODEL
"""

import argparse
import asyncio
import contextlib
import os
import sys
import traceback

from livekit import rtc
from livekit.agents.voice import Agent
from livekit.plugins import silero

from voicetest.livecall.audio_observer import AudioObserver
from voicetest.livecall.observer_mount import observe_participant
from voicetest.livecall.participant import CascadeParticipant
from voicetest.livecall.simulator_adapter import SimulatorLLM
from voicetest.livecall.worker_io import EmittingObserverTranscript
from voicetest.livecall.worker_io import build_stt
from voicetest.livecall.worker_io import build_tts
from voicetest.livecall.worker_io import output_error
from voicetest.livecall.worker_io import output_status
from voicetest.livecall.worker_io import output_transcript
from voicetest.livecall.worker_io import streaming_stt
from voicetest.simulator.user_sim import UserSimulator


# The caller participant joins with this identity (see CallManager.generate_token).
USER_IDENTITY = "user"

# When the caller reaches its max-turns cap the conversation ends, but the final
# turn is still being spoken and transcribed; give it time before teardown.
END_OF_CALL_GRACE_SECONDS = 3.0

# Ceiling on how long a single turn (agent speech + caller STT/LLM/TTS) can take.
# The overall call deadline is this times the turn cap: it guarantees teardown
# even if the simulator stalls and neither the disconnect nor the cap ever fires.
MAX_SECONDS_PER_TURN = 60.0


async def await_end_of_call(
    disconnect_event: asyncio.Event,
    done: asyncio.Event,
    max_duration_seconds: float,
) -> None:
    """Wait until the room disconnects, the caller hits its turn cap, or the
    overall call deadline passes.

    The deadline is a safety net: if the simulator keeps failing and the agent
    never hangs up, neither event fires, so without it both this worker and the
    server-side watcher would wait forever."""
    waiters = [
        asyncio.create_task(disconnect_event.wait()),
        asyncio.create_task(done.wait()),
    ]
    try:
        await asyncio.wait(
            waiters, timeout=max_duration_seconds, return_when=asyncio.FIRST_COMPLETED
        )
    finally:
        for waiter in waiters:
            waiter.cancel()
        await asyncio.gather(*waiters, return_exceptions=True)
    # Ended on the caller's max-turns cap (not a room disconnect): let the final
    # turn finish being spoken and observed before tearing down.
    if done.is_set() and not disconnect_event.is_set():
        await asyncio.sleep(END_OF_CALL_GRACE_SECONDS)


def main() -> None:
    """Main entry point for the caller worker."""
    parser = argparse.ArgumentParser(description="Voicetest caller worker")
    parser.add_argument("--room", required=True, help="LiveKit room name")
    parser.add_argument("--url", required=True, help="LiveKit server URL")
    parser.add_argument("--token", required=True, help="LiveKit access token")
    parser.add_argument(
        "--persona",
        required=True,
        help="User persona prompt (identity/goal/personality) for the simulated caller",
    )
    parser.add_argument("--model", required=True, help="LLM model for the simulated user")
    parser.add_argument(
        "--max-turns",
        type=int,
        default=20,
        help="Maximum caller turns before ending the call",
    )
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
        "--observer-token",
        default=None,
        help="LiveKit token for the observer participant that transcribes the caller's audio",
    )

    args = parser.parse_args()

    async def run():
        output_status("connecting")

        room = rtc.Room()
        observer_room: rtc.Room | None = None
        observer_tasks: list[asyncio.Task] = []

        try:
            print(f"[caller-worker] connecting to {args.url}", file=sys.stderr, flush=True)
            await room.connect(args.url, args.token)
            output_status("connected")
            print("[caller-worker] connected to room", file=sys.stderr, flush=True)

            simulator = UserSimulator(args.persona, args.model)

            # Each caller response advances the turn counter; the observer tags its
            # heard segments with the same id so they correlate regardless of STT
            # segmentation. The cap ends the call if the agent never hangs up.
            turn_counter = {"n": 0}
            done = asyncio.Event()
            sim_llm = SimulatorLLM(simulator)

            def on_response(text: str) -> None:
                turn_counter["n"] += 1
                output_transcript("user", text, turn_id=turn_counter["n"])
                if turn_counter["n"] >= args.max_turns:
                    done.set()

            sim_llm.set_on_response(on_response)

            stt = build_stt(args)
            tts = build_tts(args)

            # One VAD instance, shared by the cascade session and the observer STT.
            vad = silero.VAD.load()
            session = CascadeParticipant(
                stt=stt,
                llm=sim_llm,
                tts=tts,
                vad=vad,
            ).build_session()

            agent = Agent(instructions=args.persona)

            disconnect_event = asyncio.Event()

            @room.on("disconnected")
            def on_disconnect():
                print("[caller-worker] room disconnected event", file=sys.stderr, flush=True)
                disconnect_event.set()

            output_status("active")
            print("[caller-worker] starting session", file=sys.stderr, flush=True)

            await session.start(agent, room=room)
            print("[caller-worker] session.start() returned", file=sys.stderr, flush=True)

            # Observe the caller's own published audio from a second participant, so
            # the transcript records what the caller sounded like on the wire.
            if args.observer_token:
                observer_room = rtc.Room()
                observer = AudioObserver(
                    stt=streaming_stt(build_stt(args), vad),
                    transcript=EmittingObserverTranscript(),
                    turn_id_provider=lambda: turn_counter["n"],
                )
                observe_participant(observer_room, observer, USER_IDENTITY, "user", observer_tasks)
                await observer_room.connect(args.url, args.observer_token)
                print("[caller-worker] observer connected", file=sys.stderr, flush=True)

            # Run until the room disconnects (agent ended the call), the caller
            # reaches its max-turns cap, or the overall call deadline passes.
            print("[caller-worker] waiting for end of call", file=sys.stderr, flush=True)
            await await_end_of_call(disconnect_event, done, args.max_turns * MAX_SECONDS_PER_TURN)
            print("[caller-worker] end of call", file=sys.stderr, flush=True)

        except Exception as e:
            print(
                f"[caller-worker] exception: {type(e).__name__}: {e}", file=sys.stderr, flush=True
            )
            print(
                f"[caller-worker] traceback: {traceback.format_exc()}", file=sys.stderr, flush=True
            )
            output_error(f"Caller error: {e}")
        finally:
            for task in observer_tasks:
                task.cancel()
            if observer_tasks:
                # Let each observe_track run its cleanup (flush last final, aclose).
                await asyncio.gather(*observer_tasks, return_exceptions=True)
            # Best-effort disconnects: a failure tearing down one connection must
            # not skip the other.
            if observer_room is not None:
                with contextlib.suppress(Exception):
                    await observer_room.disconnect()
            print("[caller-worker] disconnecting from room", file=sys.stderr, flush=True)
            with contextlib.suppress(Exception):
                await room.disconnect()
            output_status("disconnected")

    asyncio.run(run())


if __name__ == "__main__":
    main()
