"""Centralized LLM call handling.

All LLM calls should go through this module to ensure consistent
retry behavior, error handling, and future enhancements.
"""

import asyncio
from collections.abc import Awaitable, Callable

import dspy
from dspy.adapters.baml_adapter import BAMLAdapter
from dspy.streaming import StreamListener, streamify

from voicetest.retry import OnErrorCallback, with_retry


# Callback type for token updates: receives token string
OnTokenCallback = Callable[[str], Awaitable[None] | None]


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
    """Execute an LLM call with automatic streaming/adapter handling.

    Single entry point for all LLM calls. Handles:
    - Streaming vs non-streaming based on on_token presence
    - Adapter selection (BAMLAdapter for non-streaming, None for streaming)
    - Retry logic with exponential backoff

    Args:
        model: LLM model identifier (e.g., "openai/gpt-4o-mini").
        signature_class: DSPy Signature class for the prediction.
        on_token: Optional callback for streaming tokens. If provided, enables streaming.
        stream_field: Field name to stream tokens for (required if on_token provided).
        on_error: Optional callback for retry notifications.
        **kwargs: Arguments to pass to the predictor.

    Returns:
        dspy.Prediction with the result.

    Usage:
        # Non-streaming
        result = await call_llm(
            "openai/gpt-4o-mini",
            MySignature,
            input="hello",
        )

        # Streaming
        result = await call_llm(
            "openai/gpt-4o-mini",
            MySignature,
            on_token=lambda t: print(t),
            stream_field="response",
            input="hello",
        )
    """
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
    lm = dspy.LM(model)
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
        lm = dspy.LM(model)
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
