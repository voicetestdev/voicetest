"""Tests for voicetest.exporters.vapi module."""

from voicetest.exporters.vapi import export_vapi_assistant
from voicetest.exporters.vapi import export_vapi_squad
from voicetest.importers.vapi import VapiImporter
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition


class TestVAPISquadBasic:
    """Baseline squad export tests."""

    def test_squad_has_members(self, simple_graph):
        result = export_vapi_squad(simple_graph)
        assert len(result["members"]) == 2

    def test_squad_entry_node_first(self, simple_graph):
        result = export_vapi_squad(simple_graph)
        assert result["members"][0]["assistant"]["name"] == "greeting"

    def test_handoff_tool_created(self, simple_graph):
        result = export_vapi_squad(simple_graph)
        greeting_tools = result["members"][0]["assistant"]["model"]["tools"]
        handoff = next(t for t in greeting_tools if t["type"] == "handoff")
        assert handoff["destinations"][0]["assistantName"] == "farewell"


class TestVAPISquadLogicSplit:
    """Logic split nodes should be skipped in squad export.

    When a logic split node sits between conversation nodes, the squad
    exporter should wire predecessors directly to successors using
    the equation conditions as handoff descriptions.
    """

    def test_logic_node_excluded_from_members(self, logic_split_graph):
        """Logic split nodes should not appear as squad members."""
        result = export_vapi_squad(logic_split_graph)
        member_names = [m["assistant"]["name"] for m in result["members"]]
        assert "router" not in member_names

    def test_predecessor_gets_direct_handoffs(self, logic_split_graph):
        """Greeting node should handoff directly to premium/standard."""
        result = export_vapi_squad(logic_split_graph)
        greeting = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        tools = greeting["assistant"]["model"]["tools"]
        handoff = next(t for t in tools if t["type"] == "handoff")
        dest_names = {d["assistantName"] for d in handoff["destinations"]}
        assert dest_names == {"premium", "standard"}

    def test_equation_condition_in_handoff_description(self, logic_split_graph):
        """Equation conditions become handoff descriptions."""
        result = export_vapi_squad(logic_split_graph)
        greeting = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        tools = greeting["assistant"]["model"]["tools"]
        handoff = next(t for t in tools if t["type"] == "handoff")
        premium_dest = next(d for d in handoff["destinations"] if d["assistantName"] == "premium")
        assert "account_type" in premium_dest["description"]
        assert "premium" in premium_dest["description"]

    def test_else_condition_in_handoff_description(self, logic_split_graph):
        """Always/else conditions get a readable fallback description."""
        result = export_vapi_squad(logic_split_graph)
        greeting = next(m for m in result["members"] if m["assistant"]["name"] == "greeting")
        tools = greeting["assistant"]["model"]["tools"]
        handoff = next(t for t in tools if t["type"] == "handoff")
        standard_dest = next(d for d in handoff["destinations"] if d["assistantName"] == "standard")
        # Should indicate this is a fallback/else path
        assert (
            "else" in standard_dest["description"].lower()
            or "fallback" in standard_dest["description"].lower()
        )

    def test_total_member_count(self, logic_split_graph):
        """Should have 4 members (greeting, premium, standard, farewell)."""
        result = export_vapi_squad(logic_split_graph)
        assert len(result["members"]) == 4


class TestVAPIAssistantLogicSplit:
    """Logic split nodes should be omitted from merged assistant prompt."""

    def test_logic_node_prompt_excluded(self, logic_split_graph):
        """Empty logic node prompts shouldn't add blank lines to output."""
        result = export_vapi_assistant(logic_split_graph)
        # The assistant format merges all nodes into one — logic node
        # has empty state_prompt so it shouldn't add noise
        model_messages = result["model"]["messages"]
        system_content = model_messages[0]["content"]
        # Should not have consecutive blank lines from empty logic node
        assert "\n\n\n" not in system_content


class TestVapiExporterBasic:
    """Test basic VAPI export functionality."""

    def test_export_single_node(self):
        """Export a simple single-node graph."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="You are a helpful assistant.",
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
        """Export graph with tools (tools go inside model config for VAPI)."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="You are a helpful assistant.",
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

        # Tools are inside model config for VAPI
        assert "tools" in result["model"]
        assert len(result["model"]["tools"]) == 1
        assert result["model"]["tools"][0]["type"] == "function"
        assert result["model"]["tools"][0]["function"]["name"] == "get_weather"
        assert result["model"]["tools"][0]["function"]["description"] == "Get current weather"
        assert "parameters" in result["model"]["tools"][0]["function"]

    def test_export_preserves_metadata(self):
        """Export preserves source metadata."""
        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="You are a helpful assistant.",
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

    def test_export_multi_node_tools_per_member(self):
        """Each squad member keeps its own tools."""
        graph = AgentGraph(
            nodes={
                "node1": AgentNode(
                    id="node1",
                    state_prompt="Node 1",
                    tools=[ToolDefinition(name="tool1", description="Tool 1", parameters={})],
                    transitions=[],
                ),
                "node2": AgentNode(
                    id="node2",
                    state_prompt="Node 2",
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

        # Tools count matches (tools are inside model config for VAPI)
        exported_tools = exported["model"].get("tools", [])
        original_tools = sample_vapi_assistant.get("tools", [])
        assert len(exported_tools) == len(original_tools)

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
        # Tools are inside model config for VAPI
        exported_tools = exported["model"].get("tools", [])
        exported_tool_names = {t["function"]["name"] for t in exported_tools}

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
