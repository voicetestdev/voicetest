"""Agent graph models representing the unified internal representation (IR).

These models define the source-agnostic representation that all importers
convert to. The AgentGraph captures the complete workflow structure.
"""

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class TransitionCondition(BaseModel):
    """Condition that triggers a transition between nodes.

    Supports multiple condition types:
    - llm_prompt: LLM evaluates a natural language condition
    - equation: Deterministic evaluation of a formula (e.g., {{age}} > 18)
    - tool_call: Transition triggered by specific tool invocation
    - always: Unconditional transition
    """

    type: Literal["llm_prompt", "equation", "tool_call", "always"]
    value: str


class Transition(BaseModel):
    """Edge from one node to another in the agent graph."""

    target_node_id: str
    condition: TransitionCondition
    description: str | None = None


class ToolDefinition(BaseModel):
    """Definition of a tool/function available to the agent."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    type: str = "custom"
    url: str | None = None


class AgentNode(BaseModel):
    """Single node (state) in the agent workflow graph.

    Each node represents a distinct conversational state with its own
    state-specific prompt, available tools, and possible transitions.
    The general_prompt is stored separately in AgentGraph.source_metadata.
    """

    id: str
    state_prompt: str
    tools: list[ToolDefinition] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class GlobalMetric(BaseModel):
    """A metric that runs on all tests for an agent.

    Global metrics are evaluated against every test transcript,
    useful for compliance checks that should always pass.
    """

    name: str
    criteria: str
    threshold: float | None = None
    enabled: bool = True


class MetricsConfig(BaseModel):
    """Configuration for metric evaluation on an agent.

    Contains the default threshold and any global metrics
    that should run on all tests.
    """

    threshold: float = 0.7
    global_metrics: list[GlobalMetric] = Field(default_factory=list)


class AgentGraph(BaseModel):
    """Complete agent workflow graph.

    This is the unified internal representation (IR) that all importers
    convert to. It captures the full structure of an agent's conversation
    flow including nodes, transitions, and metadata.
    """

    nodes: dict[str, AgentNode]
    entry_node_id: str
    source_type: str
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    default_model: str | None = Field(
        default=None, description="Default LLM model for this agent (from import)"
    )

    def get_entry_node(self) -> AgentNode:
        """Return the entry node of the graph."""
        return self.nodes[self.entry_node_id]

    def get_node(self, node_id: str) -> AgentNode | None:
        """Return a node by ID, or None if not found."""
        return self.nodes.get(node_id)
