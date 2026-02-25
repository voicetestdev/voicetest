"""Voicetest JSON exporter — preserves {%snippet%} refs and snippets dict.

This is the raw format for sharing between voicetest users.
Snippet references are NOT expanded; they remain as {%name%} tokens.
"""

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph


class VoicetestIRExporter:
    """Exports AgentGraph as-is in voicetest JSON format."""

    format_id = "voicetest"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="Voicetest JSON",
            description="Raw voicetest format preserving snippet references",
            ext="vt.json",
        )

    def export(self, graph: AgentGraph) -> str:
        return graph.model_dump_json(indent=2)
