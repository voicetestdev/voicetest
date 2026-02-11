"""Importer registry for discovering and selecting importers."""

from pathlib import Path

from voicetest.importers.base import ImporterInfo
from voicetest.importers.base import SourceImporter
from voicetest.models.agent import AgentGraph


class ImporterRegistry:
    """Registry for discovering and selecting importers."""

    def __init__(self):
        self._importers: dict[str, SourceImporter] = {}

    def register(self, importer: SourceImporter) -> None:
        """Register an importer."""
        self._importers[importer.source_type] = importer

    def get(self, source_type: str) -> SourceImporter | None:
        """Get an importer by source type."""
        return self._importers.get(source_type)

    def list_importers(self) -> list[ImporterInfo]:
        """List all registered importers."""
        return [imp.get_info() for imp in self._importers.values()]

    def auto_detect(self, path_or_config: str | Path | dict) -> SourceImporter | None:
        """Find the first importer that can handle the input."""
        for importer in self._importers.values():
            if importer.can_import(path_or_config):
                return importer
        return None

    def import_agent(
        self,
        path_or_config: str | Path | dict,
        source_type: str | None = None,
    ) -> AgentGraph:
        """Import using specified or auto-detected importer."""
        if source_type:
            importer = self.get(source_type)
            if not importer:
                raise ValueError(f"Unknown importer: {source_type}")
        else:
            importer = self.auto_detect(path_or_config)
            if not importer:
                raise ValueError("Could not auto-detect source type")

        return importer.import_agent(path_or_config)
