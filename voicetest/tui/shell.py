"""Interactive shell TUI for voicetest."""

import difflib
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, RichLog, Static

from voicetest.models.test_case import RunOptions
from voicetest.settings import Settings, load_settings, save_settings

COMMANDS = ["agent", "tests", "set", "run", "export", "importers", "clear", "quit", "exit", "help"]


class ConfigPanel(Static):
    """Panel showing current configuration."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._agent: Path | None = None
        self._tests: Path | None = None
        self._settings = load_settings()
        self._options = self._options_from_settings(self._settings)
        self._update_display()

    def _options_from_settings(self, settings: Settings) -> RunOptions:
        """Create RunOptions from Settings."""
        return RunOptions(
            agent_model=settings.models.agent,
            simulator_model=settings.models.simulator,
            judge_model=settings.models.judge,
            max_turns=settings.run.max_turns,
            verbose=settings.run.verbose,
        )

    def set_agent(self, path: Path) -> None:
        self._agent = path
        self._update_display()

    def set_tests(self, path: Path) -> None:
        self._tests = path
        self._update_display()

    def set_option(self, key: str, value: str) -> bool:
        """Set a run option and persist to .voicetest.toml. Returns True if valid."""
        if key == "agent_model":
            self._options.agent_model = value
            self._settings.models.agent = value
        elif key == "simulator_model":
            self._options.simulator_model = value
            self._settings.models.simulator = value
        elif key == "judge_model":
            self._options.judge_model = value
            self._settings.models.judge = value
        elif key == "max_turns":
            self._options.max_turns = int(value)
            self._settings.run.max_turns = int(value)
        elif key == "verbose":
            val = value.lower() in ("true", "1", "yes")
            self._options.verbose = val
            self._settings.run.verbose = val
        else:
            return False
        save_settings(self._settings)
        self._update_display()
        return True

    @property
    def agent_path(self) -> Path | None:
        return self._agent

    @property
    def tests_path(self) -> Path | None:
        return self._tests

    @property
    def options(self) -> RunOptions:
        return self._options

    def _update_display(self) -> None:
        agent_str = str(self._agent) if self._agent else "[dim]not set[/dim]"
        tests_str = str(self._tests) if self._tests else "[dim]not set[/dim]"

        self.update(
            f"[bold]Paths[/bold]\n"
            f"  agent: {agent_str}\n"
            f"  tests: {tests_str}\n"
            f"\n"
            f"[bold]Models[/bold]\n"
            f"  agent:     {self._options.agent_model}\n"
            f"  simulator: {self._options.simulator_model}\n"
            f"  judge:     {self._options.judge_model}\n"
            f"\n"
            f"[bold]Options[/bold]\n"
            f"  max_turns: {self._options.max_turns}\n"
            f"  verbose:   {self._options.verbose}"
        )


class VoicetestShell(App):
    """Interactive shell for voicetest."""

    CSS = """
    #main {
        layout: horizontal;
    }

    #left-panel {
        width: 50;
        border: solid $primary;
        padding: 1;
    }

    #right-panel {
        width: 1fr;
        border: solid $primary;
    }

    #output {
        height: 1fr;
    }

    #input-container {
        height: 3;
        dock: bottom;
        padding: 0 1;
    }

    #prompt {
        width: 2;
    }

    #command-input {
        width: 1fr;
    }

    ConfigPanel {
        height: auto;
    }
    """

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit"),
        Binding("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self):
        super().__init__()
        self._history: list[str] = []
        self._history_index = 0

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left-panel"):
                yield ConfigPanel(id="config-panel")
                yield Static(
                    "\n[bold]Commands[/bold]\n"
                    "  agent <path>     Set agent definition\n"
                    "  tests <path>     Set tests file\n"
                    "  set <key> <val>  Set option\n"
                    "  run              Run tests\n"
                    "  export <fmt>     Export (mermaid|livekit)\n"
                    "  importers        List importers\n"
                    "  clear            Clear output\n"
                    "  quit             Exit",
                    id="help-panel"
                )
            with Vertical(id="right-panel"):
                yield RichLog(id="output", highlight=True, markup=True)
                with Horizontal(id="input-container"):
                    yield Static("> ", id="prompt")
                    yield Input(placeholder="Enter command...", id="command-input")
        yield Footer()

    def on_mount(self) -> None:
        from voicetest.settings import SETTINGS_FILE
        self.title = "voicetest"
        self.sub_title = "interactive shell"
        self._log("[bold green]voicetest[/bold green] interactive shell")
        if Path(SETTINGS_FILE).exists():
            self._log(f"[dim]Loaded settings from {SETTINGS_FILE}[/dim]")
        self._log("Type 'help' for commands, 'quit' to exit\n")
        self.query_one("#command-input", Input).focus()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input."""
        command = event.value.strip()
        if not command:
            return

        event.input.value = ""
        self._history.append(command)
        self._history_index = len(self._history)

        self._log(f"[dim]>[/dim] {command}")
        await self._execute_command(command)

    async def _execute_command(self, command: str) -> None:
        """Execute a shell command."""
        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        config_panel = self.query_one("#config-panel", ConfigPanel)

        if cmd in ("quit", "exit", "q"):
            self.exit()

        elif cmd == "help":
            self._log(
                "[bold]Available commands:[/bold]\n"
                "  agent <path>        Set agent definition file\n"
                "  tests <path>        Set tests file\n"
                "  set <key> <value>   Set option (agent_model, simulator_model,\n"
                "                      judge_model, max_turns, verbose)\n"
                "  run                 Run tests\n"
                "  export <format>     Export agent (mermaid, livekit)\n"
                "  importers           List available importers\n"
                "  clear               Clear output\n"
                "  quit                Exit shell"
            )

        elif cmd == "agent":
            if not args:
                self._log("[red]Usage: agent <path>[/red]")
                return
            path = Path(args).expanduser()
            if not path.exists():
                self._log(f"[red]File not found: {path}[/red]")
                return
            config_panel.set_agent(path)
            self._log(f"[green]Agent set to {path}[/green]")

        elif cmd == "tests":
            if not args:
                self._log("[red]Usage: tests <path>[/red]")
                return
            path = Path(args).expanduser()
            if not path.exists():
                self._log(f"[red]File not found: {path}[/red]")
                return
            config_panel.set_tests(path)
            self._log(f"[green]Tests set to {path}[/green]")

        elif cmd == "set":
            parts = args.split(maxsplit=1)
            if len(parts) != 2:
                self._log("[red]Usage: set <key> <value>[/red]")
                return
            key, value = parts
            if config_panel.set_option(key, value):
                self._log(
                    f"[green]Set {key} = {value}[/green] [dim](saved to .voicetest.toml)[/dim]"
                )
            else:
                self._log(f"[red]Unknown option: {key}[/red]")

        elif cmd == "run":
            await self._run_tests(config_panel)

        elif cmd == "export":
            await self._export(config_panel, args)

        elif cmd == "importers":
            await self._list_importers()

        elif cmd == "clear":
            self.query_one("#output", RichLog).clear()

        else:
            # Try to find a similar command
            matches = difflib.get_close_matches(cmd, COMMANDS, n=1, cutoff=0.6)
            if matches:
                self._log(
                    f"[red]Unknown command: {cmd}[/red]. "
                    f"Did you mean '[cyan]{matches[0]}[/cyan]'?"
                )
            else:
                self._log(
                    f"[red]Unknown command: {cmd}[/red]. Type 'help' for available commands."
                )

    async def _run_tests(self, config_panel: ConfigPanel) -> None:
        """Run tests with current configuration."""
        if not config_panel.agent_path:
            self._log("[red]No agent set. Use 'agent <path>' first.[/red]")
            return
        if not config_panel.tests_path:
            self._log("[red]No tests set. Use 'tests <path>' first.[/red]")
            return

        from voicetest import api
        from voicetest.runner import load_test_cases

        self._log("[bold]Running tests...[/bold]")

        try:
            graph = await api.import_agent(config_panel.agent_path)
            self._log(f"  Loaded agent: {graph.source_type}, {len(graph.nodes)} nodes")

            test_cases = load_test_cases(config_panel.tests_path)
            self._log(f"  Loaded {len(test_cases)} test cases\n")

            run = await api.run_tests(graph, test_cases, config_panel.options)

            from voicetest.formatting import format_result_detail, format_run_summary

            for result in run.results:
                for line in format_result_detail(result):
                    self._log(line)

            self._log(f"\n[bold]{format_run_summary(run)}[/bold]")

        except Exception as e:
            self._log(f"[red]Error: {e}[/red]")

    async def _export(self, config_panel: ConfigPanel, format: str) -> None:
        """Export agent to format."""
        if not config_panel.agent_path:
            self._log("[red]No agent set. Use 'agent <path>' first.[/red]")
            return

        if not format:
            self._log("[red]Usage: export <format> (mermaid|livekit)[/red]")
            return

        from voicetest import api

        try:
            graph = await api.import_agent(config_panel.agent_path)
            result = await api.export_agent(graph, format=format)
            self._log(f"[bold]Exported ({format}):[/bold]\n{result}")
        except Exception as e:
            self._log(f"[red]Error: {e}[/red]")

    async def _list_importers(self) -> None:
        """List available importers."""
        from voicetest import api

        importers = api.list_importers()
        self._log("[bold]Available importers:[/bold]")
        for imp in importers:
            patterns = ", ".join(imp.file_patterns) if imp.file_patterns else "-"
            self._log(f"  [cyan]{imp.source_type}[/cyan]: {imp.description} ({patterns})")

    def action_clear(self) -> None:
        """Clear the output."""
        self.query_one("#output", RichLog).clear()

    def _log(self, message: str) -> None:
        """Log message to output."""
        self.query_one("#output", RichLog).write(message)
