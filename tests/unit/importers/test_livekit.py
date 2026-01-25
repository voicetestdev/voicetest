"""Tests for voicetest.importers.livekit module."""


class TestLiveKitImporter:
    """Tests for LiveKit Python agent importer."""

    def test_source_type(self):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        assert importer.source_type == "livekit"

    def test_can_import_python_file(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        assert importer.can_import(sample_livekit_agent_path) is True
        assert importer.can_import(str(sample_livekit_agent_path)) is True

    def test_can_import_dict_with_code(self, sample_livekit_agent_code):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        assert importer.can_import({"code": sample_livekit_agent_code}) is True

    def test_can_import_rejects_non_livekit(self, tmp_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()

        # Non-Python file
        json_file = tmp_path / "test.json"
        json_file.write_text('{"foo": "bar"}')
        assert importer.can_import(json_file) is False

        # Python file without livekit imports
        other_py = tmp_path / "other.py"
        other_py.write_text('print("hello")')
        assert importer.can_import(other_py) is False

        # Dict without code
        assert importer.can_import({"some": "data"}) is False

    def test_import_agent_from_path(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_agent_path)

        assert graph.source_type == "livekit"
        assert graph.entry_node_id == "greeting"
        assert len(graph.nodes) == 4
        assert "greeting" in graph.nodes
        assert "billing" in graph.nodes
        assert "support" in graph.nodes
        assert "end_call" in graph.nodes

    def test_import_agent_from_dict(self, sample_livekit_agent_code):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent({"code": sample_livekit_agent_code})

        assert graph.source_type == "livekit"
        assert graph.entry_node_id == "greeting"

    def test_node_instructions_imported(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_agent_path)

        greeting = graph.nodes["greeting"]
        assert "Greet the user warmly" in greeting.instructions

        billing = graph.nodes["billing"]
        assert "billing" in billing.instructions.lower()

    def test_transitions_imported(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_agent_path)

        greeting = graph.nodes["greeting"]
        assert len(greeting.transitions) == 2

        targets = [t.target_node_id for t in greeting.transitions]
        assert "billing" in targets
        assert "support" in targets

    def test_transition_conditions_imported(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_agent_path)

        greeting = graph.nodes["greeting"]
        billing_transition = next(t for t in greeting.transitions if t.target_node_id == "billing")
        assert billing_transition.condition.type == "tool_call"
        assert "billing" in billing_transition.condition.value.lower()

    def test_tools_imported(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_agent_path)

        greeting = graph.nodes["greeting"]
        tool_names = [t.name for t in greeting.tools]
        assert "route_to_billing" in tool_names
        assert "route_to_support" in tool_names

    def test_node_metadata_captured(self, sample_livekit_agent_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_agent_path)

        greeting = graph.nodes["greeting"]
        assert greeting.metadata["livekit_class"] == "Agent_greeting"

    def test_get_info(self):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        info = importer.get_info()

        assert info.source_type == "livekit"
        assert "LiveKit" in info.description
        assert "*.py" in info.file_patterns


class TestLiveKitImporterSimple:
    """Tests for LiveKit importer with simple single-agent files."""

    def test_import_simple_agent(self, sample_livekit_simple_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_simple_path)

        assert graph.source_type == "livekit"
        assert graph.entry_node_id == "GreetingAgent"
        assert len(graph.nodes) == 1

    def test_simple_agent_instructions(self, sample_livekit_simple_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_simple_path)

        node = graph.nodes["GreetingAgent"]
        assert "friendly assistant" in node.instructions

    def test_simple_agent_tools(self, sample_livekit_simple_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_simple_path)

        node = graph.nodes["GreetingAgent"]
        tool_names = [t.name for t in node.tools]
        assert "get_weather" in tool_names

    def test_tool_parameters_extracted(self, sample_livekit_simple_path):
        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        graph = importer.import_agent(sample_livekit_simple_path)

        node = graph.nodes["GreetingAgent"]
        weather_tool = next(t for t in node.tools if t.name == "get_weather")

        assert "properties" in weather_tool.parameters
        assert "city" in weather_tool.parameters["properties"]


class TestLiveKitImporterEdgeCases:
    """Tests for edge cases and error handling."""

    def test_empty_python_file(self, tmp_path):
        from voicetest.importers.livekit import LiveKitImporter

        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        importer = LiveKitImporter()
        assert importer.can_import(empty_file) is False

    def test_python_file_no_agents(self, tmp_path):
        from voicetest.importers.livekit import LiveKitImporter

        no_agent_file = tmp_path / "no_agent.py"
        no_agent_file.write_text("""
from livekit.agents import Agent

# No agent classes defined
def main():
    print("hello")
""")

        importer = LiveKitImporter()
        assert importer.can_import(no_agent_file) is True

        graph = importer.import_agent(no_agent_file)
        assert graph.entry_node_id == "main"
        assert "main" in graph.nodes

    def test_dict_without_code_raises(self):
        import pytest

        from voicetest.importers.livekit import LiveKitImporter

        importer = LiveKitImporter()
        with pytest.raises(ValueError, match="code"):
            importer.import_agent({"foo": "bar"})
