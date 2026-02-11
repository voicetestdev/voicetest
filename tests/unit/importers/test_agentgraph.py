"""Tests for voicetest.importers.agentgraph module."""


class TestAgentGraphImporter:
    """Tests for AgentGraph JSON importer."""

    def test_source_type(self):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()
        assert importer.source_type == "agentgraph"

    def test_can_import_dict_with_required_fields(self):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        valid_dict = {
            "nodes": {"start": {"id": "start", "state_prompt": "Hello"}},
            "entry_node_id": "start",
            "source_type": "test",
        }
        assert importer.can_import(valid_dict) is True

    def test_can_import_rejects_dict_without_nodes(self):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        invalid_dict = {"entry_node_id": "start", "source_type": "test"}
        assert importer.can_import(invalid_dict) is False

    def test_can_import_rejects_dict_without_entry_node_id(self):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        invalid_dict = {"nodes": {}, "source_type": "test"}
        assert importer.can_import(invalid_dict) is False

    def test_can_import_file(self, tmp_path):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        agent_file = tmp_path / "agent.json"
        agent_file.write_text('{"nodes": {}, "entry_node_id": "start", "source_type": "test"}')
        assert importer.can_import(agent_file) is True
        assert importer.can_import(str(agent_file)) is True

    def test_can_import_rejects_non_json_file(self, tmp_path):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        txt_file = tmp_path / "agent.txt"
        txt_file.write_text("not json")
        assert importer.can_import(txt_file) is False

    def test_can_import_rejects_platform_format_file(self, tmp_path):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        retell_file = tmp_path / "agent.json"
        retell_file.write_text('{"agent_id": "123", "llm": {}}')
        assert importer.can_import(retell_file) is False

    def test_can_import_rejects_missing_file(self, tmp_path):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        missing_file = tmp_path / "missing.json"
        assert importer.can_import(missing_file) is False

    def test_import_agent_from_dict(self):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()

        config = {
            "nodes": {
                "start": {"id": "start", "state_prompt": "Hello"},
            },
            "entry_node_id": "start",
            "source_type": "test",
        }

        graph = importer.import_agent(config)

        assert graph.source_type == "test"
        assert graph.entry_node_id == "start"
        assert "start" in graph.nodes

    def test_import_agent_from_file(self, tmp_path):
        from voicetest.importers.agentgraph import AgentGraphImporter
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        importer = AgentGraphImporter()

        sample_graph = AgentGraph(
            nodes={"greeting": AgentNode(id="greeting", state_prompt="Hi")},
            entry_node_id="greeting",
            source_type="agentgraph",
        )

        agent_file = tmp_path / "agent.json"
        agent_file.write_text(sample_graph.model_dump_json())

        graph = importer.import_agent(agent_file)

        assert graph.source_type == "agentgraph"
        assert graph.entry_node_id == "greeting"

    def test_get_info(self):
        from voicetest.importers.agentgraph import AgentGraphImporter

        importer = AgentGraphImporter()
        info = importer.get_info()

        assert info.source_type == "agentgraph"
        assert "AgentGraph" in info.description or "JSON" in info.description
