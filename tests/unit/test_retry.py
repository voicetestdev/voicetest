"""Tests for voicetest.retry module."""

import litellm
import openai
import pytest


class TestWithRetry:
    """Tests for with_retry async function."""

    async def test_success_on_first_attempt(self):
        from voicetest.retry import with_retry

        call_count = 0

        async def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = await with_retry(succeed)
        assert result == "success"
        assert call_count == 1

    async def test_retry_on_rate_limit_then_succeed(self):
        from voicetest.retry import with_retry

        call_count = 0

        async def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.RateLimitError(
                    message="Rate limit exceeded",
                    llm_provider="test",
                    model="test-model",
                )
            return "success"

        result = await with_retry(fail_then_succeed, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    async def test_raises_after_max_attempts(self):
        from voicetest.retry import with_retry

        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise litellm.RateLimitError(
                message="Rate limit exceeded",
                llm_provider="test",
                model="test-model",
            )

        with pytest.raises(litellm.RateLimitError):
            await with_retry(always_fail, max_attempts=3, base_delay=0.01)

        assert call_count == 3

    async def test_on_error_callback_called(self):
        from voicetest.retry import RetryError
        from voicetest.retry import with_retry

        errors_received: list[RetryError] = []

        async def on_error(error: RetryError):
            errors_received.append(error)

        call_count = 0

        async def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.RateLimitError(
                    message="Rate limit exceeded",
                    llm_provider="test",
                    model="test-model",
                )
            return "success"

        await with_retry(fail_twice, base_delay=0.01, on_error=on_error)

        assert len(errors_received) == 2
        assert errors_received[0].attempt == 1
        assert errors_received[1].attempt == 2
        assert errors_received[0].error_type == "RateLimitError"

    async def test_non_rate_limit_error_not_retried(self):
        from voicetest.retry import with_retry

        call_count = 0

        async def raise_other_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not a rate limit error")

        with pytest.raises(ValueError, match="Not a rate limit error"):
            await with_retry(raise_other_error, base_delay=0.01)

        assert call_count == 1


class TestWithRetrySync:
    """Tests for with_retry_sync function."""

    def test_success_on_first_attempt(self):
        from voicetest.retry import with_retry_sync

        call_count = 0

        def succeed():
            nonlocal call_count
            call_count += 1
            return "success"

        result = with_retry_sync(succeed)
        assert result == "success"
        assert call_count == 1

    def test_retry_on_rate_limit_then_succeed(self):
        from voicetest.retry import with_retry_sync

        call_count = 0

        def fail_then_succeed():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.RateLimitError(
                    message="Rate limit exceeded",
                    llm_provider="test",
                    model="test-model",
                )
            return "success"

        result = with_retry_sync(fail_then_succeed, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        from voicetest.retry import with_retry_sync

        call_count = 0

        def always_fail():
            nonlocal call_count
            call_count += 1
            raise litellm.RateLimitError(
                message="Rate limit exceeded",
                llm_provider="test",
                model="test-model",
            )

        with pytest.raises(litellm.RateLimitError):
            with_retry_sync(always_fail, max_attempts=3, base_delay=0.01)

        assert call_count == 3

    def test_on_error_callback_called(self):
        """on_error callback should be invoked on each retry attempt."""
        from voicetest.retry import RetryError
        from voicetest.retry import with_retry_sync

        errors_received: list[RetryError] = []

        def on_error(error: RetryError):
            errors_received.append(error)

        call_count = 0

        def fail_twice():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.RateLimitError(
                    message="Rate limit exceeded",
                    llm_provider="test",
                    model="test-model",
                )
            return "success"

        with_retry_sync(fail_twice, base_delay=0.01, on_error=on_error)

        assert len(errors_received) == 2
        assert errors_received[0].attempt == 1
        assert errors_received[1].attempt == 2
        assert errors_received[0].error_type == "RateLimitError"


class TestRetryableExceptions:
    """Tests for retrying on various exception types."""

    async def test_retry_on_timeout(self):
        """Should retry on litellm.Timeout."""
        from voicetest.retry import with_retry

        call_count = 0

        async def fail_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.Timeout(
                    message="Request timed out",
                    model="test-model",
                    llm_provider="test",
                )
            return "success"

        result = await with_retry(fail_with_timeout, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    async def test_retry_on_api_connection_error(self):
        """Should retry on litellm.APIConnectionError."""
        from voicetest.retry import with_retry

        call_count = 0

        async def fail_with_connection_error():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise litellm.APIConnectionError(
                    message="Connection failed",
                    model="test-model",
                    llm_provider="test",
                )
            return "success"

        result = await with_retry(fail_with_connection_error, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    async def test_retry_on_openai_timeout(self):
        """Should retry on openai.APITimeoutError."""
        from voicetest.retry import with_retry

        call_count = 0

        async def fail_with_openai_timeout():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise openai.APITimeoutError(request=None)
            return "success"

        result = await with_retry(fail_with_openai_timeout, base_delay=0.01)
        assert result == "success"
        assert call_count == 3

    async def test_on_error_reports_correct_type_for_timeout(self):
        """on_error should report correct error_type for different exceptions."""
        from voicetest.retry import RetryError
        from voicetest.retry import with_retry

        errors_received: list[RetryError] = []

        async def on_error(error: RetryError):
            errors_received.append(error)

        call_count = 0

        async def fail_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise litellm.Timeout(
                    message="Request timed out",
                    model="test-model",
                    llm_provider="test",
                )
            return "success"

        await with_retry(fail_with_timeout, base_delay=0.01, on_error=on_error)

        assert len(errors_received) == 1
        assert errors_received[0].error_type == "Timeout"


class TestCalculateDelay:
    """Tests for delay calculation."""

    def test_exponential_backoff(self):
        from voicetest.retry import _calculate_delay

        # With base_delay=1.0, delays should be approximately 1, 2, 4, 8, 16...
        # (plus jitter up to 10%)
        delay1 = _calculate_delay(1, 1.0, 60.0)
        delay2 = _calculate_delay(2, 1.0, 60.0)
        delay3 = _calculate_delay(3, 1.0, 60.0)

        assert 1.0 <= delay1 <= 1.1
        assert 2.0 <= delay2 <= 2.2
        assert 4.0 <= delay3 <= 4.4

    def test_respects_max_delay(self):
        from voicetest.retry import _calculate_delay

        # Attempt 10 with base_delay=1 would be 512s, but max_delay=60 caps it
        delay = _calculate_delay(10, 1.0, 60.0)
        assert delay <= 66.0  # 60 + 10% jitter
