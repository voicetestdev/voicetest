"""Live call management for voicetest.

Handles call lifecycle: room creation, token generation, subprocess management.
"""

import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field
import json
import logging
import os
import subprocess
from typing import Any
from uuid import uuid4

from livekit import api as livekit_api

from voicetest.models.agent import AgentGraph
from voicetest.services.settings import SettingsService
from voicetest.settings import resolve_model
from voicetest.web.broadcast import SessionRegistry


_logger = logging.getLogger(__name__)


# How often the caller-completion watcher polls the caller worker for exit.
_CALLER_POLL_SECONDS = 0.5

# Callback that saves a completed call as a run and returns the run id, invoked
# by the caller-completion watcher for simulated calls (no human hangs up).
OnCallerDone = Callable[[str], Awaitable[str | None]]


def _append_heard(message: dict, heard: str) -> None:
    """Concatenate an observed 'heard' segment onto a transcript message dict.

    Writes the same metadata['audio']['heard'] shape that Message.set_audio /
    Message.audio() use, preserving any other audio fields already present."""
    audio = message.setdefault("metadata", {}).setdefault("audio", {})
    prev = audio.get("heard")
    audio["heard"] = f"{prev} {heard}".strip() if prev else heard


def merge_observed_heard(
    transcript: list[dict], turn_messages: dict, role: str, heard: str, turn_id: int | None
) -> None:
    """Concatenate an observed 'heard' segment onto its intended turn's message.

    Each worker tags both intended and observed lines with a turn_id, so all STT
    segments of one turn land on that turn's message. The key is (role, turn_id)
    because the agent and caller each carry their own turn counter, so their ids
    collide without the role. If the intended message hasn't been recorded yet
    (rare ordering), a standalone turn is created and keyed the same way so later
    segments of the same turn still concatenate."""
    if not heard or not role:
        return
    key = (role, turn_id)
    message = turn_messages.get(key) if turn_id is not None else None
    if message is None:
        message = {"role": role, "content": heard}
        transcript.append(message)
        if turn_id is not None:
            turn_messages[key] = message
    _append_heard(message, heard)


def append_intended(
    transcript: list[dict], turn_messages: dict, message: dict, turn_id: int | None
) -> dict:
    """Record an intended turn's message, indexed by (role, turn_id).

    If an observed segment for the same (role, turn_id) already created a
    standalone message (out-of-order arrival), fill its content in place instead
    of appending a duplicate turn, so heard already gathered on it is kept."""
    key = (message["role"], turn_id) if turn_id is not None else None
    existing = turn_messages.get(key) if key is not None else None
    if existing is not None:
        existing["content"] = message["content"]
        return existing
    transcript.append(message)
    if key is not None:
        turn_messages[key] = message
    return message


@dataclass
class LiveKitConfig:
    """LiveKit connection configuration."""

    url: str = "ws://localhost:7880"
    public_url: str = "ws://localhost:7880"  # URL for browser connections
    api_key: str = "devkey"
    api_secret: str = "secret"
    voice_backend: str = "openai"  # 'openai', 'local', or 'mlx'
    whisper_url: str = "http://localhost:8001/v1"
    kokoro_url: str = "http://localhost:8002/v1"

    @classmethod
    def from_env(cls) -> "LiveKitConfig":
        """Load configuration from environment variables."""
        url = os.environ.get("LIVEKIT_URL", "ws://localhost:7880")
        return cls(
            url=url,
            public_url=os.environ.get("LIVEKIT_PUBLIC_URL", url),
            api_key=os.environ.get("LIVEKIT_API_KEY", "devkey"),
            api_secret=os.environ.get("LIVEKIT_API_SECRET", "secret"),
            voice_backend=os.environ.get("VOICETEST_BACKEND", "openai"),
            whisper_url=os.environ.get("WHISPER_URL", "http://localhost:8001/v1"),
            kokoro_url=os.environ.get("KOKORO_URL", "http://localhost:8002/v1"),
        )


@dataclass
class ActiveCall:
    """Tracks state of an active call."""

    call_id: str
    room_name: str
    process: subprocess.Popen | None = None
    caller_process: subprocess.Popen | None = None
    transcript: list = field(default_factory=list)
    turn_messages: dict = field(default_factory=dict)
    monitor_tasks: list = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)


class CallManager:
    """Manages live voice calls."""

    def __init__(
        self,
        settings_service: SettingsService,
        config: LiveKitConfig,
    ):
        self.config = config
        self._sessions: SessionRegistry[ActiveCall] = SessionRegistry()
        self._settings = settings_service

    async def create_room(self, room_name: str) -> None:
        """Create a LiveKit room."""
        url = self.config.url.replace("ws://", "http://").replace("wss://", "https://")
        async with livekit_api.LiveKitAPI(
            url=url,
            api_key=self.config.api_key,
            api_secret=self.config.api_secret,
        ) as lk:
            await lk.room.create_room(livekit_api.CreateRoomRequest(name=room_name))

    def generate_token(self, room_name: str, identity: str, is_agent: bool = False) -> str:
        """Generate a LiveKit access token."""
        grant = livekit_api.VideoGrants(
            room_join=True,
            room=room_name,
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
            agent=is_agent,
        )

        token = (
            livekit_api.AccessToken(self.config.api_key, self.config.api_secret)
            .with_identity(identity)
            .with_name(identity)
            .with_grants(grant)
        )
        return token.to_jwt()

    def _worker_cmd(
        self, module: str, room_name: str, token: str, observer_token: str
    ) -> list[str]:
        """Build the shared prefix for a live-call worker subprocess command."""
        return [
            "uv",
            "run",
            "python",
            "-m",
            module,
            "--room",
            room_name,
            "--url",
            self.config.url,
            "--token",
            token,
            "--backend",
            self.config.voice_backend,
            "--whisper-url",
            self.config.whisper_url,
            "--kokoro-url",
            self.config.kokoro_url,
            "--observer-token",
            observer_token,
        ]

    def _caller_cmd(
        self,
        room_name: str,
        token: str,
        observer_token: str,
        persona: str,
        model: str,
        max_turns: int | None = None,
    ) -> list[str]:
        """Build the command that launches the simulated caller worker."""
        cmd = self._worker_cmd("voicetest.livecall.caller_worker", room_name, token, observer_token)
        cmd.extend(["--persona", persona, "--model", model])
        if max_turns is not None:
            cmd.extend(["--max-turns", str(max_turns)])
        return cmd

    async def start_call(
        self,
        agent_id: str,
        graph: AgentGraph,
        call_repo: Any,
        agent_model: str | None = None,
        dynamic_variables: dict | None = None,
        persona: str | None = None,
        simulator_model: str | None = None,
        max_turns: int | None = None,
        test_id: str | None = None,
        on_caller_done: OnCallerDone | None = None,
    ) -> dict:
        """Start a new live call.

        Creates a LiveKit room, generates tokens, and spawns the agent worker.
        When persona is given, also spawns a simulated caller worker so the call
        runs fully over audio with no human; otherwise the returned user token is
        for a human caller to join from the browser."""
        settings = self._settings.get_settings()
        if agent_model is None:
            agent_model = settings.models.agent

        # A persona (even empty) marks the call as simulated: a caller worker
        # drives the user side, so no human joins. None means a human caller.
        simulated = persona is not None

        call_id = str(uuid4())
        room_name = f"voicetest-{call_id[:8]}"

        await self.create_room(room_name)

        user_token = self.generate_token(room_name, "user", is_agent=False)

        call_record = call_repo.create(agent_id, room_name, test_id=test_id)
        call_repo.update_status(call_record["id"], "connecting")

        active_call = ActiveCall(
            call_id=call_record["id"],
            room_name=room_name,
        )
        self._sessions.register(call_record["id"], active_call)

        graph_json = graph.model_dump_json()
        agent_token = self.generate_token(room_name, "agent", is_agent=True)
        observer_token = self.generate_token(room_name, "observer", is_agent=False)

        # Use 'uv run' to ensure we use the venv Python in Docker
        # This avoids issues where sys.executable might not be the venv Python
        cmd = self._worker_cmd(
            "voicetest.livecall.agent_worker", room_name, agent_token, observer_token
        )

        if agent_model:
            cmd.extend(["--agent-model", agent_model])

        if dynamic_variables:
            cmd.extend(["--dynamic-variables", json.dumps(dynamic_variables)])

        if simulated:
            # The caller worker owns the user turns; the agent must not also emit
            # the user's speech from its own STT or each user turn is duplicated.
            cmd.append("--no-user-transcript")

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            text=True,
        )

        if process.stdin:
            process.stdin.write(graph_json)
            process.stdin.close()

        active_call.process = process

        active_call.monitor_tasks.append(
            asyncio.create_task(self._monitor_agent_output(call_record["id"], process, call_repo))
        )

        # Simulated caller: join the user side over audio so no human is needed.
        # Uses its own observer identity so it can transcribe the caller's own
        # published track without colliding with the agent observer.
        if simulated:
            simulator_model = resolve_model(simulator_model or settings.models.simulator)
            caller_observer_token = self.generate_token(
                room_name, "caller-observer", is_agent=False
            )
            caller_cmd = self._caller_cmd(
                room_name, user_token, caller_observer_token, persona, simulator_model, max_turns
            )
            caller_process = subprocess.Popen(
                caller_cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=None,
                text=True,
            )
            active_call.caller_process = caller_process
            active_call.monitor_tasks.append(
                asyncio.create_task(
                    self._monitor_agent_output(call_record["id"], caller_process, call_repo)
                )
            )
            # No human hangs up a simulated call, so the backend ends and saves it
            # when the caller worker exits. Only when a save callback is supplied
            # (the web path); the CLI drives its own completion and save.
            if on_caller_done is not None:
                asyncio.create_task(
                    self._end_when_caller_done(
                        call_record["id"], caller_process, call_repo, on_caller_done
                    )
                )

        call_repo.update_status(call_record["id"], "active")

        return {
            "call_id": call_record["id"],
            "room_name": room_name,
            "livekit_url": self.config.public_url,
            # The caller worker holds the user token in simulated mode; don't hand
            # it to the browser too or the two collide on identity "user".
            "token": None if simulated else user_token,
        }

    @staticmethod
    def _terminate_processes(active_call: "ActiveCall") -> None:
        """Terminate the call's worker subprocesses, killing any that don't exit."""
        for proc in (active_call.process, active_call.caller_process):
            if proc and proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()

    async def _end_when_caller_done(
        self,
        call_id: str,
        caller_process: subprocess.Popen,
        call_repo: Any,
        on_caller_done: OnCallerDone,
    ) -> None:
        """Save and end a simulated call once its caller worker exits.

        Polls (without holding a thread) until the caller worker exits — no human
        hangs up — then tears the call down, saves it as a run via on_caller_done,
        and broadcasts call_ended carrying the run id so attached clients show it."""
        while caller_process.poll() is None:
            active_call = self._sessions.get(call_id)
            if active_call is None or active_call.cancel_event.is_set():
                return
            await asyncio.sleep(_CALLER_POLL_SECONDS)

        active_call = self._sessions.get(call_id)
        if active_call is None or active_call.cancel_event.is_set():
            return

        active_call.cancel_event.set()
        self._terminate_processes(active_call)
        # Let the output monitors drain the workers' final turns before saving.
        await asyncio.gather(*active_call.monitor_tasks, return_exceptions=True)
        call_repo.end_call(call_id)

        # Always tear the session down, even if the save raises (a judge/LLM call
        # can fail); otherwise the session and its sockets would leak with no human
        # to end the call.
        run_id = None
        try:
            run_id = await on_caller_done(call_id)
        except Exception:
            _logger.exception("Failed to save simulated call %s as a run", call_id)
        finally:
            await self._sessions.close(call_id, {"type": "call_ended", "run_id": run_id})

    async def _persist_and_broadcast(self, call_id: str, call_repo: Any, active_call) -> None:
        """Persist the current transcript and broadcast it to attached clients."""
        call_repo.update_transcript(call_id, active_call.transcript)
        await self._sessions.broadcast(
            call_id,
            {"type": "transcript_update", "transcript": active_call.transcript},
        )

    async def _ingest_line(
        self, call_id: str, call_repo: Any, active_call: "ActiveCall", line: str
    ) -> None:
        """Parse one worker stdout line and fold it into the transcript."""
        try:
            data = json.loads(line.strip())
        except json.JSONDecodeError:
            return
        if data.get("type") == "transcript" and data.get("message"):
            append_intended(
                active_call.transcript,
                active_call.turn_messages,
                data["message"],
                data.get("turn_id"),
            )
            await self._persist_and_broadcast(call_id, call_repo, active_call)
        elif data.get("type") == "observed":
            merge_observed_heard(
                active_call.transcript,
                active_call.turn_messages,
                data.get("role"),
                data.get("heard"),
                data.get("turn_id"),
            )
            await self._persist_and_broadcast(call_id, call_repo, active_call)

    async def _monitor_agent_output(
        self,
        call_id: str,
        process: subprocess.Popen,
        call_repo: Any,
    ) -> None:
        """Monitor agent worker stdout for transcript updates."""
        active_call = self._sessions.get(call_id)
        if active_call is None:
            return

        try:
            loop = asyncio.get_running_loop()
            while process.poll() is None:
                if active_call.cancel_event.is_set():
                    process.terminate()
                    break

                if process.stdout:
                    line = await loop.run_in_executor(None, process.stdout.readline)
                    if line:
                        await self._ingest_line(call_id, call_repo, active_call, line)
                else:
                    await asyncio.sleep(0.1)

            # Drain output buffered before the process exited so a run saved right
            # after teardown still records the final turns.
            if process.stdout:
                while True:
                    line = await loop.run_in_executor(None, process.stdout.readline)
                    if not line:
                        break
                    await self._ingest_line(call_id, call_repo, active_call, line)

            exit_code = process.poll()

            # Broadcast error if process exited unexpectedly
            if exit_code != 0 and not active_call.cancel_event.is_set():
                error_msg = f"Agent worker exited with code {exit_code} (check logs for details)"
                await self._sessions.broadcast(
                    call_id,
                    {"type": "error", "message": error_msg},
                )

        except Exception as e:
            await self._sessions.broadcast(
                call_id,
                {"type": "error", "message": str(e)},
            )
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    async def end_call(self, call_id: str, call_repo: Any) -> dict | None:
        """End a call and clean up resources."""
        active_call = self._sessions.get(call_id)
        if active_call is None:
            return call_repo.end_call(call_id)

        # The caller-done watcher may already be ending this call (and about to
        # broadcast call_ended with the run id); don't race it with a second,
        # run-id-less broadcast.
        if active_call.cancel_event.is_set():
            return call_repo.end_call(call_id)

        active_call.cancel_event.set()
        self._terminate_processes(active_call)
        await self._sessions.close(call_id, {"type": "call_ended"})

        return call_repo.end_call(call_id)

    def get_active_call(self, call_id: str) -> ActiveCall | None:
        """Get active call state."""
        return self._sessions.get(call_id)

    async def attach_websocket(self, call_id: str, websocket: Any) -> None:
        """Subscribe a WebSocket to call updates (after replaying any backlog)."""
        await self._sessions.attach(call_id, websocket)

    def detach_websocket(self, call_id: str, websocket: Any) -> None:
        self._sessions.detach(call_id, websocket)
