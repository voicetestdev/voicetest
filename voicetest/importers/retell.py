"""Retell Conversation Flow JSON importer."""

import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel
from pydantic import ConfigDict
from pydantic import Field
from pydantic import field_validator

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import EquationClause
from voicetest.models.agent import NodeType
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.agent import VariableExtraction


_MUSTACHE_RE = re.compile(r"^\{\{(.+?)\}\}$")

_RETELL_TYPE_MAP: dict[str, NodeType] = {
    "conversation": NodeType.CONVERSATION,
    "logic_split": NodeType.LOGIC,
    "extract_dynamic_variables": NodeType.EXTRACT,
    "end": NodeType.END,
    "transfer_call": NodeType.TRANSFER,
}


def _strip_mustache(value: str) -> str:
    """Strip {{}} wrapper from Retell variable references."""
    m = _MUSTACHE_RE.match(value.strip())
    return m.group(1) if m else value


class RetellEquation(BaseModel):
    """Single equation clause from Retell's structured equation format."""

    model_config = ConfigDict(extra="ignore")

    left: str
    operator: str
    right: str = ""


class RetellTransitionCondition(BaseModel):
    """Retell edge transition condition."""

    model_config = ConfigDict(extra="ignore")

    type: str
    prompt: str | None = None
    equations: list[RetellEquation] | None = None
    operator: str | None = None


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
    transfer_destination: dict[str, Any] | None = None
    transfer_option: dict[str, Any] | None = None


class RetellModelChoice(BaseModel):
    """Retell model choice configuration."""

    model_config = ConfigDict(extra="ignore")

    type: str | None = None
    model: str | None = None
    high_priority: bool | None = None


class RetellVariable(BaseModel):
    """Retell extract_dynamic_variables variable specification."""

    model_config = ConfigDict(extra="ignore")

    name: str
    description: str
    type: str = "string"
    choices: list[str] = Field(default_factory=list)


class RetellNode(BaseModel):
    """Retell conversation node."""

    model_config = ConfigDict(extra="ignore")

    id: str
    type: str
    name: str | None = None
    instruction: RetellInstruction | None = None
    edges: list[RetellEdge] = []
    else_edge: RetellEdge | None = None
    always_edge: RetellEdge | None = None
    display_position: dict[str, float] | None = None
    variables: list[RetellVariable] = []


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
    begin_tag_display_position: dict[str, float] | None = None

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


def _unwrap_agent_envelope(
    config: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    """Extract the CF dict and agent envelope from a Retell UI agent wrapper.

    The Retell UI exports an agent envelope with the conversation flow
    nested under ``conversationFlow``. This extracts the inner CF dict
    and returns the remaining agent-level fields (voice_id, language, etc.)
    as a separate envelope dict for round-trip preservation.

    Returns:
        Tuple of (cf_dict, agent_envelope_or_None).
    """
    if "conversationFlow" in config:
        cf_keys = {"conversationFlow"}
        envelope = {k: v for k, v in config.items() if k not in cf_keys}
        return config["conversationFlow"], envelope if envelope else None
    return config, None


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
            config, _ = self._load_config(path_or_config)
            return "start_node_id" in config and "nodes" in config
        except Exception:
            return False

    def import_agent(self, path_or_config: str | Path | dict) -> AgentGraph:
        """Convert Retell JSON to AgentGraph."""
        raw_config, agent_envelope = self._load_config(path_or_config)
        retell = RetellConfig.model_validate(raw_config)

        global_tools = [self._convert_tool(t) for t in retell.tools]

        nodes: dict[str, AgentNode] = {}
        for retell_node in retell.nodes:
            transitions = [self._convert_edge(edge) for edge in retell_node.edges]
            if retell_node.else_edge:
                transitions.append(self._convert_else_edge(retell_node.else_edge))
            if retell_node.always_edge:
                transitions.append(self._convert_else_edge(retell_node.always_edge))

            metadata: dict[str, Any] = {"retell_type": retell_node.type}
            if retell_node.name:
                metadata["name"] = retell_node.name
            if retell_node.display_position:
                metadata["display_position"] = retell_node.display_position

            variables_to_extract = [
                VariableExtraction(
                    name=v.name,
                    description=v.description,
                    type=v.type,
                    choices=v.choices,
                )
                for v in retell_node.variables
            ]

            nodes[retell_node.id] = AgentNode(
                id=retell_node.id,
                state_prompt=retell_node.instruction.text if retell_node.instruction else "",
                node_type=_RETELL_TYPE_MAP.get(retell_node.type, NodeType.CONVERSATION),
                tools=global_tools if global_tools else [],
                transitions=transitions,
                metadata=metadata,
                variables_to_extract=variables_to_extract,
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
        if retell.begin_tag_display_position:
            source_metadata["begin_tag_display_position"] = retell.begin_tag_display_position
        if agent_envelope:
            source_metadata["agent_envelope"] = agent_envelope

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

    def _load_config(
        self, path_or_config: str | Path | dict
    ) -> tuple[dict[str, Any], dict[str, Any] | None]:
        """Load config from path or return dict directly.

        Handles both bare CF dicts and the Retell UI agent wrapper format
        where the CF lives under the ``conversationFlow`` key.

        Returns:
            Tuple of (cf_dict, agent_envelope_or_None).
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
        equation_clauses: list[EquationClause] = []
        logical_operator: str = "and"

        if edge.transition_condition.type == "equation":
            condition_type = "equation"
            if edge.transition_condition.operator == "||":
                logical_operator = "or"
            if edge.transition_condition.equations:
                equation_clauses = [
                    EquationClause(
                        left=_strip_mustache(eq.left),
                        operator=eq.operator,
                        right=_strip_mustache(eq.right),
                    )
                    for eq in edge.transition_condition.equations
                ]
                # Build a readable value string from structured equations
                joiner = " OR " if logical_operator == "or" else " AND "
                parts = []
                for eq in equation_clauses:
                    if eq.operator in ("exists", "not_exist"):
                        parts.append(f"{eq.left} {eq.operator}")
                    else:
                        parts.append(f"{eq.left} {eq.operator} {eq.right}")
                condition_value = joiner.join(parts)

        return Transition(
            target_node_id=edge.destination_node_id,
            condition=TransitionCondition(
                type=condition_type,
                value=condition_value,
                equations=equation_clauses,
                logical_operator=logical_operator,
            ),
        )

    def _convert_else_edge(self, edge: RetellEdge) -> Transition:
        """Convert Retell else_edge to an always-type Transition."""
        return Transition(
            target_node_id=edge.destination_node_id,
            condition=TransitionCondition(
                type="always",
                value="Else",
            ),
        )

    def _convert_tool(self, tool: RetellTool) -> ToolDefinition:
        """Convert Retell tool to ToolDefinition.

        Transfer tools carry transfer_destination and transfer_option in
        metadata so the CF exporter can emit proper transfer_call nodes.
        """
        metadata: dict[str, Any] = {}
        if tool.transfer_destination:
            metadata["transfer_destination"] = tool.transfer_destination
        if tool.transfer_option:
            metadata["transfer_option"] = tool.transfer_option
        return ToolDefinition(
            name=tool.name,
            description=tool.description,
            parameters=tool.parameters or {},
            type=tool.type,
            url=tool.url,
            tool_id=tool.tool_id,
            metadata=metadata,
        )
