"""Tests for diagnosis data models."""

from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import DiagnosisResult
from voicetest.models.diagnosis import FaultLocation
from voicetest.models.diagnosis import FixAttemptResult
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange


class TestFaultLocation:
    def test_general_prompt_location(self):
        loc = FaultLocation(
            location_type="general_prompt",
            relevant_text="You are a helpful assistant",
            explanation="The general prompt lacks specificity",
        )
        assert loc.location_type == "general_prompt"
        assert loc.node_id is None
        assert loc.transition_target_id is None

    def test_node_prompt_location(self):
        loc = FaultLocation(
            location_type="node_prompt",
            node_id="greeting",
            relevant_text="Greet the user warmly",
            explanation="Greeting is too generic",
        )
        assert loc.location_type == "node_prompt"
        assert loc.node_id == "greeting"

    def test_transition_location(self):
        loc = FaultLocation(
            location_type="transition",
            node_id="greeting",
            transition_target_id="farewell",
            relevant_text="User wants to leave",
            explanation="Transition triggers too early",
        )
        assert loc.location_type == "transition"
        assert loc.node_id == "greeting"
        assert loc.transition_target_id == "farewell"

    def test_missing_transition_location(self):
        loc = FaultLocation(
            location_type="missing_transition",
            node_id="billing",
            relevant_text="No transition for escalation",
            explanation="Missing path to escalation node",
        )
        assert loc.location_type == "missing_transition"

    def test_serialization_roundtrip(self):
        loc = FaultLocation(
            location_type="node_prompt",
            node_id="support",
            relevant_text="Provide technical support",
            explanation="Too vague for billing questions",
        )
        data = loc.model_dump()
        restored = FaultLocation.model_validate(data)
        assert restored == loc


class TestDiagnosis:
    def test_serialization_roundtrip(self):
        diagnosis = Diagnosis(
            fault_locations=[
                FaultLocation(
                    location_type="general_prompt",
                    relevant_text="Be helpful",
                    explanation="Too vague",
                ),
                FaultLocation(
                    location_type="node_prompt",
                    node_id="billing",
                    relevant_text="Handle billing",
                    explanation="Missing refund instructions",
                ),
            ],
            root_cause="Agent lacks specific billing refund guidance",
            transcript_evidence="USER: I want a refund\nASSISTANT: I can help with that",
        )
        data = diagnosis.model_dump()
        restored = Diagnosis.model_validate(data)
        assert restored == diagnosis
        assert len(restored.fault_locations) == 2


class TestPromptChange:
    def test_general_prompt_change(self):
        change = PromptChange(
            location_type="general_prompt",
            original_text="Be helpful",
            proposed_text="Be helpful and always offer refund options when asked",
            rationale="Agent needs explicit refund guidance",
        )
        assert change.location_type == "general_prompt"
        assert change.node_id is None

    def test_node_prompt_change(self):
        change = PromptChange(
            location_type="node_prompt",
            node_id="billing",
            original_text="Handle billing",
            proposed_text="Handle billing inquiries including refunds",
            rationale="Add refund handling",
        )
        assert change.node_id == "billing"

    def test_transition_change(self):
        change = PromptChange(
            location_type="transition",
            node_id="greeting",
            transition_target_id="billing",
            original_text="User has billing question",
            proposed_text="User mentions billing, payments, or refunds",
            rationale="Broaden transition trigger",
        )
        assert change.transition_target_id == "billing"

    def test_serialization_roundtrip(self):
        change = PromptChange(
            location_type="node_prompt",
            node_id="support",
            original_text="old text",
            proposed_text="better text",
            rationale="clarity",
        )
        data = change.model_dump()
        restored = PromptChange.model_validate(data)
        assert restored == change


class TestFixSuggestion:
    def test_serialization_roundtrip(self):
        fix = FixSuggestion(
            changes=[
                PromptChange(
                    location_type="general_prompt",
                    original_text="old",
                    proposed_text="better",
                    rationale="improvement",
                ),
            ],
            summary="Updated general prompt for clarity",
            confidence=0.85,
        )
        data = fix.model_dump()
        restored = FixSuggestion.model_validate(data)
        assert restored == fix
        assert restored.confidence == 0.85

    def test_confidence_bounds(self):
        fix = FixSuggestion(
            changes=[],
            summary="No changes needed",
            confidence=0.0,
        )
        assert fix.confidence == 0.0

        fix2 = FixSuggestion(
            changes=[],
            summary="Very confident",
            confidence=1.0,
        )
        assert fix2.confidence == 1.0


class TestDiagnosisResult:
    def test_serialization_roundtrip(self):
        result = DiagnosisResult(
            diagnosis=Diagnosis(
                fault_locations=[
                    FaultLocation(
                        location_type="node_prompt",
                        node_id="greeting",
                        relevant_text="Greet user",
                        explanation="Too brief",
                    )
                ],
                root_cause="Greeting too brief",
                transcript_evidence="ASSISTANT: Hi",
            ),
            fix=FixSuggestion(
                changes=[
                    PromptChange(
                        location_type="node_prompt",
                        node_id="greeting",
                        original_text="Greet user",
                        proposed_text="Greet user warmly and ask how you can help",
                        rationale="More welcoming",
                    )
                ],
                summary="Expanded greeting prompt",
                confidence=0.9,
            ),
        )
        data = result.model_dump()
        restored = DiagnosisResult.model_validate(data)
        assert restored == result


class TestFixAttemptResult:
    def test_serialization_roundtrip(self):
        result = FixAttemptResult(
            iteration=1,
            changes_applied=[
                PromptChange(
                    location_type="general_prompt",
                    original_text="old",
                    proposed_text="better",
                    rationale="fix",
                )
            ],
            test_passed=False,
            metric_results=[
                {"metric": "helpfulness", "score": 0.8, "passed": True},
                {"metric": "accuracy", "score": 0.5, "passed": False},
            ],
            improved=True,
            original_scores={"helpfulness": 0.6, "accuracy": 0.4},
            new_scores={"helpfulness": 0.8, "accuracy": 0.5},
        )
        data = result.model_dump()
        restored = FixAttemptResult.model_validate(data)
        assert restored == result
        assert restored.improved is True
        assert restored.test_passed is False
        assert restored.iteration == 1

    def test_passed_attempt(self):
        result = FixAttemptResult(
            iteration=2,
            changes_applied=[],
            test_passed=True,
            metric_results=[],
            improved=True,
            original_scores={"helpfulness": 0.6},
            new_scores={"helpfulness": 0.95},
        )
        assert result.test_passed is True
