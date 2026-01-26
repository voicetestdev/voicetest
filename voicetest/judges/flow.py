"""Flow judge for validating conversation traversal through agent graph."""

import asyncio
from dataclasses import dataclass

import dspy

from voicetest.models.agent import AgentNode
from voicetest.models.results import Message


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

    def __init__(self, model: str = "openai/gpt-4o-mini"):
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
    ) -> FlowResult:
        """Evaluate if conversation flow was logical.

        Args:
            nodes: Agent graph nodes dict.
            transcript: Conversation transcript.
            nodes_visited: Sequence of node IDs visited.

        Returns:
            FlowResult with validity, issues, and reasoning.
        """
        if self._mock_mode and self._mock_result:
            return self._mock_result

        if not nodes_visited:
            return FlowResult(valid=True, issues=[], reasoning="No nodes visited")

        return await self._evaluate_with_llm(nodes, transcript, nodes_visited)

    async def _evaluate_with_llm(
        self,
        nodes: dict[str, AgentNode],
        transcript: list[Message],
        nodes_visited: list[str],
    ) -> FlowResult:
        """Evaluate using LLM."""
        lm = dspy.LM(self.model)

        class FlowValidationSignature(dspy.Signature):
            """Evaluate if conversation flow through an agent graph was logical.

            Given an agent graph (nodes with instructions and transitions),
            a conversation transcript, and the sequence of nodes visited,
            determine if the transitions between nodes were appropriate
            given what was said in the conversation.
            """

            nodes: dict[str, AgentNode] = dspy.InputField(
                desc="Agent graph nodes with instructions and transitions"
            )
            transcript: str = dspy.InputField(desc="Conversation between user and agent")
            nodes_visited: list[str] = dspy.InputField(
                desc="Sequence of node IDs the agent traversed"
            )

            flow_valid: bool = dspy.OutputField(
                desc="True if all transitions were logical given the conversation"
            )
            issues: list[str] = dspy.OutputField(
                desc="Specific flow issues found, empty list if valid"
            )
            reasoning: str = dspy.OutputField(desc="Explanation of the evaluation")

        formatted_transcript = self._format_transcript(transcript)

        def run_predictor():
            with dspy.context(lm=lm):
                predictor = dspy.Predict(FlowValidationSignature)
                return predictor(
                    nodes=nodes,
                    transcript=formatted_transcript,
                    nodes_visited=nodes_visited,
                )

        result = await asyncio.to_thread(run_predictor)

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
