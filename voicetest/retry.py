"""Retry utilities for handling transient LLM errors."""

import asyncio
from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
import random
import time

from dspy.utils.exceptions import AdapterParseError
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


class EmptyLLMOutputError(Exception):
    """Raised when an LLM returns None/empty for a required output field.

    Surfaced as a clear diagnostic instead of letting the None propagate
    into downstream pydantic validation with an opaque stacktrace.
    """

    def __init__(self, field_name: str, model: str):
        self.field_name = field_name
        self.model = model
        super().__init__(
            f"LLM returned None for required output field '{field_name}' (model: {model})"
        )


# Callback type for error notifications
OnErrorCallback = Callable[[RetryError], Awaitable[None] | None]

# Exceptions that should trigger a retry
RETRYABLE_EXCEPTIONS = (
    litellm.RateLimitError,
    litellm.Timeout,
    litellm.APIConnectionError,
    openai.APITimeoutError,
    AdapterParseError,
)


def _effective_max_attempts(
    exc: BaseException,
    max_attempts: int,
    max_attempts_by_exception: dict[type, int] | None,
) -> int:
    """Return the smaller of the caller's max_attempts and any per-exception cap.

    Walks the exception type's MRO so subclasses inherit caps from their parents.
    """
    if not max_attempts_by_exception:
        return max_attempts
    for cls in type(exc).__mro__:
        cap = max_attempts_by_exception.get(cls)
        if cap is not None:
            return min(max_attempts, cap)
    return max_attempts


def _calculate_delay(attempt: int, base_delay: float, max_delay: float) -> float:
    """Calculate delay with exponential backoff and jitter."""
    delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


def _retry_decision(
    exc: BaseException,
    attempt: int,
    max_attempts: int,
    base_delay: float,
    max_delay: float,
    max_attempts_by_exception: dict[type, int] | None,
) -> tuple[float, RetryError] | None:
    """Decide whether to retry after catching `exc` on the given attempt.

    Returns (retry_after, error_info) if the caller should sleep and retry,
    or None if the caller should give up and re-raise.
    """
    effective_max = _effective_max_attempts(exc, max_attempts, max_attempts_by_exception)
    if attempt >= effective_max:
        return None
    retry_after = _calculate_delay(attempt, base_delay, max_delay)
    error_info = RetryError(
        error_type=type(exc).__name__,
        message=str(exc),
        attempt=attempt,
        max_attempts=effective_max,
        retry_after=retry_after,
    )
    return retry_after, error_info


async def with_retry(
    func: Callable[[], Awaitable],
    max_attempts: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_error: OnErrorCallback | None = None,
    max_attempts_by_exception: dict[type, int] | None = None,
):
    """Execute an async function with exponential backoff retry on rate limit errors.

    Default delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s = 123s total before giving up.

    Args:
        func: Async function to execute.
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        on_error: Optional callback for error notifications.
        max_attempts_by_exception: Optional per-exception cap on attempts. Use
            this to bound expensive failure modes (e.g. timeouts that cost the
            full timeout per attempt) without changing the default budget for
            cheap failures (e.g. rate limits). Subclasses inherit caps via MRO.

    Returns:
        Result of the function.

    Raises:
        The last error if all retries are exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return await func()
        except RETRYABLE_EXCEPTIONS as e:
            decision = _retry_decision(
                e, attempt, max_attempts, base_delay, max_delay, max_attempts_by_exception
            )
            if decision is None:
                raise
            retry_after, error_info = decision
            if on_error:
                result = on_error(error_info)
                if result is not None and hasattr(result, "__await__"):
                    await result
            await asyncio.sleep(retry_after)


def with_retry_sync(
    func: Callable,
    max_attempts: int = 8,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    on_error: Callable[[RetryError], None] | None = None,
    max_attempts_by_exception: dict[type, int] | None = None,
):
    """Execute a sync function with exponential backoff retry on rate limit errors.

    Default delays: 1s, 2s, 4s, 8s, 16s, 32s, 60s = 123s total before giving up.

    Args:
        func: Sync function to execute.
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay in seconds.
        on_error: Optional callback for error notifications (sync only).
        max_attempts_by_exception: Optional per-exception cap on attempts. See
            with_retry for details.

    Returns:
        Result of the function.

    Raises:
        The last error if all retries are exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except RETRYABLE_EXCEPTIONS as e:
            decision = _retry_decision(
                e, attempt, max_attempts, base_delay, max_delay, max_attempts_by_exception
            )
            if decision is None:
                raise
            retry_after, error_info = decision
            if on_error:
                on_error(error_info)
            time.sleep(retry_after)
