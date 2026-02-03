"""AgentGraph JSON importer for files already in AgentGraph format."""

import json
from pathlib import Path
from typing import Any

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import AgentGraph


class AgentGraphImporter:
    """Import agent from AgentGraph JSON format."""

    @property
    def source_type(self) -> str:
        return "agentgraph"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="agentgraph",
            description="Import from AgentGraph JSON format",
            file_patterns=["*.json"],
        )

    def can_import(self, path_or_config: str | Path | dict[str, Any]) -> bool:
        """Check if the input is AgentGraph JSON (has nodes and entry_node_id)."""
        if isinstance(path_or_config, dict):
            return "nodes" in path_or_config and "entry_node_id" in path_or_config

        if isinstance(path_or_config, str | Path):
            path = Path(path_or_config)
            if not path.exists() or path.suffix != ".json":
                return False
            try:
                data = json.loads(path.read_text())
                return isinstance(data, dict) and "nodes" in data and "entry_node_id" in data
            except (json.JSONDecodeError, OSError):
                return False

        return False

    def import_agent(self, path_or_config: str | Path | dict[str, Any]) -> AgentGraph:
        """Import AgentGraph from JSON file or dict."""
        if isinstance(path_or_config, dict):
            return AgentGraph.model_validate(path_or_config)

        path = Path(path_or_config)
        return AgentGraph.model_validate_json(path.read_text())
