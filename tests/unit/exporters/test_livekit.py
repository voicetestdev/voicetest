"""Tests for voicetest.exporters.livekit_codegen module."""

import pytest

from voicetest.exporters.livekit_codegen import export_livekit_code
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


@pytest.fixture
def simple_livekit_graph() -> AgentGraph:
    """Two-node graph for basic LiveKit tests."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the caller.",
                transitions=[
                    Transition(
                        target_node_id="farewell",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="User wants to leave",
                        ),
                    )
                ],
            ),
            "farewell": AgentNode(
                id="farewell",
                state_prompt="Say goodbye.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
    )


class TestLiveKitBasic:
    """Baseline LiveKit export tests."""

    def test_generates_agent_classes(self, simple_livekit_graph):
        result = export_livekit_code(simple_livekit_graph)
        assert "class Agent_greeting" in result
        assert "class Agent_farewell" in result

    def test_generates_entry_point(self, simple_livekit_graph):
        result = export_livekit_code(simple_livekit_graph)
        assert "return Agent_greeting()" in result

    def test_transition_becomes_function_tool(self, simple_livekit_graph):
        result = export_livekit_code(simple_livekit_graph)
        assert "route_to_farewell" in result
        assert "User wants to leave" in result


class TestLiveKitLogicSplit:
    """Logic split nodes should generate deterministic routing code."""

    def test_logic_node_no_agent_class(self, logic_split_graph):
        """Logic split nodes should not generate an Agent class."""
        result = export_livekit_code(logic_split_graph)
        assert "class Agent_router" not in result

    def test_predecessor_gets_deterministic_routing(self, logic_split_graph):
        """Greeting node should get a routing method for the logic split."""
        result = export_livekit_code(logic_split_graph)
        # The greeting node transitions to router (a logic node).
        # Instead of a function_tool, it should generate a deterministic
        # routing method that evaluates equations.
        assert "Agent_greeting" in result
        # Should route to premium and standard (the logic node's targets)
        assert "Agent_premium" in result
        assert "Agent_standard" in result

    def test_equation_condition_in_routing_code(self, logic_split_graph):
        """Equation conditions should appear in the routing code."""
        result = export_livekit_code(logic_split_graph)
        assert "account_type" in result

    def test_else_branch_in_routing_code(self, logic_split_graph):
        """Always/else condition should generate an else branch."""
        result = export_livekit_code(logic_split_graph)
        # Should have else clause for the fallback
        assert "else" in result.lower()

    def test_logic_node_targets_have_classes(self, logic_split_graph):
        """Premium and standard nodes should have agent classes."""
        result = export_livekit_code(logic_split_graph)
        assert "class Agent_premium" in result
        assert "class Agent_standard" in result

    def test_no_route_to_logic_node(self, logic_split_graph):
        """No function_tool named route_to_router should exist."""
        result = export_livekit_code(logic_split_graph)
        assert "route_to_router" not in result
