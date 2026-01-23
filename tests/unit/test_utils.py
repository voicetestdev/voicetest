"""Tests for voicetest.utils module."""

from voicetest.utils import substitute_variables


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
