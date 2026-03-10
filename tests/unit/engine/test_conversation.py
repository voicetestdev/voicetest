"""Tests for voicetest.engine.conversation module."""

from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from voicetest.engine.conversation import ConversationEngine
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import EquationClause
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.agent import VariableExtraction


class TestConversationEngine:
    """Tests for ConversationEngine."""

    def test_create_engine(self, simple_graph):
        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

        assert engine.graph is simple_graph
        assert engine.model == "openai/gpt-4o-mini"
        assert engine.current_node == "greeting"

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
    """Tests for ConversationEngine.advance()."""

    @pytest.mark.asyncio
    async def test_advance_calls_llm(self, simple_graph):
        """Test that advance calls the LLM with correct parameters."""
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
            engine.add_user_message("Hi!")
            result = await engine.advance()

        assert result.response == "Hello there!"
        assert "user_message" in captured_kwargs
        assert captured_kwargs["user_message"] == "Hi!"
        assert captured_kwargs["model"] == "openai/gpt-4o-mini"

    @pytest.mark.asyncio
    async def test_advance_records_response(self, simple_graph):
        """Test that advance records the response in transcript."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Hello there!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            engine.add_user_message("Hi!")
            await engine.advance()

        # Should have the user message and assistant response
        assistant_msgs = [m for m in engine.transcript if m.role == "assistant"]
        assert len(assistant_msgs) == 1
        assert assistant_msgs[0].content == "Hello there!"

    @pytest.mark.asyncio
    async def test_advance_handles_transition(self, simple_graph):
        """Test that advance handles node transitions."""
        from unittest.mock import patch

        from voicetest.engine.conversation import ConversationEngine

        engine = ConversationEngine(simple_graph, model="openai/gpt-4o-mini")

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Goodbye!"
                transition_to = "farewell"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            engine.add_user_message("I want to leave")
            result = await engine.advance()

        assert result.transitioned_to == "farewell"
        assert engine.current_node == "farewell"
        assert engine.nodes_visited == ["greeting", "farewell"]

    @pytest.mark.asyncio
    async def test_advance_with_dynamic_variables(self, graph_with_dynamic_variables):
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
            engine.add_user_message("Hello")
            await engine.advance()

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
            result = await engine._process_node()

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
            result = await engine._process_node()

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
            result = await engine._process_node()

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
            result = await engine._process_node()

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
            result = await engine._process_node()

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
            result = await engine._process_node()

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
            engine.add_user_message("Hi")
            result = await engine._process_node()

        assert mock_llm.called
        assert result.response == "Hello!"


class TestLogicalOperator:
    """Tests for logical_operator (AND/OR) on equation transitions."""

    @pytest.fixture
    def or_logic_graph(self):
        """Graph with a logic node using OR logical_operator."""
        return AgentGraph(
            nodes={
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="match",
                            condition=TransitionCondition(
                                type="equation",
                                value="x == 1 OR y == 2",
                                logical_operator="or",
                                equations=[
                                    EquationClause(left="x", operator="==", right="1"),
                                    EquationClause(left="y", operator="==", right="2"),
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="fallback",
                            condition=TransitionCondition(type="always", value="Else"),
                        ),
                    ],
                ),
                "match": AgentNode(id="match", state_prompt="Matched.", transitions=[]),
                "fallback": AgentNode(id="fallback", state_prompt="Fallback.", transitions=[]),
            },
            entry_node_id="router",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_or_operator_any_clause_matches(self, or_logic_graph):
        """OR operator: any single clause matching triggers transition."""
        engine = ConversationEngine(
            or_logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"x": "1", "y": "99"},
        )

        with patch("voicetest.engine.conversation.call_llm") as mock_llm:
            result = await engine._process_node()

        mock_llm.assert_not_called()
        assert result.transitioned_to == "match"

    @pytest.mark.asyncio
    async def test_or_operator_no_clause_matches_falls_through(self, or_logic_graph):
        """OR operator: no clauses matching falls through to else."""
        engine = ConversationEngine(
            or_logic_graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"x": "99", "y": "99"},
        )

        with patch("voicetest.engine.conversation.call_llm") as mock_llm:
            result = await engine._process_node()

        mock_llm.assert_not_called()
        assert result.transitioned_to == "fallback"

    @pytest.mark.asyncio
    async def test_and_operator_explicit_all_must_match(self):
        """AND operator (explicit): all clauses must match."""
        graph = AgentGraph(
            nodes={
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="match",
                            condition=TransitionCondition(
                                type="equation",
                                value="x == 1 AND y == 2",
                                logical_operator="and",
                                equations=[
                                    EquationClause(left="x", operator="==", right="1"),
                                    EquationClause(left="y", operator="==", right="2"),
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="fallback",
                            condition=TransitionCondition(type="always", value="Else"),
                        ),
                    ],
                ),
                "match": AgentNode(id="match", state_prompt="Matched.", transitions=[]),
                "fallback": AgentNode(id="fallback", state_prompt="Fallback.", transitions=[]),
            },
            entry_node_id="router",
            source_type="retell",
        )

        # Only x matches, y does not
        engine = ConversationEngine(
            graph,
            model="openai/gpt-4o-mini",
            dynamic_variables={"x": "1", "y": "99"},
        )

        with patch("voicetest.engine.conversation.call_llm"):
            result = await engine._process_node()

        assert result.transitioned_to == "fallback"


class TestExtractNodeHandling:
    """Tests for extract_dynamic_variables node processing."""

    @pytest.fixture
    def extract_graph(self):
        """Graph with an extract node that extracts variables then routes."""
        return AgentGraph(
            nodes={
                "extract": AgentNode(
                    id="extract",
                    state_prompt="",
                    variables_to_extract=[
                        VariableExtraction(
                            name="dob_month",
                            description="The month of birth",
                            type="string",
                            choices=["January", "February"],
                        ),
                        VariableExtraction(
                            name="dob_year",
                            description="The year of birth",
                            type="string",
                        ),
                    ],
                    transitions=[
                        Transition(
                            target_node_id="match",
                            condition=TransitionCondition(
                                type="equation",
                                value="dob_month == January AND dob_year == 1990",
                                equations=[
                                    EquationClause(
                                        left="dob_month",
                                        operator="==",
                                        right="January",
                                    ),
                                    EquationClause(
                                        left="dob_year",
                                        operator="==",
                                        right="1990",
                                    ),
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="no_match",
                            condition=TransitionCondition(type="always", value="Else"),
                        ),
                    ],
                    metadata={"retell_type": "extract_dynamic_variables"},
                ),
                "match": AgentNode(id="match", state_prompt="Verified.", transitions=[]),
                "no_match": AgentNode(id="no_match", state_prompt="Not verified.", transitions=[]),
            },
            entry_node_id="extract",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_extract_node_calls_llm_to_extract_variables(self, extract_graph):
        """Extract node calls LLM to extract variables from conversation."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result) as mock_llm:
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            await engine._process_node()

        mock_llm.assert_called_once()

    @pytest.mark.asyncio
    async def test_extract_node_stores_variables(self, extract_graph):
        """Extracted values are stored in dynamic variables."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            await engine._process_node()

        assert engine._dynamic_variables["dob_month"] == "January"
        assert engine._dynamic_variables["dob_year"] == "1990"

    @pytest.mark.asyncio
    async def test_extract_node_routes_on_match(self, extract_graph):
        """Extract node routes to match when equations match extracted values."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            result = await engine._process_node()

        assert result.transitioned_to == "match"

    @pytest.mark.asyncio
    async def test_extract_node_falls_through_on_no_match(self, extract_graph):
        """Extract node falls through to else when equations don't match."""
        mock_result = AsyncMock()
        mock_result.dob_month = "February"
        mock_result.dob_year = "2000"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is February 1, 2000")
            result = await engine._process_node()

        assert result.transitioned_to == "no_match"

    @pytest.mark.asyncio
    async def test_extract_node_produces_empty_response(self, extract_graph):
        """Extract node produces empty response like logic nodes."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            result = await engine._process_node()

        assert result.response == ""

    @pytest.mark.asyncio
    async def test_extract_node_records_transition(self, extract_graph):
        """Extract node records transition in nodes_visited."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            result = await engine._process_node()

        assert "match" in engine.nodes_visited
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].name == "route_to_match"


class TestAlwaysEdgeOnConversationNodes:
    """Tests for always_edge auto-transition on conversation nodes."""

    @pytest.fixture
    def graph_with_always_edge(self):
        """Conversation node with only an always_edge (speak then auto-transition)."""
        return AgentGraph(
            nodes={
                "farewell": AgentNode(
                    id="farewell",
                    state_prompt="Thank the caller and provide contact info.",
                    transitions=[
                        Transition(
                            target_node_id="end",
                            condition=TransitionCondition(type="always", value="Always"),
                        ),
                    ],
                    metadata={"retell_type": "conversation"},
                ),
                "end": AgentNode(
                    id="end",
                    state_prompt="End.",
                    transitions=[],
                    metadata={"retell_type": "end"},
                ),
            },
            entry_node_id="farewell",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_always_edge_auto_fires_after_response(self, graph_with_always_edge):
        """Conversation node with only always transition: LLM speaks, then auto-transitions."""
        engine = ConversationEngine(graph_with_always_edge, model="openai/gpt-4o-mini")

        async def mock_call_llm(model, signature, **kwargs):
            # The LLM should NOT see available_transitions for always-only nodes
            class MockResult:
                response = "Thank you, please call us at 555-1234."
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            engine.add_user_message("ok bye")
            result = await engine._process_node()

        assert result.response == "Thank you, please call us at 555-1234."
        assert result.transitioned_to == "end"
        assert engine.current_node == "end"

    @pytest.fixture
    def graph_with_mixed_edges_and_always(self):
        """Conversation node with regular edges + an always_edge fallback."""
        return AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Help the user.",
                    transitions=[
                        Transition(
                            target_node_id="billing",
                            condition=TransitionCondition(
                                type="llm_prompt", value="User has billing question"
                            ),
                        ),
                        Transition(
                            target_node_id="end",
                            condition=TransitionCondition(type="always", value="Always"),
                        ),
                    ],
                    metadata={"retell_type": "conversation"},
                ),
                "billing": AgentNode(id="billing", state_prompt="Billing.", transitions=[]),
                "end": AgentNode(id="end", state_prompt="End.", transitions=[]),
            },
            entry_node_id="main",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_llm_transition_takes_priority_over_always(
        self, graph_with_mixed_edges_and_always
    ):
        """If LLM picks a regular transition, always doesn't fire."""
        engine = ConversationEngine(graph_with_mixed_edges_and_always, model="openai/gpt-4o-mini")

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Let me help with billing."
                transition_to = "billing"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            engine.add_user_message("I have a billing question")
            result = await engine._process_node()

        assert result.transitioned_to == "billing"

    @pytest.mark.asyncio
    async def test_always_fires_as_fallback_when_llm_picks_none(
        self, graph_with_mixed_edges_and_always
    ):
        """If LLM picks 'none', always transition fires as fallback."""
        engine = ConversationEngine(graph_with_mixed_edges_and_always, model="openai/gpt-4o-mini")

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Goodbye!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            engine.add_user_message("thanks, bye")
            result = await engine._process_node()

        assert result.transitioned_to == "end"
        assert engine.current_node == "end"


class TestToolMessagesInTranscript:
    """Tests for tool messages appearing in transcript for non-speech actions."""

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

    @pytest.fixture
    def extract_graph(self):
        """Graph with an extract node that extracts variables then routes."""
        return AgentGraph(
            nodes={
                "extract": AgentNode(
                    id="extract",
                    state_prompt="",
                    variables_to_extract=[
                        VariableExtraction(
                            name="dob_month",
                            description="The month of birth",
                            type="string",
                            choices=["January", "February"],
                        ),
                        VariableExtraction(
                            name="dob_year",
                            description="The year of birth",
                            type="string",
                        ),
                    ],
                    transitions=[
                        Transition(
                            target_node_id="match",
                            condition=TransitionCondition(
                                type="equation",
                                value="dob_month == January AND dob_year == 1990",
                                equations=[
                                    EquationClause(
                                        left="dob_month",
                                        operator="==",
                                        right="January",
                                    ),
                                    EquationClause(
                                        left="dob_year",
                                        operator="==",
                                        right="1990",
                                    ),
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="no_match",
                            condition=TransitionCondition(type="always", value="Else"),
                        ),
                    ],
                    metadata={"retell_type": "extract_dynamic_variables"},
                ),
                "match": AgentNode(id="match", state_prompt="Verified.", transitions=[]),
                "no_match": AgentNode(id="no_match", state_prompt="Not verified.", transitions=[]),
            },
            entry_node_id="extract",
            source_type="retell",
        )

    def test_apply_transition_adds_tool_message(self, logic_graph_with_fallback):
        """_apply_transition should append a tool message to the transcript."""
        from voicetest.engine.conversation import TurnResult

        engine = ConversationEngine(
            logic_graph_with_fallback,
            model="openai/gpt-4o-mini",
            dynamic_variables={"account_type": "premium"},
        )
        turn_result = TurnResult(response="")
        engine._apply_transition(turn_result, "premium_support")

        tool_msgs = [m for m in engine._transcript if m.role == "tool"]
        assert len(tool_msgs) == 1
        assert "Transitioned to premium_support" in tool_msgs[0].content
        assert tool_msgs[0].metadata["tool_name"] == "route_to_premium_support"
        assert tool_msgs[0].metadata["node_id"] == "premium_support"

    @pytest.mark.asyncio
    async def test_logic_node_produces_tool_message_not_empty_assistant(
        self, logic_graph_with_fallback
    ):
        """Logic node should produce tool messages, not an empty assistant message."""
        with patch("voicetest.engine.conversation.call_llm"):
            engine = ConversationEngine(
                logic_graph_with_fallback,
                model="openai/gpt-4o-mini",
                dynamic_variables={"account_type": "premium"},
            )
            await engine._process_node()

        # Should have a tool message for the transition
        tool_msgs = [m for m in engine._transcript if m.role == "tool"]
        assert len(tool_msgs) >= 1
        assert "Transitioned to premium_support" in tool_msgs[0].content

        # Should NOT have an empty assistant message
        assistant_msgs = [m for m in engine._transcript if m.role == "assistant"]
        empty_assistant = [m for m in assistant_msgs if m.content == ""]
        assert len(empty_assistant) == 0

    @pytest.mark.asyncio
    async def test_logic_node_always_fallback_produces_tool_message(
        self, logic_graph_with_fallback
    ):
        """Always-edge fallback should also produce a tool message."""
        with patch("voicetest.engine.conversation.call_llm"):
            engine = ConversationEngine(
                logic_graph_with_fallback,
                model="openai/gpt-4o-mini",
                dynamic_variables={"account_type": "enterprise"},
            )
            await engine._process_node()

        tool_msgs = [m for m in engine._transcript if m.role == "tool"]
        assert len(tool_msgs) >= 1
        assert "Transitioned to fallback" in tool_msgs[0].content

    @pytest.mark.asyncio
    async def test_extract_node_produces_extraction_tool_message(self, extract_graph):
        """Extract node should produce a tool message with extracted variable values."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            await engine._process_node()

        tool_msgs = [m for m in engine._transcript if m.role == "tool"]
        # Should have extraction message + transition message
        extract_msgs = [m for m in tool_msgs if "Extracted" in m.content]
        assert len(extract_msgs) == 1
        assert "dob_month=January" in extract_msgs[0].content
        assert "dob_year=1990" in extract_msgs[0].content
        assert extract_msgs[0].metadata["tool_name"] == "extract_variables"
        assert extract_msgs[0].metadata["extracted"] == {
            "dob_month": "January",
            "dob_year": "1990",
        }

    @pytest.mark.asyncio
    async def test_extract_node_extraction_plus_transition_tool_messages(self, extract_graph):
        """Extract node should have both extraction and transition tool messages."""
        mock_result = AsyncMock()
        mock_result.dob_month = "January"
        mock_result.dob_year = "1990"

        with patch("voicetest.engine.conversation.call_llm", return_value=mock_result):
            engine = ConversationEngine(extract_graph, model="openai/gpt-4o-mini")
            engine.add_user_message("My birthday is January 15, 1990")
            await engine._process_node()

        tool_msgs = [m for m in engine._transcript if m.role == "tool"]
        # One for extraction, one for transition
        assert len(tool_msgs) == 2
        assert "Extracted" in tool_msgs[0].content
        assert "Transitioned to" in tool_msgs[1].content

    @pytest.mark.asyncio
    async def test_tool_messages_have_correct_metadata(self, logic_graph_with_fallback):
        """Tool messages should have tool_name and node_id metadata."""
        with patch("voicetest.engine.conversation.call_llm"):
            engine = ConversationEngine(
                logic_graph_with_fallback,
                model="openai/gpt-4o-mini",
                dynamic_variables={"account_type": "premium"},
            )
            await engine._process_node()

        tool_msgs = [m for m in engine._transcript if m.role == "tool"]
        for msg in tool_msgs:
            assert "tool_name" in msg.metadata
            assert "node_id" in msg.metadata


class TestEngineExpandsSnippets:
    """Verify snippet refs in prompts are resolved before LLM call."""

    @pytest.fixture
    def graph_with_snippets(self):
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
            await engine._process_node()

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
