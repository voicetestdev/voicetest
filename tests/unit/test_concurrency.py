import asyncio

import pytest

from voicetest.util.concurrency import run_bounded


async def _collect(items, worker, limit, **kwargs):
    return [pair async for pair in run_bounded(items, worker, limit, **kwargs)]


class TestRunBounded:
    async def test_never_exceeds_limit(self):
        in_flight = 0
        peak = 0

        async def worker(item):
            nonlocal in_flight, peak
            in_flight += 1
            peak = max(peak, in_flight)
            await asyncio.sleep(0.01)
            in_flight -= 1
            return item

        results = await _collect(range(10), worker, 3)

        assert peak == 3
        assert sorted(r for _, r in results) == list(range(10))

    async def test_limit_one_runs_sequentially_in_order(self):
        events = []

        async def worker(item):
            events.append(("start", item))
            await asyncio.sleep(0)
            events.append(("end", item))
            return item * 2

        results = await _collect([1, 2, 3], worker, 1)

        assert events == [
            ("start", 1),
            ("end", 1),
            ("start", 2),
            ("end", 2),
            ("start", 3),
            ("end", 3),
        ]
        assert results == [(1, 2), (2, 4), (3, 6)]

    async def test_unordered_yields_as_completed(self):
        async def worker(delay):
            await asyncio.sleep(delay)
            return delay

        results = await _collect([0.03, 0.01], worker, 2)

        assert [r for _, r in results] == [0.01, 0.03]

    async def test_ordered_yields_in_input_order(self):
        async def worker(delay):
            await asyncio.sleep(delay)
            return delay

        results = await _collect([0.03, 0.01, 0.02], worker, 3, ordered=True)

        assert [r for _, r in results] == [0.03, 0.01, 0.02]

    async def test_error_cancels_others_and_propagates(self):
        cancelled = []

        async def worker(item):
            if item == "boom":
                raise RuntimeError("boom")
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled.append(item)
                raise

        with pytest.raises(RuntimeError, match="boom"):
            await _collect(["slow", "boom"], worker, 2)

        assert cancelled == ["slow"]

    async def test_closing_early_cancels_running_workers(self):
        cancelled = []

        async def worker(item):
            try:
                await asyncio.sleep(0 if item == 0 else 10)
            except asyncio.CancelledError:
                cancelled.append(item)
                raise
            return item

        stream = run_bounded([0, 1, 2], worker, 3)
        assert await anext(stream) == (0, 0)
        await stream.aclose()

        assert sorted(cancelled) == [1, 2]

    async def test_rejects_limit_below_one(self):
        with pytest.raises(ValueError, match="at least 1"):
            await _collect([1], lambda x: asyncio.sleep(0), 0)

    async def test_empty_items(self):
        assert await _collect([], lambda x: asyncio.sleep(0), 4) == []
