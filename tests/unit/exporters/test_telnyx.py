"""Tests for voicetest.exporters.telnyx module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


class TestTelnyxExporter:
    """Tests for Telnyx AI assistant exporter."""

    def test_export_returns_dict(self, sample_graph):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph)
        assert isinstance(result, dict)

    def test_export_has_instructions(self, sample_graph):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph)
        assert "instructions" in result

    def test_export_instructions_from_entry_node(self, sample_graph):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph)
        assert result["instructions"] == "You are a helpful assistant."

    def test_export_tools_converted(self, sample_graph_with_tools):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph_with_tools)

        assert "tools" in result
        assert len(result["tools"]) == 1
        assert result["tools"][0]["type"] == "webhook"
        assert result["tools"][0]["webhook"]["name"] == "get_info"
        assert result["tools"][0]["webhook"]["description"] == "Get information"

    def test_export_webhook_tool_url(self, sample_graph_with_tools):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph_with_tools)

        webhook = result["tools"][0]["webhook"]
        assert webhook["url"] == "https://api.example.com/info"

    def test_export_webhook_parameters_as_body(self, sample_graph_with_tools):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph_with_tools)

        webhook = result["tools"][0]["webhook"]
        assert "body_parameters" in webhook
        assert webhook["body_parameters"]["type"] == "object"

    def test_export_preserves_source_metadata(self, sample_graph_with_metadata):
        from voicetest.exporters.telnyx import export_telnyx_config

        result = export_telnyx_config(sample_graph_with_metadata)

        assert result["name"] == "Test Bot"
        assert result["model"] == "openai/gpt-4o"
        assert result["greeting"] == "Hello!"
        assert result["voice_settings"]["voice"] == "Telnyx.KokoroTTS.af_heart"
        assert result["transcription"]["model"] == "deepgram/nova-3"
        assert result["telephony_settings"]["noise_suppression"] == "krisp"

    def test_export_greeting_from_node_metadata(self):
        from voicetest.exporters.telnyx import export_telnyx_config

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    tools=[],
                    transitions=[],
                    metadata={"greeting": "Hi there!"},
                )
            },
            entry_node_id="main",
            source_type="test",
            source_metadata={},
        )

        result = export_telnyx_config(graph)
        assert result["greeting"] == "Hi there!"

    def test_export_empty_graph(self):
        from voicetest.exporters.telnyx import export_telnyx_config

        graph = AgentGraph(
            nodes={},
            entry_node_id="",
            source_type="test",
            source_metadata={},
        )

        result = export_telnyx_config(graph)
        assert isinstance(result, dict)
        assert result.get("instructions", "") == ""

    def test_export_transfer_tool(self):
        from voicetest.exporters.telnyx import export_telnyx_config

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Route calls",
                    tools=[
                        ToolDefinition(
                            name="transfer",
                            description="Transfer the call",
                            parameters={
                                "transfer": {"targets": [{"name": "Sales", "to": "+15551234567"}]}
                            },
                            type="transfer",
                        )
                    ],
                    transitions=[],
                    metadata={},
                )
            },
            entry_node_id="main",
            source_type="telnyx",
            source_metadata={},
        )

        result = export_telnyx_config(graph)
        transfer_tools = [t for t in result["tools"] if t["type"] == "transfer"]
        assert len(transfer_tools) == 1
        assert transfer_tools[0]["transfer"]["targets"][0]["name"] == "Sales"

    def test_export_hangup_tool(self):
        from voicetest.exporters.telnyx import export_telnyx_config

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    tools=[
                        ToolDefinition(
                            name="hangup",
                            description="End the call",
                            parameters={},
                            type="hangup",
                        )
                    ],
                    transitions=[],
                    metadata={},
                )
            },
            entry_node_id="main",
            source_type="telnyx",
            source_metadata={},
        )

        result = export_telnyx_config(graph)
        hangup_tools = [t for t in result["tools"] if t["type"] == "hangup"]
        assert len(hangup_tools) == 1
        assert hangup_tools[0]["hangup"]["description"] == "End the call"

    def test_export_transitions_as_handoff_tools(self):
        from voicetest.exporters.telnyx import export_telnyx_config

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Route callers",
                    tools=[],
                    transitions=[
                        Transition(
                            target_node_id="ast_billing_002",
                            condition=TransitionCondition(type="tool_call", value="Billing"),
                            description="Handoff to Billing",
                        ),
                        Transition(
                            target_node_id="ast_support_003",
                            condition=TransitionCondition(type="tool_call", value="Tech Support"),
                            description="Handoff to Tech Support",
                        ),
                    ],
                    metadata={},
                )
            },
            entry_node_id="main",
            source_type="telnyx",
            source_metadata={},
        )

        result = export_telnyx_config(graph)
        handoff_tools = [t for t in result.get("tools", []) if t["type"] == "handoff"]
        assert len(handoff_tools) == 1
        assistants = handoff_tools[0]["handoff"]["ai_assistants"]
        assert len(assistants) == 2
        assert assistants[0]["id"] == "ast_billing_002"
        assert assistants[0]["name"] == "Billing"
        assert assistants[1]["id"] == "ast_support_003"
        assert assistants[1]["name"] == "Tech Support"

    def test_export_tool_deduplication(self):
        from voicetest.exporters.telnyx import export_telnyx_config

        graph = AgentGraph(
            nodes={
                "n1": AgentNode(
                    id="n1",
                    state_prompt="Node 1",
                    tools=[
                        ToolDefinition(name="lookup", description="Look up info", type="custom")
                    ],
                    transitions=[],
                    metadata={},
                ),
                "n2": AgentNode(
                    id="n2",
                    state_prompt="Node 2",
                    tools=[
                        ToolDefinition(name="lookup", description="Look up info", type="custom")
                    ],
                    transitions=[],
                    metadata={},
                ),
            },
            entry_node_id="n1",
            source_type="telnyx",
            source_metadata={},
        )

        result = export_telnyx_config(graph)
        webhook_tools = [t for t in result.get("tools", []) if t["type"] == "webhook"]
        assert len(webhook_tools) == 1

    def test_exporter_class_format_id(self):
        from voicetest.exporters.telnyx import TelnyxExporter

        exporter = TelnyxExporter()
        assert exporter.format_id == "telnyx"

    def test_exporter_class_get_info(self):
        from voicetest.exporters.telnyx import TelnyxExporter

        exporter = TelnyxExporter()
        info = exporter.get_info()
        assert info.format_id == "telnyx"
        assert "Telnyx" in info.name
        assert info.ext == "json"

    def test_exporter_class_export_returns_json_string(self, sample_graph):
        import json

        from voicetest.exporters.telnyx import TelnyxExporter

        exporter = TelnyxExporter()
        result = exporter.export(sample_graph)
        assert isinstance(result, str)
        parsed = json.loads(result)
        assert "instructions" in parsed

    def test_roundtrip_import_export(self, sample_telnyx_config):
        from voicetest.exporters.telnyx import export_telnyx_config
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)
        exported = export_telnyx_config(graph)

        assert exported["instructions"] == sample_telnyx_config["instructions"]
        assert exported["model"] == sample_telnyx_config["model"]
        assert exported["name"] == sample_telnyx_config["name"]
        assert exported["greeting"] == sample_telnyx_config["greeting"]

        # Webhook tools preserved
        webhook_tools = [t for t in exported["tools"] if t["type"] == "webhook"]
        assert len(webhook_tools) == 1
        assert webhook_tools[0]["webhook"]["name"] == "check_order_status"

    def test_roundtrip_handoff(self, sample_telnyx_handoff_config):
        from voicetest.exporters.telnyx import export_telnyx_config
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_handoff_config)
        exported = export_telnyx_config(graph)

        handoff_tools = [t for t in exported["tools"] if t["type"] == "handoff"]
        assert len(handoff_tools) == 1
        assistants = handoff_tools[0]["handoff"]["ai_assistants"]
        assert len(assistants) == 2
        ids = {a["id"] for a in assistants}
        assert "ast_billing_002" in ids
        assert "ast_support_003" in ids


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
                        type="custom",
                        url="https://api.example.com/info",
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
        source_type="telnyx",
        source_metadata={
            "name": "Test Bot",
            "assistant_id": "ast_123",
            "model": "openai/gpt-4o",
            "greeting": "Hello!",
            "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart"},
            "transcription": {"model": "deepgram/nova-3", "language": "en"},
            "telephony_settings": {"noise_suppression": "krisp", "time_limit_secs": 600},
            "dynamic_variables": {"store_name": "Test Store"},
        },
    )


@pytest.fixture
def sample_telnyx_config():
    """Sample Telnyx AI assistant config for roundtrip testing."""
    return {
        "id": "ast_abc123",
        "name": "Pizza Order Bot",
        "instructions": "You are a friendly pizza ordering assistant.",
        "model": "openai/gpt-4o",
        "greeting": "Hello! Welcome to Pizza Palace.",
        "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart", "voice_speed": 1.0},
        "transcription": {"model": "deepgram/nova-3", "language": "en"},
        "telephony_settings": {"noise_suppression": "krisp", "time_limit_secs": 600},
        "tools": [
            {
                "type": "webhook",
                "webhook": {
                    "name": "check_order_status",
                    "description": "Check order status",
                    "url": "https://api.example.com/orders/{order_id}",
                    "method": "GET",
                    "path_parameters": {
                        "type": "object",
                        "properties": {"order_id": {"type": "string"}},
                        "required": ["order_id"],
                    },
                },
            },
            {
                "type": "transfer",
                "transfer": {"targets": [{"name": "Manager", "to": "+15551234567"}]},
            },
            {"type": "hangup", "hangup": {"description": "End the call"}},
        ],
    }


@pytest.fixture
def sample_telnyx_handoff_config():
    """Sample Telnyx config with handoff tools for roundtrip testing."""
    return {
        "id": "ast_main_001",
        "name": "Front Desk Bot",
        "instructions": "Route callers to the appropriate department.",
        "model": "openai/gpt-4o",
        "greeting": "How may I direct your call?",
        "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart"},
        "transcription": {"model": "deepgram/nova-3"},
        "tools": [
            {
                "type": "handoff",
                "handoff": {
                    "ai_assistants": [
                        {"id": "ast_billing_002", "name": "Billing Department"},
                        {"id": "ast_support_003", "name": "Technical Support"},
                    ],
                    "voice_mode": "unified",
                },
            },
            {
                "type": "webhook",
                "webhook": {
                    "name": "lookup_account",
                    "description": "Look up account",
                    "url": "https://api.example.com/accounts",
                    "method": "POST",
                },
            },
        ],
    }
