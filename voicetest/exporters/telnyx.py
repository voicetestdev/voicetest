"""Telnyx AI assistant configuration exporter."""

import json
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import ToolDefinition


class TelnyxExporter:
    """Exports AgentGraph to Telnyx AI assistant config format."""

    format_id = "telnyx"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="Telnyx",
            description="AI assistant config for Telnyx",
            ext="json",
        )

    def export(self, graph: AgentGraph) -> str:
        return json.dumps(export_telnyx_config(graph), indent=2)


def export_telnyx_config(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to Telnyx AI assistant configuration format.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in Telnyx AI assistant config format.
    """
    result: dict[str, Any] = {}

    # Build instructions from graph
    result["instructions"] = _graph_to_instructions(graph)

    # Collect tools from all nodes + convert transitions to handoff tools
    all_tools = _collect_all_tools(graph)
    handoff_tool = _transitions_to_handoff(graph)

    telnyx_tools: list[dict[str, Any]] = []
    for tool in all_tools:
        telnyx_tools.append(_convert_tool(tool))
    if handoff_tool:
        telnyx_tools.append(handoff_tool)

    if telnyx_tools:
        result["tools"] = telnyx_tools

    # Restore metadata from source
    if graph.source_metadata:
        _restore_metadata(result, graph.source_metadata)

    # Check entry node metadata for greeting
    entry_node = graph.nodes.get(graph.entry_node_id)
    if entry_node and entry_node.metadata and "greeting" in entry_node.metadata:
        result["greeting"] = entry_node.metadata["greeting"]

    # Set model from default_model if available and not already set
    if graph.default_model and "model" not in result:
        result["model"] = graph.default_model

    return result


def _graph_to_instructions(graph: AgentGraph) -> str:
    """Convert graph to instructions text.

    Single-node graphs return the state prompt directly.
    Multi-node graphs generate structured flow instructions.
    """
    if len(graph.nodes) == 0:
        return ""

    if len(graph.nodes) == 1:
        node = list(graph.nodes.values())[0]
        return node.state_prompt

    # Multi-node: serialize as structured flow
    parts = []
    parts.append(f"Start at: **{graph.entry_node_id}**\n")

    ordered_nodes = []
    if graph.entry_node_id in graph.nodes:
        ordered_nodes.append((graph.entry_node_id, graph.nodes[graph.entry_node_id]))
    for node_id, node in graph.nodes.items():
        if node_id != graph.entry_node_id:
            ordered_nodes.append((node_id, node))

    for node_id, node in ordered_nodes:
        parts.append(f"### State: {node_id}")
        if node.state_prompt:
            parts.append(node.state_prompt)
        parts.append("")

    return "\n".join(parts)


def _collect_all_tools(graph: AgentGraph) -> list[ToolDefinition]:
    """Collect and deduplicate tools from all nodes."""
    seen_names: set[str] = set()
    tools: list[ToolDefinition] = []

    for node in graph.nodes.values():
        for tool in node.tools:
            if tool.name not in seen_names:
                tools.append(tool)
                seen_names.add(tool.name)

    return tools


def _transitions_to_handoff(graph: AgentGraph) -> dict[str, Any] | None:
    """Convert transitions across all nodes into a single handoff tool entry."""
    assistants: list[dict[str, str]] = []

    for node in graph.nodes.values():
        for transition in node.transitions:
            if transition.condition.type == "tool_call":
                assistants.append(
                    {
                        "id": transition.target_node_id,
                        "name": transition.condition.value,
                    }
                )

    if not assistants:
        return None

    return {
        "type": "handoff",
        "handoff": {
            "ai_assistants": assistants,
        },
    }


def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert ToolDefinition to Telnyx tool format."""
    if tool.type == "transfer":
        transfer_config = tool.parameters.get("transfer", {})
        return {
            "type": "transfer",
            "transfer": transfer_config,
        }

    if tool.type == "hangup":
        return {
            "type": "hangup",
            "hangup": {
                "description": tool.description,
            },
        }

    # Default: webhook tool
    webhook: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
    }

    if tool.url:
        webhook["url"] = tool.url

    if tool.parameters:
        webhook["body_parameters"] = tool.parameters

    return {
        "type": "webhook",
        "webhook": webhook,
    }


def _restore_metadata(result: dict[str, Any], metadata: dict[str, Any]) -> None:
    """Restore source metadata fields to the exported config."""
    passthrough_fields = [
        "name",
        "model",
        "greeting",
        "voice_settings",
        "transcription",
        "telephony_settings",
        "dynamic_variables",
    ]

    for field in passthrough_fields:
        if field in metadata:
            result[field] = metadata[field]
