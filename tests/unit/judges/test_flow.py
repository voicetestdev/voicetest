"""Tests for voicetest.judges.flow module."""


class TestFlowJudge:
    """Tests for FlowJudge."""

    def test_create_judge(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        assert judge is not None

    def test_validate_returns_empty_list(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        violations = judge.validate(
            nodes_visited=["greeting", "billing", "end"],
        )

        assert violations == []

    def test_validate_with_empty_nodes(self):
        from voicetest.judges.flow import FlowJudge

        judge = FlowJudge()

        violations = judge.validate(nodes_visited=[])

        assert violations == []
