"""Tests for voicetest.importers.telnyx module."""

import json

import pytest


class TestTelnyxImporter:
    """Tests for Telnyx AI assistant importer."""

    def test_source_type(self):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        assert importer.source_type == "telnyx"

    def test_can_import_basic_assistant(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        assert importer.can_import(sample_telnyx_config) is True

    def test_can_import_with_handoff(self, sample_telnyx_handoff_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        assert importer.can_import(sample_telnyx_handoff_config) is True

    def test_can_import_file_path(self, sample_telnyx_config_path):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        assert importer.can_import(sample_telnyx_config_path) is True
        assert importer.can_import(str(sample_telnyx_config_path)) is True

    def test_can_import_rejects_non_telnyx(self):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()

        # VAPI config (model is a dict)
        assert importer.can_import({"model": {"provider": "openai"}}) is False

        # Retell LLM config
        assert importer.can_import({"general_prompt": "Hello", "llm_id": "123"}) is False

        # Retell conversation flow
        assert importer.can_import({"start_node_id": "n1", "nodes": []}) is False

        # Bland config (prompt instead of instructions)
        assert (
            importer.can_import(
                {"prompt": "Hello", "phone_number": "+1234567890", "first_sentence": "Hi"}
            )
            is False
        )

        # Empty config
        assert importer.can_import({}) is False

        # Just instructions+model, no telnyx-specific fields
        assert importer.can_import({"instructions": "Hello", "model": "gpt-4"}) is False

    def test_can_import_minimal_telnyx(self):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        config = {
            "instructions": "You are helpful",
            "model": "openai/gpt-4o",
            "greeting": "Hello!",
        }
        assert importer.can_import(config) is True

    def test_can_import_with_voice_settings(self):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        config = {
            "instructions": "You are helpful",
            "model": "openai/gpt-4o",
            "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart"},
        }
        assert importer.can_import(config) is True

    def test_import_agent_from_dict(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        assert graph.source_type == "telnyx"
        assert graph.entry_node_id == "main"
        assert len(graph.nodes) == 1
        assert "main" in graph.nodes

    def test_import_agent_from_path(self, sample_telnyx_config_path):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config_path)

        assert graph.source_type == "telnyx"
        assert graph.entry_node_id == "main"

    def test_node_instructions_from_instructions_field(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        node = graph.nodes["main"]
        assert node.state_prompt == sample_telnyx_config["instructions"]

    def test_webhook_tools_imported(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        node = graph.nodes["main"]
        webhook_tools = [t for t in node.tools if t.type == "custom"]
        assert len(webhook_tools) == 1
        assert webhook_tools[0].name == "check_order_status"
        assert webhook_tools[0].description == "Check the status of an existing pizza order"
        assert webhook_tools[0].url == "https://api.example.com/orders/{order_id}"

    def test_transfer_tool_imported(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        node = graph.nodes["main"]
        transfer_tools = [t for t in node.tools if t.type == "transfer"]
        assert len(transfer_tools) == 1
        assert transfer_tools[0].name == "transfer"

    def test_hangup_tool_imported(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        node = graph.nodes["main"]
        hangup_tools = [t for t in node.tools if t.type == "hangup"]
        assert len(hangup_tools) == 1
        assert hangup_tools[0].name == "hangup"

    def test_handoff_creates_transitions(self, sample_telnyx_handoff_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_handoff_config)

        node = graph.nodes["main"]
        assert len(node.transitions) == 2
        assert node.transitions[0].target_node_id == "ast_billing_002"
        assert node.transitions[0].condition.type == "tool_call"
        assert node.transitions[0].condition.value == "Billing Department"
        assert node.transitions[1].target_node_id == "ast_support_003"
        assert node.transitions[1].condition.value == "Technical Support"

    def test_source_metadata_captured(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        meta = graph.source_metadata
        assert meta["name"] == "Pizza Order Bot"
        assert meta["assistant_id"] == "ast_abc123"
        assert meta["model"] == "openai/gpt-4o"
        assert meta["greeting"] == "Hello! Welcome to Pizza Palace. What can I get for you today?"

    def test_default_model_set(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        assert graph.default_model == "openai/gpt-4o"

    def test_greeting_in_node_metadata(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        node = graph.nodes["main"]
        assert (
            node.metadata["greeting"]
            == "Hello! Welcome to Pizza Palace. What can I get for you today?"
        )

    def test_voice_settings_in_source_metadata(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        meta = graph.source_metadata
        assert meta["voice_settings"] == {
            "voice": "Telnyx.KokoroTTS.af_heart",
            "voice_speed": 1.0,
        }

    def test_transcription_in_source_metadata(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        meta = graph.source_metadata
        assert meta["transcription"] == {"model": "deepgram/nova-3", "language": "en"}

    def test_telephony_settings_in_source_metadata(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        meta = graph.source_metadata
        assert meta["telephony_settings"]["noise_suppression"] == "krisp"
        assert meta["telephony_settings"]["time_limit_secs"] == 600

    def test_dynamic_variables_in_source_metadata(self, sample_telnyx_config):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        graph = importer.import_agent(sample_telnyx_config)

        meta = graph.source_metadata
        assert meta["dynamic_variables"]["store_name"] == "Pizza Palace"

    def test_get_info(self):
        from voicetest.importers.telnyx import TelnyxImporter

        importer = TelnyxImporter()
        info = importer.get_info()

        assert info.source_type == "telnyx"
        assert "Telnyx" in info.description
        assert "*.json" in info.file_patterns


class TestTelnyxImporterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_minimal_config(self):
        from voicetest.importers.telnyx import TelnyxImporter

        config = {
            "instructions": "Hello",
            "model": "openai/gpt-4o",
            "greeting": "Hi",
        }

        importer = TelnyxImporter()
        graph = importer.import_agent(config)

        assert graph.source_type == "telnyx"
        assert graph.nodes["main"].state_prompt == "Hello"
        assert graph.nodes["main"].tools == []

    def test_no_tools(self):
        from voicetest.importers.telnyx import TelnyxImporter

        config = {
            "instructions": "You are helpful",
            "model": "openai/gpt-4o",
            "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart"},
        }

        importer = TelnyxImporter()
        graph = importer.import_agent(config)

        assert graph.nodes["main"].tools == []
        assert graph.nodes["main"].transitions == []

    def test_webhook_tool_parameters_merged(self):
        from voicetest.importers.telnyx import TelnyxImporter

        config = {
            "instructions": "Hello",
            "model": "openai/gpt-4o",
            "greeting": "Hi",
            "tools": [
                {
                    "type": "webhook",
                    "webhook": {
                        "name": "search",
                        "description": "Search for items",
                        "url": "https://api.example.com/search",
                        "method": "POST",
                        "body_parameters": {
                            "type": "object",
                            "properties": {"query": {"type": "string"}},
                            "required": ["query"],
                        },
                        "query_parameters": {
                            "type": "object",
                            "properties": {"limit": {"type": "integer"}},
                        },
                    },
                }
            ],
        }

        importer = TelnyxImporter()
        graph = importer.import_agent(config)

        tool = graph.nodes["main"].tools[0]
        assert tool.name == "search"
        assert "query" in tool.parameters.get("properties", {})

    def test_handoff_with_no_other_tools(self):
        from voicetest.importers.telnyx import TelnyxImporter

        config = {
            "instructions": "Route calls",
            "model": "openai/gpt-4o",
            "greeting": "Hello",
            "tools": [
                {
                    "type": "handoff",
                    "handoff": {
                        "ai_assistants": [{"id": "ast_123", "name": "Sales"}],
                        "voice_mode": "unified",
                    },
                }
            ],
        }

        importer = TelnyxImporter()
        graph = importer.import_agent(config)

        node = graph.nodes["main"]
        assert len(node.transitions) == 1
        assert node.transitions[0].target_node_id == "ast_123"
        # Handoff tools should not appear in regular tools list
        assert len(node.tools) == 0


@pytest.fixture
def sample_telnyx_config():
    """Sample Telnyx AI assistant config for testing."""
    return {
        "id": "ast_abc123",
        "name": "Pizza Order Bot",
        "instructions": "You are a friendly pizza ordering assistant. Help customers place orders.",
        "model": "openai/gpt-4o",
        "greeting": "Hello! Welcome to Pizza Palace. What can I get for you today?",
        "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart", "voice_speed": 1.0},
        "transcription": {"model": "deepgram/nova-3", "language": "en"},
        "telephony_settings": {
            "noise_suppression": "krisp",
            "time_limit_secs": 600,
            "user_idle_timeout_secs": 30,
        },
        "dynamic_variables": {"store_name": "Pizza Palace", "store_hours": "9am-10pm"},
        "tools": [
            {
                "type": "webhook",
                "webhook": {
                    "name": "check_order_status",
                    "description": "Check the status of an existing pizza order",
                    "url": "https://api.example.com/orders/{order_id}",
                    "method": "GET",
                    "path_parameters": {
                        "type": "object",
                        "properties": {
                            "order_id": {"type": "string", "description": "The order ID"}
                        },
                        "required": ["order_id"],
                    },
                },
            },
            {
                "type": "transfer",
                "transfer": {"targets": [{"name": "Manager", "to": "+15551234567"}]},
            },
            {
                "type": "hangup",
                "hangup": {"description": "End the call when the customer is done ordering"},
            },
        ],
    }


@pytest.fixture
def sample_telnyx_handoff_config():
    """Sample Telnyx AI assistant config with handoff tools."""
    return {
        "id": "ast_main_001",
        "name": "Front Desk Bot",
        "instructions": "You are the front desk assistant. Route callers.",
        "model": "openai/gpt-4o",
        "greeting": "Thank you for calling. How may I direct your call?",
        "voice_settings": {"voice": "Telnyx.KokoroTTS.af_heart"},
        "transcription": {"model": "deepgram/nova-3", "language": "en"},
        "telephony_settings": {"noise_suppression": "krisp", "time_limit_secs": 900},
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
                    "description": "Look up a customer account",
                    "url": "https://api.example.com/accounts/lookup",
                    "method": "POST",
                    "body_parameters": {
                        "type": "object",
                        "properties": {"phone": {"type": "string"}},
                        "required": ["phone"],
                    },
                },
            },
            {
                "type": "hangup",
                "hangup": {"description": "End the call"},
            },
        ],
    }


@pytest.fixture
def sample_telnyx_config_path(tmp_path, sample_telnyx_config):
    """Create a temp file with sample Telnyx config."""
    path = tmp_path / "telnyx_assistant.json"
    path.write_text(json.dumps(sample_telnyx_config))
    return path
