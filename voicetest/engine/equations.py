"""Deterministic equation evaluator for logic node transitions."""

from typing import Any

from voicetest.models.agent import EquationClause


def evaluate_equation(clause: EquationClause, variables: dict[str, Any]) -> bool:
    """Evaluate a single equation clause against dynamic variables.

    For exists/not_exist operators, checks variable presence.
    For comparison operators (>, >=, <, <=), attempts numeric coercion.
    Missing variables return False (except for not_exist).
    """
    op = clause.operator

    if op == "exists":
        return clause.left in variables

    if op == "not_exist":
        return clause.left not in variables

    if clause.left not in variables:
        return False

    actual = str(variables[clause.left])
    # Resolve right side as a variable reference if it exists in variables
    expected = str(variables[clause.right]) if clause.right in variables else clause.right

    if op == "==":
        return actual == expected

    if op == "!=":
        return actual != expected

    if op == "contains":
        return expected in actual

    if op == "not_contains":
        return expected not in actual

    # Numeric comparison operators
    if op in (">", ">=", "<", "<="):
        try:
            left_num = float(actual)
            right_num = float(expected)
        except (ValueError, TypeError):
            return False

        if op == ">":
            return left_num > right_num
        if op == ">=":
            return left_num >= right_num
        if op == "<":
            return left_num < right_num
        if op == "<=":
            return left_num <= right_num

    return False
