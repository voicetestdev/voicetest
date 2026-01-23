"""Tests for voicetest.exporters.retell_cf module."""

import pytest

from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
    Transition,
    TransitionCondition,
)


@pytest.fixture
def simple_graph() -> AgentGraph:
    """Create a simple agent graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="help",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="User needs help with something",
                        ),
                    ),
                ],
            ),
            "help": AgentNode(
                id="help",
                instructions="Help the user with their request.",
                transitions=[
                    Transition(
                        target_node_id="closing",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="User request is complete",
                        ),
                    ),
                ],
            ),
            "closing": AgentNode(
                id="closing",
                instructions="Thank the user and end the conversation.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="test",
    )


@pytest.fixture
def graph_with_tools() -> AgentGraph:
    """Create an agent graph with tools for testing."""
    lookup_tool = ToolDefinition(
        name="lookup_user",
        description="Look up user in database",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "string", "description": "User ID"},
            },
            "required": ["user_id"],
        },
    )
    end_call_tool = ToolDefinition(
        name="end_call",
        description="End the call",
        parameters={},
    )
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                instructions="Greet the user.",
                tools=[end_call_tool],
                transitions=[
                    Transition(
                        target_node_id="lookup",
                        condition=TransitionCondition(
                            type="llm_prompt",
                            value="User wants to check their account",
                        ),
                    ),
                ],
            ),
            "lookup": AgentNode(
                id="lookup",
                instructions="Look up the user's account.",
                tools=[lookup_tool, end_call_tool],
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="test",
    )


@pytest.fixture
def graph_with_metadata() -> AgentGraph:
    """Create an agent graph with source metadata from Retell CF."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                instructions="You are a helpful assistant.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="retell",
        source_metadata={
            "conversation_flow_id": "cf_test123",
            "version": 2,
            "model_choice": {"type": "cascading", "model": "gpt-4.1"},
            "model_temperature": 0.7,
            "start_speaker": "agent",
        },
    )


class TestRetellCFExporter:
    """Tests for Retell Conversation Flow exporter."""

    def test_export_returns_dict(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        assert isinstance(result, dict)

    def test_export_has_required_fields(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        assert "start_node_id" in result
        assert "nodes" in result

    def test_export_creates_nodes(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        assert len(result["nodes"]) == 3

        node_ids = [n["id"] for n in result["nodes"]]
        assert "greeting" in node_ids
        assert "help" in node_ids
        assert "closing" in node_ids

    def test_export_start_node_id_correct(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        assert result["start_node_id"] == "greeting"

    def test_export_node_instruction_format(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")

        assert "instruction" in greeting_node
        assert greeting_node["instruction"]["type"] == "prompt"
        assert "Greet the user warmly" in greeting_node["instruction"]["text"]

    def test_export_node_type(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")
        assert greeting_node["type"] == "conversation"

    def test_export_transitions_become_edges(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")

        assert len(greeting_node["edges"]) == 1
        edge = greeting_node["edges"][0]
        assert edge["destination_node_id"] == "help"
        assert edge["transition_condition"]["type"] == "prompt"
        assert "needs help" in edge["transition_condition"]["prompt"]

    def test_export_edge_has_id(self, simple_graph):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")
        assert "id" in greeting_node["edges"][0]

    def test_export_tools_flattened_to_root(self, graph_with_tools):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(graph_with_tools)
        assert "tools" in result
        tool_names = [t["name"] for t in result["tools"]]
        assert "lookup_user" in tool_names
        assert "end_call" in tool_names

    def test_export_tools_deduplicated(self, graph_with_tools):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(graph_with_tools)
        tool_names = [t["name"] for t in result["tools"]]
        assert tool_names.count("end_call") == 1

    def test_export_tool_format(self, graph_with_tools):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(graph_with_tools)
        lookup_tool = next(t for t in result["tools"] if t["name"] == "lookup_user")

        assert lookup_tool["type"] == "custom"
        assert lookup_tool["description"] == "Look up user in database"
        assert "parameters" in lookup_tool

    def test_export_preserves_metadata(self, graph_with_metadata):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(graph_with_metadata)
        assert result["conversation_flow_id"] == "cf_test123"
        assert result["version"] == 2
        assert result["model_temperature"] == 0.7
        assert result["start_speaker"] == "agent"

    def test_export_preserves_model_choice(self, graph_with_metadata):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(graph_with_metadata)
        assert result["model_choice"]["type"] == "cascading"
        assert result["model_choice"]["model"] == "gpt-4.1"

    def test_export_equation_condition_type(self):
        from voicetest.exporters.retell_cf import export_retell_cf

        graph = AgentGraph(
            nodes={
                "check": AgentNode(
                    id="check",
                    instructions="Check the value.",
                    transitions=[
                        Transition(
                            target_node_id="success",
                            condition=TransitionCondition(
                                type="equation",
                                value="{{score}} > 80",
                            ),
                        ),
                    ],
                ),
                "success": AgentNode(
                    id="success",
                    instructions="Success!",
                    transitions=[],
                ),
            },
            entry_node_id="check",
            source_type="test",
        )

        result = export_retell_cf(graph)
        check_node = next(n for n in result["nodes"] if n["id"] == "check")
        edge = check_node["edges"][0]
        assert edge["transition_condition"]["type"] == "equation"
        assert edge["transition_condition"]["equation"] == "{{score}} > 80"

    def test_roundtrip_import_export(self, sample_retell_config_complex):
        from voicetest.exporters.retell_cf import export_retell_cf
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        assert len(exported["nodes"]) == 11
        assert exported["conversation_flow_id"] == "cf_healthcare_001"
        assert len(exported["tools"]) == 6

    def test_tool_types_preserved(self, sample_retell_config_complex):
        """Test that tool types (custom, end_call, transfer_call) are preserved."""
        from voicetest.exporters.retell_cf import export_retell_cf
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        tool_types = {t["name"]: t["type"] for t in exported["tools"]}
        assert tool_types["end_call"] == "end_call"
        assert tool_types["transfer_to_nurse"] == "transfer_call"
        assert tool_types["lookup_patient"] == "custom"
