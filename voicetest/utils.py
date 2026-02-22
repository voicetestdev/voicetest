"""Utility functions for voicetest."""

from collections.abc import Callable
import re
from typing import Any


_VAR_PATTERN = re.compile(r"\{\{(\s*\w+\s*)\}\}")


def extract_variables(text: str) -> list[str]:
    """Extract unique {{var}} placeholder names from text, preserving first-appearance order.

    Args:
        text: The text containing {{var}} placeholders.

    Returns:
        List of unique variable names in first-appearance order.
    """
    raw_names = [m.strip() for m in _VAR_PATTERN.findall(text)]
    return list(dict.fromkeys(raw_names))


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

    return _VAR_PATTERN.sub(replace, text)


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
