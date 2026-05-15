"""Coverage for the FastAPI lifespan handler in voicetest.web.rest.

The lifespan builds (or reuses) `app.state.container`, then runs `init_storage`
and `setup_cache_from_settings`. Tests open the TestClient as a context manager
to force the lifespan to fire.
"""

import contextlib
from unittest.mock import patch

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import Engine

from voicetest.container import create_container
from voicetest.web import rest as rest_module


@pytest.fixture
def restore_app_state():
    """Snapshot app.state.container before the test; dispose + restore on teardown.

    The autouse `fresh_container` fixture (tests/unit/conftest.py) reassigns
    `app.state.container` for each test, but lifespan tests mutate the attribute
    mid-test (delete it, or substitute a preset). This fixture pairs each
    mutation with an explicit engine disposal so the DuckDB file lock doesn't
    leak across tests.
    """
    saved = getattr(rest_module.app.state, "container", None)
    yield
    new = getattr(rest_module.app.state, "container", None)
    if new is not None and new is not saved:
        # Dispose the engine the substituted container may have opened — DuckDB
        # holds a file lock until the engine is closed.
        with contextlib.suppress(Exception):
            new.resolve(Engine).dispose()
    if saved is None:
        if hasattr(rest_module.app.state, "container"):
            del rest_module.app.state.container
    else:
        rest_module.app.state.container = saved


def test_lifespan_initializes_container_when_absent(monkeypatch, tmp_path, restore_app_state):
    """Without a pre-set container, the lifespan creates one and runs init_storage + cache setup."""
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".voicetest").mkdir()

    # Strip the container the autouse fixture set up, so the lifespan takes
    # the "no preset container" branch.
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


def test_lifespan_reuses_preset_container(monkeypatch, tmp_path, restore_app_state):
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
