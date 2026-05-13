"""In-process coordination state for in-flight test runs.

Owns the per-process state that backed the previous module-level globals in
`voicetest.rest`: which runs are currently executing, their cancel/cancelled-
test flags, the WebSocket subscriber sets, the message queues that buffer
broadcasts until a WebSocket connects, and the orphan-cleanup single-flight.

Registered as a Punq singleton so the FastAPI app, the WebSocket handlers,
and the background `_execute_run` task all share one instance per process.
"""

import asyncio
import contextlib
import json
import threading
from typing import Any


class RunCoordinator:
    """Coordinates in-flight run state: cancellation, broadcasts, orphan cleanup."""

    def __init__(self) -> None:
        self._runs: dict[str, dict[str, Any]] = {}
        self._cleaning_orphans: set[str] = set()
        self._cleaning_orphans_lock = threading.Lock()

    def start(self, run_id: str) -> None:
        """Register a run as active. Called by start_run before submitting the job."""
        self._runs[run_id] = {
            "cancel": asyncio.Event(),
            "websockets": set(),
            "cancelled_tests": set(),
            "message_queue": [],
        }

    def end(self, run_id: str) -> None:
        """Drop a run's coordination state. Called from _execute_run's finally."""
        self._runs.pop(run_id, None)

    def is_active(self, run_id: str) -> bool:
        return run_id in self._runs

    def register_websocket(self, run_id: str, websocket: Any) -> list[str]:
        """Register a WebSocket and return any queued messages to replay.

        Returns an empty list if the run has already ended.
        """
        run = self._runs.get(run_id)
        if run is None:
            return []
        run["websockets"].add(websocket)
        queued = run["message_queue"]
        run["message_queue"] = []
        return queued

    def unregister_websocket(self, run_id: str, websocket: Any) -> None:
        run = self._runs.get(run_id)
        if run is not None:
            run["websockets"].discard(websocket)

    async def broadcast(self, run_id: str, data: dict) -> None:
        """Send a message to all subscribers; queue it if none are connected yet."""
        run = self._runs.get(run_id)
        if run is None:
            return
        message = json.dumps(data)
        websockets = run["websockets"]
        if not websockets:
            run["message_queue"].append(message)
            return
        dead = []
        for ws in websockets:
            try:
                await ws.send_text(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            websockets.discard(ws)

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
