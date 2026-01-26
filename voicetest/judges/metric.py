"""Metric judge for evaluating conversation against success criteria."""

import asyncio

import dspy

from voicetest.models.results import Message, MetricResult


DEFAULT_THRESHOLD = 0.7


class MetricJudge:
    """Evaluate conversation against success metrics using LLM.

    Uses DSPy for structured LLM generation to evaluate whether
    a conversation transcript meets specified criteria.
    """

    def __init__(self, model: str = "openai/gpt-4o-mini"):
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
    ) -> MetricResult:
        """Evaluate transcript against a single criterion.

        Args:
            transcript: Conversation transcript to evaluate.
            criterion: Success criterion to check.
            threshold: Minimum score (0-1) to pass. Defaults to 0.7.

        Returns:
            MetricResult with score, pass/fail, and reasoning.
        """
        # Mock mode for testing
        if self._mock_mode and self._mock_results:
            result = self._mock_results[self._mock_index % len(self._mock_results)]
            self._mock_index += 1
            return result

        # Real LLM evaluation
        return await self._evaluate_with_llm(transcript, criterion, threshold)

    async def evaluate_all(
        self,
        transcript: list[Message],
        criteria: list[str],
        threshold: float = DEFAULT_THRESHOLD,
    ) -> list[MetricResult]:
        """Evaluate transcript against multiple criteria.

        Args:
            transcript: Conversation transcript to evaluate.
            criteria: List of success criteria.
            threshold: Minimum score (0-1) to pass. Defaults to 0.7.

        Returns:
            List of MetricResult objects.
        """
        results = []
        for criterion in criteria:
            result = await self.evaluate(transcript, criterion, threshold)
            results.append(result)
        return results

    async def _evaluate_with_llm(
        self,
        transcript: list[Message],
        criterion: str,
        threshold: float,
    ) -> MetricResult:
        """Evaluate using LLM."""

        lm = dspy.LM(self.model)

        class MetricJudgeSignature(dspy.Signature):
            """Evaluate how well a conversation meets a success criterion."""

            transcript: str = dspy.InputField(desc="Full conversation transcript")
            criterion: str = dspy.InputField(desc="Success criterion to evaluate")

            score: float = dspy.OutputField(
                desc="Score from 0.0 to 1.0 indicating how well the criterion was met"
            )
            reasoning: str = dspy.OutputField(desc="Explanation of the judgment")
            confidence: float = dspy.OutputField(desc="Confidence in the assessment 0.0-1.0")

        formatted_transcript = self._format_transcript(transcript)

        def run_predictor():
            with dspy.context(lm=lm):
                predictor = dspy.Predict(MetricJudgeSignature)
                return predictor(
                    transcript=formatted_transcript,
                    criterion=criterion,
                )

        result = await asyncio.to_thread(run_predictor)

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
