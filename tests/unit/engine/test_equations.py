"""Tests for voicetest.engine.equations module."""

from voicetest.engine.equations import evaluate_equation
from voicetest.models.agent import EquationClause


class TestEvaluateEquationEquals:
    """Tests for == operator."""

    def test_string_match(self):
        clause = EquationClause(left="account_type", operator="==", right="premium")
        assert evaluate_equation(clause, {"account_type": "premium"}) is True

    def test_string_mismatch(self):
        clause = EquationClause(left="account_type", operator="==", right="premium")
        assert evaluate_equation(clause, {"account_type": "standard"}) is False

    def test_numeric_match(self):
        clause = EquationClause(left="age", operator="==", right="25")
        assert evaluate_equation(clause, {"age": "25"}) is True

    def test_case_sensitive(self):
        clause = EquationClause(left="status", operator="==", right="Active")
        assert evaluate_equation(clause, {"status": "active"}) is False


class TestEvaluateEquationNotEquals:
    """Tests for != operator."""

    def test_not_equal_true(self):
        clause = EquationClause(left="account_type", operator="!=", right="premium")
        assert evaluate_equation(clause, {"account_type": "standard"}) is True

    def test_not_equal_false(self):
        clause = EquationClause(left="account_type", operator="!=", right="premium")
        assert evaluate_equation(clause, {"account_type": "premium"}) is False


class TestEvaluateEquationComparisons:
    """Tests for >, >=, <, <= operators with numeric values."""

    def test_greater_than_true(self):
        clause = EquationClause(left="age", operator=">", right="18")
        assert evaluate_equation(clause, {"age": "25"}) is True

    def test_greater_than_false(self):
        clause = EquationClause(left="age", operator=">", right="18")
        assert evaluate_equation(clause, {"age": "10"}) is False

    def test_greater_than_equal(self):
        clause = EquationClause(left="age", operator=">", right="18")
        assert evaluate_equation(clause, {"age": "18"}) is False

    def test_greater_equal_true(self):
        clause = EquationClause(left="score", operator=">=", right="90")
        assert evaluate_equation(clause, {"score": "90"}) is True

    def test_greater_equal_above(self):
        clause = EquationClause(left="score", operator=">=", right="90")
        assert evaluate_equation(clause, {"score": "95"}) is True

    def test_greater_equal_below(self):
        clause = EquationClause(left="score", operator=">=", right="90")
        assert evaluate_equation(clause, {"score": "89"}) is False

    def test_less_than_true(self):
        clause = EquationClause(left="age", operator="<", right="18")
        assert evaluate_equation(clause, {"age": "10"}) is True

    def test_less_than_false(self):
        clause = EquationClause(left="age", operator="<", right="18")
        assert evaluate_equation(clause, {"age": "25"}) is False

    def test_less_equal_true(self):
        clause = EquationClause(left="count", operator="<=", right="5")
        assert evaluate_equation(clause, {"count": "5"}) is True

    def test_less_equal_below(self):
        clause = EquationClause(left="count", operator="<=", right="5")
        assert evaluate_equation(clause, {"count": "3"}) is True

    def test_less_equal_above(self):
        clause = EquationClause(left="count", operator="<=", right="5")
        assert evaluate_equation(clause, {"count": "6"}) is False

    def test_non_numeric_comparison_returns_false(self):
        clause = EquationClause(left="name", operator=">", right="18")
        assert evaluate_equation(clause, {"name": "alice"}) is False


class TestEvaluateEquationContains:
    """Tests for contains and not_contains operators."""

    def test_contains_true(self):
        clause = EquationClause(left="greeting", operator="contains", right="hello")
        assert evaluate_equation(clause, {"greeting": "hello world"}) is True

    def test_contains_false(self):
        clause = EquationClause(left="greeting", operator="contains", right="goodbye")
        assert evaluate_equation(clause, {"greeting": "hello world"}) is False

    def test_not_contains_true(self):
        clause = EquationClause(left="greeting", operator="not_contains", right="goodbye")
        assert evaluate_equation(clause, {"greeting": "hello world"}) is True

    def test_not_contains_false(self):
        clause = EquationClause(left="greeting", operator="not_contains", right="hello")
        assert evaluate_equation(clause, {"greeting": "hello world"}) is False


class TestEvaluateEquationExists:
    """Tests for exists and not_exist operators."""

    def test_exists_true(self):
        clause = EquationClause(left="account_type", operator="exists")
        assert evaluate_equation(clause, {"account_type": "premium"}) is True

    def test_exists_false(self):
        clause = EquationClause(left="account_type", operator="exists")
        assert evaluate_equation(clause, {"other_var": "value"}) is False

    def test_exists_empty_string(self):
        clause = EquationClause(left="account_type", operator="exists")
        assert evaluate_equation(clause, {"account_type": ""}) is True

    def test_not_exist_true(self):
        clause = EquationClause(left="account_type", operator="not_exist")
        assert evaluate_equation(clause, {"other_var": "value"}) is True

    def test_not_exist_false(self):
        clause = EquationClause(left="account_type", operator="not_exist")
        assert evaluate_equation(clause, {"account_type": "premium"}) is False


class TestEvaluateEquationMissingVariable:
    """Tests for missing variable behavior."""

    def test_missing_variable_equals_returns_false(self):
        clause = EquationClause(left="missing_var", operator="==", right="value")
        assert evaluate_equation(clause, {}) is False

    def test_missing_variable_not_equals_returns_false(self):
        clause = EquationClause(left="missing_var", operator="!=", right="value")
        assert evaluate_equation(clause, {}) is False

    def test_missing_variable_contains_returns_false(self):
        clause = EquationClause(left="missing_var", operator="contains", right="value")
        assert evaluate_equation(clause, {}) is False

    def test_missing_variable_comparison_returns_false(self):
        clause = EquationClause(left="missing_var", operator=">", right="5")
        assert evaluate_equation(clause, {}) is False
