"""Tests for voicetest.services.runs module."""

import pytest

from voicetest.services import get_agent_service
from voicetest.services import get_run_service


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """RunService backed by an isolated temp database."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    return get_run_service()


@pytest.fixture
def agent_id(tmp_path, monkeypatch):
    """Create a temp agent and return its ID."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)

    config = {
        "source_type": "custom",
        "entry_node_id": "main",
        "nodes": {
            "main": {
                "id": "main",
                "state_prompt": "Hello.",
                "transitions": [],
            }
        },
        "source_metadata": {},
    }
    agent_svc = get_agent_service()
    created = agent_svc.create_agent(name="Run Agent", config=config)
    return created["id"]


class TestCreateRun:
    def test_creates_run(self, agent_id):
        svc = get_run_service()
        run = svc.create_run(agent_id)
        assert "id" in run
        assert run["agent_id"] == agent_id

    def test_run_has_started_at(self, agent_id):
        svc = get_run_service()
        run = svc.create_run(agent_id)
        assert run["started_at"] is not None
        assert run["completed_at"] is None


class TestListRuns:
    def test_empty(self, agent_id):
        svc = get_run_service()
        assert svc.list_runs(agent_id) == []

    def test_lists_after_create(self, agent_id):
        svc = get_run_service()
        svc.create_run(agent_id)
        runs = svc.list_runs(agent_id)
        assert len(runs) == 1


class TestGetRun:
    def test_get_existing(self, agent_id):
        svc = get_run_service()
        created = svc.create_run(agent_id)
        run = svc.get_run(created["id"])
        assert run is not None
        assert run["id"] == created["id"]

    def test_get_nonexistent(self, svc):
        assert svc.get_run("nonexistent") is None


class TestDeleteRun:
    def test_delete(self, agent_id):
        svc = get_run_service()
        created = svc.create_run(agent_id)
        svc.delete_run(created["id"])
        assert svc.get_run(created["id"]) is None


class TestCompleteRun:
    def test_complete(self, agent_id):
        svc = get_run_service()
        created = svc.create_run(agent_id)
        svc.complete(created["id"])
        run = svc.get_run(created["id"])
        assert run["completed_at"] is not None
