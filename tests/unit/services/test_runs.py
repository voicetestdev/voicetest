"""Tests for voicetest.services.runs module."""

import pytest

from voicetest.models.results import Message
from voicetest.services import get_agent_service
from voicetest.services import get_run_service


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """RunService backed by an isolated temp database."""
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    return get_run_service()


@pytest.fixture
def agent_id(tmp_path, monkeypatch):
    """Create a temp agent and return its ID."""
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


_FOUR_TURN_TRANSCRIPT = [
    Message(role="assistant", content="Hi, how can I help?"),
    Message(role="user", content="I need to cancel."),
    Message(role="assistant", content="What's the order id?"),
    Message(role="user", content="ORD-99"),
]


class TestImportCalls:
    def test_imports_one_call(self, agent_id, imported_test_result):
        svc = get_run_service()
        run = svc.import_calls(agent_id, [imported_test_result("call_001")])

        assert run is not None
        assert run["agent_id"] == agent_id
        assert run["completed_at"] is not None  # marked complete immediately
        assert len(run["results"]) == 1
        assert run["results"][0]["status"] == "imported"
        assert run["results"][0]["test_name"] == "call_001"
        assert run["results"][0]["test_case_id"] is None
        assert run["results"][0]["call_id"] is None

    def test_imports_multiple_calls_into_one_run(self, agent_id, imported_test_result):
        svc = get_run_service()
        run = svc.import_calls(
            agent_id,
            [
                imported_test_result("call_a"),
                imported_test_result("call_b"),
                imported_test_result("call_c"),
            ],
        )

        assert len(run["results"]) == 3
        assert {r["test_name"] for r in run["results"]} == {"call_a", "call_b", "call_c"}
        assert all(r["status"] == "imported" for r in run["results"])

    def test_empty_results_creates_empty_run(self, agent_id):
        """Edge case: importing zero conversations still creates a (complete) Run.

        Worth keeping rather than raising, because the adapter might be the
        place that rejects empty payloads — the service shouldn't second-guess.
        """
        svc = get_run_service()
        run = svc.import_calls(agent_id, [])

        assert run is not None
        assert run["completed_at"] is not None
        assert run["results"] == []


def _empty_graph():
    from voicetest.models.agent import AgentGraph

    return AgentGraph(entry_node_id="x", nodes={}, source_type="test", source_metadata={})


class TestReplayRun:
    @pytest.mark.asyncio
    async def test_raises_when_source_not_found(self, agent_id):
        from voicetest.models.test_case import RunOptions

        svc = get_run_service()

        with pytest.raises(ValueError, match="Source run not found"):
            await svc.replay_run("nonexistent", _empty_graph(), RunOptions())

    @pytest.mark.asyncio
    async def test_raises_when_source_has_no_results(self, agent_id):
        from voicetest.models.test_case import RunOptions

        svc = get_run_service()
        # Empty source run
        empty_source = svc.create_run(agent_id)
        svc.complete(empty_source["id"])

        with pytest.raises(ValueError, match="no results to replay"):
            await svc.replay_run(empty_source["id"], _empty_graph(), RunOptions())

    @pytest.mark.asyncio
    async def test_replay_drives_scripted_simulator(
        self, agent_id, imported_test_result, stub_conversation_runner
    ):
        """Replay creates a new Run linked to the source's agent, with one
        replay Result per source Result. The runner is invoked with a
        ScriptedUserSimulator carrying the source's recorded user turns."""
        from voicetest.models.test_case import RunOptions

        svc = get_run_service()
        source = svc.import_calls(
            agent_id,
            [
                imported_test_result("call_a", transcript=list(_FOUR_TURN_TRANSCRIPT)),
                imported_test_result("call_b", transcript=list(_FOUR_TURN_TRANSCRIPT)),
            ],
        )
        assert len(source["results"]) == 2

        replay = await svc.replay_run(source["id"], _empty_graph(), RunOptions())

        # Two source Results → two replay Results
        assert len(replay["results"]) == 2
        assert replay["agent_id"] == agent_id
        assert replay["completed_at"] is not None
        # Each replay result is named after its source
        names = {r["test_name"] for r in replay["results"]}
        assert names == {"Replay of call_a", "Replay of call_b"}
        # Both replays got a ScriptedUserSimulator with the source's user turns
        assert len(stub_conversation_runner) == 2
        for sim in stub_conversation_runner:
            assert sim._user_turns == ["I need to cancel.", "ORD-99"]
            assert sim._index == 2
