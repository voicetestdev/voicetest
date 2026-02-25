"""Tests for voicetest.templating module."""

from voicetest.templating import expand_graph_snippets
from voicetest.templating import expand_snippets
from voicetest.templating import extract_snippet_refs
from voicetest.templating import extract_variables
from voicetest.templating import substitute_variables


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


class TestExpandGraphSnippets:
    """Tests for expand_graph_snippets function."""

    def test_expands_all_prompts(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="Node A: {%disclaimer%}",
                    transitions=[],
                ),
                "b": AgentNode(
                    id="b",
                    state_prompt="Node B: {%disclaimer%}",
                    transitions=[],
                ),
            },
            entry_node_id="a",
            source_type="custom",
            source_metadata={"general_prompt": "General: {%disclaimer%}"},
            snippets={"disclaimer": "We are not liable."},
        )

        expanded = expand_graph_snippets(graph)

        assert expanded.source_metadata["general_prompt"] == "General: We are not liable."
        assert expanded.nodes["a"].state_prompt == "Node A: We are not liable."
        assert expanded.nodes["b"].state_prompt == "Node B: We are not liable."
        assert expanded.snippets == {}

    def test_does_not_modify_original(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="{%snip%}",
                    transitions=[],
                ),
            },
            entry_node_id="a",
            source_type="custom",
            snippets={"snip": "expanded"},
        )

        expand_graph_snippets(graph)

        # Original is unchanged
        assert graph.nodes["a"].state_prompt == "{%snip%}"
        assert graph.snippets == {"snip": "expanded"}

    def test_empty_snippets_returns_copy(self):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "a": AgentNode(
                    id="a",
                    state_prompt="plain text",
                    transitions=[],
                ),
            },
            entry_node_id="a",
            source_type="custom",
        )

        expanded = expand_graph_snippets(graph)
        assert expanded.nodes["a"].state_prompt == "plain text"
        assert expanded.snippets == {}
        assert expanded is not graph
