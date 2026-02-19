"""Flow judge for validating conversation traversal through agent graph."""

from dataclasses import dataclass

import dspy

from voicetest.llm import call_llm
from voicetest.models.agent import AgentNode
from voicetest.models.results import Message
from voicetest.retry import OnErrorCallback


class FlowValidationSignature(dspy.Signature):
    """Evaluate if conversation flow through an agent graph was logical.

    Given an agent graph (nodes with instructions and transitions),
    a conversation transcript, and the sequence of nodes visited,
    determine if the transitions between nodes were appropriate
    given what was said in the conversation.
    """

    graph_structure: str = dspy.InputField(
        desc="Agent graph: nodes with their instructions and valid transitions"
    )
    transcript: str = dspy.InputField(desc="Conversation between user and agent")
    nodes_visited: list[str] = dspy.InputField(
        desc="Sequence of node IDs the agent traversed, in order"
    )

    flow_valid: bool = dspy.OutputField(
        desc="True if all transitions were logical given the conversation"
    )
    issues: list[str] = dspy.OutputField(
        desc="List of specific flow issues found (empty list if valid)"
    )
    reasoning: str = dspy.OutputField(
        desc="Step-by-step explanation of why each transition was or wasn't appropriate"
    )


@dataclass
class FlowResult:
    """Result of flow validation."""

    valid: bool
    issues: list[str]
    reasoning: str


class FlowJudge:
    """Evaluate if conversation flow through agent graph was logical.

    Uses LLM to semantically validate that node transitions make sense
    given the conversation content and graph structure.
    """

    def __init__(self, model: str):
        """Initialize the judge.

        Args:
            model: LLM model to use for evaluation.
        """
        self.model = model

        self._mock_mode = False
        self._mock_result: FlowResult | None = None

    async def evaluate(
        self,
        nodes: dict[str, AgentNode],
        transcript: list[Message],
        nodes_visited: list[str],
        on_error: OnErrorCallback | None = None,
    ) -> FlowResult:
        """Evaluate if conversation flow was logical.

        Args:
            nodes: Agent graph nodes dict.
            transcript: Conversation transcript.
            nodes_visited: Sequence of node IDs visited.
            on_error: Optional callback for retry notifications.

        Returns:
            FlowResult with validity, issues, and reasoning.
        """
        if self._mock_mode and self._mock_result:
            return self._mock_result

        if not nodes_visited:
            return FlowResult(valid=True, issues=[], reasoning="No nodes visited")

        return await self._evaluate_with_llm(nodes, transcript, nodes_visited, on_error)

    async def _evaluate_with_llm(
        self,
        nodes: dict[str, AgentNode],
        transcript: list[Message],
        nodes_visited: list[str],
        on_error: OnErrorCallback | None = None,
    ) -> FlowResult:
        """Evaluate using LLM."""
        formatted_transcript = self._format_transcript(transcript)
        formatted_graph = self._format_graph(nodes)

        result = await call_llm(
            self.model,
            FlowValidationSignature,
            on_error=on_error,
            graph_structure=formatted_graph,
            transcript=formatted_transcript,
            nodes_visited=nodes_visited,
        )

        return FlowResult(
            valid=result.flow_valid,
            issues=result.issues if result.issues else [],
            reasoning=result.reasoning,
        )

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)

    def _format_graph(self, nodes: dict[str, AgentNode]) -> str:
        """Format agent graph nodes as a string for LLM input."""
        lines = []
        for node_id, node in nodes.items():
            lines.append(f"[{node_id}]")
            lines.append(f"  Instructions: {node.state_prompt[:200]}...")
            if node.transitions:
                lines.append("  Transitions:")
                for t in node.transitions:
                    condition = t.condition.value or "unconditional"
                    lines.append(f"    -> {t.target_node_id}: {condition}")
        return "\n".join(lines)
