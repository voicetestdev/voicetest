"""Coverage for the FastAPI lifespan handler in voicetest.web.rest.

The lifespan builds (or reuses) `app.state.container`, then runs `init_storage`
and `setup_cache_from_settings`. Tests open the TestClient as a context manager
to force the lifespan to fire.
"""

from unittest.mock import patch

from fastapi.testclient import TestClient

from voicetest.container import create_container
from voicetest.web import rest as rest_module


def test_lifespan_initializes_container_when_absent(monkeypatch, tmp_path):
    """Without a pre-set container, the lifespan creates one and runs init_storage + cache setup."""
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".voicetest").mkdir()

    # Strip any prior container the autouse fixture set up.
    if hasattr(rest_module.app.state, "container"):
        del rest_module.app.state.container

    with (
        patch.object(rest_module, "init_storage") as init_storage,
        patch.object(rest_module, "setup_cache_from_settings") as setup_cache,
        TestClient(rest_module.app) as client,
    ):
        # Hit any endpoint so the lifespan actually fires (it's lazy until startup).
        resp = client.get("/api/agents")
        assert resp.status_code == 200

        assert hasattr(rest_module.app.state, "container")
        init_storage.assert_called_once()
        setup_cache.assert_called_once()


def test_lifespan_reuses_preset_container(monkeypatch, tmp_path):
    """If a test (or external caller) sets app.state.container first, lifespan respects it."""
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".voicetest").mkdir()

    preset = create_container()
    rest_module.app.state.container = preset

    with (
        patch.object(rest_module, "init_storage") as init_storage,
        patch.object(rest_module, "setup_cache_from_settings"),
        TestClient(rest_module.app) as client,
    ):
        client.get("/api/agents")
        assert rest_module.app.state.container is preset
        init_storage.assert_called_once_with(preset)
