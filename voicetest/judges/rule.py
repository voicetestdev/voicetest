"""Rule-based judge for deterministic pattern matching evaluation."""

import re

from voicetest.judges.pattern import compile_pattern
from voicetest.models.results import Message
from voicetest.models.results import MetricResult


class RuleJudge:
    """Evaluate conversation against deterministic rules.

    Checks transcripts for required substrings (includes),
    forbidden substrings (excludes), and wildcard/regex patterns.
    """

    def __init__(self, pattern_engine: str = "fnmatch"):
        self._pattern_engine = pattern_engine

    async def evaluate(
        self,
        transcript: list[Message],
        includes: list[str],
        excludes: list[str],
        patterns: list[str],
        use_heard: bool = False,
    ) -> list[MetricResult]:
        """Evaluate transcript against rules.

        Args:
            transcript: Conversation transcript to evaluate.
            includes: Substrings that must be present.
            excludes: Substrings that must NOT be present.
            patterns: Wildcard patterns (fnmatch) or regex patterns (re2).
            use_heard: If True, use metadata["heard"] for assistant messages.

        Returns:
            List of MetricResult objects for each rule.
        """
        text = self._format_transcript(transcript, use_heard=use_heard)
        results = []

        for include in includes:
            passed = include.lower() in text.lower()
            results.append(
                MetricResult(
                    metric=f"includes: {include}",
                    passed=passed,
                    reasoning=(
                        f"Found '{include}' in transcript"
                        if passed
                        else f"'{include}' not found in transcript"
                    ),
                    confidence=1.0,
                )
            )

        for exclude in excludes:
            passed = exclude.lower() not in text.lower()
            results.append(
                MetricResult(
                    metric=f"excludes: {exclude}",
                    passed=passed,
                    reasoning=(
                        f"'{exclude}' correctly absent from transcript"
                        if passed
                        else f"Found forbidden string '{exclude}' in transcript"
                    ),
                    confidence=1.0,
                )
            )

        for pattern in patterns:
            try:
                compiled = compile_pattern(pattern, engine=self._pattern_engine)
                match = compiled.search(text)
                passed = match is not None
                results.append(
                    MetricResult(
                        metric=f"pattern: {pattern}",
                        passed=passed,
                        reasoning=(
                            f"Pattern '{pattern}' matched: {match.group()}"
                            if passed
                            else f"Pattern '{pattern}' not found in transcript"
                        ),
                        confidence=1.0,
                    )
                )
            except (re.error, ImportError) as e:
                results.append(
                    MetricResult(
                        metric=f"pattern: {pattern}",
                        passed=False,
                        reasoning=f"Invalid pattern: {e}",
                        confidence=1.0,
                    )
                )

        return results

    def _format_transcript(self, transcript: list[Message], use_heard: bool = False) -> str:
        """Format transcript for text matching."""
        lines = []
        for msg in transcript:
            content = msg.content
            if use_heard and msg.role == "assistant":
                content = msg.metadata.get("heard", content)
            lines.append(f"{msg.role.upper()}: {content}")
        return "\n".join(lines)
