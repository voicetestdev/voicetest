"""Tests for voicetest.exporters.retell_cf module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


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
        assert "transfer_to_nurse" in tool_names

    def test_export_tools_deduplicated(self, graph_with_tools):
        from voicetest.exporters.retell_cf import export_retell_cf

        result = export_retell_cf(graph_with_tools)
        tool_names = [t["name"] for t in result["tools"]]
        assert tool_names.count("transfer_to_nurse") == 1

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
        from voicetest.exporters.retell_cf import export_retell_cf
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        assert len(exported["nodes"]) == 11
        assert exported["conversation_flow_id"] == "cf_healthcare_001"
        # 4 custom tools + 1 end_call + 1 transfer_call
        assert len(exported["tools"]) == 6

    def test_tool_types_preserved(self, sample_retell_config_complex):
        """Test that tool types are preserved including built-in actions."""
        from voicetest.exporters.retell_cf import export_retell_cf
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        tool_types = {t["name"]: t["type"] for t in exported["tools"]}
        assert tool_types["end_call"] == "end_call"
        assert tool_types["transfer_to_nurse"] == "transfer_call"
        assert tool_types["lookup_patient"] == "custom"

    def test_tools_array_always_present(self, sample_retell_config):
        """Test that tools array is always present even when no tools exist."""
        from voicetest.exporters.retell_cf import export_retell_cf
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)
        exported = export_retell_cf(graph)

        assert "tools" in exported
        assert isinstance(exported["tools"], list)

    def test_tool_id_preserved_in_roundtrip(self, sample_retell_config_complex):
        """Test that tool_id is preserved through import/export roundtrip."""
        from voicetest.exporters.retell_cf import export_retell_cf
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)
        exported = export_retell_cf(graph)

        tools_by_name = {t["name"]: t for t in exported["tools"]}
        assert tools_by_name["lookup_patient"]["tool_id"] == "tool_lookup_001"
        assert tools_by_name["book_appointment"]["tool_id"] == "tool_book_001"
        # Built-in tools should not have tool_id
        assert "tool_id" not in tools_by_name["end_call"]
        assert "tool_id" not in tools_by_name["transfer_to_nurse"]

    def test_export_tool_includes_tool_id(self):
        """Test that tool_id is included in export when present."""
        from voicetest.exporters.retell_cf import export_retell_cf

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

        end_tool = next(t for t in result["tools"] if t["name"] == "end_call")
        assert "tool_id" not in end_tool

    def test_export_uses_default_model_for_model_choice(self):
        """When model_choice is not in metadata, use graph.default_model."""
        from voicetest.exporters.retell_cf import export_retell_cf

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
        from voicetest.exporters.retell_cf import export_retell_cf

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
        from voicetest.exporters.retell_cf import export_retell_cf

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
