"""Tests for voicetest.exporters.bland module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition


class TestBlandExporter:
    """Tests for Bland AI inbound config exporter."""

    def test_export_returns_dict(self, sample_graph):
        from voicetest.exporters.bland import export_bland_config

        result = export_bland_config(sample_graph)
        assert isinstance(result, dict)

    def test_export_has_prompt(self, sample_graph):
        from voicetest.exporters.bland import export_bland_config

        result = export_bland_config(sample_graph)
        assert "prompt" in result

    def test_export_prompt_from_entry_node(self, sample_graph):
        from voicetest.exporters.bland import export_bland_config

        result = export_bland_config(sample_graph)
        assert result["prompt"] == "You are a helpful assistant."

    def test_export_tools_converted(self, sample_graph_with_tools):
        from voicetest.exporters.bland import export_bland_config

        result = export_bland_config(sample_graph_with_tools)

        assert "tools" in result
        assert len(result["tools"]) == 1
        assert result["tools"][0]["name"] == "get_info"
        assert result["tools"][0]["description"] == "Get information"

    def test_export_tool_parameters(self, sample_graph_with_tools):
        from voicetest.exporters.bland import export_bland_config

        result = export_bland_config(sample_graph_with_tools)

        tool = result["tools"][0]
        assert "input_schema" in tool
        assert tool["input_schema"]["type"] == "object"

    def test_export_preserves_source_metadata(self, sample_graph_with_metadata):
        from voicetest.exporters.bland import export_bland_config

        result = export_bland_config(sample_graph_with_metadata)

        assert result["phone_number"] == "+1234567890"
        assert result["voice_id"] == 1
        assert result["first_sentence"] == "Hello!"
        assert result["max_duration"] == 900

    def test_export_empty_graph(self):
        from voicetest.exporters.bland import export_bland_config

        graph = AgentGraph(
            nodes={},
            entry_node_id="",
            source_type="test",
            source_metadata={},
        )

        result = export_bland_config(graph)
        assert isinstance(result, dict)
        # Empty graph should have empty or no prompt
        assert "prompt" not in result or result.get("prompt") in (None, "")

    def test_export_node_metadata_first_sentence(self):
        from voicetest.exporters.bland import export_bland_config

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    tools=[],
                    transitions=[],
                    metadata={"first_sentence": "Hi there!"},
                )
            },
            entry_node_id="main",
            source_type="test",
            source_metadata={},
        )

        result = export_bland_config(graph)
        assert result["first_sentence"] == "Hi there!"

    def test_roundtrip_import_export(self, sample_bland_config):
        from voicetest.exporters.bland import export_bland_config
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        graph = importer.import_agent(sample_bland_config)
        exported = export_bland_config(graph)

        # Verify key fields are preserved
        assert exported["prompt"] == sample_bland_config["prompt"]
        assert exported["phone_number"] == sample_bland_config["phone_number"]
        assert exported["voice_id"] == sample_bland_config["voice_id"]
        assert exported["first_sentence"] == sample_bland_config["first_sentence"]

        # Tools should also be preserved
        assert len(exported["tools"]) == len(sample_bland_config["tools"])
        assert exported["tools"][0]["name"] == sample_bland_config["tools"][0]["name"]


@pytest.fixture
def sample_graph():
    """Sample AgentGraph for testing."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant.",
                tools=[],
                transitions=[],
                metadata={},
            )
        },
        entry_node_id="main",
        source_type="test",
        source_metadata={},
    )


@pytest.fixture
def sample_graph_with_tools():
    """Sample AgentGraph with tools for testing."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="You are a helpful assistant.",
                tools=[
                    ToolDefinition(
                        name="get_info",
                        description="Get information",
                        parameters={
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                        },
                    )
                ],
                transitions=[],
                metadata={},
            )
        },
        entry_node_id="main",
        source_type="test",
        source_metadata={},
    )


@pytest.fixture
def sample_graph_with_metadata():
    """Sample AgentGraph with source metadata for testing."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="Hello",
                tools=[],
                transitions=[],
                metadata={},
            )
        },
        entry_node_id="main",
        source_type="bland",
        source_metadata={
            "phone_number": "+1234567890",
            "voice_id": 1,
            "first_sentence": "Hello!",
            "max_duration": 900,
            "webhook": "https://example.com",
            "record": True,
        },
    )


@pytest.fixture
def sample_bland_config():
    """Sample Bland AI inbound config for testing."""
    return {
        "phone_number": "+1234567890",
        "prompt": "You are a friendly customer service representative.",
        "voice_id": 1,
        "first_sentence": "Hello! How can I help you?",
        "max_duration": 900,
        "tools": [
            {
                "name": "check_order",
                "description": "Check order status",
                "input_schema": {
                    "type": "object",
                    "properties": {"order_id": {"type": "string"}},
                },
            },
        ],
    }
