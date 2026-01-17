"""Tests for voicetest.importers.registry module."""

import pytest


class TestImporterRegistry:
    """Tests for ImporterRegistry."""

    def test_register_and_get_importer(self):
        from voicetest.importers.base import ImporterInfo
        from voicetest.importers.registry import ImporterRegistry
        from voicetest.models.agent import AgentGraph, AgentNode

        registry = ImporterRegistry()

        class MockImporter:
            @property
            def source_type(self) -> str:
                return "mock"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("mock", "Mock importer", ["*.mock"])

            def can_import(self, path_or_config) -> bool:
                return isinstance(path_or_config, dict) and "mock" in path_or_config

            def import_agent(self, path_or_config) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="test")},
                    entry_node_id="n",
                    source_type="mock",
                )

        importer = MockImporter()
        registry.register(importer)

        assert registry.get("mock") is importer
        assert registry.get("nonexistent") is None

    def test_auto_detect(self):
        from voicetest.importers.base import ImporterInfo
        from voicetest.importers.registry import ImporterRegistry
        from voicetest.models.agent import AgentGraph, AgentNode

        registry = ImporterRegistry()

        class Importer1:
            @property
            def source_type(self) -> str:
                return "type1"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("type1", "Type 1", [])

            def can_import(self, path_or_config) -> bool:
                return isinstance(path_or_config, dict) and "type1_key" in path_or_config

            def import_agent(self, path_or_config) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="t1")},
                    entry_node_id="n",
                    source_type="type1",
                )

        class Importer2:
            @property
            def source_type(self) -> str:
                return "type2"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("type2", "Type 2", [])

            def can_import(self, path_or_config) -> bool:
                return isinstance(path_or_config, dict) and "type2_key" in path_or_config

            def import_agent(self, path_or_config) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="t2")},
                    entry_node_id="n",
                    source_type="type2",
                )

        registry.register(Importer1())
        registry.register(Importer2())

        # Should find type1
        detected = registry.auto_detect({"type1_key": True})
        assert detected is not None
        assert detected.source_type == "type1"

        # Should find type2
        detected = registry.auto_detect({"type2_key": True})
        assert detected is not None
        assert detected.source_type == "type2"

        # Should return None for unknown
        assert registry.auto_detect({"unknown": True}) is None

    def test_import_agent_with_explicit_source(self):
        from voicetest.importers.base import ImporterInfo
        from voicetest.importers.registry import ImporterRegistry
        from voicetest.models.agent import AgentGraph, AgentNode

        registry = ImporterRegistry()

        class TestImporter:
            @property
            def source_type(self) -> str:
                return "test"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("test", "Test", [])

            def can_import(self, path_or_config) -> bool:
                return True

            def import_agent(self, path_or_config) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="imported")},
                    entry_node_id="n",
                    source_type="test",
                )

        registry.register(TestImporter())

        graph = registry.import_agent({}, source_type="test")
        assert graph.source_type == "test"

    def test_import_agent_with_auto_detect(self):
        from voicetest.importers.base import ImporterInfo
        from voicetest.importers.registry import ImporterRegistry
        from voicetest.models.agent import AgentGraph, AgentNode

        registry = ImporterRegistry()

        class AutoImporter:
            @property
            def source_type(self) -> str:
                return "auto"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("auto", "Auto", [])

            def can_import(self, path_or_config) -> bool:
                return isinstance(path_or_config, dict) and "auto_marker" in path_or_config

            def import_agent(self, path_or_config) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="auto")},
                    entry_node_id="n",
                    source_type="auto",
                )

        registry.register(AutoImporter())

        graph = registry.import_agent({"auto_marker": True})
        assert graph.source_type == "auto"

    def test_import_agent_unknown_source_raises(self):
        from voicetest.importers.registry import ImporterRegistry

        registry = ImporterRegistry()

        with pytest.raises(ValueError, match="Unknown importer"):
            registry.import_agent({}, source_type="nonexistent")

    def test_import_agent_no_match_raises(self):
        from voicetest.importers.registry import ImporterRegistry

        registry = ImporterRegistry()

        with pytest.raises(ValueError, match="Could not auto-detect"):
            registry.import_agent({"unknown": "config"})

    def test_list_importers(self):
        from voicetest.importers.base import ImporterInfo
        from voicetest.importers.registry import ImporterRegistry
        from voicetest.models.agent import AgentGraph, AgentNode

        registry = ImporterRegistry()

        class Imp1:
            @property
            def source_type(self) -> str:
                return "imp1"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("imp1", "Importer 1", ["*.json"])

            def can_import(self, p) -> bool:
                return False

            def import_agent(self, p) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="")},
                    entry_node_id="n",
                    source_type="imp1",
                )

        class Imp2:
            @property
            def source_type(self) -> str:
                return "imp2"

            def get_info(self) -> ImporterInfo:
                return ImporterInfo("imp2", "Importer 2", ["*.yaml"])

            def can_import(self, p) -> bool:
                return False

            def import_agent(self, p) -> AgentGraph:
                return AgentGraph(
                    nodes={"n": AgentNode(id="n", instructions="")},
                    entry_node_id="n",
                    source_type="imp2",
                )

        registry.register(Imp1())
        registry.register(Imp2())

        infos = registry.list_importers()
        assert len(infos) == 2
        types = [i.source_type for i in infos]
        assert "imp1" in types
        assert "imp2" in types


class TestGlobalRegistry:
    """Tests for the global importer registry."""

    def test_get_registry_returns_same_instance(self):
        from voicetest.importers.registry import get_registry

        r1 = get_registry()
        r2 = get_registry()
        assert r1 is r2

    def test_builtin_importers_registered(self):
        # Import the module to trigger registration
        from voicetest.importers import get_registry

        registry = get_registry()

        # Retell and Custom should be registered
        assert registry.get("retell") is not None
        assert registry.get("custom") is not None

    def test_can_import_retell_via_global_registry(self, sample_retell_config):
        from voicetest.importers import get_registry

        registry = get_registry()
        graph = registry.import_agent(sample_retell_config)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == "greeting"
