"""Main Textual application for voicetest."""

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.widgets import Footer, Header, Static

from voicetest.models.test_case import RunOptions
from voicetest.runner import TestRunContext
from voicetest.tui.widgets import ResultsPanel, TestList, TranscriptViewer


class VoicetestApp(App):
    """Interactive TUI for running voice agent tests."""

    CSS = """
    #main-container {
        layout: horizontal;
    }

    #left-panel {
        width: 40;
        border: solid $primary;
    }

    #right-panel {
        width: 1fr;
        border: solid $primary;
    }

    #status-bar {
        height: 3;
        dock: bottom;
        background: $surface;
        padding: 1;
    }

    TestList {
        height: 1fr;
    }

    ResultsPanel {
        height: auto;
        max-height: 10;
    }

    TranscriptViewer {
        height: 1fr;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "run_tests", "Run Tests"),
        Binding("j", "next_test", "Next"),
        Binding("k", "prev_test", "Previous"),
        Binding("enter", "select_test", "View Details"),
    ]

    def __init__(
        self,
        config_path: Path,
        tests_path: Path,
        source: str | None = None,
        options: RunOptions | None = None,
        mock_mode: bool = False,
    ):
        super().__init__()
        self.context = TestRunContext(
            config_path=config_path,
            tests_path=tests_path,
            source=source,
            options=options,
            mock_mode=mock_mode,
        )
        self._running = False

    def compose(self) -> ComposeResult:
        """Create the UI layout."""
        yield Header()
        with Container(id="main-container"):
            with Vertical(id="left-panel"):
                yield TestList(id="test-list")
                yield ResultsPanel(id="results-panel")
            with Vertical(id="right-panel"):
                yield TranscriptViewer(id="transcript-viewer")
        yield Static("Press 'r' to run tests, 'q' to quit", id="status-bar")
        yield Footer()

    async def on_mount(self) -> None:
        """Initialize when app starts."""
        self.title = "voicetest"
        self.sub_title = str(self.context.config_path.name)

        # Load test cases
        await self.context.load()

        # Populate test list
        test_list = self.query_one("#test-list", TestList)
        test_list.set_tests(self.context.test_cases)

        self._update_status(f"Loaded {self.context.total_tests} tests. Press 'r' to run.")

    async def action_run_tests(self) -> None:
        """Run all tests."""
        if self._running:
            return

        self._running = True
        self._update_status("Running tests...")

        test_list = self.query_one("#test-list", TestList)
        results_panel = self.query_one("#results-panel", ResultsPanel)

        async for result in self.context.run_streaming():
            test_list.update_result(result)
            results_panel.update_counts(
                self.context.passed_count,
                self.context.failed_count,
                self.context.total_tests,
            )
            self._update_status(
                f"Running... {self.context.completed_tests}/{self.context.total_tests}"
            )

        self._running = False
        self._update_status(
            f"Complete: {self.context.passed_count} passed, "
            f"{self.context.failed_count} failed"
        )

    def action_next_test(self) -> None:
        """Move to next test in list."""
        test_list = self.query_one("#test-list", TestList)
        test_list.action_cursor_down()

    def action_prev_test(self) -> None:
        """Move to previous test in list."""
        test_list = self.query_one("#test-list", TestList)
        test_list.action_cursor_up()

    def action_select_test(self) -> None:
        """View details of selected test."""
        test_list = self.query_one("#test-list", TestList)
        selected = test_list.get_selected_result()
        if selected:
            viewer = self.query_one("#transcript-viewer", TranscriptViewer)
            viewer.show_result(selected)

    def _update_status(self, message: str) -> None:
        """Update status bar."""
        status = self.query_one("#status-bar", Static)
        status.update(message)
