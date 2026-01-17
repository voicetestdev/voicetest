"""Tests for voicetest.importers.custom module."""

from pathlib import Path

import pytest


class TestCustomImporter:
    """Tests for custom Python function importer."""

    def test_source_type(self):
        from voicetest.importers.custom import CustomImporter

        importer = CustomImporter()
        assert importer.source_type == "custom"

    def test_can_import_callable(self):
        from voicetest.importers.custom import CustomImporter

        importer = CustomImporter()

        def my_func():
            pass

        assert importer.can_import(my_func) is True
        assert importer.can_import(lambda: None) is True

    def test_can_import_rejects_non_callable(self):
        from voicetest.importers.custom import CustomImporter

        importer = CustomImporter()
        assert importer.can_import("string") is False
        assert importer.can_import({"dict": "value"}) is False
        assert importer.can_import(123) is False
        assert importer.can_import(Path("/some/path")) is False

    def test_import_agent_from_function(self):
        from voicetest.importers.custom import CustomImporter
        from voicetest.models.agent import AgentGraph, AgentNode

        importer = CustomImporter()

        def create_agent() -> AgentGraph:
            return AgentGraph(
                nodes={
                    "start": AgentNode(id="start", instructions="Hello"),
                    "end": AgentNode(id="end", instructions="Goodbye"),
                },
                entry_node_id="start",
                source_type="custom",
            )

        graph = importer.import_agent(create_agent)

        assert graph.source_type == "custom"
        assert graph.entry_node_id == "start"
        assert len(graph.nodes) == 2

    def test_import_agent_from_lambda(self):
        from voicetest.importers.custom import CustomImporter
        from voicetest.models.agent import AgentGraph, AgentNode

        importer = CustomImporter()

        graph = importer.import_agent(
            lambda: AgentGraph(
                nodes={"n": AgentNode(id="n", instructions="test")},
                entry_node_id="n",
                source_type="custom",
            )
        )

        assert graph.source_type == "custom"
        assert graph.entry_node_id == "n"

    def test_import_agent_non_callable_raises(self):
        from voicetest.importers.custom import CustomImporter

        importer = CustomImporter()

        with pytest.raises(TypeError, match="callable"):
            importer.import_agent("not a function")

    def test_import_agent_wrong_return_type_raises(self):
        from voicetest.importers.custom import CustomImporter

        importer = CustomImporter()

        def bad_func():
            return {"not": "an AgentGraph"}

        with pytest.raises(TypeError, match="AgentGraph"):
            importer.import_agent(bad_func)

    def test_get_info(self):
        from voicetest.importers.custom import CustomImporter

        importer = CustomImporter()
        info = importer.get_info()

        assert info.source_type == "custom"
        assert "Python" in info.description or "function" in info.description.lower()
