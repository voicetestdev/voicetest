"""Tests for voicetest.importers.bland module."""

import pytest


class TestBlandImporter:
    """Tests for Bland AI inbound number importer."""

    def test_source_type(self):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        assert importer.source_type == "bland"

    def test_can_import_dict_with_prompt_and_phone(self):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        config = {
            "prompt": "You are a helpful assistant",
            "phone_number": "+1234567890",
        }
        assert importer.can_import(config) is True

    def test_can_import_dict_with_bland_fields(self):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        config = {
            "prompt": "You are a helpful assistant",
            "first_sentence": "Hello, how can I help?",
            "voice_id": 1,
        }
        assert importer.can_import(config) is True

    def test_can_import_file_path(self, sample_bland_config_path):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        assert importer.can_import(sample_bland_config_path) is True
        assert importer.can_import(str(sample_bland_config_path)) is True

    def test_can_import_rejects_non_bland(self):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()

        # VAPI config (model is a dict)
        assert importer.can_import({"model": {"provider": "openai"}}) is False

        # Retell LLM config
        assert importer.can_import({"general_prompt": "Hello", "llm_id": "123"}) is False

        # Retell conversation flow
        assert importer.can_import({"start_node_id": "n1", "nodes": []}) is False

        # Empty config
        assert importer.can_import({}) is False

        # Just prompt, no phone or bland fields
        assert importer.can_import({"prompt": "Hello"}) is False

    def test_import_agent_from_dict(self, sample_bland_config):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        graph = importer.import_agent(sample_bland_config)

        assert graph.source_type == "bland"
        assert graph.entry_node_id == "main"
        assert len(graph.nodes) == 1
        assert "main" in graph.nodes

    def test_import_agent_from_path(self, sample_bland_config_path):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        graph = importer.import_agent(sample_bland_config_path)

        assert graph.source_type == "bland"
        assert graph.entry_node_id == "main"

    def test_node_instructions_from_prompt(self, sample_bland_config):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        graph = importer.import_agent(sample_bland_config)

        node = graph.nodes["main"]
        assert node.state_prompt == sample_bland_config["prompt"]

    def test_tools_imported(self):
        from voicetest.importers.bland import BlandImporter

        config = {
            "prompt": "You are a helpful assistant",
            "phone_number": "+1234567890",
            "tools": [
                {
                    "name": "book_appointment",
                    "description": "Book an appointment for the caller",
                    "input_schema": {
                        "type": "object",
                        "properties": {
                            "date": {"type": "string"},
                            "time": {"type": "string"},
                        },
                    },
                },
            ],
        }

        importer = BlandImporter()
        graph = importer.import_agent(config)

        node = graph.nodes["main"]
        assert len(node.tools) == 1
        assert node.tools[0].name == "book_appointment"
        assert node.tools[0].description == "Book an appointment for the caller"
        assert "properties" in node.tools[0].parameters

    def test_source_metadata_captured(self, sample_bland_config):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        graph = importer.import_agent(sample_bland_config)

        meta = graph.source_metadata
        assert meta["phone_number"] == sample_bland_config["phone_number"]
        assert meta["voice_id"] == sample_bland_config["voice_id"]
        assert meta["first_sentence"] == sample_bland_config["first_sentence"]
        assert meta["max_duration"] == sample_bland_config["max_duration"]

    def test_node_metadata_includes_first_sentence(self):
        from voicetest.importers.bland import BlandImporter

        config = {
            "prompt": "You are a helpful assistant",
            "phone_number": "+1234567890",
            "first_sentence": "Hello, how can I help you today?",
        }

        importer = BlandImporter()
        graph = importer.import_agent(config)

        node = graph.nodes["main"]
        assert node.metadata.get("first_sentence") == "Hello, how can I help you today?"

    def test_get_info(self):
        from voicetest.importers.bland import BlandImporter

        importer = BlandImporter()
        info = importer.get_info()

        assert info.source_type == "bland"
        assert "Bland" in info.description
        assert "*.json" in info.file_patterns


class TestBlandImporterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_minimal_config(self):
        from voicetest.importers.bland import BlandImporter

        config = {
            "prompt": "Hello",
            "phone_number": "+1234567890",
        }

        importer = BlandImporter()
        graph = importer.import_agent(config)

        assert graph.source_type == "bland"
        assert graph.nodes["main"].state_prompt == "Hello"
        assert graph.nodes["main"].tools == []

    def test_transfer_list_preserved(self):
        from voicetest.importers.bland import BlandImporter

        config = {
            "prompt": "Hello",
            "phone_number": "+1234567890",
            "transfer_list": {
                "sales": "+1111111111",
                "support": "+2222222222",
            },
        }

        importer = BlandImporter()
        graph = importer.import_agent(config)

        assert graph.source_metadata["transfer_list"] == config["transfer_list"]

    def test_all_optional_fields_preserved(self):
        from voicetest.importers.bland import BlandImporter

        config = {
            "prompt": "Hello",
            "phone_number": "+1234567890",
            "voice_id": 5,
            "webhook": "https://example.com/webhook",
            "first_sentence": "Hi there!",
            "record": True,
            "max_duration": 1800,
            "transfer_phone_number": "+9999999999",
            "model": "gpt-4",
            "interruption_threshold": 100,
        }

        importer = BlandImporter()
        graph = importer.import_agent(config)

        meta = graph.source_metadata
        assert meta["voice_id"] == 5
        assert meta["webhook"] == "https://example.com/webhook"
        assert meta["first_sentence"] == "Hi there!"
        assert meta["record"] is True
        assert meta["max_duration"] == 1800
        assert meta["transfer_phone_number"] == "+9999999999"
        assert meta["model"] == "gpt-4"
        assert meta["interruption_threshold"] == 100


@pytest.fixture
def sample_bland_config():
    """Sample Bland AI inbound config for testing."""
    return {
        "phone_number": "+1234567890",
        "prompt": "You are a friendly customer service representative for a pizza shop.",
        "voice_id": 1,
        "first_sentence": "Hello! Thank you for calling. How can I help you today?",
        "max_duration": 900,
        "tools": [
            {
                "name": "check_order_status",
                "description": "Check the status of an existing order",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "order_id": {"type": "string"},
                    },
                    "required": ["order_id"],
                },
            },
        ],
    }


@pytest.fixture
def sample_bland_config_path(tmp_path, sample_bland_config):
    """Create a temp file with sample Bland config."""
    import json

    path = tmp_path / "bland_config.json"
    path.write_text(json.dumps(sample_bland_config))
    return path
