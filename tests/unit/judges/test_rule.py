"""Tests for voicetest.judges.rule module."""

import pytest

from voicetest.judges.rule import RuleJudge
from voicetest.models.results import Message


@pytest.fixture
def judge():
    return RuleJudge()


@pytest.fixture
def sample_transcript():
    return [
        Message(role="user", content="Hello, I need help with my account."),
        Message(
            role="assistant",
            content="Welcome to Acme Corp! I'd be happy to help you. "
            "Your reference number is REF-ABC123.",
        ),
        Message(role="user", content="Thank you!"),
        Message(
            role="assistant",
            content="You're welcome! Is there anything else I can help you with?",
        ),
    ]


class TestRuleJudge:
    """Tests for RuleJudge."""

    def test_create_judge(self, judge):
        assert judge is not None

    @pytest.mark.asyncio
    async def test_evaluate_includes_found(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=["welcome", "help"],
            excludes=[],
            patterns=[],
        )
        assert len(results) == 2
        assert all(r.passed for r in results)
        assert results[0].metric == "includes: welcome"
        assert results[1].metric == "includes: help"

    @pytest.mark.asyncio
    async def test_evaluate_includes_not_found(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=["goodbye"],
            excludes=[],
            patterns=[],
        )
        assert len(results) == 1
        assert not results[0].passed
        assert "not found" in results[0].reasoning

    @pytest.mark.asyncio
    async def test_evaluate_excludes_absent(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=["error", "unable"],
            patterns=[],
        )
        assert len(results) == 2
        assert all(r.passed for r in results)
        assert "correctly absent" in results[0].reasoning

    @pytest.mark.asyncio
    async def test_evaluate_excludes_present(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=["thank you"],
            patterns=[],
        )
        assert len(results) == 1
        assert not results[0].passed
        assert "forbidden" in results[0].reasoning.lower()

    @pytest.mark.asyncio
    async def test_evaluate_pattern_matches(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=[],
            patterns=["REF-[A-Z0-9]+"],
        )
        assert len(results) == 1
        assert results[0].passed
        assert "matched" in results[0].reasoning
        assert "REF-ABC123" in results[0].reasoning

    @pytest.mark.asyncio
    async def test_evaluate_pattern_no_match(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=[],
            patterns=["TICKET-[0-9]+"],
        )
        assert len(results) == 1
        assert not results[0].passed
        assert "not found" in results[0].reasoning

    @pytest.mark.asyncio
    async def test_evaluate_invalid_regex(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=[],
            patterns=["[invalid(regex"],
        )
        assert len(results) == 1
        assert not results[0].passed
        assert "Invalid regex" in results[0].reasoning

    @pytest.mark.asyncio
    async def test_evaluate_all_rules(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=["welcome"],
            excludes=["error"],
            patterns=["REF-[A-Z0-9]+"],
        )
        assert len(results) == 3
        assert all(r.passed for r in results)
        assert all(r.confidence == 1.0 for r in results)

    @pytest.mark.asyncio
    async def test_evaluate_empty_rules(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=[],
            patterns=[],
        )
        assert len(results) == 0

    @pytest.mark.asyncio
    async def test_case_insensitive_includes(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=["WELCOME", "HELP"],
            excludes=[],
            patterns=[],
        )
        assert len(results) == 2
        assert all(r.passed for r in results)

    @pytest.mark.asyncio
    async def test_case_insensitive_excludes(self, judge, sample_transcript):
        results = await judge.evaluate(
            sample_transcript,
            includes=[],
            excludes=["THANK YOU"],
            patterns=[],
        )
        assert len(results) == 1
        assert not results[0].passed
