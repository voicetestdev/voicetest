"""Template substitution for voicetest prompts.

Handles two layers of text expansion:
- Snippets: {%name%} — static, agent-level text blocks resolved before conversation
- Variables: {{name}} — dynamic, per-session values resolved at turn time
"""

from __future__ import annotations

from collections.abc import Callable
import copy
import re
from typing import TYPE_CHECKING
from typing import Any


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph

_VAR_PATTERN = re.compile(r"\{\{(\s*\w+\s*)\}\}")
_SNIPPET_PATTERN = re.compile(r"\{%\s*(\w+)\s*%\}")


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


def expand_snippets(text: str, snippets: dict[str, str]) -> str:
    """Replace {%name%} references with snippet content.

    Args:
        text: The text containing {%name%} references.
        snippets: Dictionary mapping snippet names to content.

    Returns:
        Text with known snippet refs replaced. Unknown refs are left unchanged.
    """
    if not snippets:
        return text

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        if name in snippets:
            return snippets[name]
        return match.group(0)

    return _SNIPPET_PATTERN.sub(replace, text)


def extract_snippet_refs(text: str) -> list[str]:
    """Extract unique {%name%} snippet references from text, preserving first-appearance order.

    Args:
        text: The text containing {%name%} references.

    Returns:
        List of unique snippet names in first-appearance order.
    """
    raw_names = [m.strip() for m in _SNIPPET_PATTERN.findall(text)]
    return list(dict.fromkeys(raw_names))


def expand_graph_snippets(graph: AgentGraph) -> AgentGraph:
    """Return a deep copy of the graph with all {%ref%} resolved in prompts.

    Expands snippet references in general_prompt and every node's state_prompt.
    The returned copy has an empty snippets dict.

    Args:
        graph: The agent graph containing snippets and prompt text.

    Returns:
        A deep copy with all snippet refs resolved and snippets dict emptied.
    """
    expanded = copy.deepcopy(graph)
    snippets = expanded.snippets

    # Expand general_prompt in source_metadata
    general_prompt = expanded.source_metadata.get("general_prompt")
    if general_prompt and isinstance(general_prompt, str):
        expanded.source_metadata["general_prompt"] = expand_snippets(general_prompt, snippets)

    # Expand each node's state_prompt
    for node in expanded.nodes.values():
        if node.state_prompt:
            node.state_prompt = expand_snippets(node.state_prompt, snippets)

    expanded.snippets = {}
    return expanded
