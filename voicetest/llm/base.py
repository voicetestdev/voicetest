"""Centralized LLM call handling.

All LLM calls should go through this module to ensure consistent
retry behavior, error handling, and future enhancements.
"""

import asyncio
from collections.abc import Awaitable
from collections.abc import Callable

import dspy
from dspy.adapters.baml_adapter import BAMLAdapter
from dspy.streaming import StreamListener
from dspy.streaming import streamify

from voicetest.llm.claudecode import ClaudeCodeLM
from voicetest.retry import OnErrorCallback
from voicetest.retry import with_retry


# Callback type for token updates: receives token string
OnTokenCallback = Callable[[str], Awaitable[None] | None]


def _create_lm(model: str) -> dspy.LM:
    """Create an LM instance for the given model string.

    Handles custom providers like claudecode/ prefix.
    """
    if model.startswith("claudecode/"):
        return ClaudeCodeLM(model)
    return dspy.LM(model)


async def _invoke_callback(callback: Callable, *args) -> None:
    """Invoke callback, handling both sync and async."""
    result = callback(*args)
    if result is not None and hasattr(result, "__await__"):
        await result


async def call_llm(
    model: str,
    signature_class: type,
    on_token: OnTokenCallback | None = None,
    stream_field: str | None = None,
    on_error: OnErrorCallback | None = None,
    **kwargs,
) -> dspy.Prediction:
    if on_token:
        if not stream_field:
            raise ValueError("stream_field required when on_token is provided")
        return await _call_llm_streaming(
            model, signature_class, on_token, stream_field, on_error, **kwargs
        )
    else:
        return await _call_llm_sync(model, signature_class, on_error, **kwargs)


async def _call_llm_sync(
    model: str,
    signature_class: type,
    on_error: OnErrorCallback | None = None,
    **kwargs,
) -> dspy.Prediction:
    """Non-streaming LLM call with BAMLAdapter for better structured output."""
    lm = _create_lm(model)
    adapter = BAMLAdapter()

    def run_predictor():
        with dspy.context(lm=lm, adapter=adapter):
            predictor = dspy.Predict(signature_class)
            return predictor(**kwargs)

    async def call_in_thread():
        return await asyncio.to_thread(run_predictor)

    # Retry at async level so we use asyncio.sleep() instead of blocking time.sleep()
    return await with_retry(call_in_thread, on_error=on_error)


async def _call_llm_streaming(
    model: str,
    signature_class: type,
    on_token: OnTokenCallback,
    stream_field: str,
    on_error: OnErrorCallback | None = None,
    **kwargs,
) -> dspy.Prediction:
    """Streaming LLM call with token callbacks."""

    async def stream():
        lm = _create_lm(model)
        predictor = dspy.Predict(signature_class)
        stream_listeners = [StreamListener(signature_field_name=stream_field)]

        streaming_predictor = streamify(
            predictor,
            stream_listeners=stream_listeners,
            is_async_program=False,
        )

        result = None
        with dspy.context(lm=lm, adapter=None):
            async for chunk in streaming_predictor(**kwargs):
                if isinstance(chunk, dspy.Prediction):
                    result = chunk
                elif (
                    hasattr(chunk, "chunk")
                    and hasattr(chunk, "signature_field_name")
                    and chunk.signature_field_name == stream_field
                ):
                    await _invoke_callback(on_token, chunk.chunk)

        if result is None:
            raise RuntimeError("Streaming predictor did not return a Prediction")

        return result

    return await with_retry(stream, on_error=on_error)
