"""Bland AI inbound number configuration exporter."""

import json
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import ToolDefinition


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

    Bland AI uses a single prompt, so multi-node graphs are serialized
    as structured text instructions describing the conversation flow.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in Bland AI inbound config format.
    """
    result: dict[str, Any] = {}

    # Build prompt from graph (serializes entire flow as text)
    result["prompt"] = _graph_to_prompt(graph)

    # Collect all tools from all nodes
    all_tools = _collect_all_tools(graph)
    if all_tools:
        result["tools"] = [_convert_tool(t) for t in all_tools]

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

    # Check entry node metadata for first_sentence
    entry_node = graph.nodes.get(graph.entry_node_id)
    if entry_node and entry_node.metadata and "first_sentence" in entry_node.metadata:
        result["first_sentence"] = entry_node.metadata["first_sentence"]

    return result


def _graph_to_prompt(graph: AgentGraph) -> str:
    """Convert entire graph to a text prompt describing the conversation flow.

    For single-node graphs, returns just the prompt.
    For multi-node graphs, generates structured instructions.
    """
    general_prompt = graph.source_metadata.get("general_prompt", "")

    # Empty graph: return general prompt or empty string
    if len(graph.nodes) == 0:
        return general_prompt or ""

    # Single node: just combine general + state prompt
    if len(graph.nodes) == 1:
        node = list(graph.nodes.values())[0]
        if general_prompt and node.state_prompt:
            return f"{general_prompt}\n\n{node.state_prompt}"
        return node.state_prompt or general_prompt

    # Multi-node: serialize as structured flow
    parts = []

    if general_prompt:
        parts.append(general_prompt)

    parts.append("\n## Conversation Flow\n")
    parts.append(f"Start at: **{graph.entry_node_id}**\n")

    # Build ordered list starting with entry node
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

        if node.transitions:
            parts.append("\nTransitions:")
            for transition in node.transitions:
                condition = transition.condition.value or "always"
                parts.append(f"  - When: {condition} → go to **{transition.target_node_id}**")

        parts.append("")

    return "\n".join(parts)


def _collect_all_tools(graph: AgentGraph) -> list[ToolDefinition]:
    """Collect and deduplicate all tools from all nodes."""
    seen_names: set[str] = set()
    tools: list[ToolDefinition] = []

    for node in graph.nodes.values():
        for tool in node.tools:
            if tool.name not in seen_names:
                tools.append(tool)
                seen_names.add(tool.name)

    return tools


def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert ToolDefinition to Bland AI tool format."""
    bland_tool: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
    }

    if tool.parameters:
        bland_tool["input_schema"] = tool.parameters

    return bland_tool
