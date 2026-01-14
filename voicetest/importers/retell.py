"""Retell Conversation Flow JSON importer."""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from voicetest.importers.base import ImporterInfo
from voicetest.models.agent import (
    AgentGraph,
    AgentNode,
    Transition,
    TransitionCondition,
)


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
    start_node_id: str
    nodes: list[RetellNode]


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

        nodes: dict[str, AgentNode] = {}
        for retell_node in retell.nodes:
            transitions = [self._convert_edge(edge) for edge in retell_node.edges]
            nodes[retell_node.id] = AgentNode(
                id=retell_node.id,
                instructions=retell_node.instruction.text,
                transitions=transitions,
                metadata={"retell_type": retell_node.type},
            )

        return AgentGraph(
            nodes=nodes,
            entry_node_id=retell.start_node_id,
            source_type="retell",
            source_metadata={"conversation_flow_id": retell.conversation_flow_id},
        )

    def _load_config(self, path_or_config: str | Path | dict) -> dict[str, Any]:
        """Load config from path or return dict directly."""
        if isinstance(path_or_config, dict):
            return path_or_config
        path = Path(path_or_config)
        return json.loads(path.read_text())

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
