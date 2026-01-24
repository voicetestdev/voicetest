"""Command-line interface for voicetest."""

import asyncio
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table

from voicetest import api
from voicetest.models.test_case import RunOptions
from voicetest.runner import TestRunContext


console = Console()


def _start_server(host: str, port: int, reload: bool = False) -> None:
    """Start the uvicorn web server."""
    try:
        import uvicorn
    except ImportError:
        console.print("[red]Error: uvicorn not installed.[/red]")
        console.print("Install with: uv add 'voicetest[api]'")
        raise SystemExit(1) from None

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
@click.pass_context
def main(ctx):
    """voicetest - Voice agent test harness.

    Test voice agents from multiple platforms using a unified
    execution and evaluation model.

    Run without arguments to launch interactive shell.
    """
    if ctx.invoked_subcommand is None:
        # No subcommand - launch interactive shell
        from voicetest.tui import VoicetestShell

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
def run(
    agent: Path,
    tests: Path,
    source: str | None,
    output: Path | None,
    verbose: bool,
    interactive: bool,
    run_all: bool,
    test_names: tuple[str, ...],
    max_turns: int | None,
):
    """Run tests against an agent definition."""
    if interactive:
        _run_tui(agent, tests, source, verbose)
    else:
        asyncio.run(_run_cli(agent, tests, source, output, verbose, run_all, test_names, max_turns))


def _run_tui(
    agent: Path,
    tests: Path,
    source: str | None,
    verbose: bool,
) -> None:
    """Launch interactive TUI."""
    from voicetest.settings import load_settings
    from voicetest.tui import VoicetestApp

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
) -> None:
    """Run tests in CLI mode."""
    from voicetest.settings import load_settings

    settings = load_settings()
    settings.apply_env()
    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=max_turns if max_turns is not None else settings.run.max_turns,
        verbose=verbose or settings.run.verbose,
    )
    ctx = TestRunContext(
        agent_path=agent,
        tests_path=tests,
        source=source,
        options=options,
    )

    # Load
    console.print("[bold]Importing agent definition...[/bold]")
    await ctx.load()
    console.print(f"  Source: {ctx.graph.source_type}")
    console.print(f"  Nodes: {len(ctx.graph.nodes)}")
    console.print(f"  Entry: {ctx.graph.entry_node_id}")
    console.print()

    # Filter tests if specific ones requested
    if test_names:
        ctx.filter_tests(list(test_names))
    elif not run_all:
        console.print("[yellow]Warning: No tests selected. Use --all or --test NAME[/yellow]")
        return

    # Run
    console.print(f"[bold]Running {ctx.total_tests} tests...[/bold]")
    console.print()

    run_result = await ctx.run_all()

    # Display
    _display_results(run_result)

    # Write output
    if output:
        output.write_text(run_result.model_dump_json(indent=2))
        console.print(f"\n[dim]Results written to {output}[/dim]")


def _display_results(run_result) -> None:
    """Display test results using rich."""
    from voicetest.formatting import format_run

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
    type=click.Choice(
        ["livekit", "mermaid", "retell-llm", "retell-cf", "vapi-assistant", "vapi-squad"]
    ),
    help="Export format",
)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path), help="Output file")
def export(agent: Path, format: str, output: Path | None):
    """Export agent to different formats."""
    asyncio.run(_export(agent, format, output))


def _get_export_info(format: str) -> tuple[str, str]:
    """Get file extension and suffix for export format.

    Uses list_export_formats() as the single source of truth.

    Returns:
        Tuple of (extension with dot, filename suffix).
    """
    formats = api.list_export_formats()
    for fmt in formats:
        if fmt["id"] == format:
            ext = f".{fmt['ext']}"
            suffix = f"_{format.replace('-', '_')}"
            return ext, suffix
    # Fallback for unknown formats
    return ".json", f"_{format.replace('-', '_')}"


async def _export(agent: Path, format: str, output: Path | None) -> None:
    """Async implementation of export command."""
    graph = await api.import_agent(agent)

    # Generate default output filename if not provided
    if output is None:
        agent_name = agent.stem
        ext, suffix = _get_export_info(format)
        output = Path(f"{agent_name}{suffix}{ext}")

    await api.export_agent(graph, format=format, output=output)
    console.print(f"[dim]Exported to {output}[/dim]")


@main.command()
def importers():
    """List available importers."""
    importer_list = api.list_importers()

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
    import json
    import tempfile

    from voicetest.demo import get_demo_agent, get_demo_tests

    console.print("[bold]Loading demo agent and tests...[/bold]")

    demo_agent_config = get_demo_agent()
    demo_tests = get_demo_tests()

    if serve:
        from voicetest.models.test_case import TestCase
        from voicetest.storage.db import get_connection, init_schema
        from voicetest.storage.repositories import AgentRepository, TestCaseRepository

        conn = get_connection()
        init_schema(conn)

        agent_repo = AgentRepository(conn)
        test_repo = TestCaseRepository(conn)

        graph = asyncio.run(api.import_agent(demo_agent_config))

        existing = agent_repo.list_all()
        demo_exists = any(a.get("name") == "Demo Healthcare Agent" for a in existing)

        if demo_exists:
            agent = next(a for a in existing if a.get("name") == "Demo Healthcare Agent")
            console.print(f"  Using existing demo agent: {agent['id']}")
        else:
            agent = agent_repo.create(
                name="Demo Healthcare Agent",
                source_type=graph.source_type,
                graph_json=graph.model_dump_json(),
            )
            console.print(f"  Created demo agent: {agent['id']}")

            for test_data in demo_tests:
                test_case = TestCase(**test_data)
                test_repo.create(agent["id"], test_case)

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

        from voicetest.tui import VoicetestShell

        app = VoicetestShell(agent_path=agent_path, tests_path=tests_path)
        app.run()


@main.command("smoke-test")
@click.option("--max-turns", type=int, default=2, help="Maximum conversation turns")
def smoke_test(max_turns: int):
    """Run a quick smoke test using bundled demo data.

    Runs 1 test with limited turns to verify voicetest works.
    Useful for CI pipelines.

    Example:
        voicetest smoke-test
    """
    asyncio.run(_smoke_test(max_turns))


async def _smoke_test(max_turns: int) -> None:
    """Run smoke test with bundled demo data."""
    from voicetest.demo import get_demo_agent, get_demo_tests
    from voicetest.settings import load_settings

    settings = load_settings()
    settings.apply_env()

    console.print("[bold]Running smoke test...[/bold]")

    demo_agent = get_demo_agent()
    demo_tests = get_demo_tests()

    # Use first test only
    first_test = demo_tests[0]
    console.print(f"  Test: {first_test['name']}")
    console.print(f"  Max turns: {max_turns}")
    console.print()

    graph = await api.import_agent(demo_agent)

    from voicetest.models.test_case import TestCase

    test_case = TestCase.model_validate(first_test)
    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=max_turns,
    )

    result = await api.run_test(graph, test_case, options)

    # Display result
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
def serve(host: str, port: int, reload: bool, agent: tuple[Path, ...]):
    """Start the REST API server."""
    import os

    os.environ["VOICETEST_LINKED_AGENTS"] = ",".join(str(p) for p in agent)

    if agent:
        console.print(f"  Linked agents: {len(agent)}")
        for a in agent:
            console.print(f"    - {a}")

    _start_server(host, port, reload)


if __name__ == "__main__":
    main()
