"""Tests for voicetest.services.runs module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.services.agents import AgentService
from voicetest.services.runs import RunService
from voicetest.services.testing.cases import TestCaseService


@pytest.fixture
def svc(tmp_path, monkeypatch, container):
    """RunService backed by an isolated temp database."""
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    return container.resolve(RunService)


@pytest.fixture
def agent_id(tmp_path, monkeypatch, container):
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
                "node_type": "conversation",
                "transitions": [],
            }
        },
        "source_metadata": {},
    }
    agent_svc = container.resolve(AgentService)
    created = agent_svc.create_agent(name="Run Agent", config=config)
    return created["id"]


class TestCreateRun:
    def test_creates_run(self, agent_id, svc):
        run = svc.create_run(agent_id)
        assert "id" in run
        assert run["agent_id"] == agent_id

    def test_run_has_started_at(self, agent_id, svc):
        run = svc.create_run(agent_id)
        assert run["started_at"] is not None
        assert run["completed_at"] is None


class TestListRuns:
    def test_empty(self, agent_id, svc):
        assert svc.list_runs(agent_id) == []

    def test_lists_after_create(self, agent_id, svc):
        svc.create_run(agent_id)
        runs = svc.list_runs(agent_id)
        assert len(runs) == 1


class TestGetRun:
    def test_get_existing(self, agent_id, svc):
        created = svc.create_run(agent_id)
        run = svc.get_run(created["id"])
        assert run is not None
        assert run["id"] == created["id"]

    def test_get_nonexistent(self, svc):
        assert svc.get_run("nonexistent") is None


class TestDeleteRun:
    def test_delete(self, agent_id, svc):
        created = svc.create_run(agent_id)
        svc.delete_run(created["id"])
        assert svc.get_run(created["id"]) is None


class TestCompleteRun:
    def test_complete(self, agent_id, svc):
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
    def test_imports_one_call(self, agent_id, imported_test_result, svc):
        run = svc.import_calls(agent_id, [imported_test_result("call_001")])

        assert run is not None
        assert run["agent_id"] == agent_id
        assert run["completed_at"] is not None  # marked complete immediately
        assert len(run["results"]) == 1
        assert run["results"][0]["status"] == "imported"
        assert run["results"][0]["test_name"] == "call_001"
        assert run["results"][0]["test_case_id"] is None
        assert run["results"][0]["call_id"] is None

    def test_imports_multiple_calls_into_one_run(self, agent_id, imported_test_result, svc):
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

    def test_empty_results_creates_empty_run(self, agent_id, svc):
        """Edge case: importing zero conversations still creates a (complete) Run.

        Worth keeping rather than raising, because the adapter might be the
        place that rejects empty payloads — the service shouldn't second-guess.
        """
        run = svc.import_calls(agent_id, [])

        assert run is not None
        assert run["completed_at"] is not None
        assert run["results"] == []


class TestSaveCallAsRun:
    async def test_marks_result_source_kind_live(self, agent_id, svc):
        call = {
            "id": "call-live-1",
            "agent_id": agent_id,
            "transcript_json": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello"},
            ],
            "started_at": "2026-01-01T00:00:00+00:00",
            "ended_at": "2026-01-01T00:00:05+00:00",
        }

        run_id = await svc.save_call_as_run(call)

        run = svc.get_run(run_id)
        assert run["results"][0]["source_kind"] == "live"

    async def test_empty_transcript_returns_none(self, agent_id, svc):
        assert await svc.save_call_as_run({"id": "c", "agent_id": agent_id}) is None

    async def test_result_named_after_test_case(self, agent_id, svc, container):
        test_svc = container.resolve(TestCaseService)
        created = test_svc.create_test(
            agent_id,
            TestCase(name="Books a flight", user_prompt="## Goal\nBook a flight"),
        )
        call = {
            "id": "call-1",
            "agent_id": agent_id,
            "test_id": created["id"],
            "transcript_json": [
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Book a flight"},
            ],
        }

        run_id = await svc.save_call_as_run(call)

        result = svc.get_run(run_id)["results"][0]
        assert result["test_name"] == "Books a flight"
        assert result["source_kind"] == "live"

    async def test_result_defaults_to_live_call_without_test(self, agent_id, svc):
        call = {
            "id": "call-2",
            "agent_id": agent_id,
            "transcript_json": [{"role": "assistant", "content": "Hi"}],
        }

        run_id = await svc.save_call_as_run(call)

        assert svc.get_run(run_id)["results"][0]["test_name"] == "Live Call"

    async def test_passed_test_case_is_judged_without_db_lookup(self, agent_id, svc):
        test_case = TestCase(name="Books a flight", user_prompt="## Goal\nBook a flight")
        call = {
            "id": "call-3",
            "agent_id": agent_id,
            "transcript_json": [
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Book a flight"},
            ],
        }

        run_id = await svc.save_call_as_run(call, test_case=test_case)

        result = svc.get_run(run_id)["results"][0]
        assert result["test_name"] == "Books a flight"
        assert result["source_kind"] == "live"

    async def test_status_is_error_when_metric_eval_raises(self, agent_id, svc, monkeypatch):
        test_case = TestCase(
            name="Books a flight",
            user_prompt="## Goal\nBook a flight",
            metrics=["The agent books the flight"],
        )
        call = {
            "id": "call-err",
            "agent_id": agent_id,
            "transcript_json": [
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Book a flight"},
            ],
        }

        async def boom(*args, **kwargs):
            raise RuntimeError("judge unavailable")

        monkeypatch.setattr(svc._test_execution, "evaluate_metrics", boom)

        run_id = await svc.save_call_as_run(call, test_case=test_case)

        assert svc.get_run(run_id)["results"][0]["status"] == "error"

    async def test_second_save_of_same_call_returns_existing_run(self, agent_id, svc):
        call = {
            "id": "call-dup",
            "agent_id": agent_id,
            "transcript_json": [
                {"role": "assistant", "content": "Hi"},
                {"role": "user", "content": "Book a flight"},
            ],
        }

        first = await svc.save_call_as_run(call)
        second = await svc.save_call_as_run(call)

        assert second == first
        assert len(svc.list_runs(agent_id)) == 1


def _empty_graph():
    return AgentGraph(entry_node_id="x", nodes={}, source_type="test", source_metadata={})


class TestReplayRun:
    @pytest.mark.asyncio
    async def test_raises_when_source_not_found(self, agent_id, svc):
        with pytest.raises(ValueError, match="Source run not found"):
            await svc.replay_run("nonexistent", _empty_graph(), RunOptions())

    @pytest.mark.asyncio
    async def test_raises_when_source_has_no_results(self, agent_id, svc):
        # Empty source run
        empty_source = svc.create_run(agent_id)
        svc.complete(empty_source["id"])

        with pytest.raises(ValueError, match="no results to replay"):
            await svc.replay_run(empty_source["id"], _empty_graph(), RunOptions())

    @pytest.mark.asyncio
    async def test_replay_drives_scripted_simulator(
        self, agent_id, imported_test_result, stub_conversation_runner, svc
    ):
        """Replay creates a new Run linked to the source's agent, with one
        replay Result per source Result. The runner is invoked with a
        ScriptedUserSimulator carrying the source's recorded user turns."""

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
