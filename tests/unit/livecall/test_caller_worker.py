"""Tests for the caller worker end-of-call wait."""

import asyncio

import pytest

from voicetest.livecall.caller_worker import await_end_of_call


class TestAwaitEndOfCall:
    @pytest.mark.asyncio
    async def test_returns_on_deadline_when_no_event_fires(self):
        disconnect_event = asyncio.Event()
        done = asyncio.Event()

        await asyncio.wait_for(
            await_end_of_call(disconnect_event, done, max_duration_seconds=0.05),
            timeout=1.0,
        )

    @pytest.mark.asyncio
    async def test_returns_on_disconnect_without_waiting_deadline(self):
        disconnect_event = asyncio.Event()
        done = asyncio.Event()
        disconnect_event.set()

        await asyncio.wait_for(
            await_end_of_call(disconnect_event, done, max_duration_seconds=100),
            timeout=1.0,
        )
