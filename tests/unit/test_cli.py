"""Tests for the CLI."""

import dataclasses
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


class TestCLIRunSaveOption:
    """Tests for the --save-run option on the run command."""

    def test_run_help_shows_save_run(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["run", "--help"])

        assert result.exit_code == 0
        assert "--save-run" in result.output

    def test_run_help_shows_agent_id(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["run", "--help"])

        assert result.exit_code == 0
        assert "--agent-id" in result.output

    def test_save_run_requires_agent_id(self, cli_runner, temp_agent_file, temp_tests_file):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            [
                "run",
                "--agent",
                str(temp_agent_file),
                "--tests",
                str(temp_tests_file),
                "--all",
                "--save-run",
            ],
        )

        assert result.exit_code != 0
        assert "--agent-id" in result.output


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


class TestSyncGuards:
    """Verify CLI stays in sync with service registries."""

    def test_export_choices_match_registry(self):
        """CLI export format choices must include every registered format."""
        from voicetest.services import get_discovery_service

        registry_formats = {f["id"] for f in get_discovery_service().list_export_formats()}
        assert len(registry_formats) > 0, "Expected at least one export format in registry"

        from voicetest.cli import LazyExportChoice

        choice = LazyExportChoice()
        # LazyExportChoice defers to the registry at validation time
        for fmt in registry_formats:
            assert choice.convert(fmt, None, None) == fmt

    def test_exporters_command_lists_all_formats(self, cli_runner):
        """The exporters command must list every registered export format."""
        from voicetest.cli import main
        from voicetest.services import get_discovery_service

        result = cli_runner.invoke(main, ["exporters"])
        assert result.exit_code == 0

        for fmt in get_discovery_service().list_export_formats():
            assert fmt["id"] in result.output, f"Missing format '{fmt['id']}' in exporters output"

    def test_main_help_shows_exporters(self, cli_runner):
        """The --help output must include the exporters command."""
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "exporters" in result.output


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


class TestCLIJsonOutput:
    """Tests for --json flag output."""

    def test_json_flag_in_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "--json" in result.output

    def test_importers_json(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--json", "importers"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "source_type" in item
            assert "description" in item
            assert "file_patterns" in item

    def test_importers_json_matches_registry(self, cli_runner):
        """JSON output must contain the same data as the registry."""
        from voicetest.cli import main
        from voicetest.services import get_discovery_service

        result = cli_runner.invoke(main, ["--json", "importers"])
        data = json.loads(result.output)

        registry = get_discovery_service().list_importers()
        expected = [dataclasses.asdict(imp) for imp in registry]
        assert data == expected

    def test_exporters_json(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--json", "exporters"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0
        for item in data:
            assert "id" in item
            assert "name" in item
            assert "description" in item
            assert "ext" in item

    def test_exporters_json_matches_registry(self, cli_runner):
        """JSON output must contain the same data as the registry."""
        from voicetest.cli import main
        from voicetest.services import get_discovery_service

        result = cli_runner.invoke(main, ["--json", "exporters"])
        data = json.loads(result.output)

        expected = get_discovery_service().list_export_formats()
        assert data == expected

    def test_export_json_to_stdout(self, cli_runner, temp_agent_file, tmp_path, monkeypatch):
        """--json export without -o writes content to stdout (no file created)."""
        from voicetest.cli import main

        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(
            main,
            ["--json", "export", "-a", str(temp_agent_file), "-f", "mermaid"],
        )

        assert result.exit_code == 0
        # Should contain mermaid content directly on stdout
        assert "flowchart" in result.output.lower()
        # Should NOT create a file
        generated_files = list(tmp_path.glob("*_mermaid*"))
        assert len(generated_files) == 0

    def test_export_json_with_output_file(self, cli_runner, temp_agent_file, tmp_path):
        """--json export with -o writes file and outputs JSON metadata."""
        from voicetest.cli import main

        output_path = tmp_path / "out.md"
        result = cli_runner.invoke(
            main,
            [
                "--json",
                "export",
                "-a",
                str(temp_agent_file),
                "-f",
                "mermaid",
                "-o",
                str(output_path),
            ],
        )

        assert result.exit_code == 0
        assert output_path.exists()
        # stdout should contain JSON with file path
        data = json.loads(result.output)
        assert "file" in data
        assert data["file"] == str(output_path)


class TestCLIExitCodes:
    """Tests for CLI exit codes."""

    def test_run_no_tests_selected_exits_zero(self, cli_runner, temp_agent_file, temp_tests_file):
        """run without --all or --test exits 0 (warning, not error)."""
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            ["run", "-a", str(temp_agent_file), "-t", str(temp_tests_file)],
        )

        assert result.exit_code == 0


class TestCLIAgent:
    """Tests for the agent subgroup commands."""

    def test_agent_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output
        assert "create" in result.output
        assert "update" in result.output
        assert "delete" in result.output
        assert "graph" in result.output

    def test_agent_list_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "list", "--help"])

        assert result.exit_code == 0

    def test_agent_get_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "get", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output

    def test_agent_create_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "create", "--help"])

        assert result.exit_code == 0
        assert "--agent" in result.output or "-a" in result.output

    def test_agent_update_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "update", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "--name" in result.output
        assert "--model" in result.output

    def test_agent_delete_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "delete", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "--yes" in result.output

    def test_agent_graph_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["agent", "graph", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output

    def test_agent_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "agent" in result.output


class TestCLITest:
    """Tests for the test subgroup commands."""

    def test_test_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output
        assert "create" in result.output
        assert "update" in result.output
        assert "delete" in result.output
        assert "link" in result.output
        assert "unlink" in result.output
        assert "export" in result.output

    def test_test_list_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "list", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output

    def test_test_get_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "get", "--help"])

        assert result.exit_code == 0
        assert "TEST_ID" in result.output

    def test_test_create_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "create", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "-f" in result.output

    def test_test_update_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "update", "--help"])

        assert result.exit_code == 0
        assert "TEST_ID" in result.output
        assert "-f" in result.output

    def test_test_delete_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "delete", "--help"])

        assert result.exit_code == 0
        assert "TEST_ID" in result.output
        assert "--yes" in result.output

    def test_test_link_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "link", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "PATH" in result.output

    def test_test_unlink_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "unlink", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "PATH" in result.output

    def test_test_export_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["test", "export", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "--ids" in result.output

    def test_test_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "test" in result.output


class TestCLIRuns:
    """Tests for the runs subgroup commands."""

    def test_runs_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["runs", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "get" in result.output
        assert "delete" in result.output

    def test_runs_list_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["runs", "list", "--help"])

        assert result.exit_code == 0
        assert "AGENT_ID" in result.output
        assert "--limit" in result.output

    def test_runs_get_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["runs", "get", "--help"])

        assert result.exit_code == 0
        assert "RUN_ID" in result.output

    def test_runs_delete_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["runs", "delete", "--help"])

        assert result.exit_code == 0
        assert "RUN_ID" in result.output
        assert "--yes" in result.output

    def test_runs_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "runs" in result.output


class TestCLISnippet:
    """Tests for the snippet subgroup commands."""

    def test_snippet_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["snippet", "--help"])

        assert result.exit_code == 0
        assert "list" in result.output
        assert "set" in result.output
        assert "delete" in result.output
        assert "analyze" in result.output
        assert "apply" in result.output

    def test_snippet_list_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["snippet", "list", "--help"])

        assert result.exit_code == 0
        assert "--agent-id" in result.output
        assert "--agent" in result.output or "-a" in result.output

    def test_snippet_set_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["snippet", "set", "--help"])

        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "TEXT" in result.output

    def test_snippet_delete_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["snippet", "delete", "--help"])

        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "--yes" in result.output

    def test_snippet_analyze_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["snippet", "analyze", "--help"])

        assert result.exit_code == 0
        assert "--threshold" in result.output
        assert "--min-length" in result.output

    def test_snippet_apply_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["snippet", "apply", "--help"])

        assert result.exit_code == 0
        assert "--snippets" in result.output

    def test_snippet_analyze_file_mode(self, cli_runner, temp_agent_file):
        """snippet analyze with --agent PATH loads from file."""
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            ["--json", "snippet", "analyze", "--agent", str(temp_agent_file)],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "exact" in data
        assert "fuzzy" in data

    def test_snippet_list_file_mode(self, cli_runner, temp_agent_file):
        """snippet list with --agent PATH loads from file."""
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            ["--json", "snippet", "list", "--agent", str(temp_agent_file)],
        )

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, dict)

    def test_snippet_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "snippet" in result.output


class TestCLISettings:
    """Tests for the settings command."""

    def test_settings_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["settings", "--help"])

        assert result.exit_code == 0
        assert "--set" in result.output
        assert "--defaults" in result.output

    def test_settings_json(self, cli_runner, tmp_path, monkeypatch):
        from voicetest.cli import main

        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(main, ["--json", "settings"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "models" in data
        assert "run" in data

    def test_settings_defaults(self, cli_runner, tmp_path, monkeypatch):
        from voicetest.cli import main

        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(main, ["--json", "settings", "--defaults"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "models" in data
        assert "run" in data

    def test_settings_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "settings" in result.output


class TestCLIPlatforms:
    """Tests for the platforms command."""

    def test_platforms_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["platforms", "--help"])

        assert result.exit_code == 0

    def test_platforms_json(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--json", "platforms"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)

    def test_platforms_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "platforms" in result.output


class TestCLIPlatform:
    """Tests for the platform subgroup commands."""

    def test_platform_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["platform", "--help"])

        assert result.exit_code == 0
        assert "configure" in result.output
        assert "list-agents" in result.output

    def test_platform_configure_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["platform", "configure", "--help"])

        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "--api-key" in result.output

    def test_platform_list_agents_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["platform", "list-agents", "--help"])

        assert result.exit_code == 0
        assert "NAME" in result.output

    def test_platform_import_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["platform", "import", "--help"])

        assert result.exit_code == 0
        assert "NAME" in result.output
        assert "AGENT_ID" in result.output

    def test_platform_push_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["platform", "push", "--help"])

        assert result.exit_code == 0
        assert "--agent" in result.output or "-a" in result.output

    def test_platform_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "platform" in result.output


class TestCLIEvaluate:
    """Tests for the evaluate command."""

    def test_evaluate_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["evaluate", "--help"])

        assert result.exit_code == 0
        assert "--transcript" in result.output or "-t" in result.output
        assert "--metrics" in result.output or "-m" in result.output
        assert "--judge-model" in result.output

    def test_evaluate_missing_transcript(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            ["evaluate", "--transcript", "/nonexistent/transcript.json", "-m", "polite"],
        )

        assert result.exit_code != 0

    def test_evaluate_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "evaluate" in result.output


class TestCLIDiagnose:
    """Tests for the diagnose command."""

    def test_diagnose_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["diagnose", "--help"])

        assert result.exit_code == 0
        assert "--agent" in result.output or "-a" in result.output
        assert "--tests" in result.output or "-t" in result.output
        assert "--auto-fix" in result.output
        assert "--max-iterations" in result.output
        assert "--save" in result.output

    def test_diagnose_missing_agent(self, cli_runner, temp_tests_file):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            ["diagnose", "-a", "/nonexistent/agent.json", "-t", str(temp_tests_file)],
        )

        assert result.exit_code != 0

    def test_diagnose_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "diagnose" in result.output


class TestCLIChat:
    """Tests for the chat command."""

    def test_chat_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["chat", "--help"])

        assert result.exit_code == 0
        assert "--agent" in result.output or "-a" in result.output
        assert "--model" in result.output
        assert "--var" in result.output

    def test_chat_missing_agent(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(
            main,
            ["chat", "-a", "/nonexistent/agent.json"],
        )

        assert result.exit_code != 0

    def test_chat_shown_in_main_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["--help"])

        assert result.exit_code == 0
        assert "chat" in result.output
