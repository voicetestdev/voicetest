"""Tests for the CLI."""

import json

import pytest
from click.testing import CliRunner


@pytest.fixture
def cli_runner():
    """Create a CLI test runner."""
    return CliRunner()


@pytest.fixture
def temp_agent_file(tmp_path, sample_retell_config):
    """Create a temporary agent definition file."""
    agent_path = tmp_path / "agent.json"
    agent_path.write_text(json.dumps(sample_retell_config))
    return agent_path


@pytest.fixture
def temp_tests_file(tmp_path, sample_test_cases):
    """Create a temporary tests file."""
    tests_path = tmp_path / "tests.json"
    tests_path.write_text(json.dumps(sample_test_cases))
    return tests_path


class TestCLIVersion:
    """Tests for CLI version command."""

    def test_version(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--version"])

        assert result.exit_code == 0
        assert "0.1.0" in result.output


class TestCLIImporters:
    """Tests for the importers command."""

    def test_importers_lists_available(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["importers"])

        assert result.exit_code == 0
        assert "retell" in result.output.lower()
        assert "custom" in result.output.lower()


class TestCLIExport:
    """Tests for the export command."""

    def test_export_mermaid(self, cli_runner, temp_agent_file):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main, ["export", "--agent", str(temp_agent_file), "--format", "mermaid"]
        )

        assert result.exit_code == 0
        assert "flowchart" in result.output.lower()

    def test_export_livekit(self, cli_runner, temp_agent_file):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main, ["export", "--agent", str(temp_agent_file), "--format", "livekit"]
        )

        assert result.exit_code == 0
        assert "class Agent_greeting" in result.output

    def test_export_to_file(self, cli_runner, temp_agent_file, tmp_path):
        from voicetest.cli import main

        output_path = tmp_path / "output.md"

        result = cli_runner.invoke(
            main,
            [
                "export",
                "--agent",
                str(temp_agent_file),
                "--format",
                "mermaid",
                "--output",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        assert "flowchart" in output_path.read_text().lower()


class TestCLIRun:
    """Tests for the run command."""

    def test_run_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["run", "--help"])

        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--tests" in result.output

    def test_run_missing_agent(self, cli_runner, temp_tests_file):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main, ["run", "--agent", "/nonexistent/agent.json", "--tests", str(temp_tests_file)]
        )

        assert result.exit_code != 0

    def test_run_missing_tests(self, cli_runner, temp_agent_file):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main, ["run", "--agent", str(temp_agent_file), "--tests", "/nonexistent/tests.json"]
        )

        assert result.exit_code != 0


class TestCLIMain:
    """Tests for main entry point."""

    def test_main_help_shows_commands(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        # Should show available commands
        assert "run" in result.output
        assert "export" in result.output
        assert "importers" in result.output
