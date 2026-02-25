"""Auto-DRY analysis for agent prompt graphs.

Detects repeated and near-identical text across prompts, suggesting
snippets the user can accept/reject to reduce duplication.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
import difflib
import re

from voicetest.models.agent import AgentGraph


# Split on sentence boundaries: period, exclamation, question mark, or newline
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


@dataclass
class ExactMatch:
    """A sentence that appears verbatim in 2+ prompts."""

    text: str
    locations: list[str] = field(default_factory=list)


@dataclass
class FuzzyMatch:
    """A pair of sentences that are similar but not identical."""

    texts: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    similarity: float = 0.0


@dataclass
class AnalysisResult:
    """Combined results from auto-DRY analysis."""

    exact: list[ExactMatch] = field(default_factory=list)
    fuzzy: list[FuzzyMatch] = field(default_factory=list)


def _collect_sentences(graph: AgentGraph, min_length: int) -> list[tuple[str, str]]:
    """Collect (sentence, location) pairs from all prompts.

    Location is "general_prompt" or the node ID.
    """
    pairs: list[tuple[str, str]] = []

    general_prompt = graph.source_metadata.get("general_prompt", "")
    if general_prompt:
        for sentence in _split_sentences(general_prompt, min_length):
            pairs.append((sentence, "general_prompt"))

    for node_id, node in graph.nodes.items():
        if node.state_prompt:
            for sentence in _split_sentences(node.state_prompt, min_length):
                pairs.append((sentence, node_id))

    return pairs


def _split_sentences(text: str, min_length: int) -> list[str]:
    """Split text into sentences, filtering by min_length."""
    raw = _SENTENCE_SPLIT.split(text.strip())
    return [s.strip() for s in raw if len(s.strip()) >= min_length]


def find_repeated_text(graph: AgentGraph, min_length: int = 50) -> list[ExactMatch]:
    """Find sentences that appear verbatim in 2+ prompts.

    Args:
        graph: Agent graph to analyze.
        min_length: Minimum character length for a sentence to be considered.

    Returns:
        List of ExactMatch results with text and locations.
    """
    pairs = _collect_sentences(graph, min_length)

    # Group by normalized sentence text
    groups: dict[str, list[str]] = {}
    for sentence, location in pairs:
        groups.setdefault(sentence, []).append(location)

    results = []
    for text, locations in groups.items():
        # Only report if appearing in 2+ distinct locations
        unique_locations = list(dict.fromkeys(locations))
        if len(unique_locations) >= 2:
            results.append(ExactMatch(text=text, locations=unique_locations))

    return results


def find_similar_text(
    graph: AgentGraph, threshold: float = 0.8, min_length: int = 50
) -> list[FuzzyMatch]:
    """Find sentence pairs that are similar but not identical.

    Uses difflib.SequenceMatcher for pairwise comparison.

    Args:
        graph: Agent graph to analyze.
        threshold: Minimum similarity ratio (0.0 to 1.0).
        min_length: Minimum character length for a sentence to be considered.

    Returns:
        List of FuzzyMatch results above the threshold.
    """
    pairs = _collect_sentences(graph, min_length)
    if len(pairs) < 2:
        return []

    # Collect exact sentence texts to exclude from fuzzy results
    exact_texts = set()
    groups: dict[str, list[str]] = {}
    for sentence, location in pairs:
        groups.setdefault(sentence, []).append(location)
    for text, locations in groups.items():
        if len(set(locations)) >= 2:
            exact_texts.add(text)

    results = []
    seen: set[tuple[str, str]] = set()

    for i in range(len(pairs)):
        for j in range(i + 1, len(pairs)):
            text_a, loc_a = pairs[i]
            text_b, loc_b = pairs[j]

            # Skip same-location comparisons
            if loc_a == loc_b:
                continue

            # Skip exact duplicates
            if text_a == text_b:
                continue

            # Skip if either text is an exact duplicate (handled by find_repeated_text)
            if text_a in exact_texts and text_b in exact_texts:
                continue

            # Avoid duplicate pair comparisons
            key = (min(text_a, text_b), max(text_a, text_b))
            if key in seen:
                continue
            seen.add(key)

            ratio = difflib.SequenceMatcher(None, text_a, text_b).ratio()
            if ratio >= threshold:
                results.append(
                    FuzzyMatch(
                        texts=[text_a, text_b],
                        locations=[loc_a, loc_b],
                        similarity=ratio,
                    )
                )

    return results


def suggest_snippets(
    graph: AgentGraph,
    threshold: float = 0.8,
    min_length: int = 50,
) -> AnalysisResult:
    """Run both exact and fuzzy analysis, returning combined results.

    Args:
        graph: Agent graph to analyze.
        threshold: Similarity threshold for fuzzy matching.
        min_length: Minimum sentence length to consider.

    Returns:
        AnalysisResult with both exact and fuzzy matches.
    """
    exact = find_repeated_text(graph, min_length=min_length)
    fuzzy = find_similar_text(graph, threshold=threshold, min_length=min_length)
    return AnalysisResult(exact=exact, fuzzy=fuzzy)
