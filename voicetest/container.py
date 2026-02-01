"""Dependency injection container using Punq."""

import duckdb
import punq

from voicetest.exporters.bland import BlandExporter
from voicetest.exporters.graph_viz import MermaidExporter
from voicetest.exporters.livekit_codegen import LiveKitExporter
from voicetest.exporters.registry import ExporterRegistry
from voicetest.exporters.retell_cf import RetellCFExporter
from voicetest.exporters.retell_llm import RetellLLMExporter
from voicetest.exporters.vapi import VAPIAssistantExporter, VAPISquadExporter
from voicetest.importers.bland import BlandImporter
from voicetest.importers.custom import CustomImporter
from voicetest.importers.livekit import LiveKitImporter
from voicetest.importers.registry import ImporterRegistry
from voicetest.importers.retell import RetellImporter
from voicetest.importers.retell_llm import RetellLLMImporter
from voicetest.importers.vapi import VapiImporter
from voicetest.importers.xlsform import XLSFormImporter
from voicetest.platforms.bland import BlandPlatformClient
from voicetest.platforms.livekit import LiveKitPlatformClient
from voicetest.platforms.registry import PlatformRegistry
from voicetest.platforms.retell import RetellPlatformClient
from voicetest.platforms.vapi import VapiPlatformClient
from voicetest.storage.db import create_connection
from voicetest.storage.repositories import AgentRepository, RunRepository, TestCaseRepository


def _create_importer_registry() -> ImporterRegistry:
    """Create and configure the importer registry."""
    registry = ImporterRegistry()
    registry.register(RetellImporter())
    registry.register(RetellLLMImporter())
    registry.register(VapiImporter())
    registry.register(LiveKitImporter())
    registry.register(BlandImporter())
    registry.register(XLSFormImporter())
    registry.register(CustomImporter())
    return registry


def _create_exporter_registry() -> ExporterRegistry:
    """Create and configure the exporter registry."""
    registry = ExporterRegistry()
    registry.register(MermaidExporter())
    registry.register(LiveKitExporter())
    registry.register(RetellLLMExporter())
    registry.register(RetellCFExporter())
    registry.register(VAPIAssistantExporter())
    registry.register(VAPISquadExporter())
    registry.register(BlandExporter())
    return registry


def _create_platform_registry() -> PlatformRegistry:
    """Create and configure the platform registry."""
    registry = PlatformRegistry()
    registry.register(RetellPlatformClient())
    registry.register(VapiPlatformClient())
    registry.register(LiveKitPlatformClient())
    registry.register(BlandPlatformClient())
    return registry


def create_container() -> punq.Container:
    """Create and configure the DI container."""
    container = punq.Container()

    # Database connection (singleton ensures data visibility across repositories)
    container.register(
        duckdb.DuckDBPyConnection,
        factory=create_connection,
        scope=punq.Scope.singleton,
    )

    # Registries (singletons)
    container.register(
        ImporterRegistry, factory=_create_importer_registry, scope=punq.Scope.singleton
    )
    container.register(
        ExporterRegistry, factory=_create_exporter_registry, scope=punq.Scope.singleton
    )
    container.register(
        PlatformRegistry, factory=_create_platform_registry, scope=punq.Scope.singleton
    )

    # Repositories (punq auto-injects the connection)
    container.register(AgentRepository)
    container.register(TestCaseRepository)
    container.register(RunRepository)

    return container


# Application container - initialized once at startup
_container: punq.Container | None = None


def get_container() -> punq.Container:
    """Get the application container, creating it if needed."""
    global _container
    if _container is None:
        _container = create_container()
    return _container


def reset_container() -> None:
    """Reset the container (for testing).

    This also resets the database connection since it's managed by the container.
    """
    global _container
    _container = None


def get_db_connection() -> duckdb.DuckDBPyConnection:
    """Get the database connection from the DI container."""
    return get_container().resolve(duckdb.DuckDBPyConnection)


def get_importer_registry() -> ImporterRegistry:
    """Get the importer registry from the DI container."""
    return get_container().resolve(ImporterRegistry)


def get_exporter_registry() -> ExporterRegistry:
    """Get the exporter registry from the DI container."""
    return get_container().resolve(ExporterRegistry)
