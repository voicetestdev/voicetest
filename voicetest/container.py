"""Dependency injection container using Punq."""

import os

import punq
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from voicetest.exporters.bland import BlandExporter
from voicetest.exporters.graph_viz import MermaidExporter
from voicetest.exporters.livekit_codegen import LiveKitExporter
from voicetest.exporters.registry import ExporterRegistry
from voicetest.exporters.retell_cf import RetellCFExporter
from voicetest.exporters.retell_llm import RetellLLMExporter
from voicetest.exporters.telnyx import TelnyxExporter
from voicetest.exporters.vapi import VAPIAssistantExporter
from voicetest.exporters.vapi import VAPISquadExporter
from voicetest.exporters.voicetest_ir import VoicetestIRExporter
from voicetest.importers.agentgraph import AgentGraphImporter
from voicetest.importers.bland import BlandImporter
from voicetest.importers.custom import CustomImporter
from voicetest.importers.livekit import LiveKitImporter
from voicetest.importers.registry import ImporterRegistry
from voicetest.importers.retell import RetellImporter
from voicetest.importers.retell_llm import RetellLLMImporter
from voicetest.importers.telnyx import TelnyxImporter
from voicetest.importers.vapi import VapiImporter
from voicetest.importers.xlsform import XLSFormImporter
from voicetest.platforms.bland import BlandPlatformClient
from voicetest.platforms.livekit import LiveKitPlatformClient
from voicetest.platforms.registry import PlatformRegistry
from voicetest.platforms.retell import RetellPlatformClient
from voicetest.platforms.telnyx import TelnyxPlatformClient
from voicetest.platforms.vapi import VapiPlatformClient
from voicetest.storage.engine import create_db_engine
from voicetest.storage.engine import get_session_factory
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import CallRepository
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository


def _create_importer_registry() -> ImporterRegistry:
    """Create and configure the importer registry."""
    registry = ImporterRegistry()
    registry.register(RetellImporter())
    registry.register(RetellLLMImporter())
    registry.register(VapiImporter())
    registry.register(LiveKitImporter())
    registry.register(BlandImporter())
    registry.register(TelnyxImporter())
    registry.register(XLSFormImporter())
    registry.register(CustomImporter())
    registry.register(AgentGraphImporter())
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
    registry.register(TelnyxExporter())
    registry.register(VoicetestIRExporter())
    return registry


def _create_platform_registry() -> PlatformRegistry:
    """Create and configure the platform registry."""
    registry = PlatformRegistry()
    registry.register(RetellPlatformClient())
    registry.register(VapiPlatformClient())
    registry.register(LiveKitPlatformClient())
    registry.register(BlandPlatformClient())
    registry.register(TelnyxPlatformClient())
    return registry


def create_container() -> punq.Container:
    """Create and configure the DI container."""
    container = punq.Container()

    # Engine (singleton)
    container.register(
        Engine,
        factory=lambda: create_db_engine(os.environ.get("DATABASE_URL")),
        scope=punq.Scope.singleton,
    )

    # Session factory (singleton)
    container.register(
        sessionmaker,
        factory=lambda: get_session_factory(container.resolve(Engine)),
        scope=punq.Scope.singleton,
    )

    # Session (singleton for CLI, per-request for REST API)
    container.register(
        Session,
        factory=lambda: container.resolve(sessionmaker)(),
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

    # Repositories (punq auto-injects the session)
    container.register(AgentRepository)
    container.register(TestCaseRepository)
    container.register(RunRepository)
    container.register(CallRepository)

    # Services — deferred imports to avoid circular dependency with services/__init__.py
    from voicetest.services.agents import AgentService  # noqa: PLC0415
    from voicetest.services.diagnosis import DiagnosisService  # noqa: PLC0415
    from voicetest.services.discovery import DiscoveryService  # noqa: PLC0415
    from voicetest.services.evaluation import EvaluationService  # noqa: PLC0415
    from voicetest.services.platforms import PlatformService  # noqa: PLC0415
    from voicetest.services.runs import RunService  # noqa: PLC0415
    from voicetest.services.settings import SettingsService  # noqa: PLC0415
    from voicetest.services.snippets import SnippetService  # noqa: PLC0415
    from voicetest.services.testing.cases import TestCaseService  # noqa: PLC0415
    from voicetest.services.testing.execution import TestExecutionService  # noqa: PLC0415

    container.register(DiscoveryService)
    container.register(AgentService)
    container.register(TestExecutionService)
    container.register(TestCaseService)
    container.register(EvaluationService)
    container.register(DiagnosisService)
    container.register(SnippetService)
    container.register(RunService)
    container.register(PlatformService)
    container.register(SettingsService)

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


def get_session() -> Session:
    """Get the database session from the DI container."""
    return get_container().resolve(Session)


def get_importer_registry() -> ImporterRegistry:
    """Get the importer registry from the DI container."""
    return get_container().resolve(ImporterRegistry)


def get_exporter_registry() -> ExporterRegistry:
    """Get the exporter registry from the DI container."""
    return get_container().resolve(ExporterRegistry)
