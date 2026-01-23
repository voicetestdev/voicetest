"""Tests for voicetest.engine.session module."""

import pytest

from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    Transition,
    TransitionCondition,
)


@pytest.fixture
def simple_graph() -> AgentGraph:
    """Create a simple two-node graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="farewell",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User wants to end the conversation"
                        ),
                    )
                ],
            ),
            "farewell": AgentNode(
                id="farewell", instructions="Say goodbye politely.", transitions=[]
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


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

    def test_runner_generates_agent_classes(self, simple_graph):
        from voicetest.engine.session import ConversationRunner

        runner = ConversationRunner(simple_graph)

        assert "greeting" in runner.agent_classes
        assert "farewell" in runner.agent_classes

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
