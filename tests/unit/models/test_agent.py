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
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        transition = Transition(
            target_node_id="billing",
            condition=TransitionCondition(type="llm_prompt", value="Customer needs billing help"),
            description="Route to billing department",
        )
        assert transition.target_node_id == "billing"
        assert transition.condition.type == "llm_prompt"
        assert transition.description == "Route to billing department"

    def test_transition_without_description(self):
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

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
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

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
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import ToolDefinition

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
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

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
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        nodes = {
            "start": AgentNode(id="start", state_prompt="Start here"),
            "end": AgentNode(id="end", state_prompt="End here"),
        }
        graph = AgentGraph(nodes=nodes, entry_node_id="start", source_type="retell")
        entry = graph.get_entry_node()
        assert entry.id == "start"
        assert entry.state_prompt == "Start here"

    def test_get_node(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        nodes = {
            "a": AgentNode(id="a", state_prompt="Node A"),
            "b": AgentNode(id="b", state_prompt="Node B"),
        }
        graph = AgentGraph(nodes=nodes, entry_node_id="a", source_type="custom")

        assert graph.get_node("a").state_prompt == "Node A"
        assert graph.get_node("b").state_prompt == "Node B"
        assert graph.get_node("nonexistent") is None

    def test_graph_with_source_metadata(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={"n": AgentNode(id="n", state_prompt="Test")},
            entry_node_id="n",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123", "version": 2},
        )
        assert graph.source_metadata["conversation_flow_id"] == "flow-123"
        assert graph.source_metadata["version"] == 2

    def test_graph_json_serialization(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

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


class TestVariableExtraction:
    """Tests for VariableExtraction model."""

    def test_create_variable_extraction(self):
        from voicetest.models.agent import VariableExtraction

        var = VariableExtraction(
            name="dob_month",
            description="The month of birth",
            type="string",
            choices=["January", "February", "March"],
        )
        assert var.name == "dob_month"
        assert var.description == "The month of birth"
        assert var.type == "string"
        assert var.choices == ["January", "February", "March"]

    def test_variable_extraction_defaults(self):
        from voicetest.models.agent import VariableExtraction

        var = VariableExtraction(name="age", description="Patient age")
        assert var.type == "string"
        assert var.choices == []


class TestTransitionConditionLogicalOperator:
    """Tests for logical_operator field on TransitionCondition."""

    def test_logical_operator_defaults_to_and(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(type="equation", value="x == 1")
        assert condition.logical_operator == "and"

    def test_logical_operator_set_to_or(self):
        from voicetest.models.agent import TransitionCondition

        condition = TransitionCondition(type="equation", value="x == 1", logical_operator="or")
        assert condition.logical_operator == "or"


class TestNodeType:
    """Tests for NodeType enum and model_post_init inference."""

    def test_default_is_conversation(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType

        node = AgentNode(id="greeting", state_prompt="Hello")
        assert node.node_type == NodeType.CONVERSATION

    def test_infers_logic_from_equation_transitions(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import NodeType
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition

        node = AgentNode(
            id="router",
            state_prompt="",
            transitions=[
                Transition(
                    target_node_id="a",
                    condition=TransitionCondition(
                        type="equation",
                        value="x == 1",
                        equations=[EquationClause(left="x", operator="==", right="1")],
                    ),
                ),
                Transition(
                    target_node_id="b",
                    condition=TransitionCondition(type="always", value="Else"),
                ),
            ],
        )
        assert node.node_type == NodeType.LOGIC

    def test_infers_extract_from_variables_and_equations(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import NodeType
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition
        from voicetest.models.agent import VariableExtraction

        node = AgentNode(
            id="extract",
            state_prompt="",
            variables_to_extract=[
                VariableExtraction(name="month", description="Month"),
            ],
            transitions=[
                Transition(
                    target_node_id="match",
                    condition=TransitionCondition(
                        type="equation",
                        value="month == January",
                        equations=[EquationClause(left="month", operator="==", right="January")],
                    ),
                ),
                Transition(
                    target_node_id="fallback",
                    condition=TransitionCondition(type="always", value="Else"),
                ),
            ],
        )
        assert node.node_type == NodeType.EXTRACT

    def test_variables_without_equations_stays_conversation(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType
        from voicetest.models.agent import Transition
        from voicetest.models.agent import TransitionCondition
        from voicetest.models.agent import VariableExtraction

        node = AgentNode(
            id="extract",
            state_prompt="",
            variables_to_extract=[
                VariableExtraction(name="month", description="Month"),
            ],
            transitions=[
                Transition(
                    target_node_id="next",
                    condition=TransitionCondition(type="llm_prompt", value="go next"),
                ),
            ],
        )
        assert node.node_type == NodeType.CONVERSATION

    def test_end_call_tool_does_not_infer_end_type(self):
        """Nodes with end_call tools are NOT end nodes — they're conversation nodes
        that have an end_call tool available. Only explicitly typed nodes are END."""
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType
        from voicetest.models.agent import ToolDefinition

        node = AgentNode(
            id="main",
            state_prompt="Help the user.",
            tools=[ToolDefinition(name="end_call", description="End", type="end_call")],
        )
        assert node.node_type == NodeType.CONVERSATION

    def test_transfer_tool_does_not_infer_transfer_type(self):
        """Same as end_call: transfer tools don't make a node a TRANSFER node."""
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType
        from voicetest.models.agent import ToolDefinition

        node = AgentNode(
            id="main",
            state_prompt="Help the user.",
            tools=[ToolDefinition(name="transfer", description="Transfer", type="transfer_call")],
        )
        assert node.node_type == NodeType.CONVERSATION

    def test_explicit_type_overrides_inference(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType

        node = AgentNode(
            id="special",
            state_prompt="Has a prompt but is an end node",
            node_type=NodeType.END,
        )
        assert node.node_type == NodeType.END

    def test_json_round_trip(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType

        node = AgentNode(id="end", state_prompt="", node_type=NodeType.END)
        json_str = node.model_dump_json()
        assert '"end"' in json_str

        restored = AgentNode.model_validate_json(json_str)
        assert restored.node_type == NodeType.END

    def test_backward_compat_json_without_node_type(self):
        """Old JSON without node_type field should infer logic/extract from structure."""
        import json

        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType

        old_json = json.dumps(
            {
                "id": "router",
                "state_prompt": "",
                "transitions": [
                    {
                        "target_node_id": "a",
                        "condition": {"type": "equation", "value": "x == 1"},
                    },
                ],
            }
        )
        node = AgentNode.model_validate_json(old_json)
        assert node.node_type == NodeType.LOGIC

    def test_model_copy_preserves_node_type(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import NodeType

        node = AgentNode(id="end", state_prompt="", node_type=NodeType.END)
        copied = node.model_copy(update={"state_prompt": "Goodbye"})
        assert copied.node_type == NodeType.END

    def test_enum_serializes_as_string(self):
        from voicetest.models.agent import NodeType

        assert str(NodeType.CONVERSATION) == "conversation"
        assert str(NodeType.LOGIC) == "logic"
        assert str(NodeType.EXTRACT) == "extract"
        assert str(NodeType.END) == "end"
        assert str(NodeType.TRANSFER) == "transfer"


class TestGlobalNodeSetting:
    """Tests for GlobalNodeSetting and GoBackCondition models."""

    def test_create_go_back_condition(self):
        from voicetest.models.agent import GoBackCondition
        from voicetest.models.agent import TransitionCondition

        gb = GoBackCondition(
            id="go-back-1",
            condition=TransitionCondition(
                type="llm_prompt",
                value="User wants to continue ordering",
            ),
        )
        assert gb.id == "go-back-1"
        assert gb.condition.type == "llm_prompt"
        assert gb.condition.value == "User wants to continue ordering"

    def test_create_global_node_setting(self):
        from voicetest.models.agent import GlobalNodeSetting
        from voicetest.models.agent import GoBackCondition
        from voicetest.models.agent import TransitionCondition

        setting = GlobalNodeSetting(
            condition="User wants to cancel their order",
            go_back_conditions=[
                GoBackCondition(
                    id="go-back-1",
                    condition=TransitionCondition(
                        type="llm_prompt",
                        value="User changes their mind",
                    ),
                ),
            ],
        )
        assert setting.condition == "User wants to cancel their order"
        assert len(setting.go_back_conditions) == 1
        assert setting.go_back_conditions[0].id == "go-back-1"

    def test_global_node_setting_empty_go_backs(self):
        from voicetest.models.agent import GlobalNodeSetting

        setting = GlobalNodeSetting(
            condition="User asks about specials",
        )
        assert setting.go_back_conditions == []

    def test_agent_node_global_setting_none_by_default(self):
        from voicetest.models.agent import AgentNode

        node = AgentNode(id="main", state_prompt="Help.")
        assert node.global_node_setting is None

    def test_agent_node_with_global_setting(self):
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import GlobalNodeSetting

        node = AgentNode(
            id="cancel",
            state_prompt="Ask if they want to cancel.",
            global_node_setting=GlobalNodeSetting(
                condition="User wants to cancel",
            ),
        )
        assert node.global_node_setting is not None
        assert node.global_node_setting.condition == "User wants to cancel"

    def test_agent_graph_global_nodes_empty(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="A."),
                "b": AgentNode(id="b", state_prompt="B."),
            },
            entry_node_id="a",
            source_type="custom",
        )
        assert graph.global_nodes == []

    def test_agent_graph_global_nodes_returns_marked_nodes(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import GlobalNodeSetting

        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="A."),
                "cancel": AgentNode(
                    id="cancel",
                    state_prompt="Cancel.",
                    global_node_setting=GlobalNodeSetting(
                        condition="User wants to cancel",
                    ),
                ),
                "faq": AgentNode(
                    id="faq",
                    state_prompt="FAQ.",
                    global_node_setting=GlobalNodeSetting(
                        condition="User asks a question",
                    ),
                ),
            },
            entry_node_id="a",
            source_type="custom",
        )
        global_ids = {n.id for n in graph.global_nodes}
        assert global_ids == {"cancel", "faq"}

    def test_global_node_setting_json_round_trip(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.models.agent import GlobalNodeSetting
        from voicetest.models.agent import GoBackCondition
        from voicetest.models.agent import TransitionCondition

        graph = AgentGraph(
            nodes={
                "main": AgentNode(id="main", state_prompt="Main."),
                "global": AgentNode(
                    id="global",
                    state_prompt="Global.",
                    global_node_setting=GlobalNodeSetting(
                        condition="trigger condition",
                        go_back_conditions=[
                            GoBackCondition(
                                id="gb-1",
                                condition=TransitionCondition(
                                    type="llm_prompt",
                                    value="go back",
                                ),
                            ),
                        ],
                    ),
                ),
            },
            entry_node_id="main",
            source_type="custom",
        )

        json_str = graph.model_dump_json()
        restored = AgentGraph.model_validate_json(json_str)

        assert restored.nodes["main"].global_node_setting is None
        assert restored.nodes["global"].global_node_setting is not None
        assert restored.nodes["global"].global_node_setting.condition == "trigger condition"
        assert len(restored.nodes["global"].global_node_setting.go_back_conditions) == 1
        assert restored.nodes["global"].global_node_setting.go_back_conditions[0].id == "gb-1"


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
        from voicetest.models.agent import GlobalMetric
        from voicetest.models.agent import MetricsConfig

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
        from voicetest.models.agent import GlobalMetric
        from voicetest.models.agent import MetricsConfig

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
