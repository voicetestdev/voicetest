"""Reusable in-process WebSocket broadcast bus.

Shared by `RunCoordinator`, `CallManager`, and `ChatManager`. Each consumer
owns its own bus instance; channels are keyed by an opaque id (run_id /
call_id / chat_id) the consumer chooses.

Threading contract: all bus operations run on the FastAPI event loop. Each
channel has its own `asyncio.Lock` to serialize `attach()` (drain queue
then subscribe) against `broadcast()` (snapshot subscribers + send), so a
connecting client receives queued backlog before any newly-broadcast
message.
"""

import asyncio
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
        delivered ahead of older queued messages.
        """
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
        """Send to all subscribers; queue for later if none are attached."""
        ch = self._channels.get(channel)
        if ch is None:
            return
        message = json.dumps(data)
        async with ch["lock"]:
            if not ch["websockets"]:
                ch["message_queue"].append(message)
                return
            targets = list(ch["websockets"])  # snapshot — set may mutate during sends
        dead = []
        for ws in targets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        if dead:
            ch = self._channels.get(channel)
            if ch is not None:
                for ws in dead:
                    ch["websockets"].discard(ws)
