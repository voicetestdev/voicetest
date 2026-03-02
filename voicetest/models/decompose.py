"""Decomposition models for splitting agent graphs into sub-agents.

These models represent the analysis, planning, and output of decomposing
a monolithic or multi-node AgentGraph into M coherent sub-agents with
an orchestrator manifest describing the handoff flow.
"""

from pydantic import BaseModel
from pydantic import Field

from voicetest.models.agent import AgentGraph


class NodeAssignment(BaseModel):
    """Assignment of a graph node to a sub-agent."""

    node_id: str
    sub_agent_id: str
    rationale: str


class PromptSegment(BaseModel):
    """A segment of a monolithic prompt assigned to a sub-agent."""

    sub_agent_id: str
    segment_text: str
    purpose: str


class SubAgentSpec(BaseModel):
    """Specification for one sub-agent in a decomposition plan."""

    sub_agent_id: str
    name: str
    description: str
    node_ids: list[str]  # existing node IDs or "NEW:<purpose>"
    prompt_segments: list[PromptSegment] = Field(default_factory=list)


class HandoffRule(BaseModel):
    """Rule describing when control passes between sub-agents."""

    source_sub_agent_id: str
    target_sub_agent_id: str
    condition: str
    description: str | None = None


class DecompositionPlan(BaseModel):
    """LLM-generated plan for decomposing an agent graph."""

    num_sub_agents: int
    sub_agents: list[SubAgentSpec]
    handoff_rules: list[HandoffRule]
    rationale: str


class SubAgentManifestEntry(BaseModel):
    """Entry in the orchestrator manifest for one sub-agent."""

    sub_agent_id: str
    name: str
    description: str
    filename: str


class OrchestratorManifest(BaseModel):
    """Manifest describing the orchestrator and sub-agent handoff flow."""

    entry_sub_agent_id: str
    sub_agents: list[SubAgentManifestEntry]
    handoff_rules: list[HandoffRule]


class DecompositionResult(BaseModel):
    """Complete result of a decomposition: plan + built sub-graphs + manifest."""

    plan: DecompositionPlan
    sub_graphs: dict[str, AgentGraph]  # sub_agent_id -> graph
    manifest: OrchestratorManifest
