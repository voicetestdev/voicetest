"""Test case exporters for various formats."""

from typing import Any

from voicetest.models.test_case import TestCase


def export_tests_retell(tests: list[TestCase]) -> list[dict[str, Any]]:
    """Export test cases to Retell format."""
    return [_convert_test_to_retell(t) for t in tests]


def _convert_test_to_retell(test: TestCase) -> dict[str, Any]:
    """Convert a TestCase to Retell test format.

    Retell's simulator UI only looks at the first element of the metrics
    array, so multiple metrics are combined into a single string."""
    result: dict[str, Any] = {
        "name": test.name,
        "user_prompt": test.user_prompt,
        "type": "simulation" if test.effective_type == "llm" else "unit",
    }

    if test.metrics:
        if len(test.metrics) == 1:
            result["metrics"] = test.metrics
        else:
            combined = "\n".join(f"- {m}" for m in test.metrics)
            result["metrics"] = [combined]

    if test.dynamic_variables:
        result["dynamic_variables"] = test.dynamic_variables

    if test.tool_mocks:
        result["tool_mocks"] = test.tool_mocks

    if test.llm_model:
        result["llm_model"] = test.llm_model

    if test.effective_type == "rule":
        if test.includes:
            result["includes"] = test.includes
        if test.excludes:
            result["excludes"] = test.excludes
        if test.patterns:
            result["patterns"] = test.patterns

    return result


def export_tests(tests: list[TestCase], format: str) -> list[dict[str, Any]]:
    """Export tests to the specified format."""
    if format == "retell":
        return export_tests_retell(tests)

    raise ValueError(f"Unknown test export format: {format}")
