"""Interactive shell TUI for voicetest."""

import asyncio
import difflib
import os
from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.suggester import SuggestFromList
from textual.widgets import Footer, Header, Input, RichLog, Static

from voicetest import api
from voicetest.config import get_settings_path
from voicetest.models.test_case import RunOptions, TestCase
from voicetest.runner import load_test_cases
from voicetest.settings import Settings, load_settings, save_settings


COMMANDS = [
    "agent",
    "tests",
    "set",
    "env",
    "keys",
    "run",
    "export",
    "importers",
    "clear",
    "quit",
    "exit",
    "help",
    "?",
]

API_KEY_NAMES = [
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
]


class ConfigPanel(Static):
    """Panel showing current configuration."""

    def __init__(self, **kwargs):
        super().__init__("", **kwargs)
        self._agent: Path | None = None
        self._tests: Path | None = None
        self._test_cases: list[TestCase] = []
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

    def set_tests(self, path: Path, test_cases: list[TestCase] | None = None) -> None:
        self._tests = path
        self._test_cases = test_cases or []
        self._update_display()

    @property
    def test_cases(self) -> list[TestCase]:
        return self._test_cases

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
        Binding("ctrl+c", "interrupt", "Cancel/Quit", show=False),
        Binding("ctrl+l", "clear", "Clear"),
    ]

    def __init__(self, agent_path: Path | None = None, tests_path: Path | None = None):
        super().__init__()
        self._history: list[str] = []
        self._history_index = 0
        self._initial_agent_path = agent_path
        self._initial_tests_path = tests_path
        self._running = False
        self._cancel_requested = False
        self._ctrl_c_pressed = False

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal(id="main"):
            with Vertical(id="left-panel"):
                yield ConfigPanel(id="config-panel")
                yield Static(
                    "\n[bold]Commands[/bold]\n"
                    "  agent [path]     Show graph / set agent\n"
                    "  tests [path]     List tests / set tests\n"
                    "  run [nums]       Run all/selected tests\n"
                    "  set <key> <val>  Set model options\n"
                    "  env <key> <val>  Set API key\n"
                    "  keys             List API keys\n"
                    "  export <fmt>     Export agent\n"
                    "  ?                Show help\n"
                    "  exit             Quit",
                    id="help-panel",
                )
            with Vertical(id="right-panel"):
                yield RichLog(id="output", highlight=True, markup=True)
                with Horizontal(id="input-container"):
                    yield Static("> ", id="prompt")
                    yield Input(
                        placeholder="Enter command...",
                        id="command-input",
                        suggester=SuggestFromList(COMMANDS, case_sensitive=False),
                    )
        yield Footer()

    def on_mount(self) -> None:
        self.title = "voicetest"
        self.sub_title = "interactive shell"
        self._log("[bold green]voicetest[/bold green] interactive shell")
        settings_path = get_settings_path()
        if settings_path.exists():
            self._log(f"[dim]Loaded settings from {settings_path}[/dim]")
        self._log("Type 'help' for commands, 'quit' to exit\n")

        config_panel = self.query_one("#config-panel", ConfigPanel)
        if self._initial_agent_path:
            config_panel.set_agent(self._initial_agent_path)
            self._log(f"[green]Agent loaded: {self._initial_agent_path}[/green]")
        if self._initial_tests_path:
            test_cases = load_test_cases(self._initial_tests_path)
            config_panel.set_tests(self._initial_tests_path, test_cases)
            self._log(f"[green]Tests loaded: {self._initial_tests_path}[/green]")
            self._log(f"  {len(test_cases)} test cases")
        if self._initial_agent_path or self._initial_tests_path:
            self._log("")

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

        elif cmd in ("help", "?"):
            self._log(
                "[bold]Commands:[/bold]\n"
                "  agent              Show agent graph (if set)\n"
                "  agent <path>       Set agent definition file\n"
                "  tests              List loaded tests with numbers\n"
                "  tests <path>       Set tests file\n"
                "  run                Run all tests\n"
                "  run 1 3 5          Run specific tests by number\n"
                "\n"
                "[bold]Settings:[/bold]\n"
                "  set <key> <value>  Set model option:\n"
                "                       agent_model, simulator_model, judge_model\n"
                "                       max_turns, verbose\n"
                "  env <key> <value>  Set API key (e.g., env OPENROUTER_API_KEY sk-...)\n"
                "  keys               List configured API keys\n"
                "\n"
                "[bold]Other:[/bold]\n"
                "  export <format>    Export agent (mermaid, livekit, retell-llm)\n"
                "  importers          List available importers\n"
                "  clear              Clear output\n"
                "  exit               Quit shell"
            )

        elif cmd == "agent":
            if not args:
                if not config_panel.agent_path:
                    self._log("[dim]No agent set. Use: agent <path>[/dim]")
                else:
                    await self._show_agent_graph(config_panel)
                return
            path = Path(args).expanduser()
            if not path.exists():
                self._log(f"[red]File not found: {path}[/red]")
                return
            config_panel.set_agent(path)
            self._log(f"[green]Agent set to {path}[/green]")

        elif cmd == "tests":
            if not args:
                if not config_panel.tests_path:
                    self._log("[dim]No tests set. Use: tests <path>[/dim]")
                else:
                    self._show_tests_list(config_panel)
                return
            path = Path(args).expanduser()
            if not path.exists():
                self._log(f"[red]File not found: {path}[/red]")
                return
            test_cases = load_test_cases(path)
            config_panel.set_tests(path, test_cases)
            self._log(f"[green]Tests set to {path}[/green]")
            self._log(f"  Loaded {len(test_cases)} test cases")

        elif cmd == "set":
            parts = args.split(maxsplit=1)
            if len(parts) != 2:
                self._log(
                    "[red]Usage: set <key> <value>[/red]\n"
                    "  Keys: agent_model, simulator_model, judge_model, max_turns, verbose"
                )
                return
            key, value = parts
            if config_panel.set_option(key, value):
                self._log(
                    f"[green]Set {key} = {value}[/green] [dim](saved to .voicetest.toml)[/dim]"
                )
            else:
                self._log(f"[red]Unknown option: {key}[/red]")

        elif cmd == "env":
            parts = args.split(maxsplit=1)
            if len(parts) != 2:
                self._log(
                    "[red]Usage: env <key> <value>[/red]\n"
                    "  Example: env OPENROUTER_API_KEY sk-or-v1-..."
                )
                return
            key, value = parts
            os.environ[key] = value
            masked = value[:8] + "..." if len(value) > 11 else value
            self._log(f"[green]Set {key} = {masked}[/green]")

        elif cmd == "keys":
            self._log("[bold]API Keys:[/bold]")
            found_any = False
            for key in API_KEY_NAMES:
                value = os.environ.get(key)
                if value:
                    masked = value[:8] + "..." if len(value) > 11 else value
                    self._log(f"  [green]\u2713[/green] {key} = {masked}")
                    found_any = True
            if not found_any:
                self._log("  [dim]No API keys set. Use: env <KEY> <value>[/dim]")

        elif cmd == "run":
            await self._run_tests(config_panel, args)

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
                    f"[red]Unknown command: {cmd}[/red]. Did you mean '[cyan]{matches[0]}[/cyan]'?"
                )
            else:
                self._log(f"[red]Unknown command: {cmd}[/red]. Type 'help' for available commands.")

    async def _run_tests(self, config_panel: ConfigPanel, args: str) -> None:
        """Run tests with current configuration."""
        if not config_panel.agent_path:
            self._log("[red]No agent set. Use 'agent <path>' first.[/red]")
            return
        if not config_panel.tests_path:
            self._log("[red]No tests set. Use 'tests <path>' first.[/red]")
            return

        self._running = True
        self._cancel_requested = False
        self._ctrl_c_pressed = False

        try:
            graph = await api.import_agent(config_panel.agent_path)

            if not config_panel.test_cases:
                test_cases = load_test_cases(config_panel.tests_path)
                config_panel.set_tests(config_panel.tests_path, test_cases)
            else:
                test_cases = config_panel.test_cases

            if args.strip():
                indices = []
                for part in args.split():
                    try:
                        idx = int(part) - 1
                        if 0 <= idx < len(test_cases):
                            indices.append(idx)
                        else:
                            self._log(f"[red]Invalid test number: {part}[/red]")
                            return
                    except ValueError:
                        self._log(f"[red]Invalid number: {part}[/red]")
                        return
                selected = [test_cases[i] for i in indices]
                self._log(f"[bold]Running {len(selected)} test(s)...[/bold]\n")
            else:
                selected = test_cases
                self._log(f"[bold]Running {len(selected)} test(s)...[/bold]\n")

            passed = 0
            failed = 0
            cancelled = 0

            for i, test_case in enumerate(selected):
                if self._cancel_requested:
                    cancelled += len(selected) - i
                    self._log(f"[yellow]Cancelled {cancelled} remaining test(s)[/yellow]\n")
                    break

                self._log(f"[bold cyan]Test {i + 1}: {test_case.name}[/bold cyan]")
                self._log("")

                transcript_len = 0

                async def on_turn(transcript):
                    nonlocal transcript_len
                    if self._cancel_requested:
                        raise asyncio.CancelledError()
                    for msg in transcript[transcript_len:]:
                        self._format_message(msg)
                    transcript_len = len(transcript)

                try:
                    result = await api.run_test(
                        graph, test_case, options=config_panel.options, on_turn=on_turn
                    )

                    self._log("")

                    if result.status == "pass":
                        passed += 1
                        self._log("[green]\u2713 PASS[/green]")
                    elif result.status == "error":
                        failed += 1
                        self._log(f"[red]! ERROR: {result.error_message}[/red]")
                    else:
                        failed += 1
                        self._log("[red]\u2717 FAIL[/red]")

                    for m in result.metric_results:
                        icon = "\u2713" if m.passed else "\u2717"
                        color = "green" if m.passed else "red"
                        self._log(f"  [{color}]{icon}[/{color}] {m.metric}")

                    self._log("")

                except asyncio.CancelledError:
                    cancelled += 1
                    self._log("\n[yellow]\u2717 CANCELLED[/yellow]\n")
                except Exception as e:
                    failed += 1
                    self._log(f"[red]! ERROR: {e}[/red]\n")

            summary = f"[bold]Results: {passed} passed, {failed} failed"
            if cancelled:
                summary += f", {cancelled} cancelled"
            summary += "[/bold]"
            self._log(summary)

        except Exception as e:
            self._log(f"[red]Error: {e}[/red]")
        finally:
            self._running = False
            self._cancel_requested = False
            self._ctrl_c_pressed = False

    async def _export(self, config_panel: ConfigPanel, format: str) -> None:
        """Export agent to format."""
        if not config_panel.agent_path:
            self._log("[red]No agent set. Use 'agent <path>' first.[/red]")
            return

        if not format:
            self._log("[red]Usage: export <format> (mermaid|livekit)[/red]")
            return

        try:
            graph = await api.import_agent(config_panel.agent_path)
            result = await api.export_agent(graph, format=format)
            self._log(f"[bold]Exported ({format}):[/bold]\n{result}")
        except Exception as e:
            self._log(f"[red]Error: {e}[/red]")

    async def _list_importers(self) -> None:
        """List available importers."""

        importers = api.list_importers()
        self._log("[bold]Available importers:[/bold]")
        for imp in importers:
            patterns = ", ".join(imp.file_patterns) if imp.file_patterns else "-"
            self._log(f"  [cyan]{imp.source_type}[/cyan]: {imp.description} ({patterns})")

    def action_clear(self) -> None:
        """Clear the output."""
        self.query_one("#output", RichLog).clear()

    def action_interrupt(self) -> None:
        """Handle Ctrl+C - cancel run or exit."""
        if self._running:
            if self._ctrl_c_pressed:
                self._cancel_requested = True
                self._log("[yellow]Cancelling...[/yellow]")
            else:
                self._ctrl_c_pressed = True
                self._log("[yellow]Ctrl+C again to cancel run[/yellow]")
                self.set_timer(2.0, self._reset_ctrl_c)
        else:
            if self._ctrl_c_pressed:
                self.exit()
            else:
                self._ctrl_c_pressed = True
                self._log("[yellow]Ctrl+C again to exit[/yellow]")
                self.set_timer(2.0, self._reset_ctrl_c)

    def _reset_ctrl_c(self) -> None:
        """Reset Ctrl+C state after timeout."""
        self._ctrl_c_pressed = False

    def _log(self, message: str) -> None:
        """Log message to output."""
        self.query_one("#output", RichLog).write(message)

    def _format_message(self, msg) -> None:
        """Format a transcript message with bubble styling."""
        content = msg.content if hasattr(msg, "content") else str(msg)
        role = msg.role if hasattr(msg, "role") else "unknown"

        lines = content.split("\n")
        max_width = 60

        if role == "user":
            self._log("[bold blue]User:[/bold blue]")
            for line in lines:
                wrapped = self._wrap_text(line, max_width)
                for w in wrapped:
                    self._log(f"  [blue]{w}[/blue]")
        elif role == "assistant":
            self._log("[bold green]Agent:[/bold green]")
            for line in lines:
                wrapped = self._wrap_text(line, max_width)
                for w in wrapped:
                    self._log(f"  [green]{w}[/green]")
        else:
            self._log(f"[dim]{role}: {content}[/dim]")

    def _wrap_text(self, text: str, width: int) -> list[str]:
        """Wrap text to specified width."""
        if not text:
            return [""]
        words = text.split()
        lines = []
        current = []
        current_len = 0
        for word in words:
            if current_len + len(word) + 1 > width and current:
                lines.append(" ".join(current))
                current = [word]
                current_len = len(word)
            else:
                current.append(word)
                current_len += len(word) + 1
        if current:
            lines.append(" ".join(current))
        return lines or [""]

    def _show_tests_list(self, config_panel: ConfigPanel) -> None:
        """Show numbered list of loaded tests."""
        self._log(f"[bold]Tests from {config_panel.tests_path}:[/bold]")
        for i, tc in enumerate(config_panel.test_cases, 1):
            test_type = tc.effective_type if hasattr(tc, "effective_type") else tc.type
            self._log(f"  [cyan]{i:2}.[/cyan] {tc.name} [dim]({test_type})[/dim]")
        self._log("\n[dim]Use 'run 1 2 3' to run specific tests[/dim]")

    async def _show_agent_graph(self, config_panel: ConfigPanel) -> None:
        """Show ASCII representation of agent graph."""

        try:
            graph = await api.import_agent(config_panel.agent_path)

            self._log(f"[bold]Agent: {graph.source_type}[/bold]")
            self._log(f"  Entry: [cyan]{graph.entry_node_id}[/cyan]")
            self._log(f"  Nodes: {len(graph.nodes)}")
            self._log("")

            for node_id, node in graph.nodes.items():
                marker = "[yellow]*[/yellow]" if node_id == graph.entry_node_id else " "
                self._log(f"{marker} [bold]{node_id}[/bold]")

                if node.transitions:
                    for t in node.transitions:
                        target = t.target_node_id
                        desc = t.description or t.condition.value[:30] if t.condition else ""
                        self._log(f"    \u2514\u2500> [cyan]{target}[/cyan] [dim]{desc}[/dim]")

                if node.tools:
                    tool_names = [t.name for t in node.tools]
                    self._log(f"    [dim]tools: {', '.join(tool_names)}[/dim]")

        except Exception as e:
            self._log(f"[red]Error loading agent: {e}[/red]")
