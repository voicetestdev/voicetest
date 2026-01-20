"""Dependency injection container using Punq."""

import punq

from voicetest.importers.registry import ImporterRegistry
from voicetest.storage.db import get_connection
from voicetest.storage.repositories import AgentRepository, RunRepository, TestCaseRepository


def _create_registry() -> ImporterRegistry:
    """Create and configure the importer registry."""
    from voicetest.importers.custom import CustomImporter
    from voicetest.importers.retell import RetellImporter
    from voicetest.importers.retell_llm import RetellLLMImporter
    from voicetest.importers.vapi import VapiImporter

    registry = ImporterRegistry()
    registry.register(RetellImporter())
    registry.register(RetellLLMImporter())
    registry.register(VapiImporter())
    registry.register(CustomImporter())
    return registry


def create_container() -> punq.Container:
    """Create and configure the DI container."""
    container = punq.Container()

    # Register singletons
    container.register(ImporterRegistry, factory=_create_registry, scope=punq.Scope.singleton)

    # Register repositories (new instance per resolve, sharing connection)
    container.register(
        AgentRepository,
        factory=lambda: AgentRepository(get_connection()),
    )
    container.register(
        TestCaseRepository,
        factory=lambda: TestCaseRepository(get_connection()),
    )
    container.register(
        RunRepository,
        factory=lambda: RunRepository(get_connection()),
    )

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
    """Reset the container (for testing)."""
    global _container
    _container = None
