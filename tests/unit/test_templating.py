"""Tests for voicetest.util.templating module."""

import types
import typing

from pydantic import BaseModel

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.agent import EquationClause
from voicetest.models.agent import GlobalNodeSetting
from voicetest.models.agent import GoBackCondition
from voicetest.models.agent import NodeType
from voicetest.models.agent import ToolDefinition
from voicetest.models.agent import Transition
from voicetest.models.agent import TransitionCondition
from voicetest.models.agent import VariableExtraction
from voicetest.util.templating import expand_snippets
from voicetest.util.templating import extract_graph_variables
from voicetest.util.templating import extract_snippet_refs
from voicetest.util.templating import extract_variables
from voicetest.util.templating import render_graph
from voicetest.util.templating import substitute_variables


class TestSubstituteVariables:
    """Tests for substitute_variables function."""

    def test_basic_substitution(self):
        """Test basic variable substitution."""
        text = "Hello, {{name}}!"
        result = substitute_variables(text, {"name": "World"})
        assert result == "Hello, World!"

    def test_multiple_variables(self):
        """Test multiple variable substitution."""
        text = "{{greeting}}, {{name}}! Welcome to {{place}}."
        variables = {"greeting": "Hello", "name": "Alice", "place": "Wonderland"}
        result = substitute_variables(text, variables)
        assert result == "Hello, Alice! Welcome to Wonderland."

    def test_variable_with_spaces(self):
        """Test variable names with surrounding spaces."""
        text = "Hello, {{ name }}!"
        result = substitute_variables(text, {"name": "World"})
        assert result == "Hello, World!"

    def test_unknown_variable_unchanged(self):
        """Test unknown variables remain unchanged."""
        text = "Hello, {{unknown}}!"
        result = substitute_variables(text, {"name": "World"})
        assert result == "Hello, {{unknown}}!"

    def test_empty_variables(self):
        """Test empty variables dict."""
        text = "Hello, {{name}}!"
        result = substitute_variables(text, {})
        assert result == "Hello, {{name}}!"

    def test_no_variables_in_text(self):
        """Test text without any variables."""
        text = "Hello, World!"
        result = substitute_variables(text, {"name": "Test"})
        assert result == "Hello, World!"

    def test_numeric_value(self):
        """Test numeric variable values."""
        text = "The answer is {{number}}."
        result = substitute_variables(text, {"number": 42})
        assert result == "The answer is 42."

    def test_same_variable_multiple_times(self):
        """Test same variable appearing multiple times."""
        text = "{{name}} says hello to {{name}}."
        result = substitute_variables(text, {"name": "Alice"})
        assert result == "Alice says hello to Alice."


class TestExtractVariables:
    """Tests for extract_variables function."""

    def test_basic(self):
        result = extract_variables("Hello {{name}}")
        assert result == ["name"]

    def test_multiple(self):
        result = extract_variables("{{greeting}}, {{name}}! Welcome to {{place}}.")
        assert result == ["greeting", "name", "place"]

    def test_dedup(self):
        result = extract_variables("{{a}} and {{a}}")
        assert result == ["a"]

    def test_whitespace(self):
        result = extract_variables("{{ name }}")
        assert result == ["name"]

    def test_empty(self):
        result = extract_variables("no vars here")
        assert result == []

    def test_preserves_order(self):
        result = extract_variables("{{z}} then {{a}} then {{m}}")
        assert result == ["z", "a", "m"]

    def test_dedup_preserves_first_occurrence_order(self):
        result = extract_variables("{{b}} then {{a}} then {{b}} then {{c}}")
        assert result == ["b", "a", "c"]


class TestExpandSnippets:
    """Tests for expand_snippets function."""

    def test_basic(self):
        result = expand_snippets("{%greeting%} world", {"greeting": "hello"})
        assert result == "hello world"

    def test_unknown_ref_unchanged(self):
        result = expand_snippets("{%unknown%} world", {"greeting": "hello"})
        assert result == "{%unknown%} world"

    def test_empty_dict(self):
        result = expand_snippets("{%greeting%} world", {})
        assert result == "{%greeting%} world"

    def test_whitespace_in_ref(self):
        result = expand_snippets("{% greeting %} world", {"greeting": "hello"})
        assert result == "hello world"

    def test_multiple_refs(self):
        snippets = {"greeting": "hello", "signoff": "goodbye"}
        result = expand_snippets("{%greeting%} and {%signoff%}", snippets)
        assert result == "hello and goodbye"

    def test_same_ref_multiple_times(self):
        result = expand_snippets("{%x%} then {%x%}", {"x": "val"})
        assert result == "val then val"

    def test_does_not_touch_dynamic_vars(self):
        result = expand_snippets("{{var}} and {%snip%}", {"snip": "replaced"})
        assert result == "{{var}} and replaced"

    def test_no_snippets_in_text(self):
        result = expand_snippets("plain text", {"greeting": "hello"})
        assert result == "plain text"


class TestExtractSnippetRefs:
    """Tests for extract_snippet_refs function."""

    def test_basic(self):
        result = extract_snippet_refs("{%greeting%} world")
        assert result == ["greeting"]

    def test_multiple_unique_order(self):
        result = extract_snippet_refs("{%z%} then {%a%} then {%m%}")
        assert result == ["z", "a", "m"]

    def test_dedup(self):
        result = extract_snippet_refs("{%a%} and {%a%}")
        assert result == ["a"]

    def test_whitespace(self):
        result = extract_snippet_refs("{% greeting %}")
        assert result == ["greeting"]

    def test_empty(self):
        result = extract_snippet_refs("no snippets here")
        assert result == []

    def test_ignores_dynamic_vars(self):
        result = extract_snippet_refs("{{var}} and {%snip%}")
        assert result == ["snip"]


RENDERED_FIELDS = {
    "AgentNode.state_prompt",
    "Transition.description",
    "TransitionCondition.value",
    "VariableExtraction.description",
    "VariableExtraction.choices",
    "GlobalNodeSetting.condition",
}

UNRENDERED_FIELDS = {
    "AgentGraph.entry_node_id",
    "AgentGraph.source_type",
    "AgentGraph.snippets",
    "AgentGraph.default_model",
    "AgentNode.id",
    "Transition.target_node_id",
    "EquationClause.left",
    "EquationClause.operator",
    "EquationClause.right",
    "VariableExtraction.name",
    "VariableExtraction.type",
    "ToolDefinition.name",
    "ToolDefinition.description",
    "ToolDefinition.type",
    "ToolDefinition.url",
    "ToolDefinition.tool_id",
    "GoBackCondition.id",
}


def _text_fields(model: type[BaseModel], seen: set[type] | None = None) -> set[str]:
    seen = seen if seen is not None else set()
    if model in seen:
        return set()
    seen.add(model)
    found: set[str] = set()

    def walk(owner: str, annotation: typing.Any) -> None:
        if annotation is str:
            found.add(owner)
        elif isinstance(annotation, type) and issubclass(annotation, BaseModel):
            found.update(_text_fields(annotation, seen))
        elif typing.get_origin(annotation) is dict:
            walk(owner, typing.get_args(annotation)[1])
        elif typing.get_origin(annotation) in (list, typing.Union, types.UnionType):
            for arg in typing.get_args(annotation):
                walk(owner, arg)

    for name, info in model.model_fields.items():
        walk(f"{model.__name__}.{name}", info.annotation)
    return found


class TestRenderGraph:
    @staticmethod
    def _templated_graph() -> AgentGraph:
        text = "{{color}} {%snip%}"
        return AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt=text,
                    node_type=NodeType.EXTRACT,
                    tools=[ToolDefinition(name="t", description="plain")],
                    transitions=[
                        Transition(
                            target_node_id="g",
                            condition=TransitionCondition(
                                type="equation",
                                value=text,
                                equations=[
                                    EquationClause(left="color", operator="==", right="blue")
                                ],
                            ),
                            description=text,
                        ),
                    ],
                    variables_to_extract=[
                        VariableExtraction(name="pick", description=text, choices=[text]),
                    ],
                ),
                "g": AgentNode(
                    id="g",
                    state_prompt=text,
                    node_type=NodeType.CONVERSATION,
                    global_node_setting=GlobalNodeSetting(
                        condition=text,
                        go_back_conditions=[
                            GoBackCondition(
                                id="back",
                                condition=TransitionCondition(type="llm_prompt", value=text),
                            ),
                        ],
                    ),
                ),
            },
            entry_node_id="a",
            source_type="custom",
            source_metadata={"general_prompt": text},
            snippets={"snip": "snippet"},
        )

    def test_every_text_field_is_classified(self):
        fields = _text_fields(AgentGraph)

        assert fields == RENDERED_FIELDS | UNRENDERED_FIELDS
        assert not RENDERED_FIELDS & UNRENDERED_FIELDS

    def test_renders_all_model_facing_text(self):
        rendered = render_graph(self._templated_graph(), {"color": "blue"})

        dumped = rendered.model_dump_json()
        assert "{{" not in dumped
        assert "{%" not in dumped
        assert rendered.source_metadata["general_prompt"] == "blue snippet"
        assert rendered.nodes["a"].variables_to_extract[0].choices == ["blue snippet"]
        assert rendered.nodes["g"].global_node_setting.go_back_conditions[0].condition.value == (
            "blue snippet"
        )
        assert rendered.snippets == {}

    def test_does_not_modify_original(self):
        graph = self._templated_graph()

        render_graph(graph, {"color": "blue"})

        assert graph.nodes["a"].state_prompt == "{{color}} {%snip%}"
        assert graph.snippets == {"snip": "snippet"}

    def test_without_variables_resolves_only_snippets(self):
        graph = self._templated_graph()

        rendered = render_graph(graph)

        assert rendered is not graph
        assert rendered.nodes["a"].state_prompt == "{{color}} snippet"
        assert rendered.nodes["a"].transitions[0].condition.value == "{{color}} snippet"
        assert rendered.snippets == {}

    def test_equation_operands_are_not_rendered(self):
        graph = self._templated_graph()
        graph.nodes["a"].transitions[0].condition.equations[0].right = "{{color}}"

        rendered = render_graph(graph, {"color": "blue"})

        assert rendered.nodes["a"].transitions[0].condition.equations[0].right == "{{color}}"


class TestExtractGraphVariables:
    def test_finds_variables_in_all_model_facing_text(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Hi {{name}}",
                    node_type=NodeType.EXTRACT,
                    transitions=[
                        Transition(
                            target_node_id="a",
                            condition=TransitionCondition(
                                type="llm_prompt", value="Asks about {{product}}"
                            ),
                        ),
                    ],
                    variables_to_extract=[
                        VariableExtraction(
                            name="pick", description="Return {{available_color}} if accepted"
                        ),
                    ],
                ),
            },
            entry_node_id="a",
            source_type="custom",
            source_metadata={"general_prompt": "{%intro%} {{name}}"},
            snippets={"intro": "You work for {{company}}."},
        )

        assert extract_graph_variables(graph) == ["company", "name", "product", "available_color"]

    def test_no_variables(self):
        graph = AgentGraph(
            nodes={
                "a": AgentNode(id="a", state_prompt="plain", node_type=NodeType.CONVERSATION),
            },
            entry_node_id="a",
            source_type="custom",
        )

        assert extract_graph_variables(graph) == []
