"""Tests for voicetest.exporters.retell_cf module."""

import json
from unittest.mock import patch

import pytest

from voicetest.exporters.retell_cf import RetellCFExporter
from voicetest.exporters.retell_cf import export_retell_cf
from voicetest.importers.retell import RetellImporter
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.settings import Settings


def _find_node(nodes: list[dict], node_id: str) -> dict | None:
    """Find a node by ID in a CF nodes list."""
    return next((n for n in nodes if n["id"] == node_id), None)


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
        url="https://api.example.com/lookup",
    )
    transfer_tool = ToolDefinition(
        name="transfer_to_nurse",
        description="Transfer the call",
        type="transfer_call",
        parameters={},
    )
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user.",
                tools=[transfer_tool],
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
                state_prompt="Look up the user's account.",
                tools=[lookup_tool, transfer_tool],
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
                state_prompt="You are a helpful assistant.",
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


class TestTerminalToolSynthesis:
    """Tests for converting end_call/transfer_call tools into CF node types."""

    def test_end_call_tool_becomes_end_node(self):
        """Graph with end_call tool should produce a type=end node in CF output."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Help the user, then end_call when done.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        end_nodes = [n for n in result["nodes"] if n["type"] == "end"]
        assert len(end_nodes) == 1
        assert end_nodes[0]["instruction"]["type"] == "prompt"

    def test_transfer_call_tool_becomes_transfer_node(self):
        """Graph with transfer_call tool should produce a type=transfer_call node."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="If needed, use transfer_to_nurse to transfer.",
                    tools=[
                        ToolDefinition(
                            name="transfer_to_nurse",
                            description="Transfer to nurse for medical questions",
                            type="transfer_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        transfer_nodes = [n for n in result["nodes"] if n["type"] == "transfer_call"]
        assert len(transfer_nodes) == 1
        node = transfer_nodes[0]
        assert "transfer_destination" in node
        assert node["transfer_destination"]["type"] == "predefined"
        assert "transfer_option" in node
        assert node["transfer_option"]["type"] == "cold_transfer"
        # transfer_call nodes use singular "edge" (failure edge), not "edges"
        assert "edge" in node
        assert "edges" not in node

    def test_synthesized_edges_from_prompt_mentions(self):
        """Nodes whose prompts mention a terminal tool name get edges to the synthesized node."""
        graph = AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    state_prompt="Greet the user. If they want to leave, end_call.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
                "help": AgentNode(
                    id="help",
                    state_prompt="Help the user. When done, use end_call.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="test",
        )

        result = export_retell_cf(graph)
        greeting = _find_node(result["nodes"], "greeting")
        help_node = _find_node(result["nodes"], "help")

        # Both nodes mention end_call, both should get edges to the end node
        end_nodes = [n for n in result["nodes"] if n["type"] == "end"]
        assert len(end_nodes) == 1
        end_id = end_nodes[0]["id"]

        greeting_targets = [e["destination_node_id"] for e in greeting["edges"]]
        help_targets = [e["destination_node_id"] for e in help_node["edges"]]
        assert end_id in greeting_targets
        assert end_id in help_targets

    def test_nodes_not_mentioning_tool_get_no_edge(self):
        """Nodes that don't mention the terminal tool name should not get synthesized edges."""
        graph = AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    state_prompt="Greet the user. If done, end_call.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
                "help": AgentNode(
                    id="help",
                    state_prompt="Help the user with their request.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="test",
        )

        result = export_retell_cf(graph)
        help_node = _find_node(result["nodes"], "help")

        # "help" prompt doesn't mention "end_call", so it should have no synthesized edges
        assert len(help_node["edges"]) == 0

    def test_terminal_tools_excluded_from_tools_array(self):
        """end_call and transfer_call tools should not appear in the root tools array."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Help user. Use end_call or transfer_to_nurse as needed.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                        ToolDefinition(
                            name="transfer_to_nurse",
                            description="Transfer to nurse",
                            type="transfer_call",
                        ),
                        ToolDefinition(
                            name="lookup_user",
                            description="Look up user",
                            type="custom",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        tool_names = [t["name"] for t in result["tools"]]
        assert "end_call" not in tool_names
        assert "transfer_to_nurse" not in tool_names
        assert "lookup_user" in tool_names

    def test_cf_roundtrip_skips_synthesis(self):
        """Graph from CF import (with retell_type metadata) should not double-synthesize nodes."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Help the user.",
                    transitions=[
                        Transition(
                            target_node_id="end_node",
                            condition=TransitionCondition(
                                type="llm_prompt",
                                value="Call is done",
                            ),
                        ),
                    ],
                    metadata={"retell_type": "conversation"},
                ),
                "end_node": AgentNode(
                    id="end_node",
                    state_prompt="End the call.",
                    transitions=[],
                    metadata={"retell_type": "end"},
                ),
            },
            entry_node_id="main",
            source_type="retell",
        )

        result = export_retell_cf(graph)
        end_nodes = [n for n in result["nodes"] if n["type"] == "end"]
        # Should only have the original end_node, not a synthesized duplicate
        assert len(end_nodes) == 1
        assert end_nodes[0]["id"] == "end_node"

    def test_multiple_transfer_tools_each_get_own_node(self):
        """Multiple transfer_call tools should each produce their own synthesized node."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Use transfer_to_nurse or transfer_to_billing as needed.",
                    tools=[
                        ToolDefinition(
                            name="transfer_to_nurse",
                            description="Transfer to nurse",
                            type="transfer_call",
                        ),
                        ToolDefinition(
                            name="transfer_to_billing",
                            description="Transfer to billing dept",
                            type="transfer_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        transfer_nodes = [n for n in result["nodes"] if n["type"] == "transfer_call"]
        assert len(transfer_nodes) == 2

    def test_transfer_destination_preserved_from_llm_json(self):
        """Import LLM JSON with transfer_destination → export CF → number on node."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        llm_json = {
            "general_prompt": "You are a vet clinic receptionist.",
            "model": "gpt-4o",
            "general_tools": [
                {"type": "end_call", "name": "end_call", "description": ""},
                {
                    "type": "transfer_call",
                    "name": "transfer_call_to_vet",
                    "description": "Transfer to the on-call veterinarian",
                    "transfer_destination": {
                        "type": "predefined",
                        "number": "+18005551234",
                    },
                    "transfer_option": {
                        "type": "warm_transfer",
                        "agent_detection_timeout_ms": 30000,
                    },
                },
            ],
            "states": [
                {
                    "name": "triage",
                    "state_prompt": "Ask about the pet. If urgent, transfer_call_to_vet.",
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(llm_json)
        result = export_retell_cf(graph)

        transfer_nodes = [n for n in result["nodes"] if n["type"] == "transfer_call"]
        assert len(transfer_nodes) == 1
        node = transfer_nodes[0]
        assert node["transfer_destination"]["number"] == "+18005551234"
        assert node["transfer_option"]["type"] == "warm_transfer"

    def test_transfer_destination_falls_back_without_source(self):
        """LLM JSON without transfer_destination gets placeholder number."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        llm_json = {
            "general_prompt": "You are a bakery assistant.",
            "model": "gpt-4o",
            "general_tools": [
                {
                    "type": "custom",
                    "name": "transfer_call_to_manager",
                    "description": "Transfer to the bakery manager",
                },
            ],
            "states": [
                {
                    "name": "order",
                    "state_prompt": "Take orders. If complaint, transfer_call_to_manager.",
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(llm_json)
        result = export_retell_cf(graph)

        transfer_nodes = [n for n in result["nodes"] if n["type"] == "transfer_call"]
        assert len(transfer_nodes) == 1
        node = transfer_nodes[0]
        assert node["transfer_destination"]["number"] == "+16505555555"
        assert node["transfer_option"]["type"] == "cold_transfer"

    def test_multiple_transfer_destinations_from_llm_json(self):
        """Multiple transfer tools each get their own node with their own number."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        llm_json = {
            "general_prompt": "You are a hospital switchboard.",
            "model": "gpt-4o",
            "general_tools": [
                {"type": "end_call", "name": "end_call", "description": ""},
                {
                    "type": "transfer_call",
                    "name": "transfer_call_to_er",
                    "description": "Transfer to emergency room",
                    "transfer_destination": {
                        "type": "predefined",
                        "number": "+18005559111",
                    },
                    "transfer_option": {"type": "cold_transfer"},
                },
                {
                    "type": "transfer_call",
                    "name": "transfer_call_to_pharmacy",
                    "description": "Transfer to pharmacy",
                    "transfer_destination": {
                        "type": "predefined",
                        "number": "+18005559222",
                    },
                    "transfer_option": {"type": "warm_transfer"},
                },
            ],
            "states": [
                {
                    "name": "intake",
                    "state_prompt": (
                        "Route the caller. For emergencies use transfer_call_to_er."
                        " For prescriptions use transfer_call_to_pharmacy."
                    ),
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(llm_json)
        result = export_retell_cf(graph)

        transfer_nodes = {n["id"]: n for n in result["nodes"] if n["type"] == "transfer_call"}
        assert len(transfer_nodes) == 2

        er_node = transfer_nodes["synth_transfer_call_to_er"]
        assert er_node["transfer_destination"]["number"] == "+18005559111"
        assert er_node["transfer_option"]["type"] == "cold_transfer"

        pharm_node = transfer_nodes["synth_transfer_call_to_pharmacy"]
        assert pharm_node["transfer_destination"]["number"] == "+18005559222"
        assert pharm_node["transfer_option"]["type"] == "warm_transfer"


class TestRetellCFExporter:
    """Tests for Retell Conversation Flow exporter."""

    def test_export_returns_dict(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        assert isinstance(result, dict)

    def test_export_has_required_fields(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        assert "start_node_id" in result
        assert "nodes" in result

    def test_export_creates_nodes(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        assert len(result["nodes"]) == 3

        node_ids = [n["id"] for n in result["nodes"]]
        assert "greeting" in node_ids
        assert "help" in node_ids
        assert "closing" in node_ids

    def test_export_start_node_id_correct(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        assert result["start_node_id"] == "greeting"

    def test_export_node_instruction_format(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")

        assert "instruction" in greeting_node
        assert greeting_node["instruction"]["type"] == "prompt"
        assert "Greet the user warmly" in greeting_node["instruction"]["text"]

    def test_export_node_type(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")
        assert greeting_node["type"] == "conversation"

    def test_export_transitions_become_edges(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")

        assert len(greeting_node["edges"]) == 1
        edge = greeting_node["edges"][0]
        assert edge["destination_node_id"] == "help"
        assert edge["transition_condition"]["type"] == "prompt"
        assert "needs help" in edge["transition_condition"]["prompt"]

    def test_export_edge_has_id(self, three_node_graph):
        result = export_retell_cf(three_node_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")
        assert "id" in greeting_node["edges"][0]

    def test_export_tools_flattened_to_root(self, graph_with_tools):
        result = export_retell_cf(graph_with_tools)
        assert "tools" in result
        tool_names = [t["name"] for t in result["tools"]]
        assert "lookup_user" in tool_names
        # transfer_to_nurse is a transfer_call type, now a node not a tool
        assert "transfer_to_nurse" not in tool_names

    def test_export_tools_deduplicated(self, graph_with_tools):
        result = export_retell_cf(graph_with_tools)
        tool_names = [t["name"] for t in result["tools"]]
        assert tool_names.count("lookup_user") == 1

    def test_export_tool_format(self, graph_with_tools):
        result = export_retell_cf(graph_with_tools)
        lookup_tool = next(t for t in result["tools"] if t["name"] == "lookup_user")

        assert lookup_tool["type"] == "custom"
        assert lookup_tool["description"] == "Look up user in database"
        assert "parameters" in lookup_tool

    def test_export_preserves_metadata(self, graph_with_metadata):
        result = export_retell_cf(graph_with_metadata)
        assert result["conversation_flow_id"] == "cf_test123"
        assert result["version"] == 2
        assert result["model_temperature"] == 0.7
        assert result["start_speaker"] == "agent"

    def test_export_preserves_model_choice(self, graph_with_metadata):
        result = export_retell_cf(graph_with_metadata)
        assert result["model_choice"]["type"] == "cascading"
        assert result["model_choice"]["model"] == "gpt-4.1"

    def test_export_equation_condition_type(self):
        graph = AgentGraph(
            nodes={
                "check": AgentNode(
                    id="check",
                    state_prompt="Check the value.",
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
                    state_prompt="Success!",
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
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        # 11 original conversation nodes + 2 synthesized terminal nodes
        # (end_call and transfer_to_nurse tools become proper CF node types)
        assert len(exported["nodes"]) == 13
        assert exported["conversation_flow_id"] == "cf_healthcare_001"
        # Only 4 custom tools remain (end_call + transfer_call filtered out)
        assert len(exported["tools"]) == 4

    def test_tool_types_preserved(self, sample_retell_config_complex):
        """Custom tool types are preserved; built-in types become nodes, not tools."""
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        tool_types = {t["name"]: t["type"] for t in exported["tools"]}
        # Built-in types should not be in tools array
        assert "end_call" not in tool_types
        assert "transfer_to_nurse" not in tool_types
        # Custom tools remain
        assert tool_types["lookup_patient"] == "custom"

    def test_tools_array_always_present(self, sample_retell_config):
        """Test that tools array is always present even when no tools exist."""
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)
        exported = export_retell_cf(graph)

        assert "tools" in exported
        assert isinstance(exported["tools"], list)

    def test_tool_id_preserved_in_roundtrip(self, sample_retell_config_complex):
        """Test that tool_id is preserved through import/export roundtrip."""
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        tools_by_name = {t["name"]: t for t in exported["tools"]}
        assert tools_by_name["lookup_patient"]["tool_id"] == "tool_lookup_001"
        assert tools_by_name["book_appointment"]["tool_id"] == "tool_book_001"
        # Built-in tools are now nodes, not in the tools array
        assert "end_call" not in tools_by_name
        assert "transfer_to_nurse" not in tools_by_name

    def test_export_tool_includes_tool_id(self):
        """Test that tool_id is included in export when present."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Main node.",
                    tools=[
                        ToolDefinition(
                            name="lookup_user",
                            description="Look up user",
                            tool_id="tool_abc123",
                        ),
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        lookup_tool = next(t for t in result["tools"] if t["name"] == "lookup_user")
        assert lookup_tool["tool_id"] == "tool_abc123"
        # end_call should not be in tools array (it's now a node)
        assert not any(t["name"] == "end_call" for t in result["tools"])

    def test_export_uses_default_model_for_model_choice(self):
        """When model_choice is not in metadata, use graph.default_model."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello.",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell-llm",
            source_metadata={"general_prompt": "Be helpful."},
            default_model="gpt-5.1",
        )

        result = export_retell_cf(graph)
        assert result["model_choice"]["model"] == "gpt-5.1"

    def test_export_begin_message_prepended_to_entry_node(self):
        """begin_message from metadata should be prepended to the entry node instruction."""
        graph = AgentGraph(
            nodes={
                "intro": AgentNode(
                    id="intro",
                    state_prompt="Greet the user.",
                    transitions=[],
                ),
                "other": AgentNode(
                    id="other",
                    state_prompt="Help the user.",
                    transitions=[],
                ),
            },
            entry_node_id="intro",
            source_type="retell-llm",
            source_metadata={"begin_message": "Hello, this is Kate!"},
        )

        result = export_retell_cf(graph)
        intro_node = next(n for n in result["nodes"] if n["id"] == "intro")
        other_node = next(n for n in result["nodes"] if n["id"] == "other")

        assert intro_node["instruction"]["text"].startswith(
            "[Begin message: Hello, this is Kate!]\n\n"
        )
        assert "Begin message" not in other_node["instruction"]["text"]

    def test_export_empty_begin_message_not_prepended(self):
        """Empty begin_message should not be prepended."""
        graph = AgentGraph(
            nodes={
                "intro": AgentNode(
                    id="intro",
                    state_prompt="Greet the user.",
                    transitions=[],
                ),
            },
            entry_node_id="intro",
            source_type="retell-llm",
            source_metadata={"begin_message": ""},
        )

        result = export_retell_cf(graph)
        intro_node = next(n for n in result["nodes"] if n["id"] == "intro")
        assert intro_node["instruction"]["text"] == "Greet the user."

    def test_export_transfer_call_becomes_node_with_required_fields(self):
        """transfer_call tools become nodes with transfer_destination, transfer_option, edge."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Use transfer_to_nurse if needed.",
                    tools=[
                        ToolDefinition(
                            name="transfer_to_nurse",
                            description="Transfer to nurse",
                            type="transfer_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        # Should not be in tools
        assert not any(t["name"] == "transfer_to_nurse" for t in result["tools"])
        # Should be a node
        transfer_nodes = [n for n in result["nodes"] if n["type"] == "transfer_call"]
        assert len(transfer_nodes) == 1
        node = transfer_nodes[0]
        assert "transfer_destination" in node
        assert node["transfer_destination"]["type"] == "predefined"
        assert "transfer_option" in node
        assert node["transfer_option"]["type"] == "cold_transfer"
        # Singular failure edge, not edges array
        assert "edge" in node
        assert "edges" not in node
        assert node["edge"]["transition_condition"]["type"] == "prompt"

    def test_export_end_call_becomes_end_node(self):
        """end_call tools become type=end nodes, not tools."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Help the user. Use end_call when done.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End the call",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        # Should not be in tools
        assert not any(t["name"] == "end_call" for t in result["tools"])
        # Should be a node
        end_nodes = [n for n in result["nodes"] if n["type"] == "end"]
        assert len(end_nodes) == 1

    def test_export_edge_ids_globally_unique(self):
        """Edge IDs must be globally unique across all nodes."""
        graph = AgentGraph(
            nodes={
                "node_a": AgentNode(
                    id="node_a",
                    state_prompt="Node A.",
                    transitions=[
                        Transition(
                            target_node_id="shared_target",
                            condition=TransitionCondition(type="llm_prompt", value="go to shared"),
                        ),
                    ],
                ),
                "node_b": AgentNode(
                    id="node_b",
                    state_prompt="Node B.",
                    transitions=[
                        Transition(
                            target_node_id="shared_target",
                            condition=TransitionCondition(
                                type="llm_prompt", value="also go to shared"
                            ),
                        ),
                    ],
                ),
                "shared_target": AgentNode(
                    id="shared_target",
                    state_prompt="Shared target.",
                    transitions=[],
                ),
            },
            entry_node_id="node_a",
            source_type="test",
        )

        result = export_retell_cf(graph)
        all_edge_ids = [edge["id"] for node in result["nodes"] for edge in node["edges"]]
        assert len(all_edge_ids) == len(set(all_edge_ids)), (
            f"Duplicate edge IDs found: {all_edge_ids}"
        )

    def test_exporter_produces_retell_ui_agent_wrapper(self, three_node_graph):
        """RetellCFExporter.export() wraps CF in agent envelope for Retell UI import."""
        exporter = RetellCFExporter()
        raw = json.loads(exporter.export(three_node_graph))

        assert raw["response_engine"]["type"] == "conversation-flow"
        assert "conversationFlow" in raw
        cf = raw["conversationFlow"]
        assert "nodes" in cf
        assert "start_node_id" in cf
        assert cf["start_node_id"] == "greeting"

    def test_exporter_wrapper_cf_matches_bare_export(self, three_node_graph):
        """The conversationFlow inside the wrapper matches export_retell_cf output."""
        bare = export_retell_cf(three_node_graph)
        wrapped = json.loads(RetellCFExporter().export(three_node_graph))
        cf = wrapped["conversationFlow"]

        assert cf["nodes"] == bare["nodes"]
        assert cf["start_node_id"] == bare["start_node_id"]

    def test_exporter_wrapper_has_no_builtin_tools(self):
        """Built-in tools are now nodes; only custom tools remain in tools array."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Use end_call or transfer_to_nurse as needed.",
                    tools=[
                        ToolDefinition(name="end_call", description="End", type="end_call"),
                        ToolDefinition(
                            name="transfer_to_nurse",
                            description="Transfer",
                            type="transfer_call",
                        ),
                        ToolDefinition(
                            name="lookup",
                            description="Lookup user",
                            type="custom",
                            url="https://api.example.com/lookup",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        bare = export_retell_cf(graph)
        # Only custom tools in the tools array
        assert len(bare["tools"]) == 1
        assert bare["tools"][0]["name"] == "lookup"

        wrapped = json.loads(RetellCFExporter().export(graph))
        cf_tools = wrapped["conversationFlow"]["tools"]
        assert len(cf_tools) == 1
        assert cf_tools[0]["name"] == "lookup"
        assert cf_tools[0]["type"] == "custom"

    def test_agent_envelope_preserved_through_export(self):
        """LLM JSON with voice_id -> import -> CF export -> voice_id in wrapper."""
        from voicetest.importers.retell_llm import RetellLLMImporter

        llm_json = {
            "voice_id": "voice_abc123",
            "language": "en-US",
            "agent_name": "Test Agent",
            "general_prompt": "You are a helpful agent.",
            "model": "gpt-4o",
            "general_tools": [],
            "states": [
                {
                    "name": "main",
                    "state_prompt": "Help the user.",
                    "edges": [],
                    "tools": [],
                },
            ],
        }

        importer = RetellLLMImporter()
        graph = importer.import_agent(llm_json)

        exporter = RetellCFExporter()
        wrapped = json.loads(exporter.export(graph))

        assert wrapped["voice_id"] == "voice_abc123"
        assert wrapped["language"] == "en-US"
        assert wrapped["agent_name"] == "Test Agent"
        assert "conversationFlow" in wrapped

    def test_transfer_without_end_call_failure_edge(self):
        """transfer_call with no end_call -> failure edge points to entry_node_id."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Route the caller. Use transfer_to_nurse if needed.",
                    tools=[
                        ToolDefinition(
                            name="transfer_to_nurse",
                            description="Transfer to nurse",
                            type="transfer_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        result = export_retell_cf(graph)
        transfer_nodes = [n for n in result["nodes"] if n["type"] == "transfer_call"]
        assert len(transfer_nodes) == 1

        # No end node exists, so failure edge should point to entry_node_id
        failure_edge = transfer_nodes[0]["edge"]
        assert failure_edge["destination_node_id"] == "main"


class TestDisplayPosition:
    """Tests for display_position on exported nodes."""

    _PATCH_TARGET = "voicetest.exporters.retell_cf.load_settings"

    def _patch_layout(self, enabled: bool):
        settings = Settings(export={"layout": enabled})
        return patch(self._PATCH_TARGET, return_value=settings)

    def test_nodes_have_display_position(self):
        """Every exported node has display_position with x and y."""
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Node A.",
                    transitions=[
                        Transition(
                            target_node_id="b",
                            condition=TransitionCondition(type="llm_prompt", value="go"),
                        ),
                    ],
                ),
                "b": AgentNode(id="b", state_prompt="Node B.", transitions=[]),
            },
            entry_node_id="a",
            source_type="test",
        )

        with self._patch_layout(True):
            result = export_retell_cf(graph)

        for node in result["nodes"]:
            assert "display_position" in node, f"Node {node['id']} missing display_position"
            assert "x" in node["display_position"]
            assert "y" in node["display_position"]

    def test_entry_node_leftmost(self):
        """Entry node has the smallest x position."""
        graph = AgentGraph(
            nodes={
                "start": AgentNode(
                    id="start",
                    state_prompt="Start.",
                    transitions=[
                        Transition(
                            target_node_id="mid",
                            condition=TransitionCondition(type="llm_prompt", value="go"),
                        ),
                    ],
                ),
                "mid": AgentNode(
                    id="mid",
                    state_prompt="Mid.",
                    transitions=[
                        Transition(
                            target_node_id="end_node",
                            condition=TransitionCondition(type="llm_prompt", value="go"),
                        ),
                    ],
                ),
                "end_node": AgentNode(
                    id="end_node",
                    state_prompt="End.",
                    transitions=[],
                ),
            },
            entry_node_id="start",
            source_type="test",
        )

        with self._patch_layout(True):
            result = export_retell_cf(graph)

        positions = {n["id"]: n["display_position"] for n in result["nodes"]}
        entry_x = positions["start"]["x"]
        for node_id, pos in positions.items():
            assert pos["x"] >= entry_x, f"Node {node_id} has x < entry node"

    def test_preserved_position_wins(self):
        """Node with metadata['display_position'] keeps its value."""
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Node A.",
                    transitions=[],
                    metadata={
                        "retell_type": "conversation",
                        "display_position": {"x": 999, "y": 888},
                    },
                ),
            },
            entry_node_id="a",
            source_type="retell",
        )

        with self._patch_layout(True):
            result = export_retell_cf(graph)

        node_a = next(n for n in result["nodes"] if n["id"] == "a")
        assert node_a["display_position"]["x"] == 999
        assert node_a["display_position"]["y"] == 888

    def test_begin_tag_display_position_present(self):
        """Flow-level begin_tag_display_position is emitted."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(id="main", state_prompt="Main.", transitions=[]),
            },
            entry_node_id="main",
            source_type="test",
        )

        with self._patch_layout(True):
            result = export_retell_cf(graph)

        assert "begin_tag_display_position" in result
        assert "x" in result["begin_tag_display_position"]
        assert "y" in result["begin_tag_display_position"]

    def test_begin_tag_display_position_preserved_from_import(self):
        """begin_tag_display_position from source_metadata is preserved."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(id="main", state_prompt="Main.", transitions=[]),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={
                "begin_tag_display_position": {"x": -200, "y": 50},
            },
        )

        with self._patch_layout(True):
            result = export_retell_cf(graph)

        assert result["begin_tag_display_position"]["x"] == -200
        assert result["begin_tag_display_position"]["y"] == 50

    def test_synthesized_nodes_have_position(self):
        """Synthesized end/transfer nodes get display_position."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Help user. Use end_call when done.",
                    tools=[
                        ToolDefinition(
                            name="end_call",
                            description="End",
                            type="end_call",
                        ),
                    ],
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="test",
        )

        with self._patch_layout(True):
            result = export_retell_cf(graph)

        synth_nodes = [n for n in result["nodes"] if n["id"].startswith("synth_")]
        assert len(synth_nodes) >= 1
        for node in synth_nodes:
            assert "display_position" in node, f"Synthesized node {node['id']} missing position"

    def test_layout_disabled_skips_positions(self):
        """When export.layout is False, no display_position is emitted."""
        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="Node A.", transitions=[]),
            },
            entry_node_id="a",
            source_type="test",
        )

        with self._patch_layout(False):
            result = export_retell_cf(graph)

        for node in result["nodes"]:
            assert "display_position" not in node
        assert "begin_tag_display_position" not in result


class TestLogicSplitExport:
    """Logic split nodes should export with else_edge and structured equations."""

    def test_logic_node_exported_as_logic_split_type(self, logic_split_graph):
        """Logic split nodes should have type=logic_split in the export."""
        result = export_retell_cf(logic_split_graph)
        router = next(n for n in result["nodes"] if n["id"] == "router")
        assert router["type"] == "logic_split"

    def test_else_edge_separate_from_edges(self, logic_split_graph):
        """Always-type transition should be exported as else_edge, not in edges."""
        result = export_retell_cf(logic_split_graph)
        router = next(n for n in result["nodes"] if n["id"] == "router")
        # The always/else transition should be in else_edge
        assert "else_edge" in router
        assert router["else_edge"]["destination_node_id"] == "standard"
        # edges array should only have the equation transitions
        edge_types = [e["transition_condition"]["type"] for e in router["edges"]]
        assert all(t == "equation" for t in edge_types)

    def test_structured_equations_in_edge(self, logic_split_graph):
        """Equation edges should have structured equations array."""
        result = export_retell_cf(logic_split_graph)
        router = next(n for n in result["nodes"] if n["id"] == "router")
        equation_edge = router["edges"][0]
        tc = equation_edge["transition_condition"]
        assert tc["type"] == "equation"
        assert "equations" in tc
        assert len(tc["equations"]) == 1
        eq = tc["equations"][0]
        assert eq["left"] == "account_type"
        assert eq["operator"] == "=="
        assert eq["right"] == "premium"

    def test_equation_edge_no_plain_equation_string(self, logic_split_graph):
        """Equation edges should not have the old 'equation' string key."""
        result = export_retell_cf(logic_split_graph)
        router = next(n for n in result["nodes"] if n["id"] == "router")
        equation_edge = router["edges"][0]
        tc = equation_edge["transition_condition"]
        assert "equation" not in tc

    def test_else_edge_has_retell_format(self, logic_split_graph):
        """else_edge should have proper Retell edge structure."""
        result = export_retell_cf(logic_split_graph)
        router = next(n for n in result["nodes"] if n["id"] == "router")
        else_edge = router["else_edge"]
        assert "id" in else_edge
        assert "destination_node_id" in else_edge

    def test_non_logic_nodes_unchanged(self, logic_split_graph):
        """Non-logic nodes should still export normally."""
        result = export_retell_cf(logic_split_graph)
        greeting = next(n for n in result["nodes"] if n["id"] == "greeting")
        assert greeting["type"] == "conversation"
        assert "else_edge" not in greeting
        # Should have an edge to the router
        assert any(e["destination_node_id"] == "router" for e in greeting["edges"])

    def test_roundtrip_logic_split(self, logic_split_graph):
        """Import → export → re-import preserves logic split structure."""
        exported = export_retell_cf(logic_split_graph)
        # Re-import the exported data
        importer = RetellImporter()
        reimported = importer.import_agent(exported)
        router = reimported.nodes["router"]
        assert router.is_logic_node()
        # Equation transition preserved
        eq_transitions = [t for t in router.transitions if t.condition.type == "equation"]
        assert len(eq_transitions) == 1
        assert eq_transitions[0].condition.equations[0].left == "account_type"
        # Always transition preserved
        always_transitions = [t for t in router.transitions if t.condition.type == "always"]
        assert len(always_transitions) == 1
        assert always_transitions[0].target_node_id == "standard"


class TestExportAlwaysEdge:
    """Tests for exporting always_edge on conversation nodes."""

    def test_always_transition_exported_as_always_edge(self):
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Say goodbye.",
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
            entry_node_id="main",
            source_type="retell",
        )
        result = export_retell_cf(graph)
        main = _find_node(result["nodes"], "main")
        assert "always_edge" in main
        assert main["always_edge"]["destination_node_id"] == "end"
        assert main["edges"] == []

    def test_always_edge_not_on_logic_nodes(self):
        """Logic nodes use else_edge, not always_edge."""
        from voicetest.models.agent import EquationClause

        graph = AgentGraph(
            nodes={
                "router": AgentNode(
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
                    metadata={"retell_type": "logic_split"},
                ),
                "a": AgentNode(id="a", state_prompt="A.", transitions=[]),
                "b": AgentNode(id="b", state_prompt="B.", transitions=[]),
            },
            entry_node_id="router",
            source_type="retell",
        )
        result = export_retell_cf(graph)
        router = _find_node(result["nodes"], "router")
        assert "else_edge" in router
        assert "always_edge" not in router


class TestExportExtractNodes:
    """Tests for exporting extract_dynamic_variables nodes."""

    @pytest.fixture
    def extract_graph(self):
        from voicetest.models.agent import EquationClause
        from voicetest.models.agent import VariableExtraction

        return AgentGraph(
            nodes={
                "ask_dob": AgentNode(
                    id="ask_dob",
                    state_prompt="Ask for date of birth.",
                    transitions=[
                        Transition(
                            target_node_id="extract_dob",
                            condition=TransitionCondition(
                                type="llm_prompt", value="Patient gave DOB"
                            ),
                        ),
                    ],
                ),
                "extract_dob": AgentNode(
                    id="extract_dob",
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
                        ),
                    ],
                    transitions=[
                        Transition(
                            target_node_id="match",
                            condition=TransitionCondition(
                                type="equation",
                                value="dob_month == January AND dob_year == 1990",
                                logical_operator="and",
                                equations=[
                                    EquationClause(
                                        left="dob_month", operator="==", right="January"
                                    ),
                                    EquationClause(left="dob_year", operator="==", right="1990"),
                                ],
                            ),
                        ),
                        Transition(
                            target_node_id="no_match",
                            condition=TransitionCondition(type="always", value="Else"),
                        ),
                    ],
                    metadata={
                        "retell_type": "extract_dynamic_variables",
                        "name": "Extract DOB",
                    },
                ),
                "match": AgentNode(id="match", state_prompt="Verified.", transitions=[]),
                "no_match": AgentNode(id="no_match", state_prompt="Not verified.", transitions=[]),
            },
            entry_node_id="ask_dob",
            source_type="retell",
        )

    def test_extract_node_exports_as_extract_type(self, extract_graph):
        result = export_retell_cf(extract_graph)
        extract_node = _find_node(result["nodes"], "extract_dob")
        assert extract_node["type"] == "extract_dynamic_variables"

    def test_extract_node_exports_variables(self, extract_graph):
        result = export_retell_cf(extract_graph)
        extract_node = _find_node(result["nodes"], "extract_dob")
        assert "variables" in extract_node
        assert len(extract_node["variables"]) == 2
        assert extract_node["variables"][0]["name"] == "dob_month"
        assert extract_node["variables"][0]["description"] == "The month of birth"
        assert extract_node["variables"][0]["type"] == "string"
        assert extract_node["variables"][0]["choices"] == ["January", "February"]
        assert extract_node["variables"][1]["name"] == "dob_year"

    def test_extract_node_preserves_equations(self, extract_graph):
        result = export_retell_cf(extract_graph)
        extract_node = _find_node(result["nodes"], "extract_dob")
        assert len(extract_node["edges"]) == 1
        tc = extract_node["edges"][0]["transition_condition"]
        assert tc["type"] == "equation"
        assert len(tc["equations"]) == 2

    def test_extract_node_preserves_else_edge(self, extract_graph):
        result = export_retell_cf(extract_graph)
        extract_node = _find_node(result["nodes"], "extract_dob")
        assert "else_edge" in extract_node
        assert extract_node["else_edge"]["destination_node_id"] == "no_match"


class TestExportLogicalOperator:
    """Tests for exporting logical_operator as Retell operator field."""

    @pytest.fixture
    def graph_with_or(self):
        from voicetest.models.agent import EquationClause

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
                    metadata={"retell_type": "logic_split"},
                ),
                "match": AgentNode(id="match", state_prompt="M.", transitions=[]),
                "fallback": AgentNode(id="fallback", state_prompt="F.", transitions=[]),
            },
            entry_node_id="router",
            source_type="retell",
        )

    def test_or_operator_exported(self, graph_with_or):
        result = export_retell_cf(graph_with_or)
        router = _find_node(result["nodes"], "router")
        tc = router["edges"][0]["transition_condition"]
        assert tc["operator"] == "||"

    def test_and_operator_exported(self):
        from voicetest.models.agent import EquationClause

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
                    metadata={"retell_type": "logic_split"},
                ),
                "match": AgentNode(id="match", state_prompt="M.", transitions=[]),
                "fallback": AgentNode(id="fallback", state_prompt="F.", transitions=[]),
            },
            entry_node_id="router",
            source_type="retell",
        )
        result = export_retell_cf(graph)
        router = _find_node(result["nodes"], "router")
        tc = router["edges"][0]["transition_condition"]
        assert tc["operator"] == "&&"
