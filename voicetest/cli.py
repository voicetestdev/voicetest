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
def run(
    agent: Path,
    tests: Path,
    source: str | None,
    output: Path | None,
    verbose: bool,
    interactive: bool,
):
    """Run tests against an agent definition."""
    if interactive:
        _run_tui(agent, tests, source, verbose)
    else:
        asyncio.run(_run_cli(agent, tests, source, output, verbose))


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
) -> None:
    """Run tests in CLI mode."""
    from voicetest.settings import load_settings

    settings = load_settings()
    options = RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=settings.run.max_turns,
        verbose=verbose or settings.run.verbose,
    )
    ctx = TestRunContext(
        agent_path=agent,
        tests_path=tests,
        source=source,
        options=options,
        mock_mode=True,  # For now, use mock mode
    )

    # Load
    console.print("[bold]Importing agent definition...[/bold]")
    await ctx.load()
    console.print(f"  Source: {ctx.graph.source_type}")
    console.print(f"  Nodes: {len(ctx.graph.nodes)}")
    console.print(f"  Entry: {ctx.graph.entry_node_id}")
    console.print()

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
    "--format", "-f", required=True, type=click.Choice(["livekit", "mermaid"]), help="Export format"
)
@click.option("--output", "-o", default=None, type=click.Path(path_type=Path), help="Output file")
def export(agent: Path, format: str, output: Path | None):
    """Export agent to different formats."""
    asyncio.run(_export(agent, format, output))


async def _export(agent: Path, format: str, output: Path | None) -> None:
    """Async implementation of export command."""
    graph = await api.import_agent(agent)
    result = await api.export_agent(graph, format=format, output=output)

    if not output:
        console.print(result)
    else:
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
@click.option("--host", "-h", default="127.0.0.1", help="Host to bind to")
@click.option("--port", "-p", default=8000, type=int, help="Port to bind to")
@click.option("--reload", is_flag=True, help="Enable auto-reload for development")
def serve(host: str, port: int, reload: bool):
    """Start the REST API server."""
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


if __name__ == "__main__":
    main()
