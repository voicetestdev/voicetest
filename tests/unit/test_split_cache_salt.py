"""Tests for split-mode cache salt.

In split transition mode, the response-only signature omits available_transitions.
This means the DSPy cache key doesn't change when outbound edges are modified.
The fix: pass a transitions fingerprint via LM metadata so the cache key changes
without polluting the signature or prompt.
"""

import dspy
import pytest

from voicetest.llm.base import _create_lm


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


class TestConversationEngineCacheSalt:
    """ConversationEngine passes cache_salt for split-mode response calls."""

    @pytest.mark.asyncio
    async def test_split_mode_passes_cache_salt(self):
        """Split-mode response call should include transitions fingerprint."""
        from unittest.mock import patch

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

        from voicetest.models.test_case import RunOptions

        options = RunOptions(split_transitions=True)
        engine = ConversationEngine(graph=graph, model="openai/gpt-4o-mini", options=options)

        call_args = []

        async def mock_call_llm(model, sig, *, cache_salt=None, **kwargs):
            call_args.append({"cache_salt": cache_salt, "sig_name": sig.__name__})
            return dspy.Prediction(response="Hello!", transition_to="none")

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.process_turn("hi")

        # First call is the response call — should have a cache_salt
        response_call = call_args[0]
        assert response_call["cache_salt"] is not None
        assert len(response_call["cache_salt"]) > 0

        # Second call is the transition call — no salt needed (it already has available_transitions)
        transition_call = call_args[1]
        assert transition_call["cache_salt"] is None

    @pytest.mark.asyncio
    async def test_combined_mode_no_cache_salt(self):
        """Combined-mode response call should NOT pass cache_salt."""
        from unittest.mock import patch

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
            call_args.append({"cache_salt": cache_salt})
            return dspy.Prediction(response="Hello!", transition_to="none")

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.process_turn("hi")

        # Combined mode: no salt needed, available_transitions is in the signature
        assert call_args[0]["cache_salt"] is None

    @pytest.mark.asyncio
    async def test_salt_changes_when_edges_change(self):
        """Different outbound edges should produce different cache_salt values."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition
        from voicetest.models.test_case import RunOptions

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
                options=RunOptions(split_transitions=True),
            )

        salts = []

        async def mock_call_llm(model, sig, *, cache_salt=None, **kwargs):
            salts.append(cache_salt)
            return dspy.Prediction(response="Hello!", transition_to="none")

        for targets in [["b", "c"], ["b"]]:
            salts.clear()
            engine = make_engine(targets)
            with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
                await engine.process_turn("hi")

        # Can't compare across clears, so run both and collect
        all_salts = []
        for targets in [["b", "c"], ["b"]]:
            engine = make_engine(targets)
            with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
                salts.clear()
                await engine.process_turn("hi")
                all_salts.append(salts[0])  # first call is response

        assert all_salts[0] != all_salts[1]
