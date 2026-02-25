"""Tests for diagnosis API functions in voicetest.api."""

import pytest

from voicetest.api import apply_fix_to_graph
from voicetest.api import scores_improved
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.diagnosis import PromptChange


@pytest.fixture
def graph_with_general_prompt():
    return AgentGraph(
        nodes={
            "greeting": AgentNode(
                id="greeting",
                state_prompt="Greet the user warmly.",
                transitions=[
                    Transition(
                        target_node_id="billing",
                        condition=TransitionCondition(
                            type="llm_prompt", value="User has billing question"
                        ),
                    )
                ],
            ),
            "billing": AgentNode(
                id="billing",
                state_prompt="Help with billing inquiries.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
        source_metadata={"general_prompt": "You are a customer service agent."},
    )


class TestApplyFixToGraph:
    def test_modifies_general_prompt(self, graph_with_general_prompt):
        changes = [
            PromptChange(
                location_type="general_prompt",
                original_text="You are a customer service agent.",
                proposed_text="You are a helpful customer service agent who processes refunds.",
                rationale="Add refund capability",
            )
        ]
        result = apply_fix_to_graph(graph_with_general_prompt, changes)
        assert (
            result.source_metadata["general_prompt"]
            == "You are a helpful customer service agent who processes refunds."
        )

    def test_modifies_node_state_prompt(self, graph_with_general_prompt):
        changes = [
            PromptChange(
                location_type="node_prompt",
                node_id="billing",
                original_text="Help with billing inquiries.",
                proposed_text="Help with billing inquiries including refunds and disputes.",
                rationale="Broaden scope",
            )
        ]
        result = apply_fix_to_graph(graph_with_general_prompt, changes)
        assert (
            result.nodes["billing"].state_prompt
            == "Help with billing inquiries including refunds and disputes."
        )

    def test_modifies_transition_condition(self, graph_with_general_prompt):
        changes = [
            PromptChange(
                location_type="transition",
                node_id="greeting",
                transition_target_id="billing",
                original_text="User has billing question",
                proposed_text="User mentions billing, payments, or refunds",
                rationale="Broader trigger",
            )
        ]
        result = apply_fix_to_graph(graph_with_general_prompt, changes)
        transition = result.nodes["greeting"].transitions[0]
        assert transition.condition.value == "User mentions billing, payments, or refunds"

    def test_returns_deep_copy(self, graph_with_general_prompt):
        original_prompt = graph_with_general_prompt.source_metadata["general_prompt"]
        changes = [
            PromptChange(
                location_type="general_prompt",
                original_text="You are a customer service agent.",
                proposed_text="Changed prompt",
                rationale="test",
            )
        ]
        result = apply_fix_to_graph(graph_with_general_prompt, changes)

        # Original should be unchanged
        assert graph_with_general_prompt.source_metadata["general_prompt"] == original_prompt
        assert result.source_metadata["general_prompt"] == "Changed prompt"

    def test_multiple_changes(self, graph_with_general_prompt):
        changes = [
            PromptChange(
                location_type="general_prompt",
                original_text="You are a customer service agent.",
                proposed_text="You are a helpful agent.",
                rationale="simplify",
            ),
            PromptChange(
                location_type="node_prompt",
                node_id="greeting",
                original_text="Greet the user warmly.",
                proposed_text="Greet the user warmly and offer help.",
                rationale="add offer",
            ),
        ]
        result = apply_fix_to_graph(graph_with_general_prompt, changes)
        assert result.source_metadata["general_prompt"] == "You are a helpful agent."
        assert result.nodes["greeting"].state_prompt == "Greet the user warmly and offer help."

    def test_missing_node_id_skipped(self, graph_with_general_prompt):
        changes = [
            PromptChange(
                location_type="node_prompt",
                node_id="nonexistent",
                original_text="anything",
                proposed_text="new",
                rationale="test",
            )
        ]
        # Should not raise, just skip the change
        result = apply_fix_to_graph(graph_with_general_prompt, changes)
        # Graph should be unchanged (deep copy but same content)
        assert result.nodes["greeting"].state_prompt == "Greet the user warmly."

    def test_mismatched_transition_target_skipped(self, graph_with_general_prompt):
        changes = [
            PromptChange(
                location_type="transition",
                node_id="greeting",
                transition_target_id="nonexistent",
                original_text="anything",
                proposed_text="new",
                rationale="test",
            )
        ]
        result = apply_fix_to_graph(graph_with_general_prompt, changes)
        # Transition should be unchanged
        assert (
            result.nodes["greeting"].transitions[0].condition.value == "User has billing question"
        )


class TestScoresImproved:
    def test_improved(self):
        original = {"helpfulness": 0.5, "accuracy": 0.4}
        new = {"helpfulness": 0.7, "accuracy": 0.6}
        assert scores_improved(original, new) is True

    def test_not_improved(self):
        original = {"helpfulness": 0.8, "accuracy": 0.7}
        new = {"helpfulness": 0.5, "accuracy": 0.4}
        assert scores_improved(original, new) is False

    def test_equal_not_improved(self):
        original = {"helpfulness": 0.5}
        new = {"helpfulness": 0.5}
        assert scores_improved(original, new) is False

    def test_empty_scores(self):
        assert scores_improved({}, {}) is False

    def test_single_metric(self):
        assert scores_improved({"a": 0.3}, {"a": 0.31}) is True
        assert scores_improved({"a": 0.3}, {"a": 0.29}) is False
