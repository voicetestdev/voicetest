"""Retell LLM (single/multi-prompt) JSON importer."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    ToolDefinition,
    Transition,
    TransitionCondition,
)


class RetellLLMTool(BaseModel):
    """Retell LLM tool definition."""

    model_config = ConfigDict(extra="ignore")

    type: str
    name: str
    description: str = ""
    url: str | None = None
    parameters: dict[str, Any] | None = None


class RetellLLMEdge(BaseModel):
    """Retell LLM state edge definition."""

    model_config = ConfigDict(extra="ignore")

    destination_state_name: str
    description: str = ""
    parameters: dict[str, Any] | None = None


class RetellLLMState(BaseModel):
    """Retell LLM state definition."""

    model_config = ConfigDict(extra="ignore")

    name: str
    state_prompt: str = ""
    edges: list[RetellLLMEdge] = []
    tools: list[RetellLLMTool] = []


class RetellLLMConfig(BaseModel):
    """Retell LLM configuration."""

    model_config = ConfigDict(extra="ignore")

    llm_id: str | None = None
    model: str = "gpt-4o"
    general_prompt: str = ""
    begin_message: str | None = None
    general_tools: list[RetellLLMTool] = []
    states: list[RetellLLMState] = []


class RetellLLMImporter:
    """Import Retell LLM (single/multi-prompt) JSON."""

    @property
    def source_type(self) -> str:
        return "retell-llm"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="retell-llm",
            description="Import Retell LLM (single/multi-prompt) JSON exports",
            file_patterns=["*.json"],
        )

    def _unwrap_config(self, config: dict) -> dict:
        """Unwrap retellLlmData if present (dashboard export format).

        Supports both:
        - Top-level format (official API): {"general_prompt": ..., "states": ...}
        - Wrapped format (dashboard): {"retellLlmData": {"general_prompt": ..., "states": ...}}

        Raises ValueError if LLM fields exist at both levels (ambiguous).
        """
        llm_fields = {"general_prompt", "llm_id", "states"}
        has_wrapper = "retellLlmData" in config
        has_top_level = bool(llm_fields & set(config.keys()))

        if has_wrapper and has_top_level:
            raise ValueError(
                "Ambiguous config: LLM fields found at both top level and inside retellLlmData"
            )

        if has_wrapper:
            return config["retellLlmData"]
        return config

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Detect Retell LLM format by checking for characteristic fields."""
        try:
            config = self._load_config(path_or_config)
            config = self._unwrap_config(config)
            has_general_prompt = "general_prompt" in config
            has_llm_id = "llm_id" in config
            has_states = "states" in config
            # Distinguish from Conversation Flow (which has start_node_id and nodes)
            is_not_flow = "start_node_id" not in config and "nodes" not in config
            return (has_general_prompt or has_llm_id or has_states) and is_not_flow
        except Exception:
            return False

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert Retell LLM JSON to AgentGraph."""
        raw_config = self._load_config(path_or_config)
        raw_config = self._unwrap_config(raw_config)
        llm_config = RetellLLMConfig.model_validate(raw_config)

        nodes: dict[str, AgentNode] = {}

        if llm_config.states:
            # Multi-state: each state becomes a node
            for i, state in enumerate(llm_config.states):
                transitions = [self._convert_edge(edge) for edge in state.edges]
                tools = [self._convert_tool(t) for t in state.tools]
                # Add general tools to each state
                tools.extend([self._convert_tool(t) for t in llm_config.general_tools])

                nodes[state.name] = AgentNode(
                    id=state.name,
                    state_prompt=state.state_prompt,  # State-specific only, NOT merged
                    transitions=transitions,
                    tools=tools or [],
                    metadata={"state_index": i},
                )

            entry_node_id = llm_config.states[0].name
        else:
            # Single-prompt: create one node (general_prompt becomes state_prompt)
            tools = [self._convert_tool(t) for t in llm_config.general_tools]
            nodes["main"] = AgentNode(
                id="main",
                state_prompt=llm_config.general_prompt,
                tools=tools or [],
                transitions=[],
            )
            entry_node_id = "main"

        return AgentGraph(
            nodes=nodes,
            entry_node_id=entry_node_id,
            source_type="retell-llm",
            source_metadata={
                "llm_id": llm_config.llm_id,
                "model": llm_config.model,
                "begin_message": llm_config.begin_message,
                "general_prompt": llm_config.general_prompt,  # Stored separately
            },
            default_model=llm_config.model,
        )

    def _load_config(self, path_or_config: str | Path | dict) -> dict[str, Any]:
        """Load config from path or return dict directly."""
        if isinstance(path_or_config, dict):
            return path_or_config
        path = Path(path_or_config)
        return json.loads(path.read_text())

    def _convert_edge(self, edge: RetellLLMEdge) -> Transition:
        """Convert Retell LLM edge to Transition."""
        return Transition(
            target_node_id=edge.destination_state_name,
            condition=TransitionCondition(
                type="llm_prompt",
                value=edge.description,
            ),
            description=edge.description,
        )

    def _convert_tool(self, tool: RetellLLMTool) -> ToolDefinition:
        """Convert Retell LLM tool to ToolDefinition."""
        return ToolDefinition(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters or {},
        )
