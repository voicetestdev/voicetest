"""Tests for voicetest.engine.conversation module."""

import pytest


class TestConversationEngine:
    """Tests for ConversationEngine."""

    def test_create_engine(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)

        assert engine.graph is simple_graph
        assert engine.model == "openai/gpt-4o-mini"
        assert engine.current_node == "greeting"

    def test_create_engine_with_custom_model(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4")

        assert engine.model == "openai/gpt-4"

    def test_engine_uses_graph_default_model(self, graph_with_metadata):
        from voicetest.engine.conversation import ConversationEngine

        # graph_with_metadata has source_metadata with model="gpt-4o"
        # but default_model is None, so it should use the default
        engine = ConversationEngine(graph_with_metadata)

        assert engine.model == "openai/gpt-4o-mini"

    def test_engine_initial_state(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)

        assert engine.current_node == "greeting"
        assert engine.transcript == []
        assert engine.nodes_visited == ["greeting"]
        assert engine.tools_called == []
        assert engine.end_call_invoked is False

    def test_add_user_message(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)
        engine.add_user_message("Hello!")

        assert len(engine.transcript) == 1
        assert engine.transcript[0].role == "user"
        assert engine.transcript[0].content == "Hello!"
        assert engine.transcript[0].metadata["node_id"] == "greeting"

    def test_reset_engine(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)
        engine.add_user_message("Hello!")
        engine._current_node = "farewell"
        engine._nodes_visited.append("farewell")

        engine.reset()

        assert engine.current_node == "greeting"
        assert engine.transcript == []
        assert engine.nodes_visited == ["greeting"]

    def test_transcript_returns_copy(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)
        engine.add_user_message("Hello!")

        transcript = engine.transcript
        transcript.append(None)  # Modify the copy

        assert len(engine.transcript) == 1  # Original unchanged

    def test_nodes_visited_returns_copy(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)

        nodes = engine.nodes_visited
        nodes.append("fake_node")  # Modify the copy

        assert len(engine.nodes_visited) == 1  # Original unchanged


class TestTurnResult:
    """Tests for TurnResult dataclass."""

    def test_create_turn_result(self):
        from voicetest.engine.conversation import TurnResult

        result = TurnResult(response="Hello there!")

        assert result.response == "Hello there!"
        assert result.transitioned_to is None
        assert result.tool_calls == []
        assert result.end_call_invoked is False

    def test_turn_result_with_transition(self):
        from voicetest.engine.conversation import TurnResult

        result = TurnResult(response="Goodbye!", transitioned_to="farewell")

        assert result.response == "Goodbye!"
        assert result.transitioned_to == "farewell"

    def test_turn_result_with_end_call(self):
        from voicetest.engine.conversation import TurnResult

        result = TurnResult(response="Ending call.", end_call_invoked=True)

        assert result.end_call_invoked is True


class TestProcessTurn:
    """Tests for ConversationEngine.process_turn()."""

    @pytest.mark.asyncio
    async def test_process_turn_calls_llm(self, simple_graph):
        """Test that process_turn calls the LLM with correct parameters."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)

        captured_kwargs = {}

        async def mock_call_llm(model, signature, **kwargs):
            captured_kwargs.update(kwargs)
            captured_kwargs["model"] = model

            class MockResult:
                response = "Hello there!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            result = await engine.process_turn("Hi!")

        assert result.response == "Hello there!"
        assert "user_message" in captured_kwargs
        assert captured_kwargs["user_message"] == "Hi!"
        assert captured_kwargs["model"] == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_process_turn_records_response(self, simple_graph):
        """Test that process_turn records the response in transcript."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Hello there!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.process_turn("Hi!")

        # Should have the assistant response
        assert len(engine.transcript) == 1
        assert engine.transcript[0].role == "assistant"
        assert engine.transcript[0].content == "Hello there!"

    @pytest.mark.asyncio
    async def test_process_turn_handles_transition(self, simple_graph):
        """Test that process_turn handles node transitions."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph)

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Goodbye!"
                transition_to = "farewell"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            result = await engine.process_turn("I want to leave")

        assert result.transitioned_to == "farewell"
        assert engine.current_node == "farewell"
        assert engine.nodes_visited == ["greeting", "farewell"]

    @pytest.mark.asyncio
    async def test_process_turn_with_dynamic_variables(self, graph_with_dynamic_variables):
        """Test that dynamic variables are substituted in prompts."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        dynamic_vars = {
            "customer_name": "Alice",
            "account_status": "active",
            "company_name": "Acme Corp",
        }
        engine = ConversationEngine(graph_with_dynamic_variables, dynamic_variables=dynamic_vars)

        captured_kwargs = {}

        async def mock_call_llm(model, signature, **kwargs):
            captured_kwargs.update(kwargs)

            class MockResult:
                response = "Hello Alice!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            await engine.process_turn("Hello")

        # Verify variables were substituted
        assert "Acme Corp" in captured_kwargs["general_instructions"]
        assert "Alice" in captured_kwargs["state_instructions"]
        assert "active" in captured_kwargs["state_instructions"]
