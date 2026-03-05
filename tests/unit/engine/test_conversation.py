"""Tests for voicetest.engine.conversation module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import EquationClause
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


class TestConversationEngine:
    """Tests for ConversationEngine."""

    def test_create_engine(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

        assert engine.graph is simple_graph
        assert engine.model == "openai/gpt-4o-mini"
        assert engine.current_node == "greeting"

    def test_create_engine_with_custom_model(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4")

        assert engine.model == "openai/gpt-4"

    def test_engine_uses_provided_model(self, graph_with_metadata):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(graph_with_metadata, model="anthropic/claude-3-haiku")

        assert engine.model == "anthropic/claude-3-haiku"

    def test_engine_initial_state(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

        assert engine.current_node == "greeting"
        assert engine.transcript == []
        assert engine.nodes_visited == ["greeting"]
        assert engine.tools_called == []
        assert engine.end_call_invoked is False

    def test_add_user_message(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")
        engine.add_user_message("Hello!")

        assert len(engine.transcript) == 1
        assert engine.transcript[0].role == "user"
        assert engine.transcript[0].content == "Hello!"
        assert engine.transcript[0].metadata["node_id"] == "greeting"

    def test_reset_engine(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")
        engine.add_user_message("Hello!")
        engine._current_node = "farewell"
        engine._nodes_visited.append("farewell")

        engine.reset()

        assert engine.current_node == "greeting"
        assert engine.transcript == []
        assert engine.nodes_visited == ["greeting"]

    def test_transcript_returns_copy(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")
        engine.add_user_message("Hello!")

        transcript = engine.transcript
        transcript.append(None)  # Modify the copy

        assert len(engine.transcript) == 1  # Original unchanged

    def test_nodes_visited_returns_copy(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

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

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

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

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

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

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

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
        engine = ConversationEngine(
            graph_with_dynamic_variables, model="openai/gpt-4o-mini", dynamic_variables=dynamic_vars
        )

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


class TestLogicNodeHandling:
    """Tests for deterministic logic node transitions (no LLM call)."""

    @pytest.fixture
    def logic_graph(self):
        """Graph with a logic_split node that has equation transitions."""
        return AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    state_prompt="Greet the user.",
                    transitions=[
                        Transition(
                            target_node_id="router",
                            condition=TransitionCondition(
                                type="llm_prompt", value="User provided account"
                            ),
                        )
                    ],
                ),
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="premium_support",
                            condition=TransitionCondition(
                                type="equation",
                                value="account_type == premium",
                                equations=[
                                    EquationClause(
                                        left="account_type",
                                        operator="==",
                                        right="premium",
                                    )
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="standard_support",
                            condition=TransitionCondition(
                                type="equation",
                                value="account_type == standard",
                                equations=[
                                    EquationClause(
                                        left="account_type",
                                        operator="==",
                                        right="standard",
                                    )
                                ],
                            ),
                        ),
                    ],
                    metadata={"retell_type": "logic_split"},
                ),
                "premium_support": AgentNode(
                    id="premium_support",
                    state_prompt="Premium support.",
                    transitions=[],
                ),
                "standard_support": AgentNode(
                    id="standard_support",
                    state_prompt="Standard support.",
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_logic_node_transitions_to_matching_target(self, logic_graph):
        """Logic node with matching variable transitions without LLM call."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "premium"},
        )
        engine._current_node = "router"
        engine._nodes_visited = ["greeting", "router"]

        call_count = 0

        async def mock_call_llm(model, signature, **kwargs):
            nonlocal call_count
            call_count += 1

            class MockResult:
                response = "test"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            result = await engine.process_turn("test")

        assert call_count == 0, "LLM should not be called for logic nodes"
        assert result.transitioned_to == "premium_support"
        assert engine.current_node == "premium_support"

    @pytest.mark.asyncio
    async def test_logic_node_no_match_stays_put(self, logic_graph):
        """Logic node with no matching variable does not transition."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "enterprise"},
        )
        engine._current_node = "router"
        engine._nodes_visited = ["greeting", "router"]

        with patch("voicetest.engine.conversation.call_llm") as mock_llm:
            result = await engine.process_turn("test")

        mock_llm.assert_not_called()
        assert result.transitioned_to is None
        assert engine.current_node == "router"

    @pytest.mark.asyncio
    async def test_logic_node_produces_empty_response(self, logic_graph):
        """Logic node produces an empty string response."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "premium"},
        )
        engine._current_node = "router"
        engine._nodes_visited = ["greeting", "router"]

        with patch("voicetest.engine.conversation.call_llm"):
            result = await engine.process_turn("test")

        assert result.response == ""

    @pytest.mark.asyncio
    async def test_logic_node_transition_recorded(self, logic_graph):
        """Logic node transition is recorded in nodes_visited and tool_calls."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "standard"},
        )
        engine._current_node = "router"
        engine._nodes_visited = ["greeting", "router"]

        with patch("voicetest.engine.conversation.call_llm"):
            result = await engine.process_turn("test")

        assert result.transitioned_to == "standard_support"
        assert "standard_support" in engine.nodes_visited
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "route_to_standard_support"

    @pytest.fixture
    def logic_graph_with_fallback(self):
        """Graph with a logic node that has equation edges + an always fallback."""
        return AgentGraph(
            nodes={
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="premium_support",
                            condition=TransitionCondition(
                                type="equation",
                                value="account_type == premium",
                                equations=[
                                    EquationClause(
                                        left="account_type",
                                        operator="==",
                                        right="premium",
                                    )
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="fallback",
                            condition=TransitionCondition(
                                type="always",
                                value="Else",
                            ),
                        ),
                    ],
                    metadata={"retell_type": "branch"},
                ),
                "premium_support": AgentNode(
                    id="premium_support",
                    state_prompt="Premium support.",
                    transitions=[],
                ),
                "fallback": AgentNode(
                    id="fallback",
                    state_prompt="Fallback support.",
                    transitions=[],
                ),
            },
            entry_node_id="router",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_logic_node_with_always_fallback(self, logic_graph_with_fallback):
        """When no equation matches, the always transition fires."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph_with_fallback,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "enterprise"},
        )

        with patch("voicetest.engine.conversation.call_llm") as mock_llm:
            result = await engine.process_turn("test")

        mock_llm.assert_not_called()
        assert result.transitioned_to == "fallback"
        assert engine.current_node == "fallback"

    @pytest.mark.asyncio
    async def test_logic_node_equation_takes_priority_over_always(self, logic_graph_with_fallback):
        """When an equation matches, it fires instead of the always fallback."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph_with_fallback,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "premium"},
        )

        with patch("voicetest.engine.conversation.call_llm") as mock_llm:
            result = await engine.process_turn("test")

        mock_llm.assert_not_called()
        assert result.transitioned_to == "premium_support"

    @pytest.mark.asyncio
    async def test_non_logic_node_still_calls_llm(self, logic_graph):
        """Regular conversation nodes still go through LLM as normal."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(
            logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "premium"},
        )

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Hello!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm) as mock_llm:
            result = await engine.process_turn("Hi")

        assert mock_llm.called
        assert result.response == "Hello!"
