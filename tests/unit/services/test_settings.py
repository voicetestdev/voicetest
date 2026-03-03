"""Tests for voicetest.services.settings module."""

from voicetest.services.settings import SettingsService
from voicetest.settings import Settings


class TestGetDefaults:
    def test_returns_settings(self):
        svc = SettingsService()
        defaults = svc.get_defaults()
        assert isinstance(defaults, Settings)

    def test_has_models_section(self):
        svc = SettingsService()
        defaults = svc.get_defaults()
        assert hasattr(defaults, "models")

    def test_has_run_section(self):
        svc = SettingsService()
        defaults = svc.get_defaults()
        assert hasattr(defaults, "run")


class TestGetSettings:
    def test_returns_settings(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        svc = SettingsService()
        settings = svc.get_settings()
        assert isinstance(settings, Settings)


class TestUpdateSettings:
    def test_roundtrip(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        svc = SettingsService()
        settings = svc.get_settings()
        settings.run.max_turns = 42
        returned = svc.update_settings(settings)
        assert returned.run.max_turns == 42

        reloaded = svc.get_settings()
        assert reloaded.run.max_turns == 42

    def test_returns_same_settings(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        svc = SettingsService()
        settings = Settings()
        result = svc.update_settings(settings)
        assert result is settings
