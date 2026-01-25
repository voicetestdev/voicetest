"""Utility functions for voicetest."""

import re
from typing import Any

import dspy


class DSPyAdapterMixin:
    """Mixin providing DSPy adapter context management."""

    _adapter: dspy.Adapter | None = None

    def _dspy_context(self, lm):
        """Get DSPy context with configured adapter."""
        return dspy.context(lm=lm, adapter=self._adapter)


def substitute_variables(text: str, variables: dict[str, Any]) -> str:
    """Substitute {{var}} placeholders in text with values from variables dict.

    Args:
        text: The text containing {{var}} placeholders.
        variables: Dictionary mapping variable names to values.

    Returns:
        Text with all placeholders replaced. Unknown variables are left unchanged.
    """
    if not variables:
        return text

    def replace(match: re.Match) -> str:
        var_name = match.group(1).strip()
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)

    return re.sub(r"\{\{(\s*\w+\s*)\}\}", replace, text)
