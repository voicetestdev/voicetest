"""In-process WebSocket broadcast primitives.

`BroadcastBus` is the low-level pub/sub primitive (per-channel WebSocket
set + replay queue). `SessionRegistry` composes it with a typed session
dict for `CallManager`/`ChatManager`-style managers that track per-id
state alongside the broadcast channel. `RunCoordinator` uses `BroadcastBus`
directly because its per-run state is bespoke (cancel flags + orphan
cleanup).

Threading contract: all bus operations run on the FastAPI event loop. Each
channel has its own `asyncio.Lock` covering attach (drain queue then
subscribe) AND broadcast (send to all subscribers under the lock), so
messages land in a single total order per channel and a connecting client
receives queued backlog before any newly-broadcast message.
"""

import asyncio
import contextlib
import json
from typing import Any


class BroadcastBus:
    """Per-channel WebSocket pub/sub with replay-on-attach semantics."""

    def __init__(self) -> None:
        self._channels: dict[str, dict[str, Any]] = {}

    def start(self, channel: str) -> None:
        """Open a channel so subscribers can attach and broadcasts can land."""
        self._channels[channel] = {
            "websockets": set(),
            "message_queue": [],
            "lock": asyncio.Lock(),
        }

    def end(self, channel: str) -> None:
        """Drop a channel's state. Subsequent operations are no-ops."""
        self._channels.pop(channel, None)

    def is_active(self, channel: str) -> bool:
        return channel in self._channels

    def subscribers(self, channel: str) -> set:
        """Live websocket set for the channel (empty set if channel is gone)."""
        ch = self._channels.get(channel)
        return ch["websockets"] if ch else set()

    async def attach(self, channel: str, websocket: Any) -> None:
        """Replay any queued backlog to this websocket, then subscribe it.

        Holds the per-channel lock for the entire drain + subscribe
        transition, blocking concurrent broadcasts so they can't be
        delivered ahead of older queued messages."""
        ch = self._channels.get(channel)
        if ch is None:
            return
        async with ch["lock"]:
            for msg in ch["message_queue"]:
                try:
                    await websocket.send_text(msg)
                except Exception:
                    return  # client gone mid-replay
            ch["message_queue"] = []
            ch["websockets"].add(websocket)

    def detach(self, channel: str, websocket: Any) -> None:
        ch = self._channels.get(channel)
        if ch is not None:
            ch["websockets"].discard(websocket)

    async def broadcast(self, channel: str, data: dict) -> None:
        """Send to all subscribers; queue for later if none are attached.

        Lock covers the whole send so concurrent broadcasts can't interleave:
        subscribers see messages in the order they were broadcast."""
        ch = self._channels.get(channel)
        if ch is None:
            return
        message = json.dumps(data)
        async with ch["lock"]:
            if not ch["websockets"]:
                ch["message_queue"].append(message)
                return
            dead = []
            for ws in list(ch["websockets"]):
                try:
                    await ws.send_text(message)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                ch["websockets"].discard(ws)


class SessionRegistry[TSession]:
    """Per-id session dict + BroadcastBus, the shared shape behind CallManager / ChatManager.

    Owns the lifecycle pair (`register` / `close`) plus the trivial bus
    delegations (`broadcast` / `attach` / `detach`). Subscribers are closed
    inside `close()` so callers don't have to remember the order."""

    def __init__(self) -> None:
        self._sessions: dict[str, TSession] = {}
        self._bus = BroadcastBus()

    def register(self, session_id: str, session: TSession) -> None:
        self._sessions[session_id] = session
        self._bus.start(session_id)

    def get(self, session_id: str) -> TSession | None:
        return self._sessions.get(session_id)

    def __contains__(self, session_id: str) -> bool:
        return session_id in self._sessions

    async def close(self, session_id: str, final_message: dict | None = None) -> None:
        """Broadcast `final_message` (if any), kick subscribers, drop the session."""
        if session_id not in self._sessions:
            return
        if final_message is not None:
            await self._bus.broadcast(session_id, final_message)
        for ws in list(self._bus.subscribers(session_id)):
            with contextlib.suppress(Exception):
                await ws.close()
        self._sessions.pop(session_id, None)
        self._bus.end(session_id)

    async def broadcast(self, session_id: str, data: dict) -> None:
        await self._bus.broadcast(session_id, data)

    async def attach(self, session_id: str, websocket: Any) -> None:
        await self._bus.attach(session_id, websocket)

    def detach(self, session_id: str, websocket: Any) -> None:
        self._bus.detach(session_id, websocket)
