"""Retell Conversation Flow exporter."""

import json
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition


class RetellCFExporter:
    """Exports AgentGraph to Retell Conversation Flow format."""

    format_id = "retell-cf"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="Retell CF",
            description="Conversation Flow with multi-state routing for Retell AI",
            ext="json",
        )

    def export(self, graph: AgentGraph) -> str:
        return json.dumps(export_retell_cf(graph), indent=2)


def export_retell_cf(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to Retell Conversation Flow format.

    Converts the unified AgentGraph representation to Retell's Conversation
    Flow format with nodes, edges, and tools at the root level.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in Retell Conversation Flow JSON format.
    """
    metadata = graph.source_metadata or {}

    result: dict[str, Any] = {
        "start_node_id": graph.entry_node_id,
        "nodes": _build_nodes(graph),
        "start_speaker": metadata.get("start_speaker", "agent"),
        "model_choice": metadata.get("model_choice", {"type": "cascading", "model": "gpt-4o"}),
    }

    # Add global_prompt if present
    general_prompt = metadata.get("general_prompt", "")
    if general_prompt:
        result["global_prompt"] = general_prompt

    all_tools = _collect_all_tools(graph)
    if all_tools:
        result["tools"] = [_convert_tool(t) for t in all_tools]

    if "conversation_flow_id" in metadata:
        result["conversation_flow_id"] = metadata["conversation_flow_id"]
    if "version" in metadata:
        result["version"] = metadata["version"]
    if "model_temperature" in metadata:
        result["model_temperature"] = metadata["model_temperature"]
    if "tool_call_strict_mode" in metadata:
        result["tool_call_strict_mode"] = metadata["tool_call_strict_mode"]
    if "knowledge_base_ids" in metadata:
        result["knowledge_base_ids"] = metadata["knowledge_base_ids"]
    if "default_dynamic_variables" in metadata:
        result["default_dynamic_variables"] = metadata["default_dynamic_variables"]

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
            "text": node.state_prompt,
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
    """Collect and deduplicate all tools from all nodes.

    Only includes tools that can be exported to Retell CF format.
    Built-in actions like end_call and transfer_call are handled via node
    types and edges. Custom tools require a URL (webhook endpoint) to be
    valid in Retell CF.
    """
    seen_names: set[str] = set()
    tools: list[ToolDefinition] = []

    builtin_actions = {"end_call", "transfer_call"}

    for node in graph.nodes.values():
        for tool in node.tools:
            if tool.name in builtin_actions:
                continue
            # Custom tools require a URL - skip if not present
            if tool.type == "custom" and not tool.url:
                continue
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
