"""Shared formatting utilities for CLI, TUI, and shell."""

from voicetest.models.results import TestResult, TestRun


def status_icon(status: str) -> str:
    """Get icon for test status."""
    return {
        "pass": "\u2713",
        "fail": "\u2717",
        "error": "!",
    }.get(status, "?")


def status_color(status: str) -> str:
    """Get color for test status."""
    return {
        "pass": "green",
        "fail": "red",
        "error": "yellow",
    }.get(status, "white")


def format_flow(nodes: list[str], separator: str = " -> ") -> str:
    """Format node flow as string."""
    return separator.join(nodes) if nodes else ""


def format_result_line(result: TestResult) -> str:
    """Format a single result as one line."""
    icon = status_icon(result.status)
    color = status_color(result.status)
    return (
        f"[{color}]{icon}[/{color}] [bold]{result.test_name}[/bold] "
        f"({result.turn_count} turns, {result.duration_ms}ms)"
    )


def format_result_detail(result: TestResult) -> list[str]:
    """Format full result details as list of lines."""
    lines = [format_result_line(result)]

    if result.nodes_visited:
        lines.append(f"  Flow: {format_flow(result.nodes_visited)}")

    for m in result.metric_results:
        icon = status_icon("pass" if m.passed else "fail")
        color = status_color("pass" if m.passed else "fail")
        lines.append(f"  [{color}]{icon}[/{color}] {m.metric}")

    for v in result.constraint_violations:
        lines.append(f"  [red]\u2717 {v}[/red]")

    return lines


def format_run_summary(run: TestRun) -> str:
    """Format run summary line."""
    return f"Results: {run.passed_count} passed, {run.failed_count} failed"


def format_run(run: TestRun) -> list[str]:
    """Format complete run output."""
    lines = []
    for result in run.results:
        lines.extend(format_result_detail(result))
        lines.append("")
    lines.append("\u2500" * 50)
    lines.append(format_run_summary(run))
    return lines
