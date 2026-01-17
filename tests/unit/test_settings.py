"""Tests for settings module."""

from voicetest.settings import Settings, load_settings, save_settings


class TestSettings:
    """Tests for Settings model."""

    def test_default_settings(self):
        settings = Settings()

        assert settings.models.agent == "openai/gpt-4o-mini"
        assert settings.models.simulator == "openai/gpt-4o-mini"
        assert settings.models.judge == "openai/gpt-4o-mini"
        assert settings.run.max_turns == 20
        assert settings.run.verbose is False

    def test_custom_settings(self):
        settings = Settings(
            models={"agent": "ollama/llama3", "simulator": "gemini/gemini-1.5-flash"},
            run={"max_turns": 10, "verbose": True},
        )

        assert settings.models.agent == "ollama/llama3"
        assert settings.models.simulator == "gemini/gemini-1.5-flash"
        assert settings.models.judge == "openai/gpt-4o-mini"  # default
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

        assert settings.models.agent == "openai/gpt-4o-mini"
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
        assert settings.models.simulator == "openai/gpt-4o-mini"  # default
        assert settings.run.max_turns == 20  # default
