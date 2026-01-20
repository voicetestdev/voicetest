"""Tests for the VAPI exporter."""

from voicetest.exporters.vapi import export_vapi_assistant, export_vapi_squad
from voicetest.importers.vapi import VapiImporter
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
    Transition,
    TransitionCondition,
)


class TestVapiExporterBasic:
    """Test basic VAPI export functionality."""

    def test_export_single_node(self):
        """Export a simple single-node graph."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    instructions="You are a helpful assistant.",
                    tools=[],
                    transitions=[],
                )
            },
            entry_node_id="main",
            source_type="custom",
            source_metadata={},
        )

        result = export_vapi_assistant(graph)

        assert "model" in result
        assert result["model"]["messages"][0]["role"] == "system"
        assert result["model"]["messages"][0]["content"] == "You are a helpful assistant."

    def test_export_with_tools(self):
        """Export graph with tools."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    instructions="You are a helpful assistant.",
                    tools=[
                        ToolDefinition(
                            name="get_weather",
                            description="Get current weather",
                            parameters={
                                "type": "object",
                                "properties": {"location": {"type": "string"}},
                                "required": ["location"],
                            },
                        )
                    ],
                    transitions=[],
                )
            },
            entry_node_id="main",
            source_type="custom",
            source_metadata={},
        )

        result = export_vapi_assistant(graph)

        assert "tools" in result
        assert len(result["tools"]) == 1
        assert result["tools"][0]["type"] == "function"
        assert result["tools"][0]["function"]["name"] == "get_weather"
        assert result["tools"][0]["function"]["description"] == "Get current weather"
        assert "parameters" in result["tools"][0]["function"]

    def test_export_preserves_metadata(self):
        """Export preserves source metadata."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    instructions="You are a helpful assistant.",
                    tools=[],
                    transitions=[],
                )
            },
            entry_node_id="main",
            source_type="vapi",
            source_metadata={
                "assistant_id": "asst_123",
                "name": "Test Assistant",
                "first_message": "Hello!",
                "model_provider": "openai",
                "model": "gpt-4o",
                "temperature": 0.7,
                "voice_provider": "11labs",
                "voice_id": "sarah",
                "transcriber_provider": "deepgram",
                "transcriber_model": "nova-2",
                "transcriber_language": "en",
            },
        )

        result = export_vapi_assistant(graph)

        assert result.get("id") == "asst_123"
        assert result.get("name") == "Test Assistant"
        assert result.get("firstMessage") == "Hello!"
        assert result["model"]["provider"] == "openai"
        assert result["model"]["model"] == "gpt-4o"
        assert result["model"]["temperature"] == 0.7
        assert result["voice"]["provider"] == "11labs"
        assert result["voice"]["voiceId"] == "sarah"
        assert result["transcriber"]["provider"] == "deepgram"
        assert result["transcriber"]["model"] == "nova-2"


class TestVapiExporterMultiNode:
    """Test VAPI export with multi-node graphs (exports as squad)."""

    def test_export_multi_node_creates_squad(self):
        """Multi-node graphs export as squads with separate assistants."""
        graph = AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    instructions="Greet the user warmly.",
                    tools=[],
                    transitions=[],
                ),
                "help": AgentNode(
                    id="help",
                    instructions="Provide helpful assistance.",
                    tools=[],
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="retell-llm",
            source_metadata={},
        )

        result = export_vapi_squad(graph)

        # Should export as squad
        assert "members" in result
        assert len(result["members"]) == 2

        # Each assistant has its own instructions
        greeting_member = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        help_member = next(m for m in result["members"] if m["assistant"]["name"] == "help")

        greeting_content = greeting_member["assistant"]["model"]["messages"][0]["content"]
        help_content = help_member["assistant"]["model"]["messages"][0]["content"]

        assert "Greet the user warmly" in greeting_content
        assert "Provide helpful assistance" in help_content

    def test_export_multi_node_tools_per_member(self):
        """Each squad member keeps its own tools."""
        graph = AgentGraph(
            nodes={
                "node1": AgentNode(
                    id="node1",
                    instructions="Node 1",
                    tools=[ToolDefinition(name="tool1", description="Tool 1", parameters={})],
                    transitions=[],
                ),
                "node2": AgentNode(
                    id="node2",
                    instructions="Node 2",
                    tools=[ToolDefinition(name="tool2", description="Tool 2", parameters={})],
                    transitions=[],
                ),
            },
            entry_node_id="node1",
            source_type="custom",
            source_metadata={},
        )

        result = export_vapi_squad(graph)

        node1_member = next(m for m in result["members"] if m["assistant"]["name"] == "node1")
        node2_member = next(m for m in result["members"] if m["assistant"]["name"] == "node2")

        node1_tools = node1_member["assistant"]["model"].get("tools", [])
        node2_tools = node2_member["assistant"]["model"].get("tools", [])

        node1_tool_names = {t["function"]["name"] for t in node1_tools if t.get("function")}
        node2_tool_names = {t["function"]["name"] for t in node2_tools if t.get("function")}

        assert "tool1" in node1_tool_names
        assert "tool2" in node2_tool_names

    def test_export_entry_node_first(self):
        """Entry node is first member in squad."""
        graph = AgentGraph(
            nodes={
                "node1": AgentNode(
                    id="node1",
                    instructions="Node 1",
                    tools=[],
                    transitions=[],
                ),
                "entry": AgentNode(
                    id="entry",
                    instructions="Entry node",
                    tools=[],
                    transitions=[],
                ),
            },
            entry_node_id="entry",
            source_type="custom",
            source_metadata={},
        )

        result = export_vapi_squad(graph)

        first_member = result["members"][0]["assistant"]
        assert first_member["name"] == "entry"


class TestVapiSquadExport:
    """Test VAPI squad export."""

    def test_export_multi_node_as_squad(self):
        """Multi-node graphs export as squads."""
        graph = AgentGraph(
            nodes={
                "greeting": AgentNode(
                    id="greeting",
                    instructions="Greet the user.",
                    tools=[],
                    transitions=[
                        Transition(
                            target_node_id="help",
                            condition=TransitionCondition(
                                type="llm_prompt", value="User needs help"
                            ),
                            description="User needs help",
                        )
                    ],
                ),
                "help": AgentNode(
                    id="help",
                    instructions="Help the user.",
                    tools=[],
                    transitions=[],
                ),
            },
            entry_node_id="greeting",
            source_type="custom",
            source_metadata={},
        )

        result = export_vapi_squad(graph)

        assert "members" in result
        assert len(result["members"]) == 2

        # First member should be entry node
        first_member = result["members"][0]["assistant"]
        assert first_member["name"] == "greeting"

    def test_export_squad_handoff_tools(self):
        """Transitions become handoff tools in squad export."""
        graph = AgentGraph(
            nodes={
                "node1": AgentNode(
                    id="node1",
                    instructions="Node 1",
                    tools=[],
                    transitions=[
                        Transition(
                            target_node_id="node2",
                            condition=TransitionCondition(type="llm_prompt", value="Go to node2"),
                            description="Transfer to node2",
                        )
                    ],
                ),
                "node2": AgentNode(
                    id="node2",
                    instructions="Node 2",
                    tools=[],
                    transitions=[],
                ),
            },
            entry_node_id="node1",
            source_type="custom",
            source_metadata={},
        )

        result = export_vapi_squad(graph)

        node1_member = result["members"][0]["assistant"]
        tools = node1_member["model"].get("tools", [])

        handoff_tools = [t for t in tools if t.get("type") == "handoff"]
        assert len(handoff_tools) == 1
        assert handoff_tools[0]["destinations"][0]["assistantName"] == "node2"


class TestVapiRoundTrip:
    """Test import -> export round trip."""

    def test_roundtrip_preserves_structure(self, sample_vapi_assistant: dict):
        """Import and export preserves essential structure."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)
        exported = export_vapi_assistant(graph)

        # Key fields preserved
        assert exported.get("id") == sample_vapi_assistant.get("id")
        assert exported.get("name") == sample_vapi_assistant.get("name")
        assert exported.get("firstMessage") == sample_vapi_assistant.get("firstMessage")

        # Model config preserved
        assert exported["model"]["provider"] == sample_vapi_assistant["model"]["provider"]
        assert exported["model"]["model"] == sample_vapi_assistant["model"]["model"]

        # Tools count matches
        assert len(exported.get("tools", [])) == len(sample_vapi_assistant.get("tools", []))

    def test_roundtrip_preserves_tools(self, sample_vapi_assistant: dict):
        """Tool definitions are preserved through round trip."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant)
        exported = export_vapi_assistant(graph)

        original_tool_names = {
            t["function"]["name"]
            for t in sample_vapi_assistant.get("tools", [])
            if t.get("function")
        }
        exported_tool_names = {t["function"]["name"] for t in exported.get("tools", [])}

        assert original_tool_names == exported_tool_names

    def test_roundtrip_simple_assistant(self, sample_vapi_assistant_simple: dict):
        """Simple assistant round trip works."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_assistant_simple)
        exported = export_vapi_assistant(graph)

        assert exported.get("name") == sample_vapi_assistant_simple.get("name")
        assert "tools" not in exported or len(exported["tools"]) == 0

    def test_roundtrip_squad(self, sample_vapi_squad: dict):
        """Squad round trip preserves structure."""
        importer = VapiImporter()
        graph = importer.import_agent(sample_vapi_squad)
        exported = export_vapi_squad(graph)

        # Should export as squad
        assert "members" in exported
        assert len(exported["members"]) == 5

        # Metadata preserved
        assert exported.get("id") == sample_vapi_squad.get("id")
        assert exported.get("name") == sample_vapi_squad.get("name")

        # Member names match
        original_names = {m["assistant"]["name"] for m in sample_vapi_squad["members"]}
        exported_names = {m["assistant"]["name"] for m in exported["members"]}
        assert original_names == exported_names
