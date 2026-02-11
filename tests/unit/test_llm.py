"""Tests for centralized LLM call handling."""

from unittest.mock import patch

import dspy
import litellm
import pytest

from voicetest.llm import _invoke_callback
from voicetest.llm import call_llm
from voicetest.retry import RetryError


class TestCallLlmValidation:
    """Test call_llm input validation."""

    @pytest.mark.asyncio
    async def test_raises_when_on_token_without_stream_field(self):
        """Should raise ValueError when on_token provided without stream_field."""

        class DummySignature(dspy.Signature):
            input: str = dspy.InputField()
            output: str = dspy.OutputField()

        with pytest.raises(ValueError, match="stream_field required"):
            await call_llm(
                "openai/gpt-4o-mini",
                DummySignature,
                on_token=lambda t: None,
                input="test",
            )


class TestCallLlmRetryCallback:
    """Test that on_error callback is invoked during retry."""

    @pytest.mark.asyncio
    async def test_on_error_called_on_rate_limit_non_streaming(self):
        """on_error callback should be invoked when RateLimitError occurs (non-streaming)."""
        from voicetest.llm import _call_llm_sync

        class DummySignature(dspy.Signature):
            input: str = dspy.InputField()
            output: str = dspy.OutputField()

        errors_received = []

        def on_error(error: RetryError):
            errors_received.append(error)

        call_count = 0

        def mock_predict(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.RateLimitError(
                    message="Rate limit exceeded",
                    llm_provider="openai",
                    model="gpt-4o-mini",
                )
            # Return a mock prediction
            return dspy.Prediction(output="success")

        with patch("dspy.Predict.__call__", side_effect=mock_predict):
            await _call_llm_sync(
                "openai/gpt-4o-mini",
                DummySignature,
                on_error=on_error,
                input="test",
            )

        # Should have received 2 error callbacks (attempts 1 and 2 failed)
        assert len(errors_received) == 2
        assert errors_received[0].attempt == 1
        assert errors_received[0].error_type == "RateLimitError"
        assert errors_received[1].attempt == 2


class TestCallLlmRetryIntegration:
    """Integration test for retry flow."""

    @pytest.mark.asyncio
    async def test_on_error_called_with_async_callback(self):
        """on_error should work with async callbacks in non-streaming mode."""
        from voicetest.llm import _call_llm_sync

        class DummySignature(dspy.Signature):
            input: str = dspy.InputField()
            output: str = dspy.OutputField()

        errors_received = []

        async def on_error(error: RetryError):
            errors_received.append(error)

        call_count = 0

        def mock_predict(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.RateLimitError(
                    message="Rate limit exceeded",
                    llm_provider="openai",
                    model="gpt-4o-mini",
                )
            return dspy.Prediction(output="success")

        with patch("dspy.Predict.__call__", side_effect=mock_predict):
            await _call_llm_sync(
                "openai/gpt-4o-mini",
                DummySignature,
                on_error=on_error,
                input="test",
            )

        assert len(errors_received) == 2
        assert errors_received[0].attempt == 1
        assert errors_received[1].attempt == 2


class TestInvokeCallback:
    """Test _invoke_callback helper."""

    @pytest.mark.asyncio
    async def test_invokes_sync_callback(self):
        """Should invoke sync callback."""
        called_with = []

        def sync_callback(value):
            called_with.append(value)

        await _invoke_callback(sync_callback, "test")

        assert called_with == ["test"]

    @pytest.mark.asyncio
    async def test_invokes_async_callback(self):
        """Should invoke async callback and await it."""
        called_with = []

        async def async_callback(value):
            called_with.append(value)

        await _invoke_callback(async_callback, "test")

        assert called_with == ["test"]

    @pytest.mark.asyncio
    async def test_passes_multiple_args(self):
        """Should pass multiple args to callback."""
        called_with = []

        def callback(*args):
            called_with.extend(args)

        await _invoke_callback(callback, "a", "b", "c")

        assert called_with == ["a", "b", "c"]
