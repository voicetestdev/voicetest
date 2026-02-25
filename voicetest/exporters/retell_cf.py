"""Retell Conversation Flow exporter."""

import json
import re
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition


_TERMINAL_TOOL_TYPES = {"end_call", "transfer_call"}


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
        """Export as Retell UI-importable agent JSON.

        Wraps the bare conversation flow in the agent envelope that
        Retell's UI import expects (response_engine + conversationFlow).
        Preserves agent-level fields (voice_id, language, etc.) from
        the original import when available.
        """
        cf = export_retell_cf(graph)
        metadata = graph.source_metadata or {}
        agent_envelope = metadata.get("agent_envelope")
        agent_wrapper = _wrap_for_retell_ui(cf, agent_envelope)
        return json.dumps(agent_wrapper, indent=2)


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

    default_model = graph.default_model or "gpt-4o"
    model_choice = metadata.get("model_choice", {"type": "cascading", "model": default_model})

    begin_message = metadata.get("begin_message", "")

    result: dict[str, Any] = {
        "start_node_id": graph.entry_node_id,
        "nodes": _build_nodes(graph, graph.entry_node_id, begin_message),
        "start_speaker": metadata.get("start_speaker", "agent"),
        "model_choice": model_choice,
    }

    # Add global_prompt if present
    general_prompt = metadata.get("general_prompt", "")
    if general_prompt:
        result["global_prompt"] = general_prompt

    all_tools = _collect_all_tools(graph)
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


def _find_terminal_tools(graph: AgentGraph) -> list[ToolDefinition]:
    """Collect unique tools with type in {end_call, transfer_call} across all nodes."""
    seen_names: set[str] = set()
    tools: list[ToolDefinition] = []

    for node in graph.nodes.values():
        for tool in node.tools:
            if tool.type in _TERMINAL_TOOL_TYPES and tool.name not in seen_names:
                tools.append(tool)
                seen_names.add(tool.name)

    return tools


def _find_nodes_mentioning(graph: AgentGraph, tool_name: str) -> list[str]:
    """Return node IDs where tool_name appears in state_prompt (word-boundary match)."""
    pattern = re.compile(r"\b" + re.escape(tool_name) + r"\b")
    return [node.id for node in graph.nodes.values() if pattern.search(node.state_prompt)]


def _has_node_of_type(graph: AgentGraph, retell_type: str) -> bool:
    """Check if graph already has a node with the given retell_type in metadata."""
    return any(node.metadata.get("retell_type") == retell_type for node in graph.nodes.values())


def _synthesize_end_node(tool: ToolDefinition) -> dict[str, Any]:
    """Build a CF end node dict from an end_call tool."""
    return {
        "id": f"synth_{tool.name}",
        "type": "end",
        "instruction": {
            "type": "prompt",
            "text": tool.description or "End the call.",
        },
    }


_DEFAULT_TRANSFER_DESTINATION = {"type": "predefined", "number": "+16505555555"}
_DEFAULT_TRANSFER_OPTION = {"type": "cold_transfer", "show_transferee_as_caller": True}


def _synthesize_transfer_node(tool: ToolDefinition, failure_dest_id: str) -> dict[str, Any]:
    """Build a CF transfer_call node dict from a transfer_call tool.

    Retell's transfer_call nodes use a singular ``edge`` (failure edge)
    instead of the ``edges`` array that conversation nodes use, plus
    required ``transfer_destination`` and ``transfer_option`` fields.
    Uses values from tool.metadata if the importer preserved them,
    otherwise falls back to placeholder defaults.
    """
    node_id = f"synth_{tool.name}"
    transfer_dest = tool.metadata.get("transfer_destination", _DEFAULT_TRANSFER_DESTINATION)
    transfer_opt = tool.metadata.get("transfer_option", _DEFAULT_TRANSFER_OPTION)
    return {
        "id": node_id,
        "type": "transfer_call",
        "instruction": {
            "type": "prompt",
            "text": tool.description or "Transferring the call.",
        },
        "transfer_destination": transfer_dest,
        "transfer_option": transfer_opt,
        "edge": {
            "id": f"edge_{node_id}_transfer_failed",
            "destination_node_id": failure_dest_id,
            "condition": "Transfer failed",
            "transition_condition": {
                "type": "prompt",
                "prompt": "Transfer failed",
            },
        },
    }


def _build_nodes(graph: AgentGraph, entry_node_id: str, begin_message: str) -> list[dict[str, Any]]:
    """Build nodes array from graph, synthesizing terminal nodes from tools.

    Processes end_call tools first so the end node ID is available as
    the failure destination for transfer_call nodes.
    """
    nodes = [
        _convert_node(node, is_entry=(node.id == entry_node_id), begin_message=begin_message)
        for node in graph.nodes.values()
    ]

    terminal_tools = _find_terminal_tools(graph)
    end_tools = [t for t in terminal_tools if t.type == "end_call"]
    transfer_tools = [t for t in terminal_tools if t.type == "transfer_call"]

    # Synthesize end nodes first
    end_node_id: str | None = None
    for tool in end_tools:
        if _has_node_of_type(graph, "end"):
            break
        synth_node = _synthesize_end_node(tool)
        end_node_id = synth_node["id"]
        _wire_edges_for_tool(nodes, graph, tool, synth_node)
        nodes.append(synth_node)

    # Find an existing end node ID if we didn't just create one
    if end_node_id is None:
        for node in graph.nodes.values():
            if node.metadata.get("retell_type") == "end":
                end_node_id = node.id
                break

    # Synthesize transfer nodes, failure edges point to the end node
    for tool in transfer_tools:
        if _has_node_of_type(graph, "transfer_call"):
            break
        failure_dest = end_node_id or entry_node_id
        synth_node = _synthesize_transfer_node(tool, failure_dest)
        _wire_edges_for_tool(nodes, graph, tool, synth_node)
        nodes.append(synth_node)

    return nodes


def _wire_edges_for_tool(
    nodes: list[dict[str, Any]],
    graph: AgentGraph,
    tool: ToolDefinition,
    synth_node: dict[str, Any],
) -> None:
    """Append edges from nodes whose prompts mention the tool to the synthesized node."""
    mentioning_ids = _find_nodes_mentioning(graph, tool.name)
    for cf_node in nodes:
        if cf_node["id"] in mentioning_ids:
            if tool.type == "end_call":
                condition_text = "Conversation is complete and call should end"
            else:
                condition_text = f"Caller should be transferred ({tool.description})"

            edge_id = f"edge_{cf_node['id']}_to_{synth_node['id']}_{len(cf_node['edges'])}"
            cf_node["edges"].append(
                {
                    "id": edge_id,
                    "destination_node_id": synth_node["id"],
                    "transition_condition": {
                        "type": "prompt",
                        "prompt": condition_text,
                    },
                }
            )


def _convert_node(
    node: AgentNode, *, is_entry: bool = False, begin_message: str = ""
) -> dict[str, Any]:
    """Convert an AgentNode to a Retell Conversation Flow node."""
    node_type = node.metadata.get("retell_type", "conversation")

    prompt_text = node.state_prompt
    if is_entry and begin_message:
        prompt_text = f"[Begin message: {begin_message}]\n\n{prompt_text}"

    return {
        "id": node.id,
        "type": node_type,
        "instruction": {
            "type": "prompt",
            "text": prompt_text,
        },
        "edges": [
            _convert_transition_to_edge(t, node.id, i) for i, t in enumerate(node.transitions)
        ],
    }


def _convert_transition_to_edge(transition, source_node_id: str, index: int) -> dict[str, Any]:
    """Convert a Transition to a Retell Conversation Flow edge."""
    edge: dict[str, Any] = {
        "id": f"edge_{source_node_id}_to_{transition.target_node_id}_{index}",
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
    """Collect and deduplicate all non-terminal tools from all nodes.

    Terminal tool types (end_call, transfer_call) are converted to CF nodes
    by _build_nodes and excluded from the tools array.
    """
    seen_names: set[str] = set()
    tools: list[ToolDefinition] = []

    for node in graph.nodes.values():
        for tool in node.tools:
            if tool.type in _TERMINAL_TOOL_TYPES:
                continue
            if tool.name not in seen_names:
                tools.append(tool)
                seen_names.add(tool.name)

    return tools


def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert a ToolDefinition to Retell Conversation Flow tool format.

    Only called for non-terminal tools (custom, check_availability_cal, etc.).
    Terminal tool types are handled by _build_nodes as synthesized nodes.
    """
    result: dict[str, Any] = {
        "type": tool.type,
        "name": tool.name,
        "description": tool.description,
    }
    if tool.parameters:
        result["parameters"] = tool.parameters
    if tool.url:
        result["url"] = tool.url
    if tool.tool_id:
        result["tool_id"] = tool.tool_id
    return result


def _wrap_for_retell_ui(
    cf: dict[str, Any], agent_envelope: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Wrap a bare conversation flow dict in the agent envelope Retell's UI expects.

    Merges preserved agent-level fields (voice_id, language, etc.) from the
    original import so they survive the LLM→CF conversion round-trip.

    Terminal tools (end_call, transfer_call) are already excluded from the
    tools array by _collect_all_tools, so no additional filtering is needed.
    """
    cf_id = cf.get("conversation_flow_id", "")

    wrapper: dict[str, Any] = {
        "agent_id": "",
        "response_engine": {
            "type": "conversation-flow",
            "conversation_flow_id": cf_id,
        },
        "conversationFlow": cf,
    }

    if agent_envelope:
        for key, value in agent_envelope.items():
            if key not in ("response_engine", "conversationFlow"):
                wrapper[key] = value

    return wrapper
