"""Tests for the Claude Code plugin distribution."""

import json
from pathlib import Path

from click.testing import CliRunner
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGIN_DIR = REPO_ROOT / "claude-plugin"
MARKETPLACE_FILE = REPO_ROOT / ".claude-plugin" / "marketplace.json"


@pytest.fixture
def cli_runner():
    """Create a CLI test runner."""
    return CliRunner()


class TestPluginManifest:
    """Tests for plugin.json and marketplace.json."""

    def test_plugin_json_valid(self):
        plugin_json = PLUGIN_DIR / ".claude-plugin" / "plugin.json"
        assert plugin_json.exists(), f"Missing {plugin_json}"

        data = json.loads(plugin_json.read_text())
        assert "name" in data
        assert "description" in data
        assert "version" in data
        assert data["name"] == "voicetest"

    def test_marketplace_json_valid(self):
        assert MARKETPLACE_FILE.exists(), f"Missing {MARKETPLACE_FILE}"

        data = json.loads(MARKETPLACE_FILE.read_text())
        assert "plugins" in data
        assert isinstance(data["plugins"], list)
        assert len(data["plugins"]) > 0

        plugin = data["plugins"][0]
        assert plugin["name"] == "voicetest"
        assert "source" in plugin
        assert "version" in plugin


class TestPluginCommands:
    """Tests for slash command .md files."""

    def test_commands_directory_exists(self):
        cmd_dir = PLUGIN_DIR / "commands"
        assert cmd_dir.is_dir(), f"Missing {cmd_dir}"

    def test_all_commands_exist(self):
        cmd_dir = PLUGIN_DIR / "commands"
        expected = [
            "voicetest-run.md",
            "voicetest-export.md",
            "voicetest-convert.md",
            "voicetest-info.md",
        ]
        for name in expected:
            assert (cmd_dir / name).exists(), f"Missing command file: {name}"

    def test_commands_have_frontmatter(self):
        cmd_dir = PLUGIN_DIR / "commands"
        for md_file in cmd_dir.glob("*.md"):
            content = md_file.read_text()
            assert content.startswith("---"), f"{md_file.name} missing YAML frontmatter"

            # Extract frontmatter
            parts = content.split("---", 2)
            assert len(parts) >= 3, f"{md_file.name} has malformed frontmatter"

            fm = yaml.safe_load(parts[1])
            assert "description" in fm, f"{md_file.name} missing description"
            assert "allowed-tools" in fm, f"{md_file.name} missing allowed-tools"


class TestPluginSkill:
    """Tests for the auto-activating skill."""

    def test_skill_md_exists(self):
        skill = PLUGIN_DIR / "skills" / "voicetest" / "SKILL.md"
        assert skill.exists(), f"Missing {skill}"

    def test_skill_md_has_frontmatter(self):
        skill = PLUGIN_DIR / "skills" / "voicetest" / "SKILL.md"
        content = skill.read_text()
        assert content.startswith("---"), "SKILL.md missing YAML frontmatter"

        parts = content.split("---", 2)
        fm = yaml.safe_load(parts[1])
        assert "description" in fm, "SKILL.md missing description"

    def test_reference_files_exist(self):
        ref_dir = PLUGIN_DIR / "skills" / "voicetest" / "references"
        assert (ref_dir / "test-format.md").exists(), "Missing test-format.md"
        assert (ref_dir / "platforms.md").exists(), "Missing platforms.md"


class TestSymlinks:
    """Tests for .claude/ symlinks."""

    def test_commands_symlink(self):
        link = REPO_ROOT / ".claude" / "commands"
        assert link.exists(), "Missing .claude/commands"
        assert link.is_symlink(), ".claude/commands should be a symlink"
        target = link.resolve()
        expected = (REPO_ROOT / "claude-plugin" / "commands").resolve()
        assert target == expected, f"Symlink target {target} != expected {expected}"

    def test_skills_symlink(self):
        link = REPO_ROOT / ".claude" / "skills"
        assert link.exists(), "Missing .claude/skills"
        assert link.is_symlink(), ".claude/skills should be a symlink"
        target = link.resolve()
        expected = (REPO_ROOT / "claude-plugin" / "skills").resolve()
        assert target == expected, f"Symlink target {target} != expected {expected}"


class TestInitClaudeCommand:
    """Tests for the init-claude CLI command."""

    def test_init_claude_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["init-claude", "--help"])

        assert result.exit_code == 0
        assert "Claude Code" in result.output

    def test_init_claude_creates_files(self, cli_runner, tmp_path, monkeypatch):
        from voicetest.cli import main

        monkeypatch.chdir(tmp_path)
        result = cli_runner.invoke(main, ["init-claude"])

        assert result.exit_code == 0
        assert (tmp_path / ".claude" / "commands").is_dir()
        assert (tmp_path / ".claude" / "skills").is_dir()

        # Verify command files were copied
        assert (tmp_path / ".claude" / "commands" / "voicetest-run.md").exists()
        assert (tmp_path / ".claude" / "commands" / "voicetest-export.md").exists()

        # Verify skill files were copied
        assert (tmp_path / ".claude" / "skills" / "voicetest" / "SKILL.md").exists()


class TestClaudePluginPathCommand:
    """Tests for the claude-plugin-path CLI command."""

    def test_claude_plugin_path_help(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["claude-plugin-path", "--help"])

        assert result.exit_code == 0

    def test_claude_plugin_path_prints_path(self, cli_runner):
        from voicetest.cli import main

        result = cli_runner.invoke(main, ["claude-plugin-path"])

        assert result.exit_code == 0
        output_path = Path(result.output.strip())
        assert output_path.is_dir(), f"Output path is not a directory: {output_path}"
