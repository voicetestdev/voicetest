"""Tests for the CLI."""

import json

from click.testing import CliRunner
import pytest


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

    def test_export_mermaid(self, cli_runner, temp_agent_file, tmp_path, monkeypatch):
        from voicetest.cli import main

        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(
            main, ["export", "--agent", str(temp_agent_file), "--format", "mermaid"]
        )

        assert result.exit_code == 0
        # Default output file: {agent_name}_mermaid.md
        output_file = tmp_path / "agent_mermaid.md"
        assert output_file.exists()
        assert "flowchart" in output_file.read_text().lower()

    def test_export_livekit(self, cli_runner, temp_agent_file, tmp_path, monkeypatch):
        from voicetest.cli import main

        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(
            main, ["export", "--agent", str(temp_agent_file), "--format", "livekit"]
        )

        assert result.exit_code == 0
        # Default output file: {agent_name}_livekit.py
        output_file = tmp_path / "agent_livekit.py"
        assert output_file.exists()
        assert "class Agent_greeting" in output_file.read_text()

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


class TestCLIServe:
    """Tests for the serve command."""

    def test_serve_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["serve", "--help"])

        assert result.exit_code == 0
        assert "--agent" in result.output
        assert "--host" in result.output
        assert "--port" in result.output

    def test_serve_agent_flag_accepts_path(self, cli_runner, temp_agent_file):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["serve", "--help"])

        assert result.exit_code == 0
        # Multiple flag should be documented
        assert "-a" in result.output

    def test_serve_agent_nonexistent_file_fails(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["serve", "--agent", "/nonexistent/agent.json"])

        assert result.exit_code != 0


class TestCLIUp:
    """Tests for the up command."""

    def test_up_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["up", "--help"])

        assert result.exit_code == 0
        assert "--host" in result.output
        assert "--port" in result.output
        assert "--detach" in result.output
        assert "--verbose" in result.output

    def test_up_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "up" in result.output
        assert "down" in result.output

    def test_up_fails_without_docker(self, cli_runner, monkeypatch):
        from voicetest.cli import main

        monkeypatch.setattr(
            "voicetest.cli.subprocess.run",
            lambda *a, **kw: type("Result", (), {"returncode": 1, "stdout": b"", "stderr": b""})(),
        )

        result = cli_runner.invoke(main, ["up", "--detach"])

        assert result.exit_code != 0
        assert "docker compose" in result.output.lower()

    def test_up_detach_starts_infra_only(self, cli_runner, monkeypatch):
        from voicetest.cli import main

        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

        monkeypatch.setattr("voicetest.cli.subprocess.run", mock_run)

        result = cli_runner.invoke(main, ["up", "--detach"])

        assert result.exit_code == 0
        assert "Infrastructure started" in result.output
        # Should have called docker compose version and docker compose up
        assert len(calls) == 2
        assert calls[0] == ["docker", "compose", "version"]
        assert "up" in calls[1]
        assert "-d" in calls[1]


class TestCLIDown:
    """Tests for the down command."""

    def test_down_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["down", "--help"])

        assert result.exit_code == 0
        assert "Stop infrastructure" in result.output

    def test_down_fails_without_docker(self, cli_runner, monkeypatch):
        from voicetest.cli import main

        monkeypatch.setattr(
            "voicetest.cli.subprocess.run",
            lambda *a, **kw: type("Result", (), {"returncode": 1, "stdout": b"", "stderr": b""})(),
        )

        result = cli_runner.invoke(main, ["down"])

        assert result.exit_code != 0
        assert "docker compose" in result.output.lower()

    def test_down_calls_docker_compose_down(self, cli_runner, monkeypatch):
        from voicetest.cli import main

        calls = []

        def mock_run(cmd, **kwargs):
            calls.append(cmd)
            return type("Result", (), {"returncode": 0, "stdout": b"", "stderr": b""})()

        monkeypatch.setattr("voicetest.cli.subprocess.run", mock_run)

        result = cli_runner.invoke(main, ["down"])

        assert result.exit_code == 0
        assert "stopped" in result.output.lower()
        assert len(calls) == 2
        assert calls[0] == ["docker", "compose", "version"]
        assert "down" in calls[1]


class TestCompose:
    """Tests for the compose module."""

    def test_get_compose_path_returns_valid_path(self):
        from voicetest.compose import get_compose_path

        with get_compose_path() as path:
            assert path.exists()
            assert path.name == "docker-compose.yml"

    def test_compose_file_has_expected_services(self):
        import yaml

        from voicetest.compose import get_compose_path

        with get_compose_path() as path:
            content = yaml.safe_load(path.read_text())

        assert "services" in content
        assert "livekit" in content["services"]
        assert "whisper" in content["services"]
        assert "kokoro" in content["services"]

    def test_compose_file_does_not_include_backend(self):
        import yaml

        from voicetest.compose import get_compose_path

        with get_compose_path() as path:
            content = yaml.safe_load(path.read_text())

        assert "backend" not in content["services"]
        assert "frontend" not in content["services"]
