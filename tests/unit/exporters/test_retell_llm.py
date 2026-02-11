"""Tests for voicetest.exporters.retell_llm module."""

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
                state_prompt="Greet the user.",
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
                state_prompt="Look up the user's account.",
                tools=[lookup_tool, end_call_tool],
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="test",
    )


@pytest.fixture
def graph_with_metadata() -> AgentGraph:
    """Create an agent graph with source metadata."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="retell-llm",
        source_metadata={
            "llm_id": "llm_test123",
            "model": "gpt-4o",
            "begin_message": "Hello! How can I help?",
        },
    )


class TestRetellLLMExporter:
    """Tests for Retell LLM exporter."""

    def test_export_returns_dict(self, simple_graph):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(simple_graph)
        assert isinstance(result, dict)

    def test_export_has_required_fields(self, simple_graph):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(simple_graph)
        assert "general_prompt" in result
        assert "states" in result

    def test_export_creates_states_from_nodes(self, simple_graph):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(simple_graph)
        assert len(result["states"]) == 3

        state_names = [s["name"] for s in result["states"]]
        assert "greeting" in state_names
        assert "help" in state_names
        assert "closing" in state_names

    def test_export_entry_node_is_first_state(self, simple_graph):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(simple_graph)
        assert result["states"][0]["name"] == "greeting"

    def test_export_state_prompt_contains_instructions(self, simple_graph):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(simple_graph)
        greeting_state = next(s for s in result["states"] if s["name"] == "greeting")
        assert "Greet the user warmly" in greeting_state["state_prompt"]

    def test_export_transitions_become_edges(self, simple_graph):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(simple_graph)
        greeting_state = next(s for s in result["states"] if s["name"] == "greeting")
        assert len(greeting_state["edges"]) == 1
        assert greeting_state["edges"][0]["destination_state_name"] == "help"
        assert "needs help" in greeting_state["edges"][0]["description"]

    def test_export_tools_become_state_tools(self, graph_with_tools):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(graph_with_tools)
        lookup_state = next(s for s in result["states"] if s["name"] == "lookup")
        assert len(lookup_state["tools"]) == 1

        tool_names = [t["name"] for t in lookup_state["tools"]]
        assert "lookup_user" in tool_names

    def test_export_tool_parameters_preserved(self, graph_with_tools):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(graph_with_tools)
        lookup_state = next(s for s in result["states"] if s["name"] == "lookup")
        lookup_tool = next(t for t in lookup_state["tools"] if t["name"] == "lookup_user")

        assert lookup_tool["parameters"]["type"] == "object"
        assert "user_id" in lookup_tool["parameters"]["properties"]

    def test_export_preserves_metadata(self, graph_with_metadata):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(graph_with_metadata)
        assert result["llm_id"] == "llm_test123"
        assert result["model"] == "gpt-4o"
        assert result["begin_message"] == "Hello! How can I help?"

    def test_export_single_node_no_states(self, graph_with_metadata):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(graph_with_metadata)
        assert len(result["states"]) == 1
        assert result["states"][0]["name"] == "main"

    def test_export_general_tools_extracted(self, graph_with_tools):
        from voicetest.exporters.retell_llm import export_retell_llm

        result = export_retell_llm(graph_with_tools)
        general_tool_names = [t["name"] for t in result.get("general_tools", [])]
        assert "end_call" in general_tool_names

    def test_roundtrip_import_export(self, sample_retell_llm_config):
        from voicetest.exporters.retell_llm import export_retell_llm
        from voicetest.importers.retell_llm import RetellLLMImporter

        importer = RetellLLMImporter()
        graph = importer.import_agent(sample_retell_llm_config)
        exported = export_retell_llm(graph)

        assert len(exported["states"]) == 5
        assert exported["llm_id"] == "llm_abc123def456"
        assert exported["model"] == "gpt-4o"
