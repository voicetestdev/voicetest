"""VAPI assistant and squad JSON exporter."""

import json
from typing import Any

from voicetest.exporters.base import ExporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition


class VAPIAssistantExporter:
    """Exports AgentGraph to VAPI single assistant format."""

    format_id = "vapi-assistant"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="VAPI Assistant",
            description="Single assistant config for VAPI (merges all nodes)",
            ext="json",
        )

    def export(self, graph: AgentGraph) -> str:
        return json.dumps(export_vapi_assistant(graph), indent=2)


class VAPISquadExporter:
    """Exports AgentGraph to VAPI squad format."""

    format_id = "vapi-squad"

    def get_info(self) -> ExporterInfo:
        return ExporterInfo(
            format_id=self.format_id,
            name="VAPI Squad",
            description="Multi-assistant squad for VAPI (preserves node structure)",
            ext="json",
        )

    def export(self, graph: AgentGraph) -> str:
        return json.dumps(export_vapi_squad(graph), indent=2)


def export_vapi_assistant(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to VAPI single assistant format.

    Combines all nodes into a single assistant with merged instructions.
    Multi-node graphs lose their state machine structure.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in VAPI assistant JSON format.
    """
    return _export_assistant(graph)


def export_vapi_squad(graph: AgentGraph) -> dict[str, Any]:
    """Export AgentGraph to VAPI squad format.

    Each node becomes a separate assistant in the squad.
    Transitions become handoff tools between assistants.

    Args:
        graph: The agent graph to export.

    Returns:
        Dictionary in VAPI squad JSON format.
    """
    return _export_squad(graph)


def _export_assistant(graph: AgentGraph) -> dict[str, Any]:
    """Export as single VAPI assistant."""
    result: dict[str, Any] = {}

    # Restore metadata from source
    if graph.source_metadata:
        if "assistant_id" in graph.source_metadata:
            result["id"] = graph.source_metadata["assistant_id"]
        if "name" in graph.source_metadata:
            result["name"] = graph.source_metadata["name"]

    # Build model configuration
    model_config = _build_model_config(graph)

    # Build system prompt from general_prompt + state_prompt (VAPI uses single system message)
    node = list(graph.nodes.values())[0] if graph.nodes else None
    if node:
        general_prompt = graph.source_metadata.get("general_prompt", "")
        if general_prompt and node.state_prompt:
            full_prompt = f"{general_prompt}\n\n{node.state_prompt}"
        else:
            full_prompt = node.state_prompt or general_prompt
        model_config["messages"] = [{"role": "system", "content": full_prompt}]

    result["model"] = model_config

    # Voice configuration
    if graph.source_metadata:
        voice_config = _build_voice_config(graph.source_metadata)
        if voice_config:
            result["voice"] = voice_config

    # Transcriber configuration
    if graph.source_metadata:
        transcriber_config = _build_transcriber_config(graph.source_metadata)
        if transcriber_config:
            result["transcriber"] = transcriber_config

    # First message
    if graph.source_metadata and "first_message" in graph.source_metadata:
        result["firstMessage"] = graph.source_metadata["first_message"]

    # Collect tools from the node - tools go inside model config for VAPI
    if node and node.tools:
        model_config["tools"] = [_convert_tool(t) for t in node.tools]

    return result


def _export_squad(graph: AgentGraph) -> dict[str, Any]:
    """Export as VAPI squad with multiple assistants."""
    result: dict[str, Any] = {}

    # Restore metadata
    if graph.source_metadata:
        if "squad_id" in graph.source_metadata:
            result["id"] = graph.source_metadata["squad_id"]
        if "name" in graph.source_metadata:
            result["name"] = graph.source_metadata["name"]

    members: list[dict[str, Any]] = []

    # Build ordered list starting with entry node
    ordered_nodes: list[AgentNode] = []
    entry_node = graph.nodes.get(graph.entry_node_id)
    if entry_node:
        ordered_nodes.append(entry_node)

    for node_id, node in graph.nodes.items():
        if node_id != graph.entry_node_id:
            ordered_nodes.append(node)

    # Convert each node to a squad member (only entry node gets general_prompt)
    for i, node in enumerate(ordered_nodes):
        is_entry = i == 0
        member = _convert_node_to_member(node, graph, is_entry=is_entry)
        members.append(member)

    result["members"] = members
    return result


def _convert_node_to_member(
    node: AgentNode, graph: AgentGraph, is_entry: bool = False
) -> dict[str, Any]:
    """Convert an AgentNode to a VAPI squad member."""
    assistant: dict[str, Any] = {
        "name": node.id,
    }

    # Only add general_prompt to entry node
    general_prompt = graph.source_metadata.get("general_prompt", "") if is_entry else ""
    if general_prompt and node.state_prompt:
        full_prompt = f"{general_prompt}\n\n{node.state_prompt}"
    else:
        full_prompt = node.state_prompt or general_prompt

    # Build model config
    model_config: dict[str, Any] = {
        "provider": "openai",
        "model": "gpt-4o",
        "messages": [{"role": "system", "content": full_prompt}],
    }

    # Add tools (regular tools + handoff tools for transitions)
    tools: list[dict[str, Any]] = []

    # Regular tools
    for tool in node.tools:
        tools.append(_convert_tool(tool))

    # Convert transitions to handoff tools
    if node.transitions:
        handoff_destinations: list[dict[str, Any]] = []
        for transition in node.transitions:
            handoff_destinations.append(
                {
                    "type": "assistant",
                    "assistantName": transition.target_node_id,
                    "description": transition.description or transition.condition.value,
                }
            )

        if handoff_destinations:
            tools.append(
                {
                    "type": "handoff",
                    "destinations": handoff_destinations,
                }
            )

    if tools:
        model_config["tools"] = tools

    assistant["model"] = model_config

    # First message from metadata
    if node.metadata and "first_message" in node.metadata:
        assistant["firstMessage"] = node.metadata["first_message"]

    return {"assistant": assistant}


def _build_model_config(graph: AgentGraph) -> dict[str, Any]:
    """Build model configuration from graph metadata."""
    model_config: dict[str, Any] = {}

    if graph.source_metadata:
        if "model_provider" in graph.source_metadata:
            model_config["provider"] = graph.source_metadata["model_provider"]
        if "model" in graph.source_metadata:
            model_config["model"] = graph.source_metadata["model"]
        if "temperature" in graph.source_metadata:
            model_config["temperature"] = graph.source_metadata["temperature"]
        if "max_tokens" in graph.source_metadata:
            model_config["maxTokens"] = graph.source_metadata["max_tokens"]

    # Set defaults if not present
    if "provider" not in model_config:
        model_config["provider"] = "openai"
    if "model" not in model_config:
        model_config["model"] = "gpt-4o"

    return model_config


def _build_voice_config(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build voice configuration from metadata."""
    voice_config: dict[str, Any] = {}
    if "voice_provider" in metadata:
        voice_config["provider"] = metadata["voice_provider"]
    if "voice_id" in metadata:
        voice_config["voiceId"] = metadata["voice_id"]
    return voice_config


def _build_transcriber_config(metadata: dict[str, Any]) -> dict[str, Any]:
    """Build transcriber configuration from metadata."""
    transcriber_config: dict[str, Any] = {}
    if "transcriber_provider" in metadata:
        transcriber_config["provider"] = metadata["transcriber_provider"]
    if "transcriber_model" in metadata:
        transcriber_config["model"] = metadata["transcriber_model"]
    if "transcriber_language" in metadata:
        transcriber_config["language"] = metadata["transcriber_language"]
    return transcriber_config


def _convert_tool(tool: ToolDefinition) -> dict[str, Any]:
    """Convert a ToolDefinition to VAPI tool format."""
    function_def: dict[str, Any] = {
        "name": tool.name,
        "description": tool.description,
    }
    if tool.parameters:
        function_def["parameters"] = tool.parameters

    return {
        "type": "function",
        "function": function_def,
    }
