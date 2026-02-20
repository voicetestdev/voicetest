"""Retell LLM (single/multi-prompt) exporter."""

import json
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition


class RetellLLMExporter:
    """Exports AgentGraph to Retell LLM format."""

    format_id = "retell-llm"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="Retell LLM",
            description="Single LLM agent config for Retell AI",
            ext="json",
        )

    def export(self, graph: AgentGraph) -> str:
        return json.dumps(export_retell_llm(graph), indent=2)


def export_retell_llm(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to Retell LLM format.

    Converts the unified AgentGraph representation to Retell's LLM format
    with states, edges, and tools.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in Retell LLM JSON format.
    """
    result: dict[str, Any] = {}

    if graph.source_metadata:
        if "llm_id" in graph.source_metadata:
            result["llm_id"] = graph.source_metadata["llm_id"]
        if "model" in graph.source_metadata:
            result["model"] = graph.source_metadata["model"]
        if "begin_message" in graph.source_metadata:
            result["begin_message"] = graph.source_metadata["begin_message"]
        if "model_temperature" in graph.source_metadata:
            result["model_temperature"] = graph.source_metadata["model_temperature"]

    general_tools = _extract_general_tools(graph)
    if general_tools:
        result["general_tools"] = [_convert_tool(t) for t in general_tools]

    result["general_prompt"] = graph.source_metadata.get("general_prompt", "")
    result["states"] = _build_states(graph, general_tools)

    return result


def _extract_general_tools(graph: AgentGraph) -> list[ToolDefinition]:
    """Extract tools that appear in all nodes (general tools)."""
    if not graph.nodes:
        return []

    nodes_with_tools = [n for n in graph.nodes.values() if n.tools]
    if not nodes_with_tools:
        return []

    first_node_tools = {t.name for t in nodes_with_tools[0].tools}
    common_tool_names = first_node_tools.copy()

    for node in nodes_with_tools[1:]:
        node_tool_names = {t.name for t in node.tools}
        common_tool_names &= node_tool_names

    general_tools = []
    seen_names: set[str] = set()
    for node in nodes_with_tools:
        for tool in node.tools:
            if tool.name in common_tool_names and tool.name not in seen_names:
                general_tools.append(tool)
                seen_names.add(tool.name)

    return general_tools


def _build_states(graph: AgentGraph, general_tools: list[ToolDefinition]) -> list[dict[str, Any]]:
    """Build states array from graph nodes."""
    states: list[dict[str, Any]] = []
    general_tool_names = {t.name for t in general_tools}

    entry_node = graph.nodes.get(graph.entry_node_id)
    if entry_node:
        states.append(_convert_node_to_state(entry_node, general_tool_names))

    for node_id, node in graph.nodes.items():
        if node_id != graph.entry_node_id:
            states.append(_convert_node_to_state(node, general_tool_names))

    return states


def _convert_node_to_state(node: AgentNode, general_tool_names: set[str]) -> dict[str, Any]:
    """Convert an AgentNode to a Retell LLM state."""
    state: dict[str, Any] = {
        "name": node.id,
        "state_prompt": node.state_prompt,
        "edges": [_convert_transition_to_edge(t) for t in node.transitions],
    }

    state_specific_tools = [t for t in node.tools if t.name not in general_tool_names]
    state["tools"] = [_convert_tool(t) for t in state_specific_tools]

    return state


def _convert_transition_to_edge(transition) -> dict[str, Any]:
    """Convert a Transition to a Retell LLM edge."""
    return {
        "destination_state_name": transition.target_node_id,
        "description": transition.condition.value,
    }


def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert a ToolDefinition to Retell LLM tool format."""
    result: dict[str, Any] = {
        "type": "custom",
        "name": tool.name,
        "description": tool.description,
    }
    if tool.parameters:
        result["parameters"] = tool.parameters
    return result
