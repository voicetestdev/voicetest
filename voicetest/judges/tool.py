"""Tool judge for validating tool/function calls."""

from voicetest.models.results import ToolCall


class ToolJudge:
    """Validate tool calls during conversation.

    Checks that required tools were called and validates
    their usage patterns.
    """

    def validate(
        self,
        tools_called: list[ToolCall],
        required_tools: list[str] | None = None,
    ) -> list[str]:
        """Validate tool calls against requirements.

        Args:
            tools_called: List of tool calls made during conversation.
            required_tools: Tools that must have been called.

        Returns:
            List of violation messages (empty if all requirements met).
        """
        violations = []

        if required_tools:
            called_names = {tc.name for tc in tools_called}
            for required in required_tools:
                if required not in called_names:
                    violations.append(f"Required tool '{required}' was not called")

        return violations
