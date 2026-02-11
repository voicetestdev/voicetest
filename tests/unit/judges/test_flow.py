"""Tests for voicetest.judges.flow module."""

import pytest

from voicetest.judges.flow import FlowJudge
from voicetest.judges.flow import FlowResult
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.results import Message


class TestFlowJudge:
    """Tests for FlowJudge."""

    def test_create_judge(self):
        judge = FlowJudge()
        assert judge is not None
        assert judge.model == "openai/gpt-4o-mini"

    def test_create_judge_with_model(self):
        judge = FlowJudge("anthropic/claude-3-haiku")
        assert judge.model == "anthropic/claude-3-haiku"

    @pytest.mark.asyncio
    async def test_evaluate_empty_nodes_visited(self):
        judge = FlowJudge()

        nodes = {
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user",
                transitions=[],
            )
        }
        transcript = [Message(role="assistant", content="Hello!")]

        result = await judge.evaluate(nodes, transcript, nodes_visited=[])

        assert result.valid is True
        assert result.issues == []
        assert "No nodes visited" in result.reasoning

    @pytest.mark.asyncio
    async def test_evaluate_with_mock_mode(self):
        judge = FlowJudge()
        judge._mock_mode = True
        judge._mock_result = FlowResult(
            valid=False,
            issues=["Jumped from greeting to billing without verification"],
            reasoning="The transition skipped required identity check",
        )

        nodes = {
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user",
                transitions=[
                    Transition(
                        target_node_id="verify",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User wants to proceed"
                        ),
                    )
                ],
            ),
            "verify": AgentNode(id="verify", state_prompt="Verify identity", transitions=[]),
            "billing": AgentNode(id="billing", state_prompt="Handle billing", transitions=[]),
        }
        transcript = [
            Message(role="assistant", content="Hello!"),
            Message(role="user", content="I want to pay my bill"),
            Message(role="assistant", content="Here's your bill."),
        ]

        result = await judge.evaluate(nodes, transcript, nodes_visited=["greeting", "billing"])

        assert result.valid is False
        assert len(result.issues) == 1
        assert "verification" in result.issues[0].lower()


class TestFlowResult:
    """Tests for FlowResult."""

    def test_create_result(self):
        result = FlowResult(
            valid=True,
            issues=[],
            reasoning="All transitions were logical",
        )

        assert result.valid is True
        assert result.issues == []
        assert result.reasoning == "All transitions were logical"

    def test_create_result_with_issues(self):
        result = FlowResult(
            valid=False,
            issues=["Issue 1", "Issue 2"],
            reasoning="Found problems",
        )

        assert result.valid is False
        assert len(result.issues) == 2
