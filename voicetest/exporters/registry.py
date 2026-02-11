"""Exporter registry for discovering and selecting exporters."""

from voicetest.exporters.base import Exporter
from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph


class ExporterRegistry:
    """Registry for discovering and selecting exporters."""

    def __init__(self):
        self._exporters: dict[str, Exporter] = {}

    def register(self, exporter: Exporter) -> None:
        """Register an exporter."""
        self._exporters[exporter.format_id] = exporter

    def get(self, format_id: str) -> Exporter | None:
        """Get an exporter by format ID."""
        return self._exporters.get(format_id)

    def list_formats(self) -> list[ExporterInfo]:
        """List all registered exporters."""
        return [exp.get_info() for exp in self._exporters.values()]

    def export(self, graph: AgentGraph, format_id: str) -> str:
        """Export using the specified format."""
        exporter = self.get(format_id)
        if not exporter:
            raise ValueError(f"Unknown export format: {format_id}")
        return exporter.export(graph)
