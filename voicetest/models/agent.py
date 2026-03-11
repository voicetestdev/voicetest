"""Agent graph models representing the unified internal representation (IR).

These models define the source-agnostic representation that all importers
convert to. The AgentGraph captures the complete workflow structure.
"""

from enum import StrEnum
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class NodeType(StrEnum):
    """Type of node in the agent workflow graph."""

    CONVERSATION = "conversation"
    LOGIC = "logic"
    EXTRACT = "extract"
    END = "end"
    TRANSFER = "transfer"


class EquationClause(BaseModel):
    """Single comparison clause in a deterministic equation condition."""

    left: str  # Variable name (e.g., "account_type")
    operator: str  # ==, !=, >, >=, <, <=, contains, not_contains, exists, not_exist
    right: str = ""  # Comparison value (empty for exists/not_exist)


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
    equations: list[EquationClause] = Field(default_factory=list)
    logical_operator: Literal["and", "or"] = "and"


class Transition(BaseModel):
    """Edge from one node to another in the agent graph."""

    target_node_id: str
    condition: TransitionCondition
    description: str | None = None


class TransitionOption(BaseModel):
    """Structured transition option for LLM signature input."""

    target: str
    condition: str
    condition_type: Literal["llm_prompt", "equation", "tool_call", "always"]
    description: str | None = None


class VariableExtraction(BaseModel):
    """Variable to extract from conversation context via LLM."""

    name: str
    description: str
    type: str = "string"
    choices: list[str] = Field(default_factory=list)


class ToolDefinition(BaseModel):
    """Definition of a tool/function available to the agent."""

    name: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    type: str = "custom"
    url: str | None = None
    tool_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentNode(BaseModel):
    """Single node (state) in the agent workflow graph.

    Each node represents a distinct conversational state with its own
    state-specific prompt, available tools, and possible transitions.
    The general_prompt is stored separately in AgentGraph.source_metadata.
    """

    id: str
    state_prompt: str
    node_type: NodeType = NodeType.CONVERSATION
    tools: list[ToolDefinition] = Field(default_factory=list)
    transitions: list[Transition] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    variables_to_extract: list[VariableExtraction] = Field(default_factory=list)

    def model_post_init(self, __context: Any) -> None:
        """Infer node_type from structure when not explicitly set.

        Provides backward compatibility for stored JSON that predates
        the node_type field. Only runs inference when node_type is still
        the default (CONVERSATION).

        Note: model_copy(update=...) does NOT re-run model_post_init
        in Pydantic v2. Any model_copy that changes the structural type
        must include node_type in the update dict.
        """
        if self.node_type != NodeType.CONVERSATION:
            return
        if self.variables_to_extract and self._has_equation_transitions():
            self.node_type = NodeType.EXTRACT
        elif self._has_equation_transitions():
            self.node_type = NodeType.LOGIC

    def _has_equation_transitions(self) -> bool:
        """Check if transitions are equation-only (with optional always fallback)."""
        if not self.transitions:
            return False
        return all(t.condition.type in ("equation", "always") for t in self.transitions) and any(
            t.condition.type == "equation" for t in self.transitions
        )

    def is_logic_node(self) -> bool:
        """Check if this is a logic/branch node."""
        return self.node_type == NodeType.LOGIC

    def is_end_node(self) -> bool:
        """Check if this node ends the call."""
        return self.node_type == NodeType.END

    def is_transfer_node(self) -> bool:
        """Check if this node transfers the call."""
        return self.node_type == NodeType.TRANSFER

    def is_extract_node(self) -> bool:
        """Check if this is an extract-then-branch node."""
        return self.node_type == NodeType.EXTRACT


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
    snippets: dict[str, str] = Field(
        default_factory=dict,
        description="Named text snippets referenced via {%name%} in prompts",
    )
    default_model: str | None = Field(
        default=None, description="Default LLM model for this agent (from import)"
    )

    def get_entry_node(self) -> AgentNode:
        """Return the entry node of the graph."""
        return self.nodes[self.entry_node_id]

    def get_node(self, node_id: str) -> AgentNode | None:
        """Return a node by ID, or None if not found."""
        return self.nodes.get(node_id)
