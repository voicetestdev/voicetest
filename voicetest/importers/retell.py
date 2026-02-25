"""Retell Conversation Flow JSON importer."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import field_validator

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition


class RetellTransitionCondition(BaseModel):
    """Retell edge transition condition."""

    model_config = ConfigDict(extra="ignore")

    type: str
    prompt: str | None = None
    equation: str | None = None


class RetellEdge(BaseModel):
    """Retell node edge definition."""

    model_config = ConfigDict(extra="ignore")

    id: str
    destination_node_id: str
    transition_condition: RetellTransitionCondition


class RetellInstruction(BaseModel):
    """Retell node instruction."""

    model_config = ConfigDict(extra="ignore")

    type: str
    text: str


class RetellTool(BaseModel):
    """Retell Conversation Flow tool definition."""

    model_config = ConfigDict(extra="ignore")

    type: str
    name: str
    description: str = ""
    tool_id: str | None = None
    url: str | None = None
    method: str | None = None
    parameters: dict[str, Any] | None = None


class RetellModelChoice(BaseModel):
    """Retell model choice configuration."""

    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    model: str | None = None
    high_priority: bool | None = None


class RetellNode(BaseModel):
    """Retell conversation node."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    instruction: RetellInstruction
    edges: list[RetellEdge] = []


class RetellConfig(BaseModel):
    """Retell Conversation Flow configuration."""

    model_config = ConfigDict(extra="ignore")

    conversation_flow_id: str | None = None
    version: int | None = None
    start_node_id: str
    nodes: list[RetellNode]
    tools: list[RetellTool] = []
    global_prompt: str | None = None
    model_choice: RetellModelChoice | None = None
    model_temperature: float | None = None
    tool_call_strict_mode: bool | None = None
    start_speaker: str | None = None
    knowledge_base_ids: list[str] = []
    default_dynamic_variables: dict[str, str] = {}

    @field_validator("tools", mode="before")
    @classmethod
    def tools_default(cls, v):
        return v if v is not None else []

    @field_validator("knowledge_base_ids", mode="before")
    @classmethod
    def kb_ids_default(cls, v):
        return v if v is not None else []

    @field_validator("default_dynamic_variables", mode="before")
    @classmethod
    def dyn_vars_default(cls, v):
        return v if v is not None else {}


def _unwrap_agent_envelope(config: dict[str, Any]) -> dict[str, Any]:
    """Extract the CF dict from a Retell UI agent wrapper if present.

    The Retell UI exports an agent envelope with the conversation flow
    nested under ``conversationFlow``. This extracts that inner dict
    so the importer can process it uniformly.
    """
    if "conversationFlow" in config:
        return config["conversationFlow"]
    return config


class RetellImporter:
    """Import Retell Conversation Flow JSON."""

    @property
    def source_type(self) -> str:
        return "retell"

    def get_info(self) -> ImporterInfo:
        return ImporterInfo(
            source_type="retell",
            description="Import Retell Conversation Flow JSON exports",
            file_patterns=["*.json"],
        )

    def can_import(self, path_or_config: str | Path | dict) -> bool:
        """Detect Retell format by checking for characteristic fields."""
        try:
            config = self._load_config(path_or_config)
            return "start_node_id" in config and "nodes" in config
        except Exception:
            return False

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert Retell JSON to AgentGraph."""
        raw_config = self._load_config(path_or_config)
        retell = RetellConfig.model_validate(raw_config)

        global_tools = [self._convert_tool(t) for t in retell.tools]

        nodes: dict[str, AgentNode] = {}
        for retell_node in retell.nodes:
            transitions = [self._convert_edge(edge) for edge in retell_node.edges]

            nodes[retell_node.id] = AgentNode(
                id=retell_node.id,
                state_prompt=retell_node.instruction.text,  # State-specific only
                tools=global_tools if global_tools else [],
                transitions=transitions,
                metadata={"retell_type": retell_node.type},
            )

        source_metadata: dict[str, Any] = {
            "conversation_flow_id": retell.conversation_flow_id,
            "general_prompt": retell.global_prompt or "",  # Stored separately
        }
        if retell.version is not None:
            source_metadata["version"] = retell.version
        if retell.model_choice:
            source_metadata["model_choice"] = retell.model_choice.model_dump(exclude_none=True)
        if retell.model_temperature is not None:
            source_metadata["model_temperature"] = retell.model_temperature
        if retell.tool_call_strict_mode is not None:
            source_metadata["tool_call_strict_mode"] = retell.tool_call_strict_mode
        if retell.start_speaker:
            source_metadata["start_speaker"] = retell.start_speaker
        if retell.knowledge_base_ids:
            source_metadata["knowledge_base_ids"] = retell.knowledge_base_ids
        if retell.default_dynamic_variables:
            source_metadata["default_dynamic_variables"] = retell.default_dynamic_variables

        # Extract default model from model_choice if available
        default_model = None
        if retell.model_choice and retell.model_choice.model:
            default_model = retell.model_choice.model

        return AgentGraph(
            nodes=nodes,
            entry_node_id=retell.start_node_id,
            source_type="retell",
            source_metadata=source_metadata,
            default_model=default_model,
        )

    def _load_config(self, path_or_config: str | Path | dict) -> dict[str, Any]:
        """Load config from path or return dict directly.

        Handles both bare CF dicts and the Retell UI agent wrapper format
        where the CF lives under the ``conversationFlow`` key.
        """
        if isinstance(path_or_config, dict):
            return _unwrap_agent_envelope(path_or_config)
        path = Path(path_or_config)
        raw = json.loads(path.read_text())
        return _unwrap_agent_envelope(raw)

    def _convert_edge(self, edge: RetellEdge) -> Transition:
        """Convert Retell edge to Transition."""
        condition_type = "llm_prompt"
        condition_value = edge.transition_condition.prompt or ""

        if edge.transition_condition.type == "equation":
            condition_type = "equation"
            condition_value = edge.transition_condition.equation or ""

        return Transition(
            target_node_id=edge.destination_node_id,
            condition=TransitionCondition(
                type=condition_type,
                value=condition_value,
            ),
        )

    def _convert_tool(self, tool: RetellTool) -> ToolDefinition:
        """Convert Retell tool to ToolDefinition."""
        return ToolDefinition(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters or {},
            type=tool.type,
            url=tool.url,
            tool_id=tool.tool_id,
        )
