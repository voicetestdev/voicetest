"""Base protocol and types for source importers."""

from pathlib import Path
from typing import Protocol, runtime_checkable

from voicetest.models.agent import AgentGraph


@runtime_checkable
class SourceImporter(Protocol):
    """Protocol for agent config importers.

    Importers convert platform-specific agent configurations to the
    unified AgentGraph representation.
    """

    @property
    def source_type(self) -> str:
        """Identifier for this importer (e.g., 'retell', 'vapi')."""
        ...

    def get_info(self) -> "ImporterInfo":
        """Return metadata about this importer."""
        ...

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Return True if this importer can handle the given input."""
        ...

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert source format to unified AgentGraph."""
        ...


class ImporterInfo:
    """Metadata about an available importer."""

    def __init__(
        self,
        source_type: str,
        description: str,
        file_patterns: list[str],
    ):
        self.source_type = source_type
        self.description = description
        self.file_patterns = file_patterns
