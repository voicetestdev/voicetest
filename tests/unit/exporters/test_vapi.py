"""Tests for voicetest.exporters.vapi module."""

import pytest

from voicetest.exporters.vapi import export_vapi_assistant
from voicetest.exporters.vapi import export_vapi_squad
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


@pytest.fixture
def simple_squad_graph() -> AgentGraph:
    """Two-node graph for basic squad tests."""
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


class TestVAPISquadBasic:
    """Baseline squad export tests."""

    def test_squad_has_members(self, simple_squad_graph):
        result = export_vapi_squad(simple_squad_graph)
        assert len(result["members"]) == 2

    def test_squad_entry_node_first(self, simple_squad_graph):
        result = export_vapi_squad(simple_squad_graph)
        assert result["members"][0]["assistant"]["name"] == "greeting"

    def test_handoff_tool_created(self, simple_squad_graph):
        result = export_vapi_squad(simple_squad_graph)
        greeting_tools = result["members"][0]["assistant"]["model"]["tools"]
        handoff = next(t for t in greeting_tools if t["type"] == "handoff")
        assert handoff["destinations"][0]["assistantName"] == "farewell"


class TestVAPISquadLogicSplit:
    """Logic split nodes should be skipped in squad export.

    When a logic split node sits between conversation nodes, the squad
    exporter should wire predecessors directly to successors using
    the equation conditions as handoff descriptions.
    """

    def test_logic_node_excluded_from_members(self, logic_split_graph):
        """Logic split nodes should not appear as squad members."""
        result = export_vapi_squad(logic_split_graph)
        member_names = [m["assistant"]["name"] for m in result["members"]]
        assert "router" not in member_names

    def test_predecessor_gets_direct_handoffs(self, logic_split_graph):
        """Greeting node should handoff directly to premium/standard."""
        result = export_vapi_squad(logic_split_graph)
        greeting = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        tools = greeting["assistant"]["model"]["tools"]
        handoff = next(t for t in tools if t["type"] == "handoff")
        dest_names = {d["assistantName"] for d in handoff["destinations"]}
        assert dest_names == {"premium", "standard"}

    def test_equation_condition_in_handoff_description(self, logic_split_graph):
        """Equation conditions become handoff descriptions."""
        result = export_vapi_squad(logic_split_graph)
        greeting = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        tools = greeting["assistant"]["model"]["tools"]
        handoff = next(t for t in tools if t["type"] == "handoff")
        premium_dest = next(d for d in handoff["destinations"] if d["assistantName"] == "premium")
        assert "account_type" in premium_dest["description"]
        assert "premium" in premium_dest["description"]

    def test_else_condition_in_handoff_description(self, logic_split_graph):
        """Always/else conditions get a readable fallback description."""
        result = export_vapi_squad(logic_split_graph)
        greeting = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        tools = greeting["assistant"]["model"]["tools"]
        handoff = next(t for t in tools if t["type"] == "handoff")
        standard_dest = next(d for d in handoff["destinations"] if d["assistantName"] == "standard")
        # Should indicate this is a fallback/else path
        assert (
            "else" in standard_dest["description"].lower()
            or "fallback" in standard_dest["description"].lower()
        )

    def test_total_member_count(self, logic_split_graph):
        """Should have 4 members (greeting, premium, standard, farewell)."""
        result = export_vapi_squad(logic_split_graph)
        assert len(result["members"]) == 4


class TestVAPIAssistantLogicSplit:
    """Logic split nodes should be omitted from merged assistant prompt."""

    def test_logic_node_prompt_excluded(self, logic_split_graph):
        """Empty logic node prompts shouldn't add blank lines to output."""
        result = export_vapi_assistant(logic_split_graph)
        # The assistant format merges all nodes into one — logic node
        # has empty state_prompt so it shouldn't add noise
        model_messages = result["model"]["messages"]
        system_content = model_messages[0]["content"]
        # Should not have consecutive blank lines from empty logic node
        assert "\n\n\n" not in system_content
