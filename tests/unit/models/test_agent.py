"""Tests for voicetest.models.agent module."""

import pytest
from pydantic import ValidationError


class TestTransitionCondition:
    """Tests for TransitionCondition model."""

    def test_create_llm_prompt_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(
            type="llm_prompt",
            value="Customer wants to check their balance"
        )
        assert condition.type == "llm_prompt"
        assert condition.value == "Customer wants to check their balance"

    def test_create_equation_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(
            type="equation",
            value="{{user_age}} > 18"
        )
        assert condition.type == "equation"
        assert condition.value == "{{user_age}} > 18"

    def test_create_tool_call_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(
            type="tool_call",
            value="transfer_to_agent"
        )
        assert condition.type == "tool_call"

    def test_create_always_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(type="always", value="")
        assert condition.type == "always"

    def test_invalid_condition_type(self):
        from voicetest.models.agent import TransitionCondition

        with pytest.raises(ValidationError):
            TransitionCondition(type="invalid_type", value="test")


class TestTransition:
    """Tests for Transition model."""

    def test_create_transition(self):
        from voicetest.models.agent import Transition, TransitionCondition

        transition = Transition(
            target_node_id="billing",
            condition=TransitionCondition(
                type="llm_prompt",
                value="Customer needs billing help"
            ),
            description="Route to billing department"
        )
        assert transition.target_node_id == "billing"
        assert transition.condition.type == "llm_prompt"
        assert transition.description == "Route to billing department"

    def test_transition_without_description(self):
        from voicetest.models.agent import Transition, TransitionCondition

        transition = Transition(
            target_node_id="support",
            condition=TransitionCondition(type="always", value="")
        )
        assert transition.description is None


class TestToolDefinition:
    """Tests for ToolDefinition model."""

    def test_create_tool_definition(self):
        from voicetest.models.agent import ToolDefinition

        tool = ToolDefinition(
            name="lookup_account",
            description="Look up customer account by ID",
            parameters={
                "type": "object",
                "properties": {
                    "account_id": {"type": "string"}
                },
                "required": ["account_id"]
            }
        )
        assert tool.name == "lookup_account"
        assert tool.description == "Look up customer account by ID"
        assert "account_id" in tool.parameters["properties"]


class TestAgentNode:
    """Tests for AgentNode model."""

    def test_create_basic_node(self):
        from voicetest.models.agent import AgentNode

        node = AgentNode(
            id="greeting",
            instructions="Greet the customer warmly."
        )
        assert node.id == "greeting"
        assert node.instructions == "Greet the customer warmly."
        assert node.tools == []
        assert node.transitions == []
        assert node.metadata == {}

    def test_create_node_with_transitions(self):
        from voicetest.models.agent import AgentNode, Transition, TransitionCondition

        node = AgentNode(
            id="greeting",
            instructions="Greet the customer.",
            transitions=[
                Transition(
                    target_node_id="billing",
                    condition=TransitionCondition(
                        type="llm_prompt",
                        value="Customer needs billing"
                    )
                ),
                Transition(
                    target_node_id="support",
                    condition=TransitionCondition(
                        type="llm_prompt",
                        value="Customer needs support"
                    )
                )
            ]
        )
        assert len(node.transitions) == 2
        assert node.transitions[0].target_node_id == "billing"
        assert node.transitions[1].target_node_id == "support"

    def test_create_node_with_tools(self):
        from voicetest.models.agent import AgentNode, ToolDefinition

        node = AgentNode(
            id="lookup",
            instructions="Look up the customer's information.",
            tools=[
                ToolDefinition(
                    name="get_account",
                    description="Get account details",
                    parameters={"type": "object", "properties": {}}
                )
            ]
        )
        assert len(node.tools) == 1
        assert node.tools[0].name == "get_account"

    def test_create_node_with_metadata(self):
        from voicetest.models.agent import AgentNode

        node = AgentNode(
            id="greeting",
            instructions="Greet",
            metadata={"retell_type": "conversation", "custom_field": 123}
        )
        assert node.metadata["retell_type"] == "conversation"
        assert node.metadata["custom_field"] == 123


class TestAgentGraph:
    """Tests for AgentGraph model."""

    def test_create_simple_graph(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        nodes = {
            "greeting": AgentNode(id="greeting", instructions="Hello!"),
            "end": AgentNode(id="end", instructions="Goodbye!")
        }
        graph = AgentGraph(
            nodes=nodes,
            entry_node_id="greeting",
            source_type="custom"
        )
        assert len(graph.nodes) == 2
        assert graph.entry_node_id == "greeting"
        assert graph.source_type == "custom"
        assert graph.source_metadata == {}

    def test_get_entry_node(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        nodes = {
            "start": AgentNode(id="start", instructions="Start here"),
            "end": AgentNode(id="end", instructions="End here")
        }
        graph = AgentGraph(
            nodes=nodes,
            entry_node_id="start",
            source_type="retell"
        )
        entry = graph.get_entry_node()
        assert entry.id == "start"
        assert entry.instructions == "Start here"

    def test_get_node(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        nodes = {
            "a": AgentNode(id="a", instructions="Node A"),
            "b": AgentNode(id="b", instructions="Node B")
        }
        graph = AgentGraph(nodes=nodes, entry_node_id="a", source_type="custom")

        assert graph.get_node("a").instructions == "Node A"
        assert graph.get_node("b").instructions == "Node B"
        assert graph.get_node("nonexistent") is None

    def test_graph_with_source_metadata(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        graph = AgentGraph(
            nodes={"n": AgentNode(id="n", instructions="Test")},
            entry_node_id="n",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123", "version": 2}
        )
        assert graph.source_metadata["conversation_flow_id"] == "flow-123"
        assert graph.source_metadata["version"] == 2

    def test_graph_json_serialization(self):
        from voicetest.models.agent import (
            AgentGraph,
            AgentNode,
            Transition,
            TransitionCondition,
        )

        graph = AgentGraph(
            nodes={
                "start": AgentNode(
                    id="start",
                    instructions="Hello",
                    transitions=[
                        Transition(
                            target_node_id="end",
                            condition=TransitionCondition(
                                type="llm_prompt",
                                value="User is done"
                            )
                        )
                    ]
                ),
                "end": AgentNode(id="end", instructions="Bye")
            },
            entry_node_id="start",
            source_type="custom"
        )

        json_str = graph.model_dump_json()
        assert "start" in json_str
        assert "llm_prompt" in json_str

        # Round-trip
        restored = AgentGraph.model_validate_json(json_str)
        assert restored.entry_node_id == "start"
        assert len(restored.nodes) == 2
