"""Tests for voicetest.engine.session module."""

import pytest


# simple_graph fixture is imported from conftest.py


class TestConversationState:
    """Tests for ConversationState."""

    def test_create_empty_state(self):
        from voicetest.engine.session import ConversationState

        state = ConversationState()

        assert state.transcript == []
        assert state.nodes_visited == []
        assert state.tools_called == []
        assert state.turn_count == 0
        assert state.end_reason == ""

    def test_state_tracks_nodes(self):
        from voicetest.engine.session import ConversationState

        state = ConversationState()
        state.nodes_visited.append("greeting")
        state.nodes_visited.append("billing")

        assert state.nodes_visited == ["greeting", "billing"]

    def test_state_tracks_turn_count(self):
        from voicetest.engine.session import ConversationState

        state = ConversationState()
        state.turn_count = 5

        assert state.turn_count == 5


class TestConversationRunner:
    """Tests for ConversationRunner."""

    def test_create_runner(self, simple_graph):
        from voicetest.engine.session import ConversationRunner

        runner = ConversationRunner(simple_graph)

        assert runner.graph is simple_graph
        assert runner.options is not None

    def test_runner_has_conversation_module(self, simple_graph):
        from voicetest.engine.session import ConversationRunner

        runner = ConversationRunner(simple_graph)

        # Check conversation module has state modules for each node
        assert runner._conversation_module is not None
        # State modules stored as _state_modules internally
        assert hasattr(runner._conversation_module, "_state_modules")
        assert "greeting" in runner._conversation_module._state_modules
        assert "farewell" in runner._conversation_module._state_modules

    def test_runner_with_custom_options(self, simple_graph):
        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import RunOptions

        options = RunOptions(max_turns=5, verbose=True)
        runner = ConversationRunner(simple_graph, options=options)

        assert runner.options.max_turns == 5
        assert runner.options.verbose is True


class TestNodeTracker:
    """Tests for NodeTracker utility."""

    def test_create_tracker(self):
        from voicetest.engine.session import NodeTracker

        tracker = NodeTracker()

        assert tracker.visited == []
        assert tracker.current_node is None

    def test_record_node(self):
        from voicetest.engine.session import NodeTracker

        tracker = NodeTracker()
        tracker.record("greeting")
        tracker.record("billing")

        assert tracker.visited == ["greeting", "billing"]
        assert tracker.current_node == "billing"

    def test_record_same_node_twice(self):
        from voicetest.engine.session import NodeTracker

        tracker = NodeTracker()
        tracker.record("greeting")
        tracker.record("greeting")  # Same node again

        # Should record both visits
        assert tracker.visited == ["greeting", "greeting"]


class TestConversationRunnerWithDynamicVariables:
    """Tests for ConversationRunner with dynamic variables."""

    def test_runner_accepts_dynamic_variables(self, simple_graph):
        from voicetest.engine.session import ConversationRunner

        variables = {"name": "Alice", "age": 30}
        runner = ConversationRunner(simple_graph, dynamic_variables=variables)

        assert runner._dynamic_variables == variables

    def test_runner_default_empty_dynamic_variables(self, simple_graph):
        from voicetest.engine.session import ConversationRunner

        runner = ConversationRunner(simple_graph)

        assert runner._dynamic_variables == {}


class TestMessageNodeMetadata:
    """Tests for node_id in message metadata."""

    @pytest.mark.asyncio
    async def test_messages_include_node_id_metadata(self, simple_graph):
        """Test that messages include node_id in their metadata."""
        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import TestCase
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        runner = ConversationRunner(simple_graph, mock_mode=True)
        test_case = TestCase(name="test", user_prompt="Say hello")

        simulator = UserSimulator("test", "mock-model")
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hello", should_end=False, reasoning="greeting"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        state = await runner.run(test_case, simulator)

        # Check that messages have node_id in metadata
        for msg in state.transcript:
            assert "node_id" in msg.metadata
            # Should be one of our node IDs
            assert msg.metadata["node_id"] in ["greeting", "farewell"]


class TestResponseNodeMetadata:
    """Test that assistant messages have the correct generating node_id."""

    @pytest.mark.asyncio
    async def test_response_metadata_reflects_generating_node(self, simple_graph):
        """Response should be labeled with the node that generated it, not the transition target."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import TestCase
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        runner = ConversationRunner(simple_graph)
        test_case = TestCase(name="test", user_prompt="Say hello")

        simulator = UserSimulator("test", "mock-model")
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hello", should_end=False, reasoning="greeting"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Goodbye!"
                transition_to = "farewell"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = await runner.run(test_case, simulator)

        # The assistant message should be labeled with "greeting" (the generating node),
        # not "farewell" (the transition target)
        assistant_msgs = [m for m in state.transcript if m.role == "assistant"]
        assert len(assistant_msgs) >= 1
        assert assistant_msgs[0].metadata["node_id"] == "greeting"


class TestDynamicVariableSubstitution:
    """Tests for dynamic variable substitution in prompts."""

    @pytest.mark.asyncio
    async def test_dynamic_variables_substituted_in_prompts(self, graph_with_dynamic_variables):
        """Test that dynamic variables are substituted in both general and state prompts.

        This test verifies that {{variable}} placeholders in general_prompt and state_prompt
        are replaced with actual values from dynamic_variables before being passed to the LLM.
        """
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.engine.session import ConversationState
        from voicetest.engine.session import NodeTracker

        dynamic_vars = {
            "customer_name": "Alice",
            "account_status": "active",
            "company_name": "Acme Corp",
        }
        runner = ConversationRunner(graph_with_dynamic_variables, dynamic_variables=dynamic_vars)

        # Mock call_llm to capture what gets passed
        captured_kwargs = {}

        async def mock_call_llm(model, signature, **kwargs):
            captured_kwargs.update(kwargs)

            # Return a mock result with expected attributes
            class MockResult:
                response = "Hello Alice!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = ConversationState()
            node_tracker = NodeTracker()
            node_tracker.record("main")

            await runner._process_turn(
                "main",
                "Hello",
                state,
                node_tracker,
            )

        # Verify general_instructions has substituted variables
        assert "general_instructions" in captured_kwargs
        assert "Acme Corp" in captured_kwargs["general_instructions"]
        assert "{{company_name}}" not in captured_kwargs["general_instructions"]

        # Verify state_instructions has substituted variables
        assert "state_instructions" in captured_kwargs
        assert "Alice" in captured_kwargs["state_instructions"]
        assert "active" in captured_kwargs["state_instructions"]
        assert "{{customer_name}}" not in captured_kwargs["state_instructions"]
        assert "{{account_status}}" not in captured_kwargs["state_instructions"]

    @pytest.mark.asyncio
    async def test_unknown_variables_remain_unchanged(self, graph_with_dynamic_variables):
        """Test that unknown variables are left as-is (graceful degradation)."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.engine.session import ConversationState
        from voicetest.engine.session import NodeTracker

        # Only provide some variables, not all
        dynamic_vars = {
            "customer_name": "Bob",
            # company_name and account_status are NOT provided
        }
        runner = ConversationRunner(graph_with_dynamic_variables, dynamic_variables=dynamic_vars)

        captured_kwargs = {}

        async def mock_call_llm(model, signature, **kwargs):
            captured_kwargs.update(kwargs)

            class MockResult:
                response = "Hello Bob!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = ConversationState()
            node_tracker = NodeTracker()
            node_tracker.record("main")

            await runner._process_turn(
                "main",
                "Hello",
                state,
                node_tracker,
            )

        # customer_name should be substituted
        assert "Bob" in captured_kwargs["state_instructions"]
        assert "{{customer_name}}" not in captured_kwargs["state_instructions"]

        # Unknown variables should remain as placeholders
        assert "{{account_status}}" in captured_kwargs["state_instructions"]
        assert "{{company_name}}" in captured_kwargs["general_instructions"]


class TestToolMessagePropagation:
    """Tool messages from engine should appear in session state.transcript."""

    @pytest.fixture
    def logic_graph(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

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
                        ),
                    ],
                ),
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="support",
                            condition=TransitionCondition(
                                type="equation",
                                value="tier == vip",
                                equations=[EquationClause(left="tier", operator="==", right="vip")],
                            ),
                        ),
                        Transition(
                            target_node_id="standard",
                            condition=TransitionCondition(type="always", value="Else"),
                        ),
                    ],
                ),
                "support": AgentNode(id="support", state_prompt="VIP support.", transitions=[]),
                "standard": AgentNode(id="standard", state_prompt="Standard.", transitions=[]),
            },
            entry_node_id="greeting",
            source_type="retell",
        )

    @pytest.mark.asyncio
    async def test_tool_messages_propagate_to_state_transcript(self, logic_graph):
        """Tool messages produced by engine should appear in state.transcript."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.engine.session import ConversationState
        from voicetest.engine.session import NodeTracker

        runner = ConversationRunner(logic_graph, dynamic_variables={"tier": "vip"})
        state = ConversationState()
        node_tracker = NodeTracker()
        node_tracker.record("router")

        # Directly process the logic node turn
        with patch("voicetest.engine.conversation.call_llm"):
            await runner._process_turn("router", "test", state, node_tracker)

        tool_msgs = [m for m in state.transcript if m.role == "tool"]
        assert len(tool_msgs) >= 1
        assert any("Transitioned to" in m.content for m in tool_msgs)

    @pytest.mark.asyncio
    async def test_tool_messages_from_drain_automatic_nodes(self, logic_graph):
        """Tool messages from _drain_automatic_nodes appear in state.transcript."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.engine.session import ConversationState
        from voicetest.engine.session import NodeTracker

        runner = ConversationRunner(logic_graph, dynamic_variables={"tier": "vip"})
        state = ConversationState()
        node_tracker = NodeTracker()
        node_tracker.record("router")

        with patch("voicetest.engine.conversation.call_llm"):
            await runner._drain_automatic_nodes("router", "test", state, node_tracker)

        tool_msgs = [m for m in state.transcript if m.role == "tool"]
        assert len(tool_msgs) >= 1


class TestAutoProcessLogicNodes:
    """Logic/extract nodes should auto-fire without consuming a user sim turn."""

    @pytest.fixture
    def graph_with_logic_entry(self):
        """Graph where entry node is a logic split routing to conversation nodes."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        return AgentGraph(
            nodes={
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="adult_flow",
                            condition=TransitionCondition(
                                type="equation",
                                value="",
                                equations=[
                                    EquationClause(left="is_minor", operator="==", right="False")
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="minor_flow",
                            condition=TransitionCondition(type="always", value=""),
                        ),
                    ],
                ),
                "adult_flow": AgentNode(
                    id="adult_flow",
                    state_prompt="Greet the adult patient.",
                    transitions=[],
                ),
                "minor_flow": AgentNode(
                    id="minor_flow",
                    state_prompt="Ask for guardian.",
                    transitions=[],
                ),
            },
            entry_node_id="router",
            source_type="custom",
        )

    @pytest.mark.asyncio
    async def test_logic_entry_node_auto_fires(self, graph_with_logic_entry):
        """Logic split entry node should auto-fire before first user sim turn."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import TestCase
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        runner = ConversationRunner(
            graph_with_logic_entry,
            dynamic_variables={"is_minor": "False"},
        )
        test_case = TestCase(name="test", user_prompt="Say hello")

        simulator = UserSimulator("test", "mock-model")
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hello", should_end=False, reasoning="greeting"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Hello there!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = await runner.run(test_case, simulator)

        # Logic node should have auto-fired, routing to adult_flow
        assert "router" in state.nodes_visited
        assert "adult_flow" in state.nodes_visited
        # The user sim should have talked to adult_flow, not the router
        user_msgs = [m for m in state.transcript if m.role == "user"]
        assert user_msgs[0].metadata["node_id"] == "adult_flow"

    @pytest.mark.asyncio
    async def test_logic_entry_node_fallback_route(self, graph_with_logic_entry):
        """Logic split entry node uses always fallback when no equation matches."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import TestCase
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        runner = ConversationRunner(
            graph_with_logic_entry,
            dynamic_variables={"is_minor": "True"},
        )
        test_case = TestCase(name="test", user_prompt="Say hello")

        simulator = UserSimulator("test", "mock-model")
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hello", should_end=False, reasoning="greeting"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Hello there!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = await runner.run(test_case, simulator)

        assert "router" in state.nodes_visited
        assert "minor_flow" in state.nodes_visited
        user_msgs = [m for m in state.transcript if m.role == "user"]
        assert user_msgs[0].metadata["node_id"] == "minor_flow"

    @pytest.fixture
    def graph_with_chained_logic(self):
        """Graph with two chained logic splits before a conversation node."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        return AgentGraph(
            nodes={
                "check_age": AgentNode(
                    id="check_age",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="check_status",
                            condition=TransitionCondition(
                                type="equation",
                                value="",
                                equations=[EquationClause(left="age", operator=">", right="18")],
                            ),
                        ),
                        Transition(
                            target_node_id="rejected",
                            condition=TransitionCondition(type="always", value=""),
                        ),
                    ],
                ),
                "check_status": AgentNode(
                    id="check_status",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="active_flow",
                            condition=TransitionCondition(
                                type="equation",
                                value="",
                                equations=[
                                    EquationClause(left="status", operator="==", right="active")
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="inactive_flow",
                            condition=TransitionCondition(type="always", value=""),
                        ),
                    ],
                ),
                "active_flow": AgentNode(
                    id="active_flow",
                    state_prompt="Help active user.",
                    transitions=[],
                ),
                "inactive_flow": AgentNode(
                    id="inactive_flow",
                    state_prompt="Reactivate account.",
                    transitions=[],
                ),
                "rejected": AgentNode(
                    id="rejected",
                    state_prompt="Cannot proceed.",
                    transitions=[],
                ),
            },
            entry_node_id="check_age",
            source_type="custom",
        )

    @pytest.mark.asyncio
    async def test_chained_logic_nodes_all_auto_fire(self, graph_with_chained_logic):
        """Multiple chained logic splits should all auto-fire before user input."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import TestCase
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        runner = ConversationRunner(
            graph_with_chained_logic,
            dynamic_variables={"age": "25", "status": "active"},
        )
        test_case = TestCase(name="test", user_prompt="Say hello")

        simulator = UserSimulator("test", "mock-model")
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hello", should_end=False, reasoning="greeting"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Welcome!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = await runner.run(test_case, simulator)

        # Both logic nodes and the destination should be visited
        assert "check_age" in state.nodes_visited
        assert "check_status" in state.nodes_visited
        assert "active_flow" in state.nodes_visited
        # User should talk to the conversation node, not the logic nodes
        user_msgs = [m for m in state.transcript if m.role == "user"]
        assert user_msgs[0].metadata["node_id"] == "active_flow"

    @pytest.fixture
    def graph_with_mid_conversation_logic(self):
        """Graph where a conversation node transitions to a logic node mid-flow."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        return AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    state_prompt="Greet the user.",
                    transitions=[
                        Transition(
                            target_node_id="router",
                            condition=TransitionCondition(type="always", value=""),
                        ),
                    ],
                ),
                "router": AgentNode(
                    id="router",
                    state_prompt="",
                    transitions=[
                        Transition(
                            target_node_id="vip",
                            condition=TransitionCondition(
                                type="equation",
                                value="",
                                equations=[EquationClause(left="tier", operator="==", right="vip")],
                            ),
                        ),
                        Transition(
                            target_node_id="standard",
                            condition=TransitionCondition(type="always", value=""),
                        ),
                    ],
                ),
                "vip": AgentNode(
                    id="vip",
                    state_prompt="VIP support.",
                    transitions=[],
                ),
                "standard": AgentNode(
                    id="standard",
                    state_prompt="Standard support.",
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="custom",
        )

    @pytest.mark.asyncio
    async def test_logic_node_after_conversation_auto_fires(
        self, graph_with_mid_conversation_logic
    ):
        """When conversation node transitions to logic node, logic auto-fires."""
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner
        from voicetest.models.test_case import TestCase
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        runner = ConversationRunner(
            graph_with_mid_conversation_logic,
            dynamic_variables={"tier": "vip"},
        )
        test_case = TestCase(name="test", user_prompt="Say hello")

        simulator = UserSimulator("test", "mock-model")
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(message="Hi there", should_end=False, reasoning="greeting"),
            SimulatorResponse(message="Thanks", should_end=False, reasoning="reply"),
            SimulatorResponse(message="", should_end=True, reasoning="done"),
        ]

        async def mock_call_llm(model, signature, **kwargs):
            class MockResult:
                response = "Welcome!"
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=mock_call_llm):
            state = await runner.run(test_case, simulator)

        # greeting -> router (auto) -> vip
        assert "greeting" in state.nodes_visited
        assert "router" in state.nodes_visited
        assert "vip" in state.nodes_visited
        # After greeting responds, always-edge fires to router, then router auto-fires to vip
        # The next user message should be directed at vip, not router
        vip_messages = [m for m in state.transcript if m.metadata.get("node_id") == "vip"]
        assert len(vip_messages) > 0
