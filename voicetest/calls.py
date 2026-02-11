"""Live call management for voicetest.

Handles call lifecycle: room creation, token generation, subprocess management.
"""

import asyncio
import contextlib
from dataclasses import dataclass
from dataclasses import field
import json
import os
import subprocess
from typing import Any
from uuid import uuid4

from livekit import api as livekit_api

from voicetest.models.agent import AgentGraph


@dataclass
class LiveKitConfig:
    """LiveKit connection configuration."""

    url: str = "ws://localhost:7880"
    public_url: str = "ws://localhost:7880"  # URL for browser connections
    api_key: str = "devkey"
    api_secret: str = "secret"
    voice_backend: str = "openai"  # 'openai', 'local', or 'mlx'
    ollama_url: str = "http://localhost:11434/v1"
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
            ollama_url=os.environ.get("OLLAMA_URL", "http://localhost:11434/v1"),
            whisper_url=os.environ.get("WHISPER_URL", "http://localhost:8001/v1"),
            kokoro_url=os.environ.get("KOKORO_URL", "http://localhost:8002/v1"),
        )


@dataclass
class ActiveCall:
    """Tracks state of an active call."""

    call_id: str
    room_name: str
    process: subprocess.Popen | None = None
    websockets: set = field(default_factory=set)
    transcript: list = field(default_factory=list)
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    message_queue: list = field(default_factory=list)


class CallManager:
    """Manages live voice calls."""

    def __init__(self, config: LiveKitConfig | None = None):
        self.config = config or LiveKitConfig.from_env()
        self._active_calls: dict[str, ActiveCall] = {}

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

    async def start_call(
        self,
        agent_id: str,
        graph: AgentGraph,
        call_repo: Any,
    ) -> dict:
        """Start a new live call.

        Creates LiveKit room, generates tokens, spawns agent worker subprocess.

        Returns:
            Dict with call_id, room_name, livekit_url, token (for user)
        """
        call_id = str(uuid4())
        room_name = f"voicetest-{call_id[:8]}"

        await self.create_room(room_name)

        user_token = self.generate_token(room_name, "user", is_agent=False)

        call_record = call_repo.create(agent_id, room_name)
        call_repo.update_status(call_record["id"], "connecting")

        active_call = ActiveCall(
            call_id=call_record["id"],
            room_name=room_name,
        )
        self._active_calls[call_record["id"]] = active_call

        graph_json = graph.model_dump_json()
        agent_token = self.generate_token(room_name, "agent", is_agent=True)

        # Use 'uv run' to ensure we use the venv Python in Docker
        # This avoids issues where sys.executable might not be the venv Python
        cmd = [
            "uv",
            "run",
            "python",
            "-m",
            "voicetest.agent_worker",
            "--room",
            room_name,
            "--url",
            self.config.url,
            "--token",
            agent_token,
            "--backend",
            self.config.voice_backend,
            "--ollama-url",
            self.config.ollama_url,
            "--whisper-url",
            self.config.whisper_url,
            "--kokoro-url",
            self.config.kokoro_url,
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if process.stdin:
            process.stdin.write(graph_json)
            process.stdin.close()

        active_call.process = process

        asyncio.create_task(self._monitor_agent_output(call_record["id"], process, call_repo))

        call_repo.update_status(call_record["id"], "active")

        return {
            "call_id": call_record["id"],
            "room_name": room_name,
            "livekit_url": self.config.public_url,
            "token": user_token,
        }

    async def _monitor_agent_output(
        self,
        call_id: str,
        process: subprocess.Popen,
        call_repo: Any,
    ) -> None:
        """Monitor agent worker stdout for transcript updates."""
        if call_id not in self._active_calls:
            return

        active_call = self._active_calls[call_id]

        try:
            loop = asyncio.get_running_loop()
            while process.poll() is None:
                if active_call.cancel_event.is_set():
                    process.terminate()
                    break

                if process.stdout:
                    line = await loop.run_in_executor(None, process.stdout.readline)
                    if line:
                        try:
                            data = json.loads(line.strip())
                            if data.get("type") == "transcript":
                                active_call.transcript.append(data["message"])
                                call_repo.update_transcript(call_id, active_call.transcript)
                                await self._broadcast_update(
                                    call_id,
                                    {
                                        "type": "transcript_update",
                                        "transcript": active_call.transcript,
                                    },
                                )
                        except json.JSONDecodeError:
                            pass
                else:
                    await asyncio.sleep(0.1)

            exit_code = process.poll()

            # Broadcast error if process exited unexpectedly
            if exit_code != 0 and not active_call.cancel_event.is_set():
                await self._broadcast_update(
                    call_id,
                    {"type": "error", "message": f"Agent worker exited with code {exit_code}"},
                )

        except Exception as e:
            await self._broadcast_update(
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

    async def _broadcast_update(self, call_id: str, data: dict) -> None:
        """Broadcast update to all WebSocket clients watching this call."""
        if call_id not in self._active_calls:
            return

        active_call = self._active_calls[call_id]
        message = json.dumps(data)

        if not active_call.websockets:
            active_call.message_queue.append(message)
            return

        dead_sockets = []
        for ws in active_call.websockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead_sockets.append(ws)

        for ws in dead_sockets:
            active_call.websockets.discard(ws)

    async def end_call(self, call_id: str, call_repo: Any) -> dict | None:
        """End a call and clean up resources."""
        if call_id not in self._active_calls:
            return call_repo.end_call(call_id)

        active_call = self._active_calls[call_id]
        active_call.cancel_event.set()

        if active_call.process and active_call.process.poll() is None:
            active_call.process.terminate()
            try:
                active_call.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                active_call.process.kill()

        await self._broadcast_update(call_id, {"type": "call_ended"})

        for ws in list(active_call.websockets):
            with contextlib.suppress(Exception):
                await ws.close()

        del self._active_calls[call_id]

        return call_repo.end_call(call_id)

    def get_active_call(self, call_id: str) -> ActiveCall | None:
        """Get active call state."""
        return self._active_calls.get(call_id)

    def register_websocket(self, call_id: str, websocket: Any) -> list[str]:
        """Register a WebSocket for call updates.

        Returns queued messages for replay.
        """
        if call_id not in self._active_calls:
            return []

        active_call = self._active_calls[call_id]
        active_call.websockets.add(websocket)

        queued = active_call.message_queue
        active_call.message_queue = []
        return queued

    def unregister_websocket(self, call_id: str, websocket: Any) -> None:
        """Unregister a WebSocket from call updates."""
        if call_id in self._active_calls:
            self._active_calls[call_id].websockets.discard(websocket)


_call_manager: CallManager | None = None


def get_call_manager() -> CallManager:
    """Get or create the global CallManager instance."""
    global _call_manager
    if _call_manager is None:
        _call_manager = CallManager()
    return _call_manager
