"""Metric judge for evaluating conversation against success criteria."""

from typing import get_args

import dspy

from voicetest.llm import call_llm
from voicetest.models.events import JUDGE_INPUT_EVENTS
from voicetest.models.events import EventKind
from voicetest.models.events import JudgeEvent
from voicetest.models.events import JudgeInput
from voicetest.models.events import events_from_messages
from voicetest.models.events import order_events
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.util.retry import OnErrorCallback


DEFAULT_THRESHOLD = 0.7

Conversation = list[Message] | list[JudgeEvent]

EVENTS_FIELD_DESC = (
    "Chronologically ordered conversation events, including speech and actions. "
    f"kind is one of: {', '.join(get_args(EventKind))}. "
    "speaker is who produced the event, when applicable. "
    "start_offset_ms and end_offset_ms are milliseconds from conversation start, "
    "omitted when unknown. "
    "content is text such as an utterance. "
    "payload holds structured event data, such as keypad digits or a tool name, "
    "arguments, and result."
)


class MetricJudgeSignature(dspy.Signature):
    """Evaluate if a conversation transcript meets a success criterion.

    For criteria with multiple requirements, evaluate EACH requirement separately.
    Quote specific parts of the transcript as evidence for each judgment."""

    transcript: str = dspy.InputField(desc="Full conversation transcript")
    criterion: str = dspy.InputField(
        desc="Success criterion - may contain multiple requirements separated by periods"
    )

    reasoning: str = dspy.OutputField(
        desc="Which requirements passed/failed, with transcript quotes as evidence"
    )
    score: float = dspy.OutputField(
        desc="0.0-1.0 based on fraction of requirements met (e.g., 2/3 met = 0.67)"
    )
    confidence: float = dspy.OutputField(desc="Confidence in assessment 0.0-1.0")


class MetricJudgeEventsSignature(dspy.Signature):
    """Evaluate a success criterion against a structured conversation timeline.

    Treat speech and non-speech events as distinct evidence. Cite relevant
    event content or timing in the reasoning. Do not infer timing that is absent."""

    events: list[JudgeEvent] = dspy.InputField(desc=EVENTS_FIELD_DESC)
    criterion: str = dspy.InputField(desc="Success criterion; may contain multiple requirements")

    reasoning: str = dspy.OutputField(
        desc="Which requirements passed or failed, citing relevant event evidence"
    )
    score: float = dspy.OutputField(desc="0.0-1.0 based on the fraction of requirements met")
    confidence: float = dspy.OutputField(desc="Confidence in the assessment from 0.0 to 1.0")


class MetricJudge:
    """Evaluate conversation against success metrics using LLM."""

    def __init__(self, model: str):
        self.model = model

        self._mock_mode = False
        self._mock_results: list[MetricResult] = []
        self._mock_index = 0

    async def evaluate(
        self,
        transcript: Conversation,
        criterion: str,
        threshold: float = DEFAULT_THRESHOLD,
        on_error: OnErrorCallback | None = None,
        use_heard: bool = False,
    ) -> MetricResult:
        """Evaluate transcript against a single criterion."""
        if self._mock_mode and self._mock_results:
            result = self._mock_results[self._mock_index % len(self._mock_results)]
            self._mock_index += 1
            return result

        return await self._evaluate_with_llm(
            transcript, criterion, threshold, on_error, use_heard=use_heard
        )

    async def evaluate_all(
        self,
        transcript: Conversation,
        criteria: list[str],
        threshold: float = DEFAULT_THRESHOLD,
        on_error: OnErrorCallback | None = None,
        use_heard: bool = False,
    ) -> list[MetricResult]:
        """Evaluate transcript against multiple criteria."""
        results = []
        for criterion in criteria:
            result = await self.evaluate(
                transcript, criterion, threshold, on_error, use_heard=use_heard
            )
            results.append(result)
        return results

    async def _evaluate_with_llm(
        self,
        transcript: Conversation,
        criterion: str,
        threshold: float,
        on_error: OnErrorCallback | None = None,
        use_heard: bool = False,
    ) -> MetricResult:
        """Evaluate using LLM."""
        signature, inputs = build_judge_call(transcript, criterion, use_heard=use_heard)

        result = await call_llm(
            self.model,
            signature,
            on_error=on_error,
            predictor_class=dspy.ChainOfThought,
            **inputs,
        )

        return MetricResult(
            metric=criterion,
            score=result.score,
            passed=result.score >= threshold,
            reasoning=result.reasoning,
            threshold=threshold,
            confidence=result.confidence,
        )

    @staticmethod
    def _format_transcript(transcript: list[Message], use_heard: bool = False) -> str:
        """Format transcript for LLM input.

        Filters out internal tool messages (transitions, extractions) to keep
        the judge focused on the actual user/assistant conversation."""
        lines = []
        for msg in transcript:
            if msg.role == "tool":
                continue
            content = msg.content
            if use_heard and msg.role == "assistant":
                heard = msg.audio().heard
                content = heard if heard is not None else content
            lines.append(f"{msg.role.upper()}: {content}")
        return "\n".join(lines)


def build_judge_call(
    conversation: Conversation, criterion: str, use_heard: bool = False
) -> tuple[type[dspy.Signature], dict]:
    """Select the judge signature and inputs from the conversation's element type."""
    if conversation and all(isinstance(item, JudgeEvent) for item in conversation):
        return MetricJudgeEventsSignature, {
            "events": order_events(conversation),
            "criterion": criterion,
        }
    if all(isinstance(item, Message) for item in conversation):
        return MetricJudgeSignature, {
            "transcript": MetricJudge._format_transcript(conversation, use_heard=use_heard),
            "criterion": criterion,
        }
    raise TypeError("Judge input must be all Message or all JudgeEvent items")


def conversation_for_judge(
    transcript: list[Message], judge_input: JudgeInput, use_heard: bool = False
) -> Conversation:
    """Shape a transcript into the judge input format selected for the run."""
    if judge_input == JUDGE_INPUT_EVENTS:
        return events_from_messages(transcript, use_heard=use_heard)
    return transcript
