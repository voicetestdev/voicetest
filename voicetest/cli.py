"""Command-line interface for voicetest."""

import asyncio
import contextlib
import dataclasses
import importlib.resources
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import click
from rich.console import Console
from rich.table import Table
from rich.tree import Tree
import uvicorn

from voicetest.compose import get_compose_path
from voicetest.demo import get_demo_agent
from voicetest.demo import get_demo_tests
from voicetest.engine.conversation import ConversationEngine
from voicetest.formatting import format_run
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import TestResult
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.retry import RetryError
from voicetest.runner import TestRunContext
from voicetest.services import get_agent_service
from voicetest.services import get_decompose_service
from voicetest.services import get_diagnosis_service
from voicetest.services import get_discovery_service
from voicetest.services import get_evaluation_service
from voicetest.services import get_platform_service
from voicetest.services import get_run_service
from voicetest.services import get_settings_service
from voicetest.services import get_snippet_service
from voicetest.services import get_test_case_service
from voicetest.services import get_test_execution_service
from voicetest.settings import Settings
from voicetest.settings import load_settings
from voicetest.snippets import suggest_snippets
from voicetest.tui import VoicetestApp
from voicetest.tui import VoicetestShell


console = Console()
err_console = Console(stderr=True)


def _echo(msg: str) -> None:
    """Print a progress message to the appropriate console.

    When --json is active, writes to stderr so stdout stays parseable.
    Otherwise writes to the normal stdout console.
    """
    ctx = click.get_current_context(silent=True)
    json_mode = ctx and ctx.find_root().obj and ctx.find_root().obj.get("json")
    if json_mode:
        err_console.print(msg)
    else:
        console.print(msg)


def _start_server(host: str, port: int, reload: bool = False) -> None:
    """Start the uvicorn web server."""
    console.print("[bold]Starting voicetest API server...[/bold]")
    console.print(f"  URL: http://{host}:{port}")
    console.print(f"  Docs: http://{host}:{port}/docs")
    console.print()

    uvicorn.run(
        "voicetest.rest:app",
        host=host,
        port=port,
        reload=reload,
    )


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="voicetest")
@click.option("--json", "json_mode", is_flag=True, help="Output as JSON (for programmatic use)")
@click.pass_context
def main(ctx, json_mode):
    """voicetest - Voice agent test harness.

    Test voice agents from multiple platforms using a unified
    execution and evaluation model.

    Run without arguments to launch interactive shell.
    """
    ctx.ensure_object(dict)
    ctx.obj["json"] = json_mode
    if ctx.invoked_subcommand is None:
        # No subcommand - launch interactive shell
        app = VoicetestShell()
        app.run()


@main.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option(
    "--tests",
    "-t",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Test cases JSON file",
)
@click.option("--source", "-s", default=None, help="Source type (auto-detect if not specified)")
@click.option(
    "--output", "-o", default=None, type=click.Path(path_type=Path), help="Output file (JSON)"
)
@click.option("--verbose", "-v", is_flag=True, help="Verbose output")
@click.option("--interactive", "-i", is_flag=True, help="Launch interactive TUI")
@click.option("--all", "run_all", is_flag=True, help="Run all tests")
@click.option("--test", "test_names", multiple=True, help="Run specific test(s) by name")
@click.option("--max-turns", type=int, default=None, help="Maximum conversation turns")
@click.option("--save-run", is_flag=True, help="Save run to database (requires --agent-id)")
@click.option("--agent-id", default=None, help="Agent ID in database (for --save-run)")
@click.pass_context
def run(
    ctx,
    agent: Path,
    tests: Path,
    source: str | None,
    output: Path | None,
    verbose: bool,
    interactive: bool,
    run_all: bool,
    test_names: tuple[str, ...],
    max_turns: int | None,
    save_run: bool,
    agent_id: str | None,
):
    """Run tests against an agent definition."""
    if save_run and not agent_id:
        raise click.UsageError("--save-run requires --agent-id")
    json_mode = ctx.obj.get("json", False)
    if interactive:
        _run_tui(agent, tests, source, verbose)
    else:
        asyncio.run(
            _run_cli(
                agent,
                tests,
                source,
                output,
                verbose,
                run_all,
                test_names,
                max_turns,
                json_mode=json_mode,
                save_run=save_run,
                agent_id=agent_id,
            )
        )


def _run_tui(
    agent: Path,
    tests: Path,
    source: str | None,
    verbose: bool,
) -> None:
    """Launch interactive TUI."""
    settings = load_settings()
    settings.apply_env()
    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=settings.run.max_turns,
        verbose=verbose or settings.run.verbose,
    )
    app = VoicetestApp(
        agent_path=agent,
        tests_path=tests,
        source=source,
        options=options,
        mock_mode=True,  # For now, use mock mode
    )
    app.run()


async def _run_cli(
    agent: Path,
    tests: Path,
    source: str | None,
    output: Path | None,
    verbose: bool,
    run_all: bool,
    test_names: tuple[str, ...],
    max_turns: int | None,
    *,
    json_mode: bool = False,
    save_run: bool = False,
    agent_id: str | None = None,
) -> None:
    """Run tests in CLI mode."""
    settings = load_settings()
    settings.apply_env()
    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=max_turns if max_turns is not None else settings.run.max_turns,
        verbose=verbose or settings.run.verbose,
    )
    run_ctx = TestRunContext(
        agent_path=agent,
        tests_path=tests,
        source=source,
        options=options,
    )

    # Load
    _echo("[bold]Importing agent definition...[/bold]")
    await run_ctx.load()
    _echo(f"  Source: {run_ctx.graph.source_type}")
    _echo(f"  Nodes: {len(run_ctx.graph.nodes)}")
    _echo(f"  Entry: {run_ctx.graph.entry_node_id}")
    _echo("")

    # Filter tests if specific ones requested
    if test_names:
        run_ctx.filter_tests(list(test_names))
    elif not run_all:
        _echo("[yellow]Warning: No tests selected. Use --all or --test NAME[/yellow]")
        return

    # Run
    _echo(f"[bold]Running {run_ctx.total_tests} tests...[/bold]")
    _echo("")

    def on_error(error: RetryError) -> None:
        _echo(
            f"[yellow]Rate limited - retrying ({error.attempt}/{error.max_attempts})... "
            f"waiting {error.retry_after:.1f}s[/yellow]"
        )

    run_result = await run_ctx.run_all(on_error=on_error)

    # Save to database if requested
    if save_run and agent_id:
        run_svc = get_run_service()
        db_run = run_svc.create_run(agent_id)
        for result in run_result.results:
            run_svc.add_result(db_run["id"], "", result)
        run_svc.complete(db_run["id"])
        _echo(f"[dim]Run saved to database: {db_run['id']}[/dim]")

    # Display
    if json_mode:
        click.echo(run_result.model_dump_json(indent=2))
    else:
        _display_results(run_result)

    # Write output
    if output:
        output.write_text(run_result.model_dump_json(indent=2))
        _echo(f"\n[dim]Results written to {output}[/dim]")

    # Exit non-zero when tests fail
    if run_result.failed_count > 0:
        raise SystemExit(1)


def _display_results(run_result) -> None:
    """Display test results using rich."""
    for line in format_run(run_result):
        console.print(line)


@main.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option(
    "--tests",
    "-t",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Test cases JSON file",
)
@click.option("--source", "-s", default=None, help="Source type (auto-detect if not specified)")
def tui(agent: Path, tests: Path, source: str | None):
    """Launch interactive TUI for test execution."""
    _run_tui(agent, tests, source, verbose=False)


def _get_export_format_ids() -> list[str]:
    """Get export format IDs from the registry (single source of truth)."""
    return [f["id"] for f in get_discovery_service().list_export_formats()]


class LazyExportChoice(click.Choice):
    """Choice type that reads export formats from registry at validation time."""

    def __init__(self):
        super().__init__([])

    @property
    def choices(self):
        return _get_export_format_ids()

    @choices.setter
    def choices(self, value):
        pass


@main.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option(
    "--format",
    "-f",
    required=True,
    type=LazyExportChoice(),
    help="Export format (see 'voicetest exporters' for list)",
)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path), help="Output file")
@click.pass_context
def export(ctx, agent: Path, format: str, output: Path | None):
    """Export agent to different formats.

    Examples:

        voicetest export -a agent.json -f mermaid

        voicetest export -a agent.json -f retell-llm -o out.json
    """
    json_mode = ctx.obj.get("json", False)
    asyncio.run(_export(agent, format, output, json_mode=json_mode))


def _get_export_info(format: str) -> tuple[str, str]:
    """Get file extension and suffix for export format.

    Uses the DiscoveryService as the single source of truth.

    Returns:
        Tuple of (extension with dot, filename suffix).
    """
    formats = get_discovery_service().list_export_formats()
    for fmt in formats:
        if fmt["id"] == format:
            ext = f".{fmt['ext']}"
            suffix = f"_{format.replace('-', '_')}"
            return ext, suffix
    # Fallback for unknown formats
    return ".json", f"_{format.replace('-', '_')}"


async def _export(
    agent: Path, format: str, output: Path | None, *, json_mode: bool = False
) -> None:
    """Async implementation of export command."""
    svc = get_agent_service()
    graph = await svc.import_agent(agent)

    if json_mode and output is None:
        # Write export content directly to stdout, no file created
        content = await svc.export_agent(graph, format=format)
        click.echo(content)
        return

    # Generate default output filename if not provided
    if output is None:
        agent_name = agent.stem
        ext, suffix = _get_export_info(format)
        output = Path(f"{agent_name}{suffix}{ext}")

    await svc.export_agent(graph, format=format, output=output)

    if json_mode:
        click.echo(json.dumps({"file": str(output)}))
    else:
        console.print(f"[dim]Exported to {output}[/dim]")


@main.command()
@click.pass_context
def importers(ctx):
    """List available importers."""
    svc = get_discovery_service()
    importer_list = svc.list_importers()

    if ctx.obj.get("json"):
        click.echo(json.dumps([dataclasses.asdict(imp) for imp in importer_list], indent=2))
        return

    table = Table(title="Available Importers")
    table.add_column("Source Type", style="cyan")
    table.add_column("Description")
    table.add_column("File Patterns")

    for imp in importer_list:
        table.add_row(
            imp.source_type,
            imp.description,
            ", ".join(imp.file_patterns) if imp.file_patterns else "-",
        )

    console.print(table)


@main.command()
@click.pass_context
def exporters(ctx):
    """List available export formats."""
    svc = get_discovery_service()
    format_list = svc.list_export_formats()

    if ctx.obj.get("json"):
        click.echo(json.dumps(format_list, indent=2))
        return

    table = Table(title="Available Export Formats")
    table.add_column("Format ID", style="cyan")
    table.add_column("Name")
    table.add_column("Description")
    table.add_column("Extension")

    for fmt in format_list:
        table.add_row(fmt["id"], fmt["name"], fmt["description"], fmt["ext"])

    console.print(table)


@main.command()
@click.option("--serve", "-s", is_flag=True, help="Start web server instead of shell")
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to (with --serve)")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind to (with --serve)")
def demo(serve: bool, host: str, port: int):
    """Load demo agent and tests for trying voicetest.

    Loads a sample healthcare receptionist agent with test cases.

    Examples:

        voicetest demo              # Load demo, start shell

        voicetest demo --serve      # Load demo, start web server
    """
    console.print("[bold]Loading demo agent and tests...[/bold]")

    demo_agent_config = get_demo_agent()
    demo_tests = get_demo_tests()

    if serve:
        agent_svc = get_agent_service()
        test_svc = get_test_case_service()

        asyncio.run(agent_svc.import_agent(demo_agent_config))

        existing = agent_svc.list_agents()
        demo_exists = any(a.get("name") == "Demo Healthcare Agent" for a in existing)

        if demo_exists:
            agent = next(a for a in existing if a.get("name") == "Demo Healthcare Agent")
            console.print(f"  Using existing demo agent: {agent['id']}")
        else:
            agent = agent_svc.create_agent(
                name="Demo Healthcare Agent",
                config=demo_agent_config,
            )
            console.print(f"  Created demo agent: {agent['id']}")

            for test_data in demo_tests:
                test_case = TestCase(**test_data)
                test_svc.create_test(agent["id"], test_case)

            console.print(f"  Created {len(demo_tests)} test cases")

        console.print()
        _start_server(host, port)
    else:
        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_agent.json", delete=False
        ) as agent_file:
            json.dump(demo_agent_config, agent_file, indent=2)
            agent_path = Path(agent_file.name)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix="_tests.json", delete=False
        ) as tests_file:
            json.dump(demo_tests, tests_file, indent=2)
            tests_path = Path(tests_file.name)

        console.print(f"  Agent: {agent_path}")
        console.print(f"  Tests: {tests_path}")
        console.print()

        app = VoicetestShell(agent_path=agent_path, tests_path=tests_path)
        app.run()


@main.command("smoke-test")
@click.option("--max-turns", type=int, default=2, help="Maximum conversation turns")
@click.pass_context
def smoke_test(ctx, max_turns: int):
    """Run a quick smoke test using bundled demo data.

    Runs 1 test with limited turns to verify voicetest works.
    Useful for CI pipelines.

    Example:
        voicetest smoke-test
    """
    json_mode = ctx.obj.get("json", False)
    asyncio.run(_smoke_test(max_turns, json_mode=json_mode))


async def _smoke_test(max_turns: int, *, json_mode: bool = False) -> None:
    """Run smoke test with bundled demo data."""
    settings = load_settings()
    settings.apply_env()

    _echo("[bold]Running smoke test...[/bold]")

    demo_agent = get_demo_agent()
    demo_tests = get_demo_tests()

    # Use first test only
    first_test = demo_tests[0]
    _echo(f"  Test: {first_test['name']}")
    _echo(f"  Max turns: {max_turns}")
    _echo("")

    agent_svc = get_agent_service()
    exec_svc = get_test_execution_service()

    graph = await agent_svc.import_agent(demo_agent)
    test_case = TestCase.model_validate(first_test)
    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=max_turns,
    )

    def on_error(error: RetryError) -> None:
        _echo(
            f"[yellow]Rate limited - retrying ({error.attempt}/{error.max_attempts})... "
            f"waiting {error.retry_after:.1f}s[/yellow]"
        )

    result = await exec_svc.run_test(graph, test_case, options, on_error=on_error)

    if json_mode:
        click.echo(result.model_dump_json(indent=2))
    else:
        status_color = "green" if result.status == "pass" else "red"
        console.print(f"[{status_color}]Status: {result.status.upper()}[/{status_color}]")
        console.print(f"Turns: {len(result.transcript)}")

    if result.status == "fail":
        raise SystemExit(1)


@main.command()
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
@click.option(
    "--agent",
    "-a",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file(s) to link",
)
@click.option(
    "--tests",
    "-t",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Test file(s) to link (paired with preceding --agent)",
)
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
def serve(
    host: str,
    port: int,
    reload: bool,
    agent: tuple[Path, ...],
    tests: tuple[Path, ...],
    verbose: bool,
):
    """Start the REST API server.

    Use --agent to link agent files, and --tests to link test files.
    Test files are associated with the last specified --agent.
    If multiple agents need different tests, specify them in order:
      --agent a1.json --tests t1.json --agent a2.json --tests t2.json
    """
    os.environ["VOICETEST_LOG_LEVEL"] = "DEBUG" if verbose else "INFO"

    os.environ["VOICETEST_LINKED_AGENTS"] = ",".join(str(p) for p in agent)

    # Build VOICETEST_LINKED_TESTS mapping: "agent_path=test1,test2;..."
    if tests and agent:
        # Associate all test files with the last agent
        last_agent = str(agent[-1])
        tests_str = ",".join(str(t) for t in tests)
        os.environ["VOICETEST_LINKED_TESTS"] = f"{last_agent}={tests_str}"

    if agent:
        console.print(f"  Linked agents: {len(agent)}")
        for a in agent:
            console.print(f"    - {a}")
    if tests:
        console.print(f"  Linked tests: {len(tests)}")
        for t in tests:
            console.print(f"    - {t}")

    _start_server(host, port, reload)


def _check_docker_compose() -> None:
    """Verify that docker compose is available, or exit with a helpful message."""
    try:
        result = subprocess.run(
            ["docker", "compose", "version"],
            capture_output=True,
        )
        if result.returncode != 0:
            raise FileNotFoundError
    except FileNotFoundError:
        console.print(
            "[red]Error: 'docker compose' is not available.[/red]\n"
            "Install Docker Desktop (https://docs.docker.com/get-docker/) "
            "or the compose plugin (https://docs.docker.com/compose/install/)."
        )
        raise SystemExit(1) from None


@main.command()
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind to")
@click.option("--verbose", "-v", is_flag=True, help="Enable debug logging")
@click.option("--detach", "-d", is_flag=True, help="Start infra and exit (no backend server)")
def up(host: str, port: int, verbose: bool, detach: bool):
    """Start infrastructure services and the backend server.

    Launches LiveKit, Whisper, and Kokoro via Docker Compose,
    then starts the voicetest backend server.

    Use --detach to start only the Docker infrastructure without
    the backend server.

    Examples:

        voicetest up                # Start infra + backend

        voicetest up --detach       # Start infra only

        voicetest up -p 9000        # Backend on port 9000
    """
    _check_docker_compose()

    os.environ["VOICETEST_LOG_LEVEL"] = "DEBUG" if verbose else "INFO"

    with get_compose_path() as compose_path:
        console.print("[bold]Starting infrastructure services...[/bold]")
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "up", "-d"],
            capture_output=not verbose,
        )
        if result.returncode != 0:
            console.print("[red]Failed to start infrastructure services.[/red]")
            if not verbose and result.stderr:
                console.print(result.stderr.decode())
            raise SystemExit(1)

        console.print("  LiveKit:  localhost:7880")
        console.print("  Whisper:  localhost:8001")
        console.print("  Kokoro:   localhost:8002")
        console.print()

        if detach:
            console.print("[dim]Infrastructure started. Run 'voicetest down' to stop.[/dim]")
            return

        _start_server(host, port)


@main.command()
def down():
    """Stop infrastructure services.

    Stops the LiveKit, Whisper, and Kokoro containers started
    by 'voicetest up'.

    Example:

        voicetest down
    """
    _check_docker_compose()

    with get_compose_path() as compose_path:
        console.print("[bold]Stopping infrastructure services...[/bold]")
        result = subprocess.run(
            ["docker", "compose", "-f", str(compose_path), "down"],
            capture_output=True,
        )
        if result.returncode != 0:
            console.print("[red]Failed to stop infrastructure services.[/red]")
            if result.stderr:
                console.print(result.stderr.decode())
            raise SystemExit(1)

        console.print("[dim]Infrastructure stopped.[/dim]")


# ---------------------------------------------------------------------------
# Agent subgroup
# ---------------------------------------------------------------------------


@main.group()
def agent():
    """Manage agents in the voicetest database."""


@agent.command("list")
@click.pass_context
def agent_list(ctx):
    """List all agents."""
    svc = get_agent_service()
    agents = svc.list_agents()

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(agents, indent=2))
        return

    table = Table(title="Agents")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Source")
    table.add_column("Updated")

    for a in agents:
        table.add_row(
            a.get("id", ""),
            a.get("name", ""),
            a.get("source", ""),
            a.get("updated_at", ""),
        )

    console.print(table)


@agent.command("get")
@click.argument("agent_id")
@click.pass_context
def agent_get(ctx, agent_id):
    """Get agent details by ID."""
    svc = get_agent_service()
    result = svc.get_agent(agent_id)

    if result is None:
        _echo(f"[red]Agent not found: {agent_id}[/red]")
        raise SystemExit(1)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    for key, value in result.items():
        console.print(f"[bold]{key}:[/bold] {value}")


@agent.command("create")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option("--name", default=None, help="Agent name")
@click.pass_context
def agent_create(ctx, agent_path, name):
    """Create an agent from a definition file."""
    svc = get_agent_service()

    config = json.loads(agent_path.read_text())
    agent_name = name or agent_path.stem
    source = None

    # Auto-detect source type via import
    try:
        graph = asyncio.run(svc.import_agent(config))
        source = graph.source_type
    except Exception:
        pass

    result = svc.create_agent(agent_name, config=config, path=str(agent_path), source=source)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Created agent:[/green] {result.get('id', '')}")
    console.print(f"  Name: {result.get('name', '')}")


@agent.command("update")
@click.argument("agent_id")
@click.option("--name", default=None, help="Agent name")
@click.option("--model", default=None, help="Default model")
@click.pass_context
def agent_update(ctx, agent_id, name, model):
    """Update an agent's properties."""
    svc = get_agent_service()
    result = svc.update_agent(agent_id, name=name, default_model=model)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Updated agent:[/green] {agent_id}")


@agent.command("delete")
@click.argument("agent_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def agent_delete(ctx, agent_id, yes):
    """Delete an agent."""
    if not yes:
        click.confirm(f"Delete agent {agent_id}?", abort=True)

    svc = get_agent_service()
    svc.delete_agent(agent_id)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps({"deleted": True}))
        return

    console.print(f"[dim]Deleted agent {agent_id}[/dim]")


@agent.command("graph")
@click.argument("agent_id")
@click.pass_context
def agent_graph(ctx, agent_id):
    """Display agent graph structure."""
    svc = get_agent_service()
    _agent_dict, graph = svc.load_graph(agent_id)

    if ctx.find_root().obj.get("json"):
        click.echo(graph.model_dump_json(indent=2))
        return

    tree = Tree(f"[bold]Agent Graph[/bold] (entry: {graph.entry_node_id})")
    for node_id, node in graph.nodes.items():
        node_branch = tree.add(f"[cyan]{node_id}[/cyan]")
        if node.transitions:
            for t in node.transitions:
                node_branch.add(f"→ {t.target_node_id}")
    if graph.snippets:
        snippets_branch = tree.add("[bold]Snippets[/bold]")
        for name in graph.snippets:
            snippets_branch.add(name)

    console.print(tree)


# ---------------------------------------------------------------------------
# Test subgroup
# ---------------------------------------------------------------------------


@main.group("test")
def test_group():
    """Manage test cases for agents."""


@test_group.command("list")
@click.argument("agent_id")
@click.pass_context
def test_list(ctx, agent_id):
    """List test cases for an agent."""
    svc = get_test_case_service()
    tests = svc.list_tests(agent_id)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(tests, indent=2))
        return

    table = Table(title="Test Cases")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Metrics")

    for t in tests:
        table.add_row(
            t.get("id", ""),
            t.get("name", ""),
            t.get("type", ""),
            str(t.get("metrics_count", "")),
        )

    console.print(table)


@test_group.command("get")
@click.argument("test_id")
@click.pass_context
def test_get(ctx, test_id):
    """Get test case details."""
    svc = get_test_case_service()
    result = svc.get_test(test_id)

    if result is None:
        _echo(f"[red]Test not found: {test_id}[/red]")
        raise SystemExit(1)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    for key, value in result.items():
        console.print(f"[bold]{key}:[/bold] {value}")


@test_group.command("create")
@click.argument("agent_id")
@click.option(
    "--file",
    "-f",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Test case JSON file",
)
@click.pass_context
def test_create(ctx, agent_id, file):
    """Create a test case from a JSON file."""
    svc = get_test_case_service()
    test_data = json.loads(file.read_text())
    test_case = TestCase.model_validate(test_data)
    result = svc.create_test(agent_id, test_case)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Created test:[/green] {result.get('id', '')}")


@test_group.command("update")
@click.argument("test_id")
@click.option(
    "--file",
    "-f",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Test case JSON file",
)
@click.pass_context
def test_update(ctx, test_id, file):
    """Update a test case from a JSON file."""
    svc = get_test_case_service()
    test_data = json.loads(file.read_text())
    test_case = TestCase.model_validate(test_data)
    result = svc.update_test(test_id, test_case)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Updated test:[/green] {test_id}")


@test_group.command("delete")
@click.argument("test_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def test_delete(ctx, test_id, yes):
    """Delete a test case."""
    if not yes:
        click.confirm(f"Delete test {test_id}?", abort=True)

    svc = get_test_case_service()
    svc.delete_test(test_id)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps({"deleted": True}))
        return

    console.print(f"[dim]Deleted test {test_id}[/dim]")


@test_group.command("link")
@click.argument("agent_id")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def test_link(ctx, agent_id, path):
    """Link an external test file to an agent."""
    svc = get_test_case_service()
    result = svc.link_test_file(agent_id, str(path))

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Linked {path} to agent {agent_id}[/green]")


@test_group.command("unlink")
@click.argument("agent_id")
@click.argument("path", type=click.Path(path_type=Path))
@click.pass_context
def test_unlink(ctx, agent_id, path):
    """Unlink an external test file from an agent."""
    svc = get_test_case_service()
    result = svc.unlink_test_file(agent_id, str(path))

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[dim]Unlinked {path} from agent {agent_id}[/dim]")


@test_group.command("export")
@click.argument("agent_id")
@click.option("--ids", default=None, help="Comma-separated test IDs to export")
@click.option("--format", "-f", "fmt", default="json", help="Export format")
@click.pass_context
def test_export(ctx, agent_id, ids, fmt):
    """Export test cases for an agent."""
    svc = get_test_case_service()
    test_ids = ids.split(",") if ids else None
    result = svc.export_tests(agent_id, test_ids, fmt)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    click.echo(json.dumps(result, indent=2))


# ---------------------------------------------------------------------------
# Runs subgroup
# ---------------------------------------------------------------------------


@main.group()
def runs():
    """View and manage test run history."""


@runs.command("list")
@click.argument("agent_id")
@click.option("--limit", "-n", default=50, type=int, help="Maximum runs to show")
@click.pass_context
def runs_list(ctx, agent_id, limit):
    """List test runs for an agent."""
    svc = get_run_service()
    run_list = svc.list_runs(agent_id, limit)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(run_list, indent=2))
        return

    table = Table(title="Test Runs")
    table.add_column("ID", style="cyan")
    table.add_column("Started")
    table.add_column("Completed")
    table.add_column("Results")

    for r in run_list:
        table.add_row(
            r.get("id", ""),
            r.get("started_at", ""),
            r.get("completed_at", ""),
            str(r.get("result_count", "")),
        )

    console.print(table)


@runs.command("get")
@click.argument("run_id")
@click.pass_context
def runs_get(ctx, run_id):
    """Get run details with results."""
    svc = get_run_service()
    result = svc.get_run(run_id)

    if result is None:
        _echo(f"[red]Run not found: {run_id}[/red]")
        raise SystemExit(1)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[bold]Run ID:[/bold] {result.get('id', '')}")
    console.print(f"[bold]Started:[/bold] {result.get('started_at', '')}")
    console.print(f"[bold]Completed:[/bold] {result.get('completed_at', '')}")

    results = result.get("results", [])
    if results:
        table = Table(title="Results")
        table.add_column("Test", style="cyan")
        table.add_column("Status")
        for r in results:
            status = r.get("status", "")
            color = "green" if status == "pass" else "red"
            table.add_row(r.get("test_name", ""), f"[{color}]{status}[/{color}]")
        console.print(table)


@runs.command("delete")
@click.argument("run_id")
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def runs_delete(ctx, run_id, yes):
    """Delete a test run."""
    if not yes:
        click.confirm(f"Delete run {run_id}?", abort=True)

    svc = get_run_service()
    svc.delete_run(run_id)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps({"deleted": True}))
        return

    console.print(f"[dim]Deleted run {run_id}[/dim]")


# ---------------------------------------------------------------------------
# Snippet subgroup
# ---------------------------------------------------------------------------


def _require_agent_source(agent_id, agent_path):
    """Validate that exactly one of --agent-id or --agent is provided."""
    if agent_id and agent_path:
        raise click.UsageError("Provide either --agent-id or --agent, not both.")
    if not agent_id and not agent_path:
        raise click.UsageError("Provide --agent-id or --agent.")


@main.group()
def snippet():
    """Manage and analyze agent prompt snippets."""


@snippet.command("list")
@click.option("--agent-id", default=None, help="Agent ID in database")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Agent file path",
)
@click.pass_context
def snippet_list(ctx, agent_id, agent_path):
    """List snippets for an agent."""
    _require_agent_source(agent_id, agent_path)

    if agent_id:
        svc = get_snippet_service()
        snippets = svc.get_snippets(agent_id)
    else:
        svc = get_agent_service()
        graph = asyncio.run(svc.import_agent(agent_path))
        snippets = graph.snippets

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(snippets, indent=2))
        return

    table = Table(title="Snippets")
    table.add_column("Name", style="cyan")
    table.add_column("Text")

    for name, text in snippets.items():
        preview = text[:80] + "..." if len(text) > 80 else text
        table.add_row(name, preview)

    console.print(table)


@snippet.command("set")
@click.argument("name")
@click.argument("text")
@click.option("--agent-id", default=None, help="Agent ID in database")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Agent file path",
)
@click.pass_context
def snippet_set(ctx, name, text, agent_id, agent_path):
    """Create or update a snippet."""
    _require_agent_source(agent_id, agent_path)

    if agent_id:
        svc = get_snippet_service()
        snippets = svc.update_snippet(agent_id, name, text)
    else:
        agent_svc = get_agent_service()
        graph = asyncio.run(agent_svc.import_agent(agent_path))
        graph.snippets[name] = text
        asyncio.run(agent_svc.export_agent(graph, format=graph.source_type, output=agent_path))
        snippets = graph.snippets

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(snippets, indent=2))
        return

    console.print(f"[green]Set snippet '{name}'[/green]")


@snippet.command("delete")
@click.argument("name")
@click.option("--agent-id", default=None, help="Agent ID in database")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Agent file path",
)
@click.option("--yes", is_flag=True, help="Skip confirmation")
@click.pass_context
def snippet_delete(ctx, name, agent_id, agent_path, yes):
    """Delete a snippet."""
    _require_agent_source(agent_id, agent_path)

    if not yes:
        click.confirm(f"Delete snippet '{name}'?", abort=True)

    if agent_id:
        svc = get_snippet_service()
        snippets = svc.delete_snippet(agent_id, name)
    else:
        agent_svc = get_agent_service()
        graph = asyncio.run(agent_svc.import_agent(agent_path))
        if name not in graph.snippets:
            raise click.ClickException(f"Snippet not found: {name}")
        del graph.snippets[name]
        asyncio.run(agent_svc.export_agent(graph, format=graph.source_type, output=agent_path))
        snippets = graph.snippets

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(snippets, indent=2))
        return

    console.print(f"[dim]Deleted snippet '{name}'[/dim]")


@snippet.command("analyze")
@click.option("--agent-id", default=None, help="Agent ID in database")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Agent file path",
)
@click.option("--threshold", default=0.8, type=float, help="Similarity threshold")
@click.option("--min-length", default=50, type=int, help="Minimum text length")
@click.pass_context
def snippet_analyze(ctx, agent_id, agent_path, threshold, min_length):
    """Analyze agent prompts for repeated text (DRY analysis)."""
    _require_agent_source(agent_id, agent_path)

    if agent_id:
        svc = get_snippet_service()
        result = svc.analyze_dry(agent_id)
    else:
        agent_svc = get_agent_service()
        graph = asyncio.run(agent_svc.import_agent(agent_path))
        analysis = suggest_snippets(graph, threshold=threshold, min_length=min_length)
        result = {
            "exact": [{"text": m.text, "locations": m.locations} for m in analysis.exact],
            "fuzzy": [
                {"texts": m.texts, "locations": m.locations, "similarity": m.similarity}
                for m in analysis.fuzzy
            ],
        }

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    exact = result.get("exact", [])
    fuzzy = result.get("fuzzy", [])

    if exact:
        table = Table(title="Exact Matches")
        table.add_column("Text")
        table.add_column("Locations")
        for m in exact:
            table.add_row(m["text"][:80], ", ".join(m["locations"]))
        console.print(table)

    if fuzzy:
        table = Table(title="Fuzzy Matches")
        table.add_column("Texts")
        table.add_column("Locations")
        table.add_column("Similarity")
        for m in fuzzy:
            table.add_row(
                " | ".join(t[:40] for t in m["texts"]),
                ", ".join(m["locations"]),
                f"{m['similarity']:.2f}",
            )
        console.print(table)

    if not exact and not fuzzy:
        console.print("[dim]No duplicate text found.[/dim]")


@snippet.command("apply")
@click.option("--agent-id", default=None, help="Agent ID in database")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Agent file path",
)
@click.option("--snippets", required=True, help="JSON array of {name, text} objects")
@click.pass_context
def snippet_apply(ctx, agent_id, agent_path, snippets):
    """Apply snippets to agent prompts."""
    _require_agent_source(agent_id, agent_path)

    snippets_list = json.loads(snippets)

    if agent_id:
        svc = get_snippet_service()
        graph = svc.apply_snippets(agent_id, snippets_list)
    else:
        agent_svc = get_agent_service()
        graph = asyncio.run(agent_svc.import_agent(agent_path))

        for s in snippets_list:
            name = s["name"]
            text = s["text"]
            graph.snippets[name] = text
            ref = "{%" + name + "%}"

            general_prompt = graph.source_metadata.get("general_prompt", "")
            if text in general_prompt:
                graph.source_metadata["general_prompt"] = general_prompt.replace(text, ref)

            for node in graph.nodes.values():
                if text in node.state_prompt:
                    node.state_prompt = node.state_prompt.replace(text, ref)

        asyncio.run(agent_svc.export_agent(graph, format=graph.source_type, output=agent_path))

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps({"nodes": len(graph.nodes), "snippets": len(graph.snippets)}))
        return

    console.print(f"[green]Applied {len(snippets_list)} snippet(s)[/green]")


# ---------------------------------------------------------------------------
# Settings command
# ---------------------------------------------------------------------------


@main.command()
@click.option("--set", "set_values", multiple=True, help="Set value: section.key=value")
@click.option("--defaults", is_flag=True, help="Show defaults")
@click.pass_context
def settings(ctx, set_values, defaults):
    """Show or edit .voicetest.toml settings."""
    svc = get_settings_service()

    if defaults:
        s = svc.get_defaults()
        if ctx.obj.get("json"):
            click.echo(s.model_dump_json(indent=2))
            return
        _display_settings(s)
        return

    s = svc.get_settings()

    if set_values:
        data = s.model_dump()
        for pair in set_values:
            key, _, value = pair.partition("=")
            parts = key.split(".")
            target = data
            for part in parts[:-1]:
                target = target.setdefault(part, {})
            # Coerce booleans and ints
            if value.lower() in ("true", "false"):
                value = value.lower() == "true"
            else:
                with contextlib.suppress(ValueError):
                    value = int(value)
            target[parts[-1]] = value

        s = Settings.model_validate(data)
        svc.update_settings(s)

    if ctx.obj.get("json"):
        click.echo(s.model_dump_json(indent=2))
        return

    _display_settings(s)


def _display_settings(s) -> None:
    """Render settings as a Rich table."""
    table = Table(title="Settings")
    table.add_column("Section", style="cyan")
    table.add_column("Key")
    table.add_column("Value")

    for section_name, section in s.model_dump().items():
        if isinstance(section, dict):
            for key, value in section.items():
                table.add_row(section_name, key, str(value))
        else:
            table.add_row("", section_name, str(section))

    console.print(table)


# ---------------------------------------------------------------------------
# Platforms command (read-only list)
# ---------------------------------------------------------------------------


@main.command()
@click.pass_context
def platforms(ctx):
    """List available platforms with configuration status."""
    svc = get_platform_service()
    platform_list = svc.list_platforms()

    if ctx.obj.get("json"):
        click.echo(json.dumps(platform_list, indent=2))
        return

    table = Table(title="Platforms")
    table.add_column("Platform", style="cyan")
    table.add_column("Configured")
    table.add_column("Env Key")

    for p in platform_list:
        configured = "[green]Yes[/green]" if p.get("configured") else "[dim]No[/dim]"
        table.add_row(p.get("name", ""), configured, p.get("env_key", ""))

    console.print(table)


# ---------------------------------------------------------------------------
# Platform subgroup
# ---------------------------------------------------------------------------


@main.group()
@click.pass_context
def platform(ctx):
    """Platform integration operations."""


@platform.command("configure")
@click.argument("name")
@click.option("--api-key", required=True, help="Platform API key")
@click.option("--api-secret", default=None, help="Platform API secret (if required)")
@click.pass_context
def platform_configure(ctx, name, api_key, api_secret):
    """Configure platform credentials."""
    svc = get_platform_service()
    result = svc.configure(name, api_key, api_secret)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Configured {name}[/green]")


@platform.command("list-agents")
@click.argument("name")
@click.pass_context
def platform_list_agents(ctx, name):
    """List agents from a remote platform."""
    svc = get_platform_service()
    agents = svc.list_remote_agents(name)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(agents, indent=2))
        return

    table = Table(title=f"Remote Agents ({name})")
    table.add_column("ID", style="cyan")
    table.add_column("Name")

    for a in agents:
        table.add_row(a.get("id", ""), a.get("name", ""))

    console.print(table)


@platform.command("import")
@click.argument("name")
@click.argument("agent_id")
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path), help="Output file")
@click.pass_context
def platform_import(ctx, name, agent_id, output):
    """Import an agent from a remote platform."""
    svc = get_platform_service()
    graph = svc.import_from_platform(name, agent_id)

    if output:
        agent_svc = get_agent_service()
        asyncio.run(agent_svc.export_agent(graph, format=graph.source_type, output=output))
        if ctx.find_root().obj.get("json"):
            click.echo(json.dumps({"file": str(output)}))
        else:
            console.print(f"[green]Imported to {output}[/green]")
    else:
        click.echo(graph.model_dump_json(indent=2))


@platform.command("push")
@click.argument("name")
@click.option(
    "--agent",
    "-a",
    "agent_path",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option("--agent-name", default=None, help="Name for the remote agent")
@click.pass_context
def platform_push(ctx, name, agent_path, agent_name):
    """Push an agent to a remote platform."""
    agent_svc = get_agent_service()
    graph = asyncio.run(agent_svc.import_agent(agent_path))

    svc = get_platform_service()
    result = svc.export_to_platform(name, graph, agent_name)

    if ctx.find_root().obj.get("json"):
        click.echo(json.dumps(result, indent=2))
        return

    console.print(f"[green]Pushed to {name}:[/green] {result.get('id', '')}")


# ---------------------------------------------------------------------------
# Evaluate command
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--transcript",
    "-t",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Transcript JSON file",
)
@click.option("--metrics", "-m", multiple=True, required=True, help="Metric criteria")
@click.option("--judge-model", default=None, help="LLM model for evaluation")
@click.pass_context
def evaluate(ctx, transcript, metrics, judge_model):
    """Evaluate a transcript against metrics (no simulation)."""
    json_mode = ctx.obj.get("json", False)
    asyncio.run(_evaluate(transcript, list(metrics), judge_model, json_mode=json_mode))


async def _evaluate(
    transcript_path: Path,
    metrics: list[str],
    judge_model: str | None,
    *,
    json_mode: bool = False,
) -> None:
    """Async implementation of evaluate command."""
    transcript_data = json.loads(transcript_path.read_text())
    transcript = [Message.model_validate(m) for m in transcript_data]

    svc = get_evaluation_service()
    results = await svc.evaluate_transcript(transcript, metrics, judge_model)

    if json_mode:
        click.echo(json.dumps([r.model_dump() for r in results], indent=2))
    else:
        table = Table(title="Evaluation Results")
        table.add_column("Metric")
        table.add_column("Pass/Fail")
        table.add_column("Score")
        table.add_column("Reasoning")

        for r in results:
            color = "green" if r.passed else "red"
            status = "PASS" if r.passed else "FAIL"
            score = f"{r.score:.2f}" if r.score is not None else "-"
            table.add_row(r.metric, f"[{color}]{status}[/{color}]", score, r.reasoning[:80])

        console.print(table)

    if any(not r.passed for r in results):
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Diagnose command
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option(
    "--tests",
    "-t",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Test cases JSON file",
)
@click.option(
    "--results",
    "-r",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Previous results JSON (skip rerun)",
)
@click.option("--test", "test_name", default=None, help="Specific test to diagnose")
@click.option("--all", "run_all", is_flag=True, help="Run all tests first")
@click.option("--max-iterations", default=3, type=int, help="Max fix iterations")
@click.option("--auto-fix", is_flag=True, help="Iterate until fixed or max iterations")
@click.option(
    "--save",
    "-s",
    default=None,
    type=click.Path(path_type=Path),
    help="Save fixed agent to file",
)
@click.pass_context
def diagnose(ctx, agent, tests, results, test_name, run_all, max_iterations, auto_fix, save):
    """Diagnose test failures and suggest prompt fixes."""
    json_mode = ctx.obj.get("json", False)
    asyncio.run(
        _diagnose(
            agent,
            tests,
            results,
            test_name,
            run_all,
            max_iterations,
            auto_fix,
            save,
            json_mode=json_mode,
        )
    )


async def _diagnose(
    agent_path: Path,
    tests_path: Path,
    results_path: Path | None,
    test_name: str | None,
    run_all: bool,
    max_iterations: int,
    auto_fix: bool,
    save_path: Path | None,
    *,
    json_mode: bool = False,
) -> None:
    """Async implementation of diagnose command."""
    settings = load_settings()
    settings.apply_env()

    agent_svc = get_agent_service()
    exec_svc = get_test_execution_service()
    diag_svc = get_diagnosis_service()

    graph = await agent_svc.import_agent(agent_path)
    test_cases = get_test_case_service().load_test_cases(tests_path)

    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=settings.run.max_turns,
    )
    judge_model = settings.models.judge or "groq/llama-3.1-8b-instant"

    # Run tests or load previous results
    if results_path:
        results_data = json.loads(results_path.read_text())
        test_results = [TestResult.model_validate(r) for r in results_data]
    else:
        _echo("[bold]Running tests...[/bold]")
        run_result = await exec_svc.run_tests(graph, test_cases, options)
        test_results = run_result.results

    # Find failing test
    failing = [r for r in test_results if r.status == "fail"]
    if not failing:
        _echo("[green]All tests passed. Nothing to diagnose.[/green]")
        if json_mode:
            click.echo(json.dumps({"status": "all_passed"}))
        return

    target = failing[0]
    if test_name:
        named = [r for r in failing if r.test_name == test_name]
        if named:
            target = named[0]

    _echo(f"[bold]Diagnosing: {target.test_name}[/bold]")

    failed_metrics = [m for m in target.metric_results if not m.passed]
    test_scenario = ""
    for tc in test_cases:
        if tc.name == target.test_name:
            test_scenario = tc.user_prompt
            break

    diagnosis_result = await diag_svc.diagnose_failure(
        graph,
        target.transcript,
        target.nodes_visited,
        failed_metrics,
        test_scenario,
        judge_model,
    )

    output = {"diagnosis": diagnosis_result.model_dump()}

    if auto_fix:
        fix_attempts = []
        current_graph = graph
        current_fix = diagnosis_result.fix

        for i in range(1, max_iterations + 1):
            _echo(f"[bold]Fix attempt {i}/{max_iterations}...[/bold]")

            # Find the matching test case
            target_case = None
            for tc in test_cases:
                if tc.name == target.test_name:
                    target_case = tc
                    break

            if target_case is None:
                _echo("[red]Could not find matching test case.[/red]")
                break

            attempt = await diag_svc.apply_and_rerun(
                current_graph,
                target_case,
                current_fix.changes,
                failed_metrics,
                i,
                options,
            )
            fix_attempts.append(attempt.model_dump())

            if attempt.test_passed:
                _echo(f"[green]Fixed on iteration {i}![/green]")
                current_graph = diag_svc.apply_fix_to_graph(current_graph, current_fix.changes)
                break

            if i < max_iterations:
                new_metrics = [MetricResult.model_validate(m) for m in attempt.metric_results]
                current_fix = await diag_svc.revise_fix(
                    current_graph,
                    diagnosis_result.diagnosis,
                    current_fix.changes,
                    new_metrics,
                    judge_model,
                )

        output["fix_attempts"] = fix_attempts

        if save_path and fix_attempts and fix_attempts[-1].get("test_passed"):
            await agent_svc.export_agent(current_graph, format=graph.source_type, output=save_path)
            output["saved"] = str(save_path)
            _echo(f"[green]Saved fixed agent to {save_path}[/green]")

    if json_mode:
        click.echo(json.dumps(output, indent=2))
    else:
        diag = diagnosis_result.diagnosis
        console.print(f"\n[bold]Root Cause:[/bold] {diag.root_cause}")
        console.print(f"[bold]Evidence:[/bold] {diag.transcript_evidence}")

        if diagnosis_result.fix.changes:
            confidence = f"{diagnosis_result.fix.confidence:.0%}"
            console.print(f"\n[bold]Suggested Fix ({confidence} confidence):[/bold]")
            for change in diagnosis_result.fix.changes:
                console.print(f"  [{change.location_type}] {change.rationale}")

    if not auto_fix or not fix_attempts or not fix_attempts[-1].get("test_passed"):
        raise SystemExit(1)


# ---------------------------------------------------------------------------
# Decompose command
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option(
    "--output",
    "-o",
    required=True,
    type=click.Path(path_type=Path),
    help="Output directory for sub-agent files",
)
@click.option(
    "--num-agents",
    "-n",
    default=0,
    type=int,
    help="Number of sub-agents (0 = LLM decides)",
)
@click.option("--model", "-m", default=None, help="LLM model override")
@click.pass_context
def decompose(ctx, agent, output, num_agents, model):
    """Decompose an agent into sub-agents with orchestrator manifest."""
    json_mode = ctx.obj.get("json", False)
    asyncio.run(
        _decompose(
            agent,
            output,
            num_agents,
            model,
            json_mode=json_mode,
        )
    )


async def _decompose(
    agent_path: Path,
    output_dir: Path,
    num_agents: int,
    model_override: str | None,
    *,
    json_mode: bool = False,
) -> None:
    """Async implementation of decompose command."""
    settings = load_settings()
    settings.apply_env()

    agent_svc = get_agent_service()
    decompose_svc = get_decompose_service()

    graph = await agent_svc.import_agent(agent_path)

    judge_model = model_override or settings.models.judge or "groq/llama-3.1-8b-instant"

    result = await decompose_svc.decompose(graph, judge_model, num_agents)

    # Write output files
    output_dir.mkdir(parents=True, exist_ok=True)

    for sub_agent_id, sub_graph in result.sub_graphs.items():
        sub_path = output_dir / f"{sub_agent_id}.json"
        sub_path.write_text(sub_graph.model_dump_json(indent=2))

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(result.manifest.model_dump_json(indent=2))

    if json_mode:
        click.echo(result.model_dump_json(indent=2))
    else:
        console.print(f"[bold]Decomposed into {result.plan.num_sub_agents} sub-agents[/bold]")
        for entry in result.manifest.sub_agents:
            console.print(f"  {entry.name}: {entry.filename}")
        console.print(f"\n[bold]Manifest:[/bold] {manifest_path}")
        console.print(f"[bold]Rationale:[/bold] {result.plan.rationale}")


# ---------------------------------------------------------------------------
# Chat command
# ---------------------------------------------------------------------------


@main.command()
@click.option(
    "--agent",
    "-a",
    required=True,
    type=click.Path(exists=True, path_type=Path),
    help="Agent definition file",
)
@click.option("--model", default=None, help="LLM model for agent responses")
@click.option("--var", "variables", multiple=True, help="Dynamic variable: name=value")
@click.pass_context
def chat(ctx, agent, model, variables):
    """Interactive text chat with an agent."""
    json_mode = ctx.obj.get("json", False)
    asyncio.run(_chat(agent, model, variables, json_mode=json_mode))


async def _chat(
    agent_path: Path,
    model: str | None,
    variables: tuple[str, ...],
    *,
    json_mode: bool = False,
) -> None:
    """Async implementation of chat command."""
    settings = load_settings()
    settings.apply_env()

    agent_svc = get_agent_service()
    graph = await agent_svc.import_agent(agent_path)

    agent_model = model or settings.models.agent or "groq/llama-3.1-8b-instant"
    options = RunOptions(agent_model=agent_model)

    dynamic_vars = {}
    for var in variables:
        key, _, value = var.partition("=")
        dynamic_vars[key] = value

    engine = ConversationEngine(graph, agent_model, options, dynamic_vars)

    _echo(f"[bold]Chat with agent[/bold] (model: {agent_model})")
    _echo("[dim]Type 'quit' or 'exit' to end. Ctrl-D also works.[/dim]")
    _echo("")

    try:
        while not engine.end_call_invoked:
            try:
                user_input = input("You: ")
            except EOFError:
                break

            if user_input.strip().lower() in ("quit", "exit"):
                break

            result = await engine.process_turn(user_input)

            if json_mode:
                pass  # Accumulate; dump transcript at end
            else:
                console.print(f"[bold blue]Agent:[/bold blue] {result.response}")
                if result.transitioned_to:
                    console.print(f"  [dim]→ transitioned to: {result.transitioned_to}[/dim]")
                if result.end_call_invoked:
                    console.print("  [dim]→ call ended[/dim]")

    except KeyboardInterrupt:
        pass

    if json_mode:
        transcript = [m.model_dump() for m in engine.transcript]
        click.echo(json.dumps(transcript, indent=2))
    else:
        _echo(f"\n[dim]Session ended. {len(engine.transcript)} messages exchanged.[/dim]")


# ---------------------------------------------------------------------------
# Claude Code plugin commands
# ---------------------------------------------------------------------------


def _get_plugin_source() -> Path:
    """Get the path to the bundled Claude Code plugin files.

    Uses importlib.resources to find the plugin data bundled in the package.
    Falls back to the source tree if running from a development checkout.
    """
    # Try the bundled package data path (installed via pip/uv)
    pkg = importlib.resources.files("voicetest") / "claude_plugin"
    pkg_path = Path(str(pkg))
    if pkg_path.is_dir():
        return pkg_path

    # Fall back to source tree (development mode)
    source_path = Path(__file__).resolve().parent.parent / "claude-plugin"
    if source_path.is_dir():
        return source_path

    raise FileNotFoundError("Could not find Claude Code plugin files")


@main.command("init-claude")
def init_claude():
    """Set up Claude Code skills and commands for this project.

    Copies voicetest slash commands and skills into the current project's
    .claude/ directory so Claude Code can discover them automatically.
    """
    source = _get_plugin_source()
    target = Path.cwd() / ".claude"

    target.mkdir(parents=True, exist_ok=True)

    # Copy commands
    src_commands = source / "commands"
    dst_commands = target / "commands"
    if dst_commands.exists():
        console.print("[yellow]Overwriting existing .claude/commands/[/yellow]")
        shutil.rmtree(dst_commands)
    shutil.copytree(src_commands, dst_commands)
    console.print(f"  Created .claude/commands/ ({len(list(dst_commands.glob('*.md')))} commands)")

    # Copy skills
    src_skills = source / "skills"
    dst_skills = target / "skills"
    if dst_skills.exists():
        console.print("[yellow]Overwriting existing .claude/skills/[/yellow]")
        shutil.rmtree(dst_skills)
    shutil.copytree(src_skills, dst_skills)
    console.print(f"  Created .claude/skills/ ({len(list(dst_skills.rglob('*.md')))} files)")

    console.print()
    console.print("[bold]Claude Code integration ready.[/bold]")
    console.print("  Available commands: /voicetest-run, /voicetest-export,")
    console.print("  /voicetest-convert, /voicetest-info")


@main.command("claude-plugin-path")
def claude_plugin_path():
    """Print path to the bundled Claude Code plugin directory.

    Useful for: claude --plugin-dir $(voicetest claude-plugin-path)
    """
    source = _get_plugin_source()
    click.echo(str(source))


if __name__ == "__main__":
    main()
