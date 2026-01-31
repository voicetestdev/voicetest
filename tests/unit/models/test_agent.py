"""Tests for voicetest.models.agent module."""

from pydantic import ValidationError
import pytest


class TestTransitionCondition:
    """Tests for TransitionCondition model."""

    def test_create_llm_prompt_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(
            type="llm_prompt", value="Customer wants to check their balance"
        )
        assert condition.type == "llm_prompt"
        assert condition.value == "Customer wants to check their balance"

    def test_create_equation_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(type="equation", value="{{user_age}} > 18")
        assert condition.type == "equation"
        assert condition.value == "{{user_age}} > 18"

    def test_create_tool_call_condition(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(type="tool_call", value="transfer_to_agent")
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
            condition=TransitionCondition(type="llm_prompt", value="Customer needs billing help"),
            description="Route to billing department",
        )
        assert transition.target_node_id == "billing"
        assert transition.condition.type == "llm_prompt"
        assert transition.description == "Route to billing department"

    def test_transition_without_description(self):
        from voicetest.models.agent import Transition, TransitionCondition

        transition = Transition(
            target_node_id="support", condition=TransitionCondition(type="always", value="")
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
                "properties": {"account_id": {"type": "string"}},
                "required": ["account_id"],
            },
        )
        assert tool.name == "lookup_account"
        assert tool.description == "Look up customer account by ID"
        assert "account_id" in tool.parameters["properties"]


class TestAgentNode:
    """Tests for AgentNode model."""

    def test_create_basic_node(self):
        from voicetest.models.agent import AgentNode

        node = AgentNode(id="greeting", state_prompt="Greet the customer warmly.")
        assert node.id == "greeting"
        assert node.state_prompt == "Greet the customer warmly."
        assert node.tools == []
        assert node.transitions == []
        assert node.metadata == {}

    def test_create_node_with_transitions(self):
        from voicetest.models.agent import AgentNode, Transition, TransitionCondition

        node = AgentNode(
            id="greeting",
            state_prompt="Greet the customer.",
            transitions=[
                Transition(
                    target_node_id="billing",
                    condition=TransitionCondition(
                        type="llm_prompt", value="Customer needs billing"
                    ),
                ),
                Transition(
                    target_node_id="support",
                    condition=TransitionCondition(
                        type="llm_prompt", value="Customer needs support"
                    ),
                ),
            ],
        )
        assert len(node.transitions) == 2
        assert node.transitions[0].target_node_id == "billing"
        assert node.transitions[1].target_node_id == "support"

    def test_create_node_with_tools(self):
        from voicetest.models.agent import AgentNode, ToolDefinition

        node = AgentNode(
            id="lookup",
            state_prompt="Look up the customer's information.",
            tools=[
                ToolDefinition(
                    name="get_account",
                    description="Get account details",
                    parameters={"type": "object", "properties": {}},
                )
            ],
        )
        assert len(node.tools) == 1
        assert node.tools[0].name == "get_account"

    def test_create_node_with_metadata(self):
        from voicetest.models.agent import AgentNode

        node = AgentNode(
            id="greeting",
            state_prompt="Greet",
            metadata={"retell_type": "conversation", "custom_field": 123},
        )
        assert node.metadata["retell_type"] == "conversation"
        assert node.metadata["custom_field"] == 123


class TestAgentGraph:
    """Tests for AgentGraph model."""

    def test_create_simple_graph(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        nodes = {
            "greeting": AgentNode(id="greeting", state_prompt="Hello!"),
            "end": AgentNode(id="end", state_prompt="Goodbye!"),
        }
        graph = AgentGraph(nodes=nodes, entry_node_id="greeting", source_type="custom")
        assert len(graph.nodes) == 2
        assert graph.entry_node_id == "greeting"
        assert graph.source_type == "custom"
        assert graph.source_metadata == {}

    def test_get_entry_node(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        nodes = {
            "start": AgentNode(id="start", state_prompt="Start here"),
            "end": AgentNode(id="end", state_prompt="End here"),
        }
        graph = AgentGraph(nodes=nodes, entry_node_id="start", source_type="retell")
        entry = graph.get_entry_node()
        assert entry.id == "start"
        assert entry.state_prompt == "Start here"

    def test_get_node(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        nodes = {
            "a": AgentNode(id="a", state_prompt="Node A"),
            "b": AgentNode(id="b", state_prompt="Node B"),
        }
        graph = AgentGraph(nodes=nodes, entry_node_id="a", source_type="custom")

        assert graph.get_node("a").state_prompt == "Node A"
        assert graph.get_node("b").state_prompt == "Node B"
        assert graph.get_node("nonexistent") is None

    def test_graph_with_source_metadata(self):
        from voicetest.models.agent import AgentGraph, AgentNode

        graph = AgentGraph(
            nodes={"n": AgentNode(id="n", state_prompt="Test")},
            entry_node_id="n",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123", "version": 2},
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
                    state_prompt="Hello",
                    transitions=[
                        Transition(
                            target_node_id="end",
                            condition=TransitionCondition(type="llm_prompt", value="User is done"),
                        )
                    ],
                ),
                "end": AgentNode(id="end", state_prompt="Bye"),
            },
            entry_node_id="start",
            source_type="custom",
        )

        json_str = graph.model_dump_json()
        assert "start" in json_str
        assert "llm_prompt" in json_str

        # Round-trip
        restored = AgentGraph.model_validate_json(json_str)
        assert restored.entry_node_id == "start"
        assert len(restored.nodes) == 2


class TestGlobalMetric:
    """Tests for GlobalMetric model."""

    def test_create_global_metric(self):
        from voicetest.models.agent import GlobalMetric

        metric = GlobalMetric(
            name="HIPAA",
            criteria="Agent confirmed patient name AND DOB before sharing PHI",
        )
        assert metric.name == "HIPAA"
        assert metric.criteria == "Agent confirmed patient name AND DOB before sharing PHI"
        assert metric.threshold is None
        assert metric.enabled is True

    def test_create_global_metric_with_threshold(self):
        from voicetest.models.agent import GlobalMetric

        metric = GlobalMetric(
            name="compliance",
            criteria="Agent follows compliance rules",
            threshold=0.9,
        )
        assert metric.threshold == 0.9

    def test_create_disabled_global_metric(self):
        from voicetest.models.agent import GlobalMetric

        metric = GlobalMetric(
            name="test",
            criteria="Test criteria",
            enabled=False,
        )
        assert metric.enabled is False


class TestMetricsConfig:
    """Tests for MetricsConfig model."""

    def test_create_empty_metrics_config(self):
        from voicetest.models.agent import MetricsConfig

        config = MetricsConfig()
        assert config.threshold == 0.7
        assert config.global_metrics == []

    def test_create_metrics_config_with_threshold(self):
        from voicetest.models.agent import MetricsConfig

        config = MetricsConfig(threshold=0.8)
        assert config.threshold == 0.8

    def test_create_metrics_config_with_global_metrics(self):
        from voicetest.models.agent import GlobalMetric, MetricsConfig

        config = MetricsConfig(
            threshold=0.75,
            global_metrics=[
                GlobalMetric(name="HIPAA", criteria="Check HIPAA compliance"),
                GlobalMetric(name="PCI", criteria="Check PCI compliance", threshold=0.9),
            ],
        )
        assert config.threshold == 0.75
        assert len(config.global_metrics) == 2
        assert config.global_metrics[0].name == "HIPAA"
        assert config.global_metrics[1].threshold == 0.9

    def test_metrics_config_json_serialization(self):
        from voicetest.models.agent import GlobalMetric, MetricsConfig

        config = MetricsConfig(
            threshold=0.8,
            global_metrics=[
                GlobalMetric(name="test", criteria="Test criteria", enabled=False),
            ],
        )

        json_str = config.model_dump_json()
        assert "test" in json_str
        assert "0.8" in json_str

        restored = MetricsConfig.model_validate_json(json_str)
        assert restored.threshold == 0.8
        assert len(restored.global_metrics) == 1
        assert restored.global_metrics[0].enabled is False
