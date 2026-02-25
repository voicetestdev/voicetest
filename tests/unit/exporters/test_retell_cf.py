"""Tests for voicetest.exporters.retell_cf module."""

import json

import pytest

from voicetest.exporters.retell_cf import RetellCFExporter
from voicetest.exporters.retell_cf import export_retell_cf
from voicetest.importers.retell import RetellImporter
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


def _find_node(nodes: list[dict], node_id: str) -> dict | None:
    """Find a node by ID in a CF nodes list."""
    return next((n for n in nodes if n["id"] == node_id), None)


@pytest.fixture
def simple_graph() -> AgentGraph:
    """Create a simple agent graph for testing."""
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user warmly.",
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
                state_prompt="Help the user with their request.",
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
                state_prompt="Thank the user and end the conversation.",
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

    def test_export_returns_dict(self, simple_graph):
        result = export_retell_cf(simple_graph)
        assert isinstance(result, dict)

    def test_export_has_required_fields(self, simple_graph):
        result = export_retell_cf(simple_graph)
        assert "start_node_id" in result
        assert "nodes" in result

    def test_export_creates_nodes(self, simple_graph):
        result = export_retell_cf(simple_graph)
        assert len(result["nodes"]) == 3

        node_ids = [n["id"] for n in result["nodes"]]
        assert "greeting" in node_ids
        assert "help" in node_ids
        assert "closing" in node_ids

    def test_export_start_node_id_correct(self, simple_graph):
        result = export_retell_cf(simple_graph)
        assert result["start_node_id"] == "greeting"

    def test_export_node_instruction_format(self, simple_graph):
        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")

        assert "instruction" in greeting_node
        assert greeting_node["instruction"]["type"] == "prompt"
        assert "Greet the user warmly" in greeting_node["instruction"]["text"]

    def test_export_node_type(self, simple_graph):
        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")
        assert greeting_node["type"] == "conversation"

    def test_export_transitions_become_edges(self, simple_graph):
        result = export_retell_cf(simple_graph)
        greeting_node = next(n for n in result["nodes"] if n["id"] == "greeting")

        assert len(greeting_node["edges"]) == 1
        edge = greeting_node["edges"][0]
        assert edge["destination_node_id"] == "help"
        assert edge["transition_condition"]["type"] == "prompt"
        assert "needs help" in edge["transition_condition"]["prompt"]

    def test_export_edge_has_id(self, simple_graph):
        result = export_retell_cf(simple_graph)
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

    def test_exporter_produces_retell_ui_agent_wrapper(self, simple_graph):
        """RetellCFExporter.export() wraps CF in agent envelope for Retell UI import."""
        exporter = RetellCFExporter()
        raw = json.loads(exporter.export(simple_graph))

        assert raw["response_engine"]["type"] == "conversation-flow"
        assert "conversationFlow" in raw
        cf = raw["conversationFlow"]
        assert "nodes" in cf
        assert "start_node_id" in cf
        assert cf["start_node_id"] == "greeting"

    def test_exporter_wrapper_cf_matches_bare_export(self, simple_graph):
        """The conversationFlow inside the wrapper matches export_retell_cf output."""
        bare = export_retell_cf(simple_graph)
        wrapped = json.loads(RetellCFExporter().export(simple_graph))
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
