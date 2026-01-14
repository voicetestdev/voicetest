"""Tests for voicetest.importers.retell module."""


class TestRetellImporter:
    """Tests for Retell JSON importer."""

    def test_source_type(self):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        assert importer.source_type == "retell"

    def test_can_import_dict(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        assert importer.can_import(sample_retell_config) is True

    def test_can_import_file_path(self, sample_retell_config_path):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        assert importer.can_import(sample_retell_config_path) is True
        assert importer.can_import(str(sample_retell_config_path)) is True

    def test_can_import_rejects_non_retell(self):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        # Missing required fields
        assert importer.can_import({"some": "config"}) is False
        assert importer.can_import({"nodes": []}) is False  # Missing start_node_id
        assert importer.can_import({"start_node_id": "x"}) is False  # Missing nodes

    def test_import_agent_from_dict(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

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
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config_path)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"

    def test_node_instructions_imported(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert "Greet the customer" in greeting.instructions

        billing = graph.nodes["billing"]
        assert "billing inquiry" in billing.instructions

    def test_transitions_imported(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert len(greeting.transitions) == 2

        targets = [t.target_node_id for t in greeting.transitions]
        assert "billing" in targets
        assert "support" in targets

    def test_transition_conditions_imported(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        billing_transition = next(
            t for t in greeting.transitions if t.target_node_id == "billing"
        )
        assert billing_transition.condition.type == "llm_prompt"
        assert "billing" in billing_transition.condition.value.lower()

    def test_source_metadata_captured(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        assert graph.source_metadata["conversation_flow_id"] == "test-flow-001"

    def test_node_metadata_captured(self, sample_retell_config):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)

        greeting = graph.nodes["greeting"]
        assert greeting.metadata["retell_type"] == "conversation"

    def test_get_info(self):
        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        info = importer.get_info()

        assert info.source_type == "retell"
        assert "Retell" in info.description
        assert "*.json" in info.file_patterns
