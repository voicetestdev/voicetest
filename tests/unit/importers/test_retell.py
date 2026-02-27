"""Tests for voicetest.importers.retell module."""

from voicetest.importers.retell import RetellImporter


class TestRetellImporter:
    """Tests for Retell JSON importer."""

    def test_source_type(self):
        importer = RetellImporter()
        assert importer.source_type == "retell"

    def test_can_import_dict(self, sample_retell_config):
        importer = RetellImporter()
        assert importer.can_import(sample_retell_config) is True

    def test_can_import_file_path(self, sample_retell_config_path):
        importer = RetellImporter()
        assert importer.can_import(sample_retell_config_path) is True
        assert importer.can_import(str(sample_retell_config_path)) is True

    def test_can_import_rejects_non_retell(self):
        importer = RetellImporter()
        # Missing required fields
        assert importer.can_import({"some": "config"}) is False
        assert importer.can_import({"nodes": []}) is False  # Missing start_node_id
        assert importer.can_import({"start_node_id": "x"}) is False  # Missing nodes

    def test_import_agent_from_dict(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4
        assert "greeting" in graph.nodes
        assert "billing" in graph.nodes
        assert "support" in graph.nodes
        assert "end_call" in graph.nodes

    def test_import_agent_from_path(self, sample_retell_config_path):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_path)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"

    def test_node_instructions_imported(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert "Greet the customer" in greeting.state_prompt

        billing = graph.nodes["billing"]
        assert "billing inquiry" in billing.state_prompt

    def test_transitions_imported(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert len(greeting.transitions) == 2

        targets = [t.target_node_id for t in greeting.transitions]
        assert "billing" in targets
        assert "support" in targets

    def test_transition_conditions_imported(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        billing_transition = next(t for t in greeting.transitions if t.target_node_id == "billing")
        assert billing_transition.condition.type == "llm_prompt"
        assert "billing" in billing_transition.condition.value.lower()

    def test_source_metadata_captured(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        assert graph.source_metadata["conversation_flow_id"] == "test-flow-001"

    def test_node_metadata_captured(self, sample_retell_config):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert greeting.metadata["retell_type"] == "conversation"

    def test_get_info(self):
        importer = RetellImporter()
        info = importer.get_info()

        assert info.source_type == "retell"
        assert "Retell" in info.description
        assert "*.json" in info.file_patterns


class TestRetellImporterComplex:
    """Tests for Retell importer with complex configuration including tools."""

    def test_import_complex_config(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 11

    def test_tools_imported(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        greeting = graph.nodes["greeting"]
        assert greeting.tools is not None
        assert len(greeting.tools) == 6

        tool_names = [t.name for t in greeting.tools]
        assert "lookup_patient" in tool_names
        assert "get_available_slots" in tool_names
        assert "book_appointment" in tool_names
        assert "cancel_appointment" in tool_names
        assert "end_call" in tool_names
        assert "transfer_to_nurse" in tool_names

    def test_tool_parameters_imported(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        greeting = graph.nodes["greeting"]
        lookup_tool = next(t for t in greeting.tools if t.name == "lookup_patient")
        assert lookup_tool.parameters is not None
        assert "properties" in lookup_tool.parameters
        assert "full_name" in lookup_tool.parameters["properties"]
        assert "date_of_birth" in lookup_tool.parameters["properties"]

    def test_global_prompt_stored_separately(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        greeting = graph.nodes["greeting"]
        # state_prompt has only node-specific instructions
        assert "Greet the caller warmly" in greeting.state_prompt
        # general_prompt stored in source_metadata (not merged)
        assert "professional medical receptionist" in graph.source_metadata.get(
            "general_prompt", ""
        )

    def test_source_metadata_includes_model_settings(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        assert graph.source_metadata["conversation_flow_id"] == "cf_healthcare_001"
        assert graph.source_metadata["version"] == 2
        assert graph.source_metadata["model_temperature"] == 0.7
        assert graph.source_metadata["tool_call_strict_mode"] is True
        assert graph.source_metadata["start_speaker"] == "agent"

    def test_source_metadata_includes_model_choice(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        model_choice = graph.source_metadata["model_choice"]
        assert model_choice["type"] == "cascading"
        assert model_choice["model"] == "gpt-4.1"
        assert model_choice["high_priority"] is True

    def test_source_metadata_includes_knowledge_bases(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        kb_ids = graph.source_metadata["knowledge_base_ids"]
        assert "kb_office_policies" in kb_ids
        assert "kb_insurance_info" in kb_ids

    def test_source_metadata_includes_dynamic_variables(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        vars = graph.source_metadata["default_dynamic_variables"]
        assert vars["office_name"] == "Acme Healthcare"
        assert vars["office_hours"] == "Monday-Friday 8am-6pm"
        assert vars["office_phone"] == "555-123-4567"

    def test_all_nodes_have_same_tools(self, sample_retell_config_complex):
        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_complex)

        for node in graph.nodes.values():
            assert len(node.tools) == 6


class TestRetellImporterTransferMetadata:
    """Tests for CF importer preserving transfer tool metadata."""

    def test_cf_importer_preserves_transfer_metadata(self):
        """CF import with transfer_call tool -> transfer_destination in tool metadata."""
        from voicetest.importers.retell import RetellImporter

        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Help the user."},
                    "edges": [],
                },
            ],
            "tools": [
                {
                    "type": "transfer_call",
                    "name": "transfer_to_billing",
                    "description": "Transfer to billing",
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
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        main_node = graph.nodes["main"]
        transfer_tool = next(t for t in main_node.tools if t.name == "transfer_to_billing")
        assert transfer_tool.metadata["transfer_destination"]["number"] == "+18005551234"
        assert transfer_tool.metadata["transfer_option"]["type"] == "warm_transfer"


class TestRetellImporterDisplayPosition:
    """Tests for importing display_position data from Retell CF."""

    def test_display_position_preserved_on_import(self):
        """Nodes with display_position in JSON have it stored in metadata."""
        config = {
            "start_node_id": "greeting",
            "nodes": [
                {
                    "id": "greeting",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hello."},
                    "edges": [],
                    "display_position": {"x": 100, "y": 200},
                },
                {
                    "id": "farewell",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Bye."},
                    "edges": [],
                    "display_position": {"x": 600, "y": 200},
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert graph.nodes["greeting"].metadata["display_position"] == {"x": 100, "y": 200}
        assert graph.nodes["farewell"].metadata["display_position"] == {"x": 600, "y": 200}

    def test_display_position_absent_not_in_metadata(self):
        """Nodes without display_position don't have it in metadata."""
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hi."},
                    "edges": [],
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert "display_position" not in graph.nodes["main"].metadata

    def test_begin_tag_display_position_preserved(self):
        """begin_tag_display_position at flow level is stored in source_metadata."""
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hi."},
                    "edges": [],
                },
            ],
            "begin_tag_display_position": {"x": -150, "y": 0},
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert graph.source_metadata["begin_tag_display_position"] == {"x": -150, "y": 0}

    def test_begin_tag_display_position_absent(self):
        """When begin_tag_display_position is missing, it's not in source_metadata."""
        config = {
            "start_node_id": "main",
            "nodes": [
                {
                    "id": "main",
                    "type": "conversation",
                    "instruction": {"type": "prompt", "text": "Hi."},
                    "edges": [],
                },
            ],
        }

        importer = RetellImporter()
        graph = importer.import_agent(config)

        assert "begin_tag_display_position" not in graph.source_metadata


class TestRetellImporterWrappedFormat:
    """Tests for importing Retell UI agent wrapper format."""

    def test_can_import_wrapped_format(self, sample_retell_config):
        wrapped = {
            "agent_id": "",
            "response_engine": {"type": "conversation-flow"},
            "conversationFlow": sample_retell_config,
        }
        importer = RetellImporter()
        assert importer.can_import(wrapped) is True

    def test_import_wrapped_format(self, sample_retell_config):
        wrapped = {
            "agent_id": "",
            "response_engine": {"type": "conversation-flow"},
            "conversationFlow": sample_retell_config,
        }
        importer = RetellImporter()
        graph = importer.import_agent(wrapped)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4
