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
        from voicetest.simulator.user_sim import SimulatorResponse, UserSimulator

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


class TestDynamicVariableSubstitution:
    """Tests for dynamic variable substitution in prompts."""

    @pytest.mark.asyncio
    async def test_dynamic_variables_substituted_in_prompts(self, graph_with_dynamic_variables):
        """Test that dynamic variables are substituted in both general and state prompts.

        This test verifies that {{variable}} placeholders in general_prompt and state_prompt
        are replaced with actual values from dynamic_variables before being passed to the LLM.
        """
        from unittest.mock import patch

        from voicetest.engine.session import ConversationRunner, ConversationState, NodeTracker

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

        with patch("voicetest.engine.session.call_llm", side_effect=mock_call_llm):
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

        from voicetest.engine.session import ConversationRunner, ConversationState, NodeTracker

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

        with patch("voicetest.engine.session.call_llm", side_effect=mock_call_llm):
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
