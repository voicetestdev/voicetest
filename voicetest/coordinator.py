"""In-process coordination state for in-flight test runs.

Owns the per-run cancellation flags + orphan-cleanup single-flight, and
delegates WebSocket pub/sub to a `BroadcastBus`.

Registered as a Punq singleton so the FastAPI app, the WebSocket handlers,
and the background `_execute_run` task all share one instance per process.
"""

import asyncio
import contextlib
import threading
from typing import Any

from voicetest.broadcast import BroadcastBus


class RunCoordinator:
    """Per-run cancellation + orphan-cleanup + broadcast surface."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._bus = BroadcastBus()
        self._cleaning_orphans: set[str] = set()
        self._cleaning_orphans_lock = threading.Lock()

    def start(self, run_id: str) -> None:
        """Register a run as active. Called by start_run before submitting the job."""
        self._runs[run_id] = {
            "cancel": asyncio.Event(),
            "cancelled_tests": set(),
        }
        self._bus.start(run_id)

    def end(self, run_id: str) -> None:
        """Drop a run's coordination state. Called from _execute_run's finally."""
        self._runs.pop(run_id, None)
        self._bus.end(run_id)

    def is_active(self, run_id: str) -> bool:
        return run_id in self._runs

    async def attach(self, run_id: str, websocket: Any) -> None:
        await self._bus.attach(run_id, websocket)

    def detach(self, run_id: str, websocket: Any) -> None:
        self._bus.detach(run_id, websocket)

    async def broadcast(self, run_id: str, data: dict) -> None:
        await self._bus.broadcast(run_id, data)

    def cancel_run(self, run_id: str) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run["cancel"].set()

    def cancel_test(self, run_id: str, result_id: str) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run["cancelled_tests"].add(result_id)

    def is_test_cancelled(self, run_id: str, result_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        return result_id in run["cancelled_tests"]

    def is_cancelled(self, run_id: str, result_id: str | None = None) -> bool:
        """Check if the run is cancelled, or (optionally) if a specific test is."""
        run = self._runs.get(run_id)
        if run is None:
            return False
        if result_id and result_id in run["cancelled_tests"]:
            return True
        return run["cancel"].is_set()

    @contextlib.contextmanager
    def claim_orphan_cleanup(self, run_id: str):
        """Claim the orphan-cleanup slot for a run.

        Yields True if this caller owns the cleanup; False if another caller
        already claimed it. The slot is released on exit either way.
        """
        with self._cleaning_orphans_lock:
            if run_id in self._cleaning_orphans:
                owns = False
            else:
                self._cleaning_orphans.add(run_id)
                owns = True
        try:
            yield owns
        finally:
            if owns:
                with self._cleaning_orphans_lock:
                    self._cleaning_orphans.discard(run_id)
