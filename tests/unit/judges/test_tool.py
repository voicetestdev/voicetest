"""Tests for voicetest.judges.tool module."""

from voicetest.models.results import ToolCall


class TestToolJudge:
    """Tests for ToolJudge (optional)."""

    def test_create_judge(self):
        from voicetest.judges.tool import ToolJudge

        judge = ToolJudge()

        assert judge is not None

    def test_validate_required_tools_called(self):
        from voicetest.judges.tool import ToolJudge

        judge = ToolJudge()

        tools_called = [
            ToolCall(name="lookup_account", arguments={"id": "123"}),
            ToolCall(name="get_balance", arguments={}),
        ]

        violations = judge.validate(
            tools_called=tools_called,
            required_tools=["lookup_account"]
        )

        assert violations == []

    def test_validate_required_tool_not_called(self):
        from voicetest.judges.tool import ToolJudge

        judge = ToolJudge()

        tools_called = [
            ToolCall(name="lookup_account", arguments={"id": "123"}),
        ]

        violations = judge.validate(
            tools_called=tools_called,
            required_tools=["lookup_account", "process_refund"]
        )

        assert len(violations) == 1
        assert "process_refund" in violations[0]
