"""Custom Python function importer."""

from collections.abc import Callable
from pathlib import Path

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import AgentGraph


class CustomImporter:
    """Import agent from a Python function that returns AgentGraph."""

    @property
    def source_type(self) -> str:
        return "custom"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="custom",
            description="Import from Python function returning AgentGraph",
            file_patterns=[],
        )

    def can_import(self, path_or_config: str | Path | dict | Callable) -> bool:
        """Custom importer handles callable objects."""
        return callable(path_or_config)

    def import_agent(self, path_or_config: str | Path | dict | Callable) -> AgentGraph:
        """Call the function to get AgentGraph."""
        if not callable(path_or_config):
            raise TypeError("CustomImporter requires a callable")

        result = path_or_config()
        if not isinstance(result, AgentGraph):
            raise TypeError(f"Function must return AgentGraph, got {type(result)}")

        return result
