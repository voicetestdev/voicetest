"""Run async work over a list with a bounded number of workers."""

import asyncio
from collections.abc import AsyncIterator
from collections.abc import Awaitable
from collections.abc import Callable
from collections.abc import Sequence


async def run_bounded[T, R](
    items: Sequence[T],
    worker: Callable[[T], Awaitable[R]],
    limit: int,
    *,
    ordered: bool = False,
) -> AsyncIterator[tuple[T, R]]:
    """Run `worker` over `items` with at most `limit` in flight, yielding `(item, result)`.

    Results arrive as they finish, or in input order when `ordered`. If a worker
    raises, the others are cancelled and the error propagates. Closing the
    iterator early also cancels whatever is still running."""
    if limit < 1:
        raise ValueError(f"limit must be at least 1, got {limit}")

    pending = iter(enumerate(items))
    running: dict[asyncio.Task[R], tuple[int, T]] = {}
    buffered: dict[int, tuple[T, R]] = {}
    next_index = 0

    def fill() -> None:
        while len(running) < limit:
            entry = next(pending, None)
            if entry is None:
                return
            running[asyncio.ensure_future(worker(entry[1]))] = entry

    try:
        fill()
        while running:
            done, _ = await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            finished = sorted((running.pop(task), task) for task in done)
            errors = [task.exception() for _, task in finished]
            error = next((e for e in errors if e is not None), None)
            if error is not None:
                raise error
            fill()
            for (index, item), task in finished:
                buffered[index] = (item, task.result())
            if ordered:
                while next_index in buffered:
                    yield buffered.pop(next_index)
                    next_index += 1
            else:
                for index in sorted(buffered):
                    yield buffered.pop(index)
    finally:
        for task in running:
            task.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)
