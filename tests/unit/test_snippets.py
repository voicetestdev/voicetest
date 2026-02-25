"""Tests for voicetest.snippets auto-DRY analysis module."""

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.snippets import find_repeated_text
from voicetest.snippets import find_similar_text
from voicetest.snippets import suggest_snippets


def _make_graph(**node_prompts: str) -> AgentGraph:
    """Helper to build a graph from node_id -> state_prompt pairs."""
    nodes = {}
    first_id = None
    for node_id, prompt in node_prompts.items():
        if first_id is None:
            first_id = node_id
        nodes[node_id] = AgentNode(id=node_id, state_prompt=prompt, transitions=[])
    return AgentGraph(
        nodes=nodes,
        entry_node_id=first_id or "a",
        source_type="custom",
    )


class TestFindRepeatedText:
    """Tests for find_repeated_text (exact match detection)."""

    def test_exact_duplicate_detected(self):
        graph = _make_graph(
            a="Please verify your identity. Then proceed.",
            b="Please verify your identity. Help with billing.",
        )
        results = find_repeated_text(graph, min_length=20)
        texts = [r.text for r in results]
        assert any("Please verify your identity" in t for t in texts)

    def test_no_duplicates_returns_empty(self):
        graph = _make_graph(
            a="Completely unique prompt for node A.",
            b="Totally different prompt for node B.",
        )
        results = find_repeated_text(graph, min_length=20)
        assert results == []

    def test_short_duplicates_below_threshold_ignored(self):
        graph = _make_graph(
            a="Hi there. Do task A.",
            b="Hi there. Do task B.",
        )
        # "Hi there" is only 8 chars, below min_length=20
        results = find_repeated_text(graph, min_length=20)
        assert results == []

    def test_general_prompt_included(self):
        graph = _make_graph(a="Please verify your identity. Then greet.")
        graph.source_metadata["general_prompt"] = (
            "Please verify your identity. General instructions."
        )
        results = find_repeated_text(graph, min_length=20)
        texts = [r.text for r in results]
        assert any("Please verify your identity" in t for t in texts)

    def test_locations_tracked(self):
        graph = _make_graph(
            a="Always be polite and professional. Task A.",
            b="Always be polite and professional. Task B.",
        )
        results = find_repeated_text(graph, min_length=20)
        match = next(r for r in results if "polite and professional" in r.text)
        assert "a" in match.locations
        assert "b" in match.locations


class TestFindSimilarText:
    """Tests for find_similar_text (fuzzy match detection)."""

    def test_similar_detected(self):
        graph = _make_graph(
            a="Please verify the caller's identity before proceeding with the request.",
            b="Please verify the caller identity before proceeding with any request.",
        )
        results = find_similar_text(graph, threshold=0.8, min_length=30)
        assert len(results) > 0
        assert results[0].similarity >= 0.8

    def test_dissimilar_not_flagged(self):
        graph = _make_graph(
            a="Talk about the weather and current events in detail.",
            b="Process the payment and send a confirmation email now.",
        )
        results = find_similar_text(graph, threshold=0.8, min_length=20)
        assert results == []

    def test_exact_matches_excluded(self):
        graph = _make_graph(
            a="Please verify the caller identity. Do task A.",
            b="Please verify the caller identity. Do task B.",
        )
        # The exact-match sentence should not appear in fuzzy results
        results = find_similar_text(graph, threshold=0.8, min_length=20)
        for r in results:
            assert len(set(r.texts)) > 1, "Exact duplicates should be excluded from fuzzy"


class TestSuggestSnippets:
    """Tests for suggest_snippets orchestrator."""

    def test_combined_results(self):
        polite = "Always be polite and professional."
        graph = _make_graph(
            a=f"{polite} Please verify the caller's identity before helping.",
            b=f"{polite} Please verify the callers identity before helping.",
        )
        result = suggest_snippets(graph, min_length=20)
        # Should have at least exact match for "Always be polite and professional"
        assert len(result.exact) > 0 or len(result.fuzzy) > 0
