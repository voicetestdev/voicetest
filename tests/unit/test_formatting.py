"""Tests for formatting utilities."""

from datetime import datetime

from voicetest.formatting import (
    format_flow,
    format_result_detail,
    format_result_line,
    format_run,
    format_run_summary,
    status_color,
    status_icon,
)
from voicetest.models.results import MetricResult, TestResult, TestRun


class TestStatusIcon:
    """Tests for status_icon function."""

    def test_pass_icon(self):
        assert status_icon("pass") == "\u2713"

    def test_fail_icon(self):
        assert status_icon("fail") == "\u2717"

    def test_error_icon(self):
        assert status_icon("error") == "!"

    def test_unknown_icon(self):
        assert status_icon("unknown") == "?"


class TestStatusColor:
    """Tests for status_color function."""

    def test_pass_color(self):
        assert status_color("pass") == "green"

    def test_fail_color(self):
        assert status_color("fail") == "red"

    def test_error_color(self):
        assert status_color("error") == "yellow"

    def test_unknown_color(self):
        assert status_color("unknown") == "white"


class TestFormatFlow:
    """Tests for format_flow function."""

    def test_empty_flow(self):
        assert format_flow([]) == ""

    def test_single_node(self):
        assert format_flow(["greeting"]) == "greeting"

    def test_multiple_nodes(self):
        assert format_flow(["greeting", "collect_info", "end"]) == "greeting -> collect_info -> end"

    def test_custom_separator(self):
        assert format_flow(["a", "b", "c"], " | ") == "a | b | c"


class TestFormatResultLine:
    """Tests for format_result_line function."""

    def test_pass_result(self):
        result = TestResult(
            test_id="test-1",
            test_name="Test One",
            status="pass",
            turn_count=5,
            duration_ms=100,
        )
        line = format_result_line(result)
        assert "[green]\u2713[/green]" in line
        assert "[bold]Test One[/bold]" in line
        assert "5 turns" in line
        assert "100ms" in line

    def test_fail_result(self):
        result = TestResult(
            test_id="test-1",
            test_name="Test One",
            status="fail",
            turn_count=3,
            duration_ms=50,
        )
        line = format_result_line(result)
        assert "[red]\u2717[/red]" in line


class TestFormatResultDetail:
    """Tests for format_result_detail function."""

    def test_basic_result(self):
        result = TestResult(
            test_id="test-1",
            test_name="Test One",
            status="pass",
            turn_count=5,
            duration_ms=100,
        )
        lines = format_result_detail(result)
        assert len(lines) == 1

    def test_result_with_flow(self):
        result = TestResult(
            test_id="test-1",
            test_name="Test One",
            status="pass",
            turn_count=5,
            duration_ms=100,
            nodes_visited=["greeting", "collect_info"],
        )
        lines = format_result_detail(result)
        assert any("Flow:" in line for line in lines)
        assert any("greeting -> collect_info" in line for line in lines)

    def test_result_with_metrics(self):
        result = TestResult(
            test_id="test-1",
            test_name="Test One",
            status="pass",
            turn_count=5,
            duration_ms=100,
            metric_results=[
                MetricResult(metric="politeness", passed=True, score=0.9, reasoning="Good"),
                MetricResult(metric="accuracy", passed=False, score=0.3, reasoning="Bad"),
            ],
        )
        lines = format_result_detail(result)
        assert any("[green]\u2713[/green] politeness" in line for line in lines)
        assert any("[red]\u2717[/red] accuracy" in line for line in lines)

    def test_result_with_violations(self):
        result = TestResult(
            test_id="test-1",
            test_name="Test One",
            status="fail",
            turn_count=5,
            duration_ms=100,
            constraint_violations=["Failed to visit end node"],
        )
        lines = format_result_detail(result)
        assert any("Failed to visit end node" in line for line in lines)


class TestFormatRunSummary:
    """Tests for format_run_summary function."""

    def test_summary(self):
        run = TestRun(
            run_id="run-1",
            started_at=datetime.now(),
            results=[
                TestResult(test_id="1", test_name="A", status="pass", turn_count=1, duration_ms=10),
                TestResult(test_id="2", test_name="B", status="pass", turn_count=1, duration_ms=10),
                TestResult(test_id="3", test_name="C", status="fail", turn_count=1, duration_ms=10),
            ],
        )
        summary = format_run_summary(run)
        assert "2 passed" in summary
        assert "1 failed" in summary


class TestFormatRun:
    """Tests for format_run function."""

    def test_format_full_run(self):
        run = TestRun(
            run_id="run-1",
            started_at=datetime.now(),
            results=[
                TestResult(
                    test_id="1", test_name="Test A", status="pass", turn_count=1, duration_ms=10
                ),
                TestResult(
                    test_id="2", test_name="Test B", status="fail", turn_count=2, duration_ms=20
                ),
            ],
        )
        lines = format_run(run)
        assert any("Test A" in line for line in lines)
        assert any("Test B" in line for line in lines)
        assert any("1 passed" in line for line in lines)
        assert any("1 failed" in line for line in lines)
