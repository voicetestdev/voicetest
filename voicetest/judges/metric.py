"""Metric judge for evaluating conversation against success criteria."""

import dspy

from voicetest.llm import call_llm
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.retry import OnErrorCallback


DEFAULT_THRESHOLD = 0.7


class MetricJudgeSignature(dspy.Signature):
    """Evaluate if a conversation transcript meets a success criterion.

    For criteria with multiple requirements, evaluate EACH requirement separately.
    Quote specific parts of the transcript as evidence for each judgment.
    """

    transcript: str = dspy.InputField(desc="Full conversation transcript")
    criterion: str = dspy.InputField(
        desc="Success criterion - may contain multiple requirements separated by periods"
    )

    analysis: str = dspy.OutputField(
        desc="Break down criterion into requirements, evaluate each with transcript quotes"
    )
    score: float = dspy.OutputField(
        desc="0.0-1.0 based on fraction of requirements met (e.g., 2/3 met = 0.67)"
    )
    reasoning: str = dspy.OutputField(desc="Summary: which requirements passed/failed")
    confidence: float = dspy.OutputField(desc="Confidence in assessment 0.0-1.0")


class MetricJudge:
    """Evaluate conversation against success metrics using LLM.

    Uses DSPy for structured LLM generation to evaluate whether
    a conversation transcript meets specified criteria.
    """

    def __init__(self, model: str):
        """Initialize the judge.

        Args:
            model: LLM model to use for evaluation.
        """
        self.model = model

        # Mock mode for testing without LLM calls
        self._mock_mode = False
        self._mock_results: list[MetricResult] = []
        self._mock_index = 0

    async def evaluate(
        self,
        transcript: list[Message],
        criterion: str,
        threshold: float = DEFAULT_THRESHOLD,
        on_error: OnErrorCallback | None = None,
    ) -> MetricResult:
        """Evaluate transcript against a single criterion.

        Args:
            transcript: Conversation transcript to evaluate.
            criterion: Success criterion to check.
            threshold: Minimum score (0-1) to pass. Defaults to 0.7.
            on_error: Optional callback for retry notifications.

        Returns:
            MetricResult with score, pass/fail, and reasoning.
        """
        # Mock mode for testing
        if self._mock_mode and self._mock_results:
            result = self._mock_results[self._mock_index % len(self._mock_results)]
            self._mock_index += 1
            return result

        # Real LLM evaluation
        return await self._evaluate_with_llm(transcript, criterion, threshold, on_error)

    async def evaluate_all(
        self,
        transcript: list[Message],
        criteria: list[str],
        threshold: float = DEFAULT_THRESHOLD,
        on_error: OnErrorCallback | None = None,
    ) -> list[MetricResult]:
        """Evaluate transcript against multiple criteria.

        Args:
            transcript: Conversation transcript to evaluate.
            criteria: List of success criteria.
            threshold: Minimum score (0-1) to pass. Defaults to 0.7.
            on_error: Optional callback for retry notifications.

        Returns:
            List of MetricResult objects.
        """
        results = []
        for criterion in criteria:
            result = await self.evaluate(transcript, criterion, threshold, on_error)
            results.append(result)
        return results

    async def _evaluate_with_llm(
        self,
        transcript: list[Message],
        criterion: str,
        threshold: float,
        on_error: OnErrorCallback | None = None,
    ) -> MetricResult:
        """Evaluate using LLM."""
        formatted_transcript = self._format_transcript(transcript)

        result = await call_llm(
            self.model,
            MetricJudgeSignature,
            on_error=on_error,
            transcript=formatted_transcript,
            criterion=criterion,
        )

        return MetricResult(
            metric=criterion,
            score=result.score,
            passed=result.score >= threshold,
            reasoning=result.reasoning,
            threshold=threshold,
            confidence=result.confidence,
        )

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)
