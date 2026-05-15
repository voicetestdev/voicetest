"""Tests for RunCoordinator's composition of BroadcastBus.

Covers the audit gap: no test for RunCoordinator + BroadcastBus end-to-end. The
unit-level BroadcastBus behavior is exercised here via the coordinator's public
API (start/broadcast/attach/detach/end) using `AsyncMock` WebSockets — the same
shape the chat-manager unit tests use, but rooted at the coordinator layer.
"""

from unittest.mock import AsyncMock

import pytest

from voicetest.web.coordinator import RunCoordinator


@pytest.fixture
def coordinator() -> RunCoordinator:
    return RunCoordinator()


class TestRunCoordinatorBroadcast:
    """RunCoordinator delegates to its BroadcastBus correctly."""

    @pytest.mark.asyncio
    async def test_broadcast_to_attached_websocket(self, coordinator):
        run_id = "run-1"
        coordinator.start(run_id)

        ws = AsyncMock()
        await coordinator.attach(run_id, ws)

        await coordinator.broadcast(run_id, {"type": "test_started", "result_id": "r1"})
        ws.send_text.assert_called_once()
        coordinator.end(run_id)

    @pytest.mark.asyncio
    async def test_broadcast_before_attach_replays_on_attach(self, coordinator):
        """The replay-on-attach race that motivated the per-channel lock."""
        run_id = "run-2"
        coordinator.start(run_id)

        # Broadcast with no WS attached — message is queued.
        await coordinator.broadcast(run_id, {"type": "test_started"})
        await coordinator.broadcast(run_id, {"type": "test_completed"})

        ws = AsyncMock()
        await coordinator.attach(run_id, ws)

        # Both queued messages replayed in order.
        assert ws.send_text.call_count == 2
        first_payload = ws.send_text.call_args_list[0].args[0]
        second_payload = ws.send_text.call_args_list[1].args[0]
        assert '"type": "test_started"' in first_payload
        assert '"type": "test_completed"' in second_payload
        coordinator.end(run_id)

    @pytest.mark.asyncio
    async def test_detached_websocket_does_not_receive_broadcasts(self, coordinator):
        run_id = "run-3"
        coordinator.start(run_id)
        ws = AsyncMock()
        await coordinator.attach(run_id, ws)
        coordinator.detach(run_id, ws)

        await coordinator.broadcast(run_id, {"type": "test_started"})
        ws.send_text.assert_not_called()
        coordinator.end(run_id)

    @pytest.mark.asyncio
    async def test_dead_websocket_dropped_from_subscribers(self, coordinator):
        """A WS that raises on send_text is removed; later broadcasts don't retry it."""
        run_id = "run-4"
        coordinator.start(run_id)

        ws = AsyncMock()
        ws.send_text.side_effect = Exception("client gone")
        await coordinator.attach(run_id, ws)

        await coordinator.broadcast(run_id, {"type": "test_started"})

        ws.send_text.reset_mock()
        ws.send_text.side_effect = None
        await coordinator.broadcast(run_id, {"type": "test_completed"})
        ws.send_text.assert_not_called()
        coordinator.end(run_id)

    @pytest.mark.asyncio
    async def test_end_drops_channel_state(self, coordinator):
        run_id = "run-5"
        coordinator.start(run_id)
        assert coordinator.is_active(run_id)
        coordinator.end(run_id)
        assert not coordinator.is_active(run_id)

        # Operations on a dropped channel are no-ops, not errors.
        ws = AsyncMock()
        await coordinator.attach(run_id, ws)
        await coordinator.broadcast(run_id, {"type": "test_started"})
        ws.send_text.assert_not_called()


class TestRunCoordinatorCancellation:
    """Cancellation flags live alongside the bus; verify their independent semantics."""

    def test_cancel_run_sets_flag(self, coordinator):
        coordinator.start("r")
        assert not coordinator.is_run_cancelled("r")
        coordinator.cancel_run("r")
        assert coordinator.is_run_cancelled("r")
        coordinator.end("r")

    def test_cancel_test_only_marks_that_result(self, coordinator):
        coordinator.start("r")
        coordinator.cancel_test("r", "result-1")
        assert coordinator.is_test_cancelled("r", "result-1")
        assert not coordinator.is_test_cancelled("r", "result-2")
        # Test-level cancel does not propagate to run-level.
        assert not coordinator.is_run_cancelled("r")
        coordinator.end("r")

    def test_run_and_test_cancellation_are_independent(self, coordinator):
        coordinator.start("r")
        coordinator.cancel_run("r")
        coordinator.cancel_test("r", "result-1")
        assert coordinator.is_run_cancelled("r")
        assert coordinator.is_test_cancelled("r", "result-1")
        assert not coordinator.is_test_cancelled("r", "result-2")
        coordinator.end("r")

    def test_orphan_cleanup_is_single_flight(self, coordinator):
        """claim_orphan_cleanup yields True for the first caller, False for concurrent ones."""
        run_id = "orphan-run"
        with coordinator.claim_orphan_cleanup(run_id) as first:
            assert first is True
            with coordinator.claim_orphan_cleanup(run_id) as second:
                assert second is False
        # After the first context exits, a new caller can claim again.
        with coordinator.claim_orphan_cleanup(run_id) as again:
            assert again is True
