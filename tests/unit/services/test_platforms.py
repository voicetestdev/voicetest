"""Tests for voicetest.services.platforms module."""

import pytest

from voicetest.services import get_platform_service


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """PlatformService backed by an isolated temp database."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".voicetest").mkdir()
    # Clear platform API keys to ensure clean state
    monkeypatch.delenv("RETELL_API_KEY", raising=False)
    monkeypatch.delenv("VAPI_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
    monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)
    monkeypatch.delenv("BLAND_API_KEY", raising=False)
    monkeypatch.delenv("TELNYX_API_KEY", raising=False)
    return get_platform_service()


class TestListPlatforms:
    def test_returns_list(self, svc):
        platforms = svc.list_platforms()
        assert isinstance(platforms, list)
        assert len(platforms) > 0

    def test_each_has_required_keys(self, svc):
        for p in svc.list_platforms():
            assert "name" in p
            assert "configured" in p
            assert "env_key" in p

    def test_includes_retell(self, svc):
        names = {p["name"] for p in svc.list_platforms()}
        assert "retell" in names

    def test_unconfigured_by_default(self, svc):
        for p in svc.list_platforms():
            assert p["configured"] is False


class TestGetStatus:
    def test_unconfigured(self, svc):
        status = svc.get_status("retell")
        assert status["configured"] is False
        assert status["platform"] == "retell"

    def test_invalid_platform_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid platform"):
            svc.get_status("nonexistent_platform")


class TestConfigure:
    def test_configure_platform(self, svc):
        result = svc.configure("retell", api_key="test_key_123")
        assert result["configured"] is True
        assert result["platform"] == "retell"

    def test_configure_already_configured_raises(self, svc):
        svc.configure("retell", api_key="test_key_123")
        with pytest.raises(ValueError, match="already configured"):
            svc.configure("retell", api_key="another_key")

    def test_configure_invalid_platform_raises(self, svc):
        with pytest.raises(ValueError, match="Invalid platform"):
            svc.configure("nonexistent", api_key="key")


class TestGetSyncStatus:
    def test_nonexistent_agent(self, svc):
        result = svc.get_sync_status("nonexistent-agent-id")
        assert result["can_sync"] is False
