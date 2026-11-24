"""Template substitution for voicetest prompts.

Handles two layers of text expansion:
- Snippets: {%name%} — static, agent-level text blocks resolved before conversation
- Variables: {{name}} — dynamic, per-session values resolved at turn time
"""

from __future__ import annotations

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


def expand_graph_snippets(graph: AgentGraph) -> AgentGraph:
    """Return a deep copy of the graph with all {%ref%} resolved in prompts."""
    expanded = copy.deepcopy(graph)
    snippets = expanded.snippets

    general_prompt = expanded.source_metadata.get("general_prompt")
    if general_prompt and isinstance(general_prompt, str):
        expanded.source_metadata["general_prompt"] = expand_snippets(general_prompt, snippets)

    for node in expanded.nodes.values():
        if node.state_prompt:
            node.state_prompt = expand_snippets(node.state_prompt, snippets)

    expanded.snippets = {}
    return expanded


def render_graph(graph: AgentGraph, variables: dict[str, Any]) -> AgentGraph:
    """Return a deep copy of the graph with snippets and variables resolved in model-facing text."""
    rendered = copy.deepcopy(graph)
    snippets = rendered.snippets

    def render(text: str) -> str:
        return substitute_variables(expand_snippets(text, snippets), variables)

    general_prompt = rendered.source_metadata.get("general_prompt")
    if isinstance(general_prompt, str):
        rendered.source_metadata["general_prompt"] = render(general_prompt)

    for node in rendered.nodes.values():
        node.state_prompt = render(node.state_prompt)
        for transition in node.transitions:
            transition.condition.value = render(transition.condition.value)
            if transition.description:
                transition.description = render(transition.description)
        for var in node.variables_to_extract:
            var.description = render(var.description)
            var.choices = [render(choice) for choice in var.choices]
        for tool in node.tools:
            tool.description = render(tool.description)
        if node.global_node_setting:
            setting = node.global_node_setting
            setting.condition = render(setting.condition)
            for go_back in setting.go_back_conditions:
                go_back.condition.value = render(go_back.condition.value)

    rendered.snippets = {}
    return rendered
