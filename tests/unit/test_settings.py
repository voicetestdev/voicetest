"""Tests for settings module."""

import os

from voicetest.settings import Settings, load_settings, save_settings


class TestSettings:
    """Tests for Settings model."""

    def test_default_settings(self):
        settings = Settings()

        # Models default to None (not configured)
        assert settings.models.agent is None
        assert settings.models.simulator is None
        assert settings.models.judge is None
        assert settings.run.max_turns == 20
        assert settings.run.verbose is False
        assert settings.run.test_model_precedence is False
        assert settings.env == {}

    def test_env_settings(self):
        settings = Settings(env={"OPENAI_API_KEY": "sk-test123", "CUSTOM_VAR": "value"})

        assert settings.env["OPENAI_API_KEY"] == "sk-test123"
        assert settings.env["CUSTOM_VAR"] == "value"

    def test_apply_env(self, monkeypatch):
        monkeypatch.delenv("TEST_API_KEY", raising=False)

        settings = Settings(env={"TEST_API_KEY": "test-value-123"})
        settings.apply_env()

        assert os.environ.get("TEST_API_KEY") == "test-value-123"

    def test_apply_env_does_not_clear_existing(self, monkeypatch):
        monkeypatch.setenv("EXISTING_KEY", "existing-value")

        settings = Settings(env={"NEW_KEY": "new-value"})
        settings.apply_env()

        assert os.environ.get("EXISTING_KEY") == "existing-value"
        assert os.environ.get("NEW_KEY") == "new-value"

    def test_custom_settings(self):
        settings = Settings(
            models={"agent": "ollama/llama3", "simulator": "gemini/gemini-1.5-flash"},
            run={"max_turns": 10, "verbose": True},
        )

        assert settings.models.agent == "ollama/llama3"
        assert settings.models.simulator == "gemini/gemini-1.5-flash"
        assert settings.models.judge is None  # default is None
        assert settings.run.max_turns == 10
        assert settings.run.verbose is True


class TestSettingsPersistence:
    """Tests for loading and saving settings."""

    def test_save_and_load(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"

        original = Settings(
            models={"agent": "anthropic/claude-3-haiku"},
            run={"max_turns": 5},
        )
        save_settings(original, settings_file)

        loaded = load_settings(settings_file)

        assert loaded.models.agent == "anthropic/claude-3-haiku"
        assert loaded.run.max_turns == 5

    def test_load_missing_file_returns_defaults(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"

        settings = load_settings(settings_file)

        assert settings.models.agent is None  # default is None
        assert settings.run.max_turns == 20

    def test_toml_format(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"

        settings = Settings(
            models={"agent": "test/model"},
            run={"verbose": True},
        )
        save_settings(settings, settings_file)

        content = settings_file.read_text()

        assert "[models]" in content
        assert 'agent = "test/model"' in content
        assert "[run]" in content
        assert "verbose = true" in content

    def test_partial_toml_uses_defaults(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"
        settings_file.write_text('[models]\nagent = "custom/model"\n')

        settings = load_settings(settings_file)

        assert settings.models.agent == "custom/model"
        assert settings.models.simulator is None  # default is None
        assert settings.run.max_turns == 20  # default

    def test_save_and_load_with_env(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"

        original = Settings(env={"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "ant-test"})
        save_settings(original, settings_file)

        loaded = load_settings(settings_file)

        assert loaded.env["OPENAI_API_KEY"] == "sk-test"
        assert loaded.env["ANTHROPIC_API_KEY"] == "ant-test"

    def test_toml_format_with_env(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"

        settings = Settings(env={"MY_API_KEY": "secret123"})
        save_settings(settings, settings_file)

        content = settings_file.read_text()

        assert "[env]" in content
        assert 'MY_API_KEY = "secret123"' in content

    def test_toml_no_env_section_when_empty(self, tmp_path):
        settings_file = tmp_path / ".voicetest.toml"

        settings = Settings()
        save_settings(settings, settings_file)

        content = settings_file.read_text()

        assert "[env]" not in content
