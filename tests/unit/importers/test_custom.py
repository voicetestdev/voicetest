"""Tests for voicetest.importers.custom module."""

from pathlib import Path

import pytest

from voicetest.importers.custom import CustomImporter
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import NodeType


class TestCustomImporter:
    """Tests for custom Python function importer."""

    def test_source_type(self):
        importer = CustomImporter()
        assert importer.source_type == "custom"

    def test_can_import_callable(self):
        importer = CustomImporter()

        def my_func():
            pass

        assert importer.can_import(my_func) is True
        assert importer.can_import(lambda: None) is True

    def test_can_import_rejects_non_callable(self):
        importer = CustomImporter()
        assert importer.can_import("string") is False
        assert importer.can_import({"dict": "value"}) is False
        assert importer.can_import(123) is False
        assert importer.can_import(Path("/some/path")) is False

    def test_import_agent_from_function(self):
        importer = CustomImporter()

        def create_agent() -> AgentGraph:
            return AgentGraph(
                nodes={
                    "start": AgentNode(
                        id="start", state_prompt="Hello", node_type=NodeType.CONVERSATION
                    ),
                    "end": AgentNode(
                        id="end", state_prompt="Goodbye", node_type=NodeType.CONVERSATION
                    ),
                },
                entry_node_id="start",
                source_type="custom",
            )

        graph = importer.import_agent(create_agent)

        assert graph.source_type == "custom"
        assert graph.entry_node_id == "start"
        assert len(graph.nodes) == 2

    def test_import_agent_from_lambda(self):
        importer = CustomImporter()

        graph = importer.import_agent(
            lambda: AgentGraph(
                nodes={
                    "n": AgentNode(id="n", state_prompt="test", node_type=NodeType.CONVERSATION)
                },
                entry_node_id="n",
                source_type="custom",
            )
        )

        assert graph.source_type == "custom"
        assert graph.entry_node_id == "n"

    def test_import_agent_non_callable_raises(self):
        importer = CustomImporter()

        with pytest.raises(TypeError, match="callable"):
            importer.import_agent("not a function")

    def test_import_agent_wrong_return_type_raises(self):
        importer = CustomImporter()

        def bad_func():
            return {"not": "an AgentGraph"}

        with pytest.raises(TypeError, match="AgentGraph"):
            importer.import_agent(bad_func)

    def test_get_info(self):
        importer = CustomImporter()
        info = importer.get_info()

        assert info.source_type == "custom"
        assert "Python" in info.description or "function" in info.description.lower()
