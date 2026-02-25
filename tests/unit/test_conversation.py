"""Tests for ConversationEngine snippet expansion."""

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from voicetest.engine.conversation import ConversationEngine
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode


@pytest.fixture
def graph_with_snippets():
    """Graph with snippet refs in both general and node prompts."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="Node says: {%greeting%}. Use {{name}}.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="custom",
        source_metadata={"general_prompt": "General: {%greeting%}"},
        snippets={"greeting": "Hello friend"},
    )


class TestEngineExpandsSnippets:
    """Verify snippet refs in prompts are resolved before LLM call."""

    @pytest.mark.asyncio
    async def test_snippets_expanded_before_llm_call(self, graph_with_snippets):
        engine = ConversationEngine(
            graph=graph_with_snippets,
            model="test/model",
            dynamic_variables={"name": "Alice"},
        )
        engine.add_user_message("hi")

        # Mock call_llm to capture what instructions are passed
        mock_result = AsyncMock()
        mock_result.response = "mock response"
        mock_result.transition_to = "none"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result) as mock_llm:
            await engine.process_turn("hello")

            # Inspect the kwargs passed to call_llm
            call_kwargs = mock_llm.call_args
            general = call_kwargs.kwargs.get("general_instructions", "")
            state = call_kwargs.kwargs.get("state_instructions", "")

            # Snippets should be expanded
            assert "Hello friend" in general
            assert "{%greeting%}" not in general

            # Snippets expanded AND variables substituted in state
            assert "Hello friend" in state
            assert "{%greeting%}" not in state
            assert "Alice" in state
            assert "{{name}}" not in state
