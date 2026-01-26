"""Bland AI inbound number configuration exporter."""

import json
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph, ToolDefinition


class BlandExporter:
    """Exports AgentGraph to Bland AI config format."""

    format_id = "bland"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="Bland",
            description="Agent config for Bland AI",
            ext="json",
        )

    def export(self, graph: AgentGraph) -> str:
        return json.dumps(export_bland_config(graph), indent=2)


def export_bland_config(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to Bland AI inbound number configuration format.

    Bland AI uses a single prompt with tools, so multi-node graphs
    have their instructions merged.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in Bland AI inbound config format.
    """
    result: dict[str, Any] = {}

    # Get the entry node (or first node if no entry specified)
    node = None
    if graph.entry_node_id and graph.entry_node_id in graph.nodes:
        node = graph.nodes[graph.entry_node_id]
    elif graph.nodes:
        node = list(graph.nodes.values())[0]

    # Build prompt from node instructions
    if node:
        result["prompt"] = node.instructions

        # Convert tools to Bland format
        if node.tools:
            result["tools"] = [_convert_tool(t) for t in node.tools]

    # Restore metadata from source
    if graph.source_metadata:
        if "phone_number" in graph.source_metadata:
            result["phone_number"] = graph.source_metadata["phone_number"]
        if "voice_id" in graph.source_metadata:
            result["voice_id"] = graph.source_metadata["voice_id"]
        if "webhook" in graph.source_metadata:
            result["webhook"] = graph.source_metadata["webhook"]
        if "first_sentence" in graph.source_metadata:
            result["first_sentence"] = graph.source_metadata["first_sentence"]
        if "record" in graph.source_metadata:
            result["record"] = graph.source_metadata["record"]
        if "max_duration" in graph.source_metadata:
            result["max_duration"] = graph.source_metadata["max_duration"]
        if "transfer_phone_number" in graph.source_metadata:
            result["transfer_phone_number"] = graph.source_metadata["transfer_phone_number"]
        if "transfer_list" in graph.source_metadata:
            result["transfer_list"] = graph.source_metadata["transfer_list"]
        if "model" in graph.source_metadata:
            result["model"] = graph.source_metadata["model"]
        if "interruption_threshold" in graph.source_metadata:
            result["interruption_threshold"] = graph.source_metadata["interruption_threshold"]

    # Check node metadata for first_sentence
    if node and node.metadata and "first_sentence" in node.metadata:
        result["first_sentence"] = node.metadata["first_sentence"]

    return result


def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert ToolDefinition to Bland AI tool format."""
    bland_tool: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
    }

    if tool.parameters:
        bland_tool["input_schema"] = tool.parameters

    return bland_tool
