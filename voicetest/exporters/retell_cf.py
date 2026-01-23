"""Retell Conversation Flow exporter."""

from typing import Any

from voicetest.models.agent import AgentGraph, AgentNode, ToolDefinition


def export_retell_cf(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to Retell Conversation Flow format.

    Converts the unified AgentGraph representation to Retell's Conversation
    Flow format with nodes, edges, and tools at the root level.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in Retell Conversation Flow JSON format.
    """
    result: dict[str, Any] = {
        "start_node_id": graph.entry_node_id,
        "nodes": _build_nodes(graph),
    }

    all_tools = _collect_all_tools(graph)
    if all_tools:
        result["tools"] = [_convert_tool(t) for t in all_tools]

    if graph.source_metadata:
        if "conversation_flow_id" in graph.source_metadata:
            result["conversation_flow_id"] = graph.source_metadata["conversation_flow_id"]
        if "version" in graph.source_metadata:
            result["version"] = graph.source_metadata["version"]
        if "model_choice" in graph.source_metadata:
            result["model_choice"] = graph.source_metadata["model_choice"]
        if "model_temperature" in graph.source_metadata:
            result["model_temperature"] = graph.source_metadata["model_temperature"]
        if "tool_call_strict_mode" in graph.source_metadata:
            result["tool_call_strict_mode"] = graph.source_metadata["tool_call_strict_mode"]
        if "start_speaker" in graph.source_metadata:
            result["start_speaker"] = graph.source_metadata["start_speaker"]
        if "knowledge_base_ids" in graph.source_metadata:
            result["knowledge_base_ids"] = graph.source_metadata["knowledge_base_ids"]
        if "default_dynamic_variables" in graph.source_metadata:
            result["default_dynamic_variables"] = graph.source_metadata["default_dynamic_variables"]

    return result


def _build_nodes(graph: AgentGraph) -> list[dict[str, Any]]:
    """Build nodes array from graph."""
    return [_convert_node(node) for node in graph.nodes.values()]


def _convert_node(node: AgentNode) -> dict[str, Any]:
    """Convert an AgentNode to a Retell Conversation Flow node."""
    node_type = node.metadata.get("retell_type", "conversation")

    return {
        "id": node.id,
        "type": node_type,
        "instruction": {
            "type": "prompt",
            "text": node.instructions,
        },
        "edges": [_convert_transition_to_edge(t, i) for i, t in enumerate(node.transitions)],
    }


def _convert_transition_to_edge(transition, index: int) -> dict[str, Any]:
    """Convert a Transition to a Retell Conversation Flow edge."""
    edge: dict[str, Any] = {
        "id": f"edge_{transition.target_node_id}_{index}",
        "destination_node_id": transition.target_node_id,
    }

    if transition.condition.type == "equation":
        edge["transition_condition"] = {
            "type": "equation",
            "equation": transition.condition.value,
        }
    else:
        edge["transition_condition"] = {
            "type": "prompt",
            "prompt": transition.condition.value,
        }

    return edge


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
    """Convert a ToolDefinition to Retell Conversation Flow tool format."""
    result: dict[str, Any] = {
        "type": tool.type,
        "name": tool.name,
        "description": tool.description,
    }
    if tool.parameters:
        result["parameters"] = tool.parameters
    return result
