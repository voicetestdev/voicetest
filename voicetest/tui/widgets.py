"""Textual widgets for voicetest TUI."""

from textual.widgets import ListItem, ListView, Static

from voicetest.formatting import format_flow, status_color, status_icon
from voicetest.models.results import TestResult
from voicetest.models.test_case import TestCase


class TestListItem(ListItem):
    """A single test case in the list."""

    def __init__(self, test_case: TestCase):
        super().__init__()
        self.test_case = test_case
        self.result: TestResult | None = None

    def compose(self):
        """Create the item content."""
        yield Static(self._format_label())

    def _format_label(self) -> str:
        """Format the display label."""
        if self.result is None:
            icon = "\u25cb"  # Empty circle
            color = "dim"
        else:
            icon = status_icon(self.result.status)
            color = status_color(self.result.status)

        return f"[{color}]{icon}[/{color}] {self.test_case.name}"

    def set_result(self, result: TestResult) -> None:
        """Update with test result."""
        self.result = result
        static = self.query_one(Static)
        static.update(self._format_label())


class TestList(ListView):
    """List of test cases with status."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._items: dict[str, TestListItem] = {}

    def set_tests(self, test_cases: list[TestCase]) -> None:
        """Populate the list with test cases."""
        self.clear()
        self._items.clear()

        for tc in test_cases:
            item = TestListItem(tc)
            self._items[tc.id] = item
            self.append(item)

    def update_result(self, result: TestResult) -> None:
        """Update a test with its result."""
        if result.test_id in self._items:
            self._items[result.test_id].set_result(result)

    def get_selected_result(self) -> TestResult | None:
        """Get the result for the currently selected test."""
        if self.highlighted_child and isinstance(self.highlighted_child, TestListItem):
            return self.highlighted_child.result
        return None


class ResultsPanel(Static):
    """Summary panel showing pass/fail counts."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._passed = 0
        self._failed = 0
        self._total = 0
        self._update_display()

    def update_counts(self, passed: int, failed: int, total: int) -> None:
        """Update the counts."""
        self._passed = passed
        self._failed = failed
        self._total = total
        self._update_display()

    def _update_display(self) -> None:
        """Refresh the display."""
        completed = self._passed + self._failed
        self.update(
            f"[bold]Results[/bold]\n"
            f"[green]\u2713 {self._passed} passed[/green]  "
            f"[red]\u2717 {self._failed} failed[/red]  "
            f"[dim]{completed}/{self._total}[/dim]"
        )


class TranscriptViewer(Static):
    """Viewer for test transcript and details."""

    def __init__(self, **kwargs):
        super().__init__("Select a test to view details", **kwargs)

    def show_result(self, result: TestResult) -> None:
        """Display a test result."""
        color = status_color(result.status)
        lines = [
            f"[bold]{result.test_name}[/bold]",
            f"Status: [{color}]{result.status}[/{color}]",
            f"Duration: {result.duration_ms}ms | Turns: {result.turn_count}",
            "",
        ]

        # Flow
        if result.nodes_visited:
            lines.append("[bold]Flow:[/bold]")
            lines.append(format_flow(result.nodes_visited, " \u2192 "))
            lines.append("")

        # Metrics
        if result.metric_results:
            lines.append("[bold]Metrics:[/bold]")
            for m in result.metric_results:
                m_status = "pass" if m.passed else "fail"
                icon = status_icon(m_status)
                m_color = status_color(m_status)
                lines.append(f"  [{m_color}]{icon}[/{m_color}] {m.metric}")
            lines.append("")

        # Violations
        if result.constraint_violations:
            lines.append("[bold red]Violations:[/bold red]")
            for v in result.constraint_violations:
                lines.append(f"  [red]{status_icon('fail')} {v}[/red]")
            lines.append("")

        # Transcript
        if result.transcript:
            lines.append("[bold]Transcript:[/bold]")
            for msg in result.transcript:
                role_color = "cyan" if msg.role == "user" else "green"
                lines.append(f"  [{role_color}]{msg.role.upper()}:[/{role_color}] {msg.content}")

        self.update("\n".join(lines))
