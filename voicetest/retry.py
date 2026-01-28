"""Retry utilities for handling transient LLM errors."""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import random
import time

import litellm
import openai


@dataclass
class RetryError:
    """Information about a retry-triggering error."""

    error_type: str
    message: str
    attempt: int
    max_attempts: int
    retry_after: float


# Callback type for error notifications
OnErrorCallback = Callable[[RetryError], Awaitable[None] | None]

# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.APIConnectionError,
    openai.APITimeoutError,
)


def _calculate_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


async def with_retry(
    func: Callable[[], Awaitable],
    max_attempts: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_error: OnErrorCallback | None = None,
):
    """Execute an async function with exponential backoff retry on rate limit errors.

    Default delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s = 123s total before giving up.

    Args:
        func: Async function to execute.
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        on_error: Optional callback for error notifications.

    Returns:
        Result of the function.

    Raises:
        The last error if all retries are exhausted.
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except RETRYABLE_EXCEPTIONS as e:
            last_error = e

            if attempt == max_attempts:
                raise

            retry_after = _calculate_delay(attempt, base_delay, max_delay)

            if on_error:
                error_info = RetryError(
                    error_type=type(e).__name__,
                    message=str(e),
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_after=retry_after,
                )
                result = on_error(error_info)
                if result is not None and hasattr(result, "__await__"):
                    await result

            await asyncio.sleep(retry_after)

    raise last_error


def with_retry_sync(
    func: Callable,
    max_attempts: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_error: Callable[[RetryError], None] | None = None,
):
    """Execute a sync function with exponential backoff retry on rate limit errors.

    Default delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s = 123s total before giving up.

    Args:
        func: Sync function to execute.
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        on_error: Optional callback for error notifications (sync only).

    Returns:
        Result of the function.

    Raises:
        The last error if all retries are exhausted.
    """
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except RETRYABLE_EXCEPTIONS as e:
            last_error = e

            if attempt == max_attempts:
                raise

            retry_after = _calculate_delay(attempt, base_delay, max_delay)

            if on_error:
                error_info = RetryError(
                    error_type=type(e).__name__,
                    message=str(e),
                    attempt=attempt,
                    max_attempts=max_attempts,
                    retry_after=retry_after,
                )
                on_error(error_info)

            time.sleep(retry_after)

    raise last_error
