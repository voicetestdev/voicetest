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
    with states, edges, and tools. Synthetic terminal nodes (end_call,
    transfer_call) are collapsed back into general_tools with edges removed.

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

    # Identify synthetic terminal nodes to collapse back into general_tools
    terminal_node_ids, terminal_tools = _collect_terminal_nodes(graph)

    general_tools = _extract_general_tools(graph, exclude_nodes=terminal_node_ids)
    all_general_tools = list(terminal_tools) + list(general_tools)
    if all_general_tools:
        result["general_tools"] = [_convert_tool(t) for t in all_general_tools]

    result["general_prompt"] = graph.source_metadata.get("general_prompt", "")
    result["states"] = _build_states(graph, general_tools, exclude_nodes=terminal_node_ids)

    return result


def _collect_terminal_nodes(graph: AgentGraph) -> tuple[set[str], list[ToolDefinition]]:
    """Identify synthetic terminal nodes (end_call/transfer_call) and extract their tools.

    Returns:
        Tuple of (terminal node IDs to exclude, tool definitions to restore as general_tools).
    """
    terminal_node_ids: set[str] = set()
    terminal_tools: list[ToolDefinition] = []

    for node_id, node in graph.nodes.items():
        if (
            (node.is_end_node() or node.is_transfer_node())
            and not node.state_prompt
            and not node.transitions
        ):
            terminal_node_ids.add(node_id)
            terminal_tools.extend(node.tools)

    return terminal_node_ids, terminal_tools


def _extract_general_tools(
    graph: AgentGraph,
    exclude_nodes: set[str] | None = None,
) -> list[ToolDefinition]:
    """Extract tools that appear in all nodes (general tools)."""
    exclude = exclude_nodes or set()
    if not graph.nodes:
        return []

    nodes_with_tools = [n for n in graph.nodes.values() if n.tools and n.id not in exclude]
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


def _build_states(
    graph: AgentGraph,
    general_tools: list[ToolDefinition],
    exclude_nodes: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Build states array from graph nodes, excluding synthetic terminal nodes."""
    exclude = exclude_nodes or set()
    states: list[dict[str, Any]] = []
    general_tool_names = {t.name for t in general_tools}

    entry_node = graph.nodes.get(graph.entry_node_id)
    if entry_node and entry_node.id not in exclude:
        states.append(_convert_node_to_state(entry_node, general_tool_names, exclude))

    for node_id, node in graph.nodes.items():
        if node_id != graph.entry_node_id and node_id not in exclude:
            states.append(_convert_node_to_state(node, general_tool_names, exclude))

    return states


def _convert_node_to_state(
    node: AgentNode,
    general_tool_names: set[str],
    exclude_edge_targets: set[str] | None = None,
) -> dict[str, Any]:
    """Convert an AgentNode to a Retell LLM state.

    Edges pointing to excluded nodes (synthetic terminal nodes) are stripped
    since those are represented as general_tools in the LLM format.
    """
    exclude = exclude_edge_targets or set()
    edges = [
        _convert_transition_to_edge(t) for t in node.transitions if t.target_node_id not in exclude
    ]
    state: dict[str, Any] = {
        "name": node.id,
        "state_prompt": node.state_prompt,
        "edges": edges,
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
