"""Tests for voicetest.llm.base module.

Covers centralized LLM call handling, cache salt behavior,
and no-cache integration with RunOptions.
"""

from unittest.mock import patch

import dspy
import litellm
import pytest

from voicetest.llm import _invoke_callback
from voicetest.llm import call_llm
from voicetest.llm.base import _create_lm
from voicetest.retry import RetryError


# ---------------------------------------------------------------------------
# call_llm input validation
# ---------------------------------------------------------------------------


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
                predictor_class=dspy.Predict,
                input="test",
            )


# ---------------------------------------------------------------------------
# Retry callback
# ---------------------------------------------------------------------------


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
                predictor_class=dspy.Predict,
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
                predictor_class=dspy.Predict,
                input="test",
            )

        assert len(errors_received) == 2
        assert errors_received[0].attempt == 1
        assert errors_received[1].attempt == 2


# ---------------------------------------------------------------------------
# _invoke_callback helper
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _create_lm cache salt
# ---------------------------------------------------------------------------


class TestCreateLmCacheSalt:
    """_create_lm with cache_salt produces different cache keys."""

    def test_no_salt_no_metadata(self):
        lm = _create_lm("openai/gpt-4o-mini")
        assert "metadata" not in lm.kwargs

    def test_salt_sets_metadata(self):
        lm = _create_lm("openai/gpt-4o-mini", cache_salt="abc123")
        assert lm.kwargs["metadata"] == {"_cache_salt": "abc123"}

    def test_different_salt_different_cache_key(self):
        lm1 = _create_lm("openai/gpt-4o-mini", cache_salt="aaa")
        lm2 = _create_lm("openai/gpt-4o-mini", cache_salt="bbb")

        messages = [{"role": "user", "content": "hello"}]
        ignored = ["api_key", "api_base", "base_url"]

        req1 = dict(model=lm1.model, messages=messages, **lm1.kwargs)
        req2 = dict(model=lm2.model, messages=messages, **lm2.kwargs)

        key1 = dspy.cache.cache_key(req1, ignored)
        key2 = dspy.cache.cache_key(req2, ignored)
        assert key1 != key2

    def test_no_salt_vs_salt_different_cache_key(self):
        lm1 = _create_lm("openai/gpt-4o-mini")
        lm2 = _create_lm("openai/gpt-4o-mini", cache_salt="abc")

        messages = [{"role": "user", "content": "hello"}]
        ignored = ["api_key", "api_base", "base_url"]

        req1 = dict(model=lm1.model, messages=messages, **lm1.kwargs)
        req2 = dict(model=lm2.model, messages=messages, **lm2.kwargs)

        key1 = dspy.cache.cache_key(req1, ignored)
        key2 = dspy.cache.cache_key(req2, ignored)
        assert key1 != key2


# ---------------------------------------------------------------------------
# _create_lm no_cache
# ---------------------------------------------------------------------------


class TestCreateLmNoCache:
    """_create_lm with no_cache=True disables DSPy caching."""

    def test_no_cache_false_by_default(self):
        lm = _create_lm("openai/gpt-4o-mini")
        assert lm.cache is True

    def test_no_cache_true_sets_cache_false(self):
        lm = _create_lm("openai/gpt-4o-mini", no_cache=True)
        assert lm.cache is False

    def test_no_cache_with_salt(self):
        """no_cache and cache_salt can coexist."""
        lm = _create_lm("openai/gpt-4o-mini", cache_salt="abc", no_cache=True)
        assert lm.cache is False
        assert lm.kwargs["metadata"] == {"_cache_salt": "abc"}


# ---------------------------------------------------------------------------
# ConversationEngine cache salt integration
# ---------------------------------------------------------------------------


class TestConversationEngineCacheSalt:
    """ConversationEngine passes cache_salt for response calls with transitions."""

    @pytest.mark.asyncio
    async def test_response_call_includes_cache_salt(self):
        """Response call should include transitions fingerprint as cache_salt."""
        from voicetest.engine.conversation import ConversationEngine
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Greet.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(type="llm_prompt", value="go to b"),
                        )
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="Help."),
            },
            entry_node_id="a",
            source_type="custom",
            source_metadata={"general_prompt": "Be helpful."},
        )

        engine = ConversationEngine(graph=graph, model="openai/gpt-4o-mini")

        call_args = []

        async def mock_call_llm(model, sig, *, cache_salt=None, **kwargs):
            call_args.append({"cache_salt": cache_salt, "sig_name": sig.__name__})
            return dspy.Prediction(
                response="Hello!", objectives_complete=False, transition_to="none"
            )

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.add_user_message("hi")
            await engine.advance()

        # First call is the transition call — no salt needed
        transition_call = call_args[0]
        assert transition_call["cache_salt"] is None

        # Second call is the response call — should have a cache_salt
        response_call = call_args[1]
        assert response_call["cache_salt"] is not None
        assert len(response_call["cache_salt"]) > 0

    @pytest.mark.asyncio
    async def test_salt_changes_when_edges_change(self):
        """Different outbound edges should produce different cache_salt values."""
        from voicetest.engine.conversation import ConversationEngine
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        def make_engine(targets: list[str]) -> ConversationEngine:
            graph = AgentGraph(
                nodes={
                    "a": AgentNode(
                        id="a",
                        state_prompt="Greet.",
                        transitions=[
                            Transition(
                                target_node_id=t,
                                condition=TransitionCondition(
                                    type="llm_prompt", value=f"go to {t}"
                                ),
                            )
                            for t in targets
                        ],
                    ),
                    "b": AgentNode(id="b", state_prompt="Help."),
                    "c": AgentNode(id="c", state_prompt="Support."),
                },
                entry_node_id="a",
                source_type="custom",
                source_metadata={"general_prompt": "Be helpful."},
            )
            return ConversationEngine(
                graph=graph,
                model="openai/gpt-4o-mini",
            )

        salts = []

        async def mock_call_llm(model, sig, *, cache_salt=None, **kwargs):
            salts.append(cache_salt)
            return dspy.Prediction(
                response="Hello!", objectives_complete=False, transition_to="none"
            )

        all_salts = []
        for targets in [["b", "c"], ["b"]]:
            engine = make_engine(targets)
            with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
                salts.clear()
                await engine.add_user_message("hi")
                await engine._process_node()
                all_salts.append(salts[0])  # first call is response

        assert all_salts[0] != all_salts[1]


# ---------------------------------------------------------------------------
# ConversationEngine no-cache integration
# ---------------------------------------------------------------------------


class TestConversationEngineNoCache:
    """ConversationEngine passes no_cache from RunOptions to call_llm."""

    @pytest.mark.asyncio
    async def test_no_cache_option_passed_to_call_llm(self):
        """RunOptions(no_cache=True) should pass no_cache=True to call_llm."""
        from voicetest.engine.conversation import ConversationEngine
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.test_case import RunOptions

        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="Greet."),
            },
            entry_node_id="a",
            source_type="custom",
            source_metadata={"general_prompt": "Be helpful."},
        )

        options = RunOptions(no_cache=True)
        engine = ConversationEngine(graph=graph, model="openai/gpt-4o-mini", options=options)

        call_args = []

        async def mock_call_llm(model, sig, *, cache_salt=None, no_cache=False, **kwargs):
            call_args.append({"no_cache": no_cache})
            return dspy.Prediction(
                response="Hello!", objectives_complete=False, transition_to="none"
            )

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.add_user_message("hi")
            await engine._process_node()

        assert call_args[0]["no_cache"] is True

    @pytest.mark.asyncio
    async def test_no_cache_default_false(self):
        """Default RunOptions should pass no_cache=False to call_llm."""
        from voicetest.engine.conversation import ConversationEngine
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="Greet."),
            },
            entry_node_id="a",
            source_type="custom",
            source_metadata={"general_prompt": "Be helpful."},
        )

        engine = ConversationEngine(graph=graph, model="openai/gpt-4o-mini")

        call_args = []

        async def mock_call_llm(model, sig, *, cache_salt=None, no_cache=False, **kwargs):
            call_args.append({"no_cache": no_cache})
            return dspy.Prediction(
                response="Hello!", objectives_complete=False, transition_to="none"
            )

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.add_user_message("hi")
            await engine._process_node()

        assert call_args[0]["no_cache"] is False
