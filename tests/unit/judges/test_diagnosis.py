"""Tests for voicetest.judges.diagnosis module."""

import json

import pytest

from voicetest.judges.diagnosis import DiagnosisJudge
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import FaultLocation
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange
from voicetest.models.results import Message
from voicetest.models.results import MetricResult


@pytest.fixture
def judge():
    return DiagnosisJudge("openai/gpt-4o-mini")


@pytest.fixture
def sample_graph():
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user warmly and ask how you can help.",
                transitions=[
                    Transition(
                        target_node_id="billing",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User has billing question"
                        ),
                    ),
                    Transition(
                        target_node_id="support",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User needs technical support"
                        ),
                    ),
                ],
            ),
            "billing": AgentNode(
                id="billing",
                state_prompt="Help the customer with billing inquiries.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Billing resolved"),
                    )
                ],
            ),
            "support": AgentNode(
                id="support",
                state_prompt="Provide technical support.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Support complete"),
                    )
                ],
            ),
            "end": AgentNode(
                id="end",
                state_prompt="Thank the customer and end the call politely.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
        source_metadata={"general_prompt": "You are a professional customer service agent."},
    )


@pytest.fixture
def sample_transcript():
    return [
        Message(
            role="assistant", content="Hello! How can I help?", metadata={"node_id": "greeting"}
        ),
        Message(role="user", content="I want a refund on my last charge"),
        Message(
            role="assistant",
            content="I can help with that. Let me look into it.",
            metadata={"node_id": "billing"},
        ),
        Message(role="user", content="It was charged twice"),
        Message(
            role="assistant",
            content="I understand. Unfortunately I cannot process refunds.",
            metadata={"node_id": "billing"},
        ),
    ]


@pytest.fixture
def failed_metrics():
    return [
        MetricResult(
            metric="Agent resolves billing issue satisfactorily",
            score=0.3,
            passed=False,
            reasoning="Agent said it cannot process refunds instead of helping",
            threshold=0.7,
            confidence=0.9,
        ),
    ]


class TestDiagnosisJudgeInit:
    def test_create_judge(self, judge):
        assert judge.model == "openai/gpt-4o-mini"

    def test_create_with_different_model(self):
        judge = DiagnosisJudge("anthropic/claude-3-haiku")
        assert judge.model == "anthropic/claude-3-haiku"


class TestFormatGraphFull:
    def test_includes_general_prompt(self, judge, sample_graph):
        formatted = judge._format_graph_full(sample_graph)
        assert "You are a professional customer service agent." in formatted

    def test_includes_complete_node_prompts(self, judge, sample_graph):
        formatted = judge._format_graph_full(sample_graph)
        assert "Greet the user warmly and ask how you can help." in formatted
        assert "Help the customer with billing inquiries." in formatted
        assert "Provide technical support." in formatted
        assert "Thank the customer and end the call politely." in formatted

    def test_includes_transitions(self, judge, sample_graph):
        formatted = judge._format_graph_full(sample_graph)
        assert "User has billing question" in formatted
        assert "User needs technical support" in formatted
        assert "billing" in formatted
        assert "support" in formatted

    def test_no_general_prompt(self, judge):
        graph = AgentGraph(
            nodes={
                "main": AgentNode(id="main", state_prompt="Hello", transitions=[]),
            },
            entry_node_id="main",
            source_type="custom",
        )
        formatted = judge._format_graph_full(graph)
        assert "Hello" in formatted


class TestFormatTranscriptWithNodes:
    def test_includes_node_ids(self, judge, sample_transcript):
        formatted = judge._format_transcript_with_nodes(sample_transcript)
        assert "[greeting]" in formatted
        assert "[billing]" in formatted

    def test_includes_roles_and_content(self, judge, sample_transcript):
        formatted = judge._format_transcript_with_nodes(sample_transcript)
        assert "ASSISTANT:" in formatted
        assert "USER:" in formatted
        assert "Hello! How can I help?" in formatted
        assert "I want a refund on my last charge" in formatted

    def test_empty_transcript(self, judge):
        formatted = judge._format_transcript_with_nodes([])
        assert formatted == ""


class TestFormatFailedMetrics:
    def test_includes_only_failed(self, judge):
        metrics = [
            MetricResult(
                metric="greeting",
                score=0.9,
                passed=True,
                reasoning="Good greeting",
                threshold=0.7,
            ),
            MetricResult(
                metric="resolution",
                score=0.3,
                passed=False,
                reasoning="Did not resolve",
                threshold=0.7,
            ),
        ]
        formatted = judge._format_failed_metrics(metrics)
        assert "resolution" in formatted
        assert "greeting" not in formatted

    def test_includes_score_threshold_reasoning(self, judge, failed_metrics):
        formatted = judge._format_failed_metrics(failed_metrics)
        assert "0.3" in formatted
        assert "0.7" in formatted
        assert "cannot process refunds" in formatted

    def test_all_passed_returns_empty(self, judge):
        metrics = [
            MetricResult(metric="test", score=0.9, passed=True, reasoning="ok", threshold=0.7),
        ]
        formatted = judge._format_failed_metrics(metrics)
        assert formatted == ""


class TestParseFaultLocations:
    def test_parses_json_list(self, judge):
        raw = json.dumps(
            [
                {
                    "location_type": "node_prompt",
                    "node_id": "billing",
                    "relevant_text": "Help with billing",
                    "explanation": "Too vague",
                }
            ]
        )
        locations = judge._parse_fault_locations(raw)
        assert len(locations) == 1
        assert locations[0].location_type == "node_prompt"
        assert locations[0].node_id == "billing"

    def test_parses_multiple(self, judge):
        raw = json.dumps(
            [
                {
                    "location_type": "general_prompt",
                    "relevant_text": "Be helpful",
                    "explanation": "Missing refund instructions",
                },
                {
                    "location_type": "transition",
                    "node_id": "greeting",
                    "transition_target_id": "billing",
                    "relevant_text": "billing question",
                    "explanation": "Too narrow",
                },
            ]
        )
        locations = judge._parse_fault_locations(raw)
        assert len(locations) == 2

    def test_handles_invalid_json(self, judge):
        locations = judge._parse_fault_locations("not json at all")
        assert locations == []


class TestParseChanges:
    def test_parses_json_list(self, judge):
        raw = json.dumps(
            [
                {
                    "location_type": "node_prompt",
                    "node_id": "billing",
                    "original_text": "Help with billing",
                    "proposed_text": "Help with billing including refunds",
                    "rationale": "Add refund capability",
                }
            ]
        )
        changes = judge._parse_changes(raw)
        assert len(changes) == 1
        assert changes[0].location_type == "node_prompt"
        assert changes[0].proposed_text == "Help with billing including refunds"

    def test_handles_invalid_json(self, judge):
        changes = judge._parse_changes("broken json")
        assert changes == []


class TestMockMode:
    @pytest.mark.asyncio
    async def test_diagnose_mock(self, judge, sample_graph, sample_transcript, failed_metrics):
        judge._mock_mode = True
        judge._mock_diagnosis = Diagnosis(
            fault_locations=[
                FaultLocation(
                    location_type="node_prompt",
                    node_id="billing",
                    relevant_text="Help the customer with billing inquiries.",
                    explanation="Lacks refund handling instructions",
                ),
            ],
            root_cause="Billing node prompt lacks refund guidance",
            transcript_evidence="ASSISTANT: I cannot process refunds",
        )

        result = await judge.diagnose(
            sample_graph,
            sample_transcript,
            ["greeting", "billing"],
            failed_metrics,
            "Ask about a refund",
        )
        assert result.root_cause == "Billing node prompt lacks refund guidance"
        assert len(result.fault_locations) == 1

    @pytest.mark.asyncio
    async def test_suggest_fix_mock(self, judge, sample_graph, failed_metrics):
        judge._mock_mode = True
        judge._mock_fix = FixSuggestion(
            changes=[
                PromptChange(
                    location_type="node_prompt",
                    node_id="billing",
                    original_text="Help the customer with billing inquiries.",
                    proposed_text="Help the customer with billing inquiries including refunds.",
                    rationale="Add refund handling",
                ),
            ],
            summary="Added refund support to billing node",
            confidence=0.85,
        )

        diagnosis = Diagnosis(
            fault_locations=[],
            root_cause="Missing refund guidance",
            transcript_evidence="",
        )

        result = await judge.suggest_fix(sample_graph, diagnosis, failed_metrics)
        assert len(result.changes) == 1
        assert result.confidence == 0.85

    @pytest.mark.asyncio
    async def test_revise_fix_mock(self, judge, sample_graph, failed_metrics):
        judge._mock_mode = True
        judge._mock_fix = FixSuggestion(
            changes=[
                PromptChange(
                    location_type="node_prompt",
                    node_id="billing",
                    original_text="Help the customer with billing inquiries.",
                    proposed_text="Handle all billing including refunds, disputes, and credits.",
                    rationale="Broader coverage",
                ),
            ],
            summary="Expanded billing scope",
            confidence=0.9,
        )

        diagnosis = Diagnosis(
            fault_locations=[],
            root_cause="Missing refund guidance",
            transcript_evidence="",
        )
        prev_changes = [
            PromptChange(
                location_type="node_prompt",
                node_id="billing",
                original_text="old",
                proposed_text="new",
                rationale="first try",
            )
        ]

        result = await judge.revise_fix(sample_graph, diagnosis, prev_changes, failed_metrics)
        assert result.confidence == 0.9
