"""Tests for voicetest.services.diagnosis module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import DiagnosisResult
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange
from voicetest.models.results import MetricResult
from voicetest.services.diagnosis import DiagnosisService


@pytest.fixture
def graph():
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
                    ),
                ],
            ),
            "billing": AgentNode(
                id="billing",
                state_prompt="Help with billing.",
                transitions=[
                    Transition(
                        target_node_id="end",
                        condition=TransitionCondition(type="llm_prompt", value="Billing resolved"),
                    ),
                ],
            ),
            "end": AgentNode(
                id="end",
                state_prompt="Thank and close.",
                transitions=[],
            ),
        },
        entry_node_id="greeting",
        source_type="custom",
        source_metadata={"general_prompt": "You are a professional agent."},
    )


@pytest.fixture
def service():
    """DiagnosisService with a dummy execution service (not used by tested methods)."""

    class StubExecution:
        pass

    return DiagnosisService(StubExecution())


class TestApplyFixToGraph:
    def test_general_prompt_change(self, service, graph):
        changes = [
            PromptChange(
                location_type="general_prompt",
                original_text="You are a professional agent.",
                proposed_text="You are a billing specialist.",
                rationale="Focus on billing",
            ),
        ]
        modified = service.apply_fix_to_graph(graph, changes)
        assert modified.source_metadata["general_prompt"] == "You are a billing specialist."

    def test_node_prompt_change(self, service, graph):
        changes = [
            PromptChange(
                location_type="node_prompt",
                node_id="billing",
                original_text="Help with billing.",
                proposed_text="Help with billing including refunds.",
                rationale="Add refund support",
            ),
        ]
        modified = service.apply_fix_to_graph(graph, changes)
        assert modified.nodes["billing"].state_prompt == "Help with billing including refunds."

    def test_transition_change(self, service, graph):
        changes = [
            PromptChange(
                location_type="transition",
                node_id="greeting",
                transition_target_id="billing",
                original_text="User has billing question",
                proposed_text="User mentions billing, payments, or refunds",
                rationale="Broaden trigger",
            ),
        ]
        modified = service.apply_fix_to_graph(graph, changes)
        t = modified.nodes["greeting"].transitions[0]
        assert t.condition.value == "User mentions billing, payments, or refunds"

    def test_nonexistent_node_skipped(self, service, graph):
        changes = [
            PromptChange(
                location_type="node_prompt",
                node_id="nonexistent",
                original_text="old",
                proposed_text="new",
                rationale="test",
            ),
        ]
        modified = service.apply_fix_to_graph(graph, changes)
        # Should not raise, just skip
        assert "nonexistent" not in modified.nodes

    def test_nonexistent_transition_skipped(self, service, graph):
        changes = [
            PromptChange(
                location_type="transition",
                node_id="greeting",
                transition_target_id="nonexistent",
                original_text="old",
                proposed_text="new",
                rationale="test",
            ),
        ]
        modified = service.apply_fix_to_graph(graph, changes)
        # Transition should be unchanged
        assert (
            modified.nodes["greeting"].transitions[0].condition.value == "User has billing question"
        )

    def test_deep_copy_does_not_mutate_original(self, service, graph):
        changes = [
            PromptChange(
                location_type="general_prompt",
                original_text="old",
                proposed_text="changed",
                rationale="test",
            ),
            PromptChange(
                location_type="node_prompt",
                node_id="billing",
                original_text="old",
                proposed_text="changed billing",
                rationale="test",
            ),
        ]
        service.apply_fix_to_graph(graph, changes)
        assert graph.source_metadata["general_prompt"] == "You are a professional agent."
        assert graph.nodes["billing"].state_prompt == "Help with billing."

    def test_multiple_changes(self, service, graph):
        changes = [
            PromptChange(
                location_type="general_prompt",
                original_text="old",
                proposed_text="Updated general prompt.",
                rationale="update",
            ),
            PromptChange(
                location_type="node_prompt",
                node_id="greeting",
                original_text="old",
                proposed_text="Warmly greet.",
                rationale="update",
            ),
            PromptChange(
                location_type="node_prompt",
                node_id="billing",
                original_text="old",
                proposed_text="Handle billing with refunds.",
                rationale="update",
            ),
        ]
        modified = service.apply_fix_to_graph(graph, changes)
        assert modified.source_metadata["general_prompt"] == "Updated general prompt."
        assert modified.nodes["greeting"].state_prompt == "Warmly greet."
        assert modified.nodes["billing"].state_prompt == "Handle billing with refunds."

    def test_empty_changes(self, service, graph):
        modified = service.apply_fix_to_graph(graph, [])
        assert modified.source_metadata == graph.source_metadata
        assert set(modified.nodes.keys()) == set(graph.nodes.keys())


class TestScoresImproved:
    def test_improved(self, service):
        original = {"helpfulness": 0.6, "accuracy": 0.4}
        new = {"helpfulness": 0.8, "accuracy": 0.5}
        assert service.scores_improved(original, new) is True

    def test_not_improved(self, service):
        original = {"helpfulness": 0.8, "accuracy": 0.9}
        new = {"helpfulness": 0.7, "accuracy": 0.6}
        assert service.scores_improved(original, new) is False

    def test_equal_scores(self, service):
        original = {"helpfulness": 0.7}
        new = {"helpfulness": 0.7}
        assert service.scores_improved(original, new) is False

    def test_empty_original(self, service):
        assert service.scores_improved({}, {"a": 0.5}) is False

    def test_empty_new(self, service):
        assert service.scores_improved({"a": 0.5}, {}) is False

    def test_both_empty(self, service):
        assert service.scores_improved({}, {}) is False

    def test_single_metric_improved(self, service):
        assert service.scores_improved({"m": 0.3}, {"m": 0.9}) is True


class TestDiagnoseFailure:
    @pytest.mark.asyncio
    async def test_returns_diagnosis_result(self, graph):
        """diagnose_failure creates a judge in mock mode and returns a result."""

        # Build a real DiagnosisService with a stub execution
        class StubExec:
            pass

        svc = DiagnosisService(StubExec())

        # Monkey-patch the judge creation to use mock mode
        from voicetest.judges.diagnosis import DiagnosisJudge

        original_init = DiagnosisJudge.__init__

        def mock_init(self_judge, model):
            original_init(self_judge, model)
            self_judge._mock_mode = True
            self_judge._mock_diagnosis = Diagnosis(
                fault_locations=[],
                root_cause="Test root cause",
                transcript_evidence="test evidence",
            )
            self_judge._mock_fix = FixSuggestion(
                changes=[],
                summary="No changes",
                confidence=0.5,
            )

        DiagnosisJudge.__init__ = mock_init
        try:
            result = await svc.diagnose_failure(
                graph=graph,
                transcript=[],
                nodes_visited=["greeting"],
                failed_metrics=[
                    MetricResult(
                        metric="test",
                        passed=False,
                        reasoning="failed",
                        score=0.3,
                        threshold=0.7,
                    ),
                ],
                test_scenario="test scenario",
                judge_model="mock/model",
            )
            assert isinstance(result, DiagnosisResult)
            assert result.diagnosis.root_cause == "Test root cause"
            assert result.fix.confidence == 0.5
        finally:
            DiagnosisJudge.__init__ = original_init
