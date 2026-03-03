"""Tests for voicetest.judges.decompose module."""

import json

import pytest

from voicetest.judges.decompose import DecomposeJudge
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.decompose import DecompositionPlan
from voicetest.models.decompose import HandoffRule
from voicetest.models.decompose import SubAgentSpec


@pytest.fixture
def judge():
    return DecomposeJudge("openai/gpt-4o-mini")


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
def monolithic_graph():
    """Single-node graph simulating a monolithic prompt."""
    return AgentGraph(
        nodes={
            "main": AgentNode(
                id="main",
                state_prompt="Handle everything: greet, verify identity, schedule, close.",
                transitions=[],
            ),
        },
        entry_node_id="main",
        source_type="custom",
        source_metadata={
            "general_prompt": (
                "You are a scheduling assistant. "
                "First greet the caller, then verify their identity, "
                "then help them schedule an appointment, "
                "then close the call politely."
            )
        },
    )


@pytest.fixture
def mock_plan():
    return DecompositionPlan(
        num_sub_agents=2,
        sub_agents=[
            SubAgentSpec(
                sub_agent_id="intake",
                name="Intake Agent",
                description="Handles greeting and routing",
                node_ids=["greeting"],
            ),
            SubAgentSpec(
                sub_agent_id="billing",
                name="Billing Agent",
                description="Handles billing inquiries",
                node_ids=["billing", "end"],
            ),
        ],
        handoff_rules=[
            HandoffRule(
                source_sub_agent_id="intake",
                target_sub_agent_id="billing",
                condition="User has billing question",
            ),
        ],
        rationale="Split intake from billing domain",
    )


class TestDecomposeJudgeInit:
    def test_create_judge(self, judge):
        assert judge.model == "openai/gpt-4o-mini"

    def test_create_with_different_model(self):
        j = DecomposeJudge("anthropic/claude-3-haiku")
        assert j.model == "anthropic/claude-3-haiku"


class TestFormatGraphFull:
    def test_includes_general_prompt(self, judge, sample_graph):
        formatted = judge._format_graph_full(sample_graph)
        assert "You are a professional customer service agent." in formatted

    def test_includes_node_prompts(self, judge, sample_graph):
        formatted = judge._format_graph_full(sample_graph)
        assert "Greet the user warmly" in formatted
        assert "Help the customer with billing" in formatted
        assert "Provide technical support" in formatted

    def test_includes_transitions(self, judge, sample_graph):
        formatted = judge._format_graph_full(sample_graph)
        assert "User has billing question" in formatted
        assert "billing" in formatted

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
        assert "GENERAL PROMPT" not in formatted

    def test_monolithic_graph(self, judge, monolithic_graph):
        formatted = judge._format_graph_full(monolithic_graph)
        assert "scheduling assistant" in formatted
        assert "Handle everything" in formatted


class TestMockMode:
    @pytest.mark.asyncio
    async def test_analyze_graph_mock(self, judge, sample_graph, mock_plan):
        judge._mock_mode = True
        judge._mock_plan = mock_plan

        result = await judge.analyze_graph(sample_graph, requested_num_agents=0)
        assert result.num_sub_agents == 2
        assert len(result.sub_agents) == 2
        assert result.sub_agents[0].sub_agent_id == "intake"

    @pytest.mark.asyncio
    async def test_analyze_graph_with_requested_num(self, judge, sample_graph, mock_plan):
        judge._mock_mode = True
        judge._mock_plan = mock_plan

        result = await judge.analyze_graph(sample_graph, requested_num_agents=3)
        assert result.num_sub_agents == 2  # Mock ignores override

    @pytest.mark.asyncio
    async def test_refine_sub_agent_mock(self, judge, sample_graph):
        judge._mock_mode = True
        judge._mock_refined_prompt = "Refined general prompt for intake"
        judge._mock_node_prompts = {"greeting": "Warmly greet and route the caller."}

        spec = SubAgentSpec(
            sub_agent_id="intake",
            name="Intake Agent",
            description="Handles greeting",
            node_ids=["greeting"],
        )
        general_prompt, node_prompts = await judge.refine_sub_agent(sample_graph, spec)
        assert general_prompt == "Refined general prompt for intake"
        assert node_prompts["greeting"] == "Warmly greet and route the caller."

    @pytest.mark.asyncio
    async def test_refine_returns_empty_when_no_mock(self, judge, sample_graph):
        judge._mock_mode = True
        # No mock values set — should return defaults
        spec = SubAgentSpec(
            sub_agent_id="intake",
            name="Intake",
            description="Test",
            node_ids=["greeting"],
        )
        general_prompt, node_prompts = await judge.refine_sub_agent(sample_graph, spec)
        assert general_prompt == ""
        assert node_prompts == {}


class TestParseDecompositionPlan:
    def test_parses_valid_json(self, judge):
        sub_agents_json = json.dumps(
            [
                {
                    "sub_agent_id": "intake",
                    "name": "Intake",
                    "description": "Handles intake",
                    "node_ids": ["greeting"],
                },
            ]
        )
        handoff_rules_json = json.dumps(
            [
                {
                    "source_sub_agent_id": "intake",
                    "target_sub_agent_id": "billing",
                    "condition": "Billing question",
                },
            ]
        )
        plan = judge._parse_plan(
            num_sub_agents=1,
            sub_agents_raw=sub_agents_json,
            handoff_rules_raw=handoff_rules_json,
            rationale="Test split",
        )
        assert plan.num_sub_agents == 1
        assert len(plan.sub_agents) == 1
        assert len(plan.handoff_rules) == 1

    def test_handles_invalid_sub_agents_json(self, judge):
        plan = judge._parse_plan(
            num_sub_agents=0,
            sub_agents_raw="not json",
            handoff_rules_raw="[]",
            rationale="broken",
        )
        assert plan.num_sub_agents == 0
        assert plan.sub_agents == []

    def test_handles_invalid_handoff_json(self, judge):
        sub_agents_json = json.dumps(
            [
                {
                    "sub_agent_id": "a",
                    "name": "A",
                    "description": "Test",
                    "node_ids": ["n1"],
                },
            ]
        )
        plan = judge._parse_plan(
            num_sub_agents=1,
            sub_agents_raw=sub_agents_json,
            handoff_rules_raw="broken",
            rationale="test",
        )
        assert len(plan.sub_agents) == 1
        assert plan.handoff_rules == []


class TestParseNodePrompts:
    def test_parses_valid_json(self, judge):
        raw = json.dumps({"greeting": "Hello there!", "billing": "Help with billing."})
        result = judge._parse_node_prompts(raw)
        assert result == {"greeting": "Hello there!", "billing": "Help with billing."}

    def test_handles_invalid_json(self, judge):
        result = judge._parse_node_prompts("not json")
        assert result == {}

    def test_handles_non_dict(self, judge):
        result = judge._parse_node_prompts(json.dumps(["a", "b"]))
        assert result == {}
