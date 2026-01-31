"""Utility functions for voicetest."""

from collections.abc import Callable
import re
from typing import Any


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


def create_template_filler(template: str) -> Callable[[dict[str, Any]], str]:
    """Create a reusable filler that always uses the original template.

    This prevents accidental double-substitution by always starting
    from the original template text.

    Args:
        template: The original template text with {{var}} placeholders.

    Returns:
        A function that takes a variables dict and returns the filled template.
    """

    def fill(variables: dict[str, Any]) -> str:
        return substitute_variables(template, variables)

    return fill
