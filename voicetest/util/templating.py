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
    """Extract unique {{var}} placeholder names from text, preserving first-appearance order."""
    raw_names = [m.strip() for m in _VAR_PATTERN.findall(text)]
    return list(dict.fromkeys(raw_names))


def substitute_variables(text: str, variables: dict[str, Any]) -> str:
    """Substitute {{var}} placeholders in text with values from variables dict.

    Unknown variables are left unchanged."""
    if not variables:
        return text

    def replace(match: re.Match) -> str:
        var_name = match.group(1).strip()
        if var_name in variables:
            return str(variables[var_name])
        return match.group(0)

    return _VAR_PATTERN.sub(replace, text)


def expand_snippets(text: str, snippets: dict[str, str]) -> str:
    """Replace {%name%} references with snippet content.

    Unknown refs are left unchanged."""
    if not snippets:
        return text

    def replace(match: re.Match) -> str:
        name = match.group(1).strip()
        if name in snippets:
            return snippets[name]
        return match.group(0)

    return _SNIPPET_PATTERN.sub(replace, text)


def extract_snippet_refs(text: str) -> list[str]:
    """Extract unique {%name%} snippet references from text, preserving first-appearance order."""
    raw_names = [m.strip() for m in _SNIPPET_PATTERN.findall(text)]
    return list(dict.fromkeys(raw_names))


def _rewrite_text(graph: AgentGraph, fn: Callable[[str], str]) -> None:
    general_prompt = graph.source_metadata.get("general_prompt")
    if isinstance(general_prompt, str):
        graph.source_metadata["general_prompt"] = fn(general_prompt)

    for node in graph.nodes.values():
        node.state_prompt = fn(node.state_prompt)
        for transition in node.transitions:
            transition.condition.value = fn(transition.condition.value)
            if transition.description:
                transition.description = fn(transition.description)
        for var in node.variables_to_extract:
            var.description = fn(var.description)
            var.choices = [fn(choice) for choice in var.choices]
        if node.global_node_setting:
            setting = node.global_node_setting
            setting.condition = fn(setting.condition)
            for go_back in setting.go_back_conditions:
                go_back.condition.value = fn(go_back.condition.value)


def render_graph(graph: AgentGraph, variables: dict[str, Any] | None = None) -> AgentGraph:
    rendered = copy.deepcopy(graph)
    snippets = rendered.snippets
    _rewrite_text(
        rendered,
        lambda text: substitute_variables(expand_snippets(text, snippets), variables or {}),
    )
    rendered.snippets = {}
    return rendered


def extract_graph_variables(graph: AgentGraph) -> list[str]:
    texts: list[str] = []

    def collect(text: str) -> str:
        texts.append(text)
        return text

    _rewrite_text(render_graph(graph), collect)
    return extract_variables("\n".join(texts))
