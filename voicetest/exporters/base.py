"""Base protocol and types for exporters."""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from voicetest.models.agent import AgentGraph


@runtime_checkable
class Exporter(Protocol):
    """Protocol for agent graph exporters.

    Exporters convert the unified AgentGraph representation to
    platform-specific formats.
    """

    @property
    def format_id(self) -> str:
        """Identifier for this format (e.g., 'mermaid', 'retell-llm')."""
        ...

    def get_info(self) -> "ExporterInfo":
        """Return metadata about this exporter."""
        ...

    def export(self, graph: AgentGraph) -> str:
        """Convert AgentGraph to target format string."""
        ...


@dataclass
class ExporterInfo:
    """Metadata about an available exporter."""

    format_id: str
    name: str
    description: str
    ext: str
