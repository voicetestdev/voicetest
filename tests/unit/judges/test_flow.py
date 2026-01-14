"""Tests for voicetest.judges.flow module."""

from voicetest.models.test_case import TestCase


class TestFlowJudge:
    """Tests for FlowJudge."""

    def test_create_judge(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        assert judge is not None

    def test_validate_with_no_constraints(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test"
        )

        violations = judge.validate(
            nodes_visited=["greeting", "billing", "end"],
            test_case=test_case
        )

        assert violations == []

    def test_validate_required_nodes_all_visited(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test",
            required_nodes=["greeting", "billing"]
        )

        violations = judge.validate(
            nodes_visited=["greeting", "billing", "end"],
            test_case=test_case
        )

        assert violations == []

    def test_validate_required_node_missing(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test",
            required_nodes=["greeting", "billing", "supervisor"]
        )

        violations = judge.validate(
            nodes_visited=["greeting", "billing"],
            test_case=test_case
        )

        assert len(violations) == 1
        assert "supervisor" in violations[0]
        assert "not visited" in violations[0].lower()

    def test_validate_multiple_required_nodes_missing(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test",
            required_nodes=["greeting", "billing", "supervisor", "end"]
        )

        violations = judge.validate(
            nodes_visited=["greeting"],
            test_case=test_case
        )

        assert len(violations) == 3

    def test_validate_forbidden_nodes_not_visited(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test",
            forbidden_nodes=["escalation", "error"]
        )

        violations = judge.validate(
            nodes_visited=["greeting", "billing", "end"],
            test_case=test_case
        )

        assert violations == []

    def test_validate_forbidden_node_visited(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test",
            forbidden_nodes=["escalation"]
        )

        violations = judge.validate(
            nodes_visited=["greeting", "escalation", "end"],
            test_case=test_case
        )

        assert len(violations) == 1
        assert "escalation" in violations[0]
        assert "visited" in violations[0].lower()

    def test_validate_combined_required_and_forbidden(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        test_case = TestCase(
            id="test",
            name="Test",
            user_prompt="test",
            required_nodes=["greeting", "billing"],
            forbidden_nodes=["escalation"]
        )

        # Missing billing, visited escalation
        violations = judge.validate(
            nodes_visited=["greeting", "escalation", "end"],
            test_case=test_case
        )

        assert len(violations) == 2
