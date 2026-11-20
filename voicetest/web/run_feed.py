"""Per-agent push feed of run-list changes.

`RunService` publishes from synchronous code that may run on the event loop
or in a worker thread, so `publish` hops onto the loop captured at attach
time. Nothing is queued: an agent with no subscribers drops its events, and
clients refetch the run list on (re)connect.
"""

import asyncio
from typing import Any

from voicetest.web.broadcast import BroadcastBus


class RunFeed:
    def __init__(self) -> None:
        self._bus = BroadcastBus()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._tasks: set[asyncio.Task] = set()
        self._watched: set[str] = set()

    @property
    def watched(self) -> bool:
        return bool(self._watched)

    async def attach(self, agent_id: str, websocket: Any) -> None:
        self._loop = asyncio.get_running_loop()
        if not self._bus.is_active(agent_id):
            self._bus.start(agent_id)
            self._watched.add(agent_id)
        await self._bus.attach(agent_id, websocket)

    def detach(self, agent_id: str, websocket: Any) -> None:
        self._bus.detach(agent_id, websocket)
        if not self._bus.subscribers(agent_id):
            self._bus.end(agent_id)
            self._watched.discard(agent_id)

    def publish(self, agent_id: str, data: dict) -> None:
        loop = self._loop
        if loop is None or loop.is_closed() or not self._bus.subscribers(agent_id):
            return
        loop.call_soon_threadsafe(self._schedule, agent_id, data)

    def _schedule(self, agent_id: str, data: dict) -> None:
        task = asyncio.ensure_future(self._bus.broadcast(agent_id, data))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
