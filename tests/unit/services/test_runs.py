"""Tests for voicetest.services.runs module."""

import pytest

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


class TestImportCalls:
    def _make_imported(self, name: str, transcript: list | None = None):
        from voicetest.models.results import Message
        from voicetest.models.results import TestResult

        return TestResult(
            test_name=name,
            status="imported",
            transcript=transcript
            or [
                Message(role="assistant", content="Hi"),
                Message(role="user", content="Hello"),
            ],
            turn_count=2,
            duration_ms=12000,
            end_reason="ended",
        )

    def test_imports_one_call(self, agent_id):
        svc = get_run_service()
        results = [self._make_imported("call_001")]

        run = svc.import_calls(agent_id, results)

        assert run is not None
        assert run["agent_id"] == agent_id
        assert run["completed_at"] is not None  # marked complete immediately
        assert len(run["results"]) == 1
        assert run["results"][0]["status"] == "imported"
        assert run["results"][0]["test_name"] == "call_001"
        assert run["results"][0]["test_case_id"] is None
        assert run["results"][0]["call_id"] is None

    def test_imports_multiple_calls_into_one_run(self, agent_id):
        svc = get_run_service()
        results = [
            self._make_imported("call_a"),
            self._make_imported("call_b"),
            self._make_imported("call_c"),
        ]

        run = svc.import_calls(agent_id, results)

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


class TestReplayRun:
    def _make_imported(self, name: str):
        from voicetest.models.results import Message
        from voicetest.models.results import TestResult

        return TestResult(
            test_name=name,
            status="imported",
            transcript=[
                Message(role="assistant", content="Hi, how can I help?"),
                Message(role="user", content="I need to cancel."),
                Message(role="assistant", content="What's the order id?"),
                Message(role="user", content="ORD-99"),
            ],
            turn_count=4,
            duration_ms=10000,
            end_reason="ended",
        )

    @pytest.mark.asyncio
    async def test_raises_when_source_not_found(self, agent_id):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.test_case import RunOptions

        svc = get_run_service()
        graph = AgentGraph(entry_node_id="x", nodes={}, source_type="test", source_metadata={})

        with pytest.raises(ValueError, match="Source run not found"):
            await svc.replay_run("nonexistent", graph, RunOptions())

    @pytest.mark.asyncio
    async def test_raises_when_source_has_no_results(self, agent_id):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.test_case import RunOptions

        svc = get_run_service()
        # Empty source run
        empty_source = svc.create_run(agent_id)
        svc.complete(empty_source["id"])

        graph = AgentGraph(entry_node_id="x", nodes={}, source_type="test", source_metadata={})

        with pytest.raises(ValueError, match="no results to replay"):
            await svc.replay_run(empty_source["id"], graph, RunOptions())

    @pytest.mark.asyncio
    async def test_replay_drives_scripted_simulator(self, agent_id, monkeypatch):
        """Replay creates a new Run linked to the source's agent, with one
        replay Result per source Result. The runner is invoked with a
        ScriptedUserSimulator carrying the source's recorded user turns."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.results import Message
        from voicetest.models.test_case import RunOptions

        svc = get_run_service()
        # Seed an imported source run
        source = svc.import_calls(
            agent_id,
            [self._make_imported("call_a"), self._make_imported("call_b")],
        )
        assert len(source["results"]) == 2

        # Stub ConversationRunner.run so we don't need a real graph or LLM —
        # just verify the simulator passed in has the right user turns.
        captured_simulators: list = []

        async def fake_run(self, test_case, simulator, **kwargs):
            from voicetest.engine.session import ConversationState

            captured_simulators.append(simulator)
            # Drain the simulator so we can verify its user turns
            transcript = []
            while True:
                response = await simulator.generate(transcript)
                if response is None:
                    break
                transcript.append(Message(role="user", content=response.message))
                # Simulate an agent turn so the conversation has shape
                transcript.append(Message(role="assistant", content="ack"))

            state = ConversationState()
            state.transcript = transcript
            state.turn_count = len(transcript) // 2
            state.end_reason = "ended"
            return state

        monkeypatch.setattr("voicetest.engine.session.ConversationRunner.run", fake_run)

        graph = AgentGraph(entry_node_id="x", nodes={}, source_type="test", source_metadata={})
        replay = await svc.replay_run(source["id"], graph, RunOptions())

        # Two source Results → two replay Results
        assert len(replay["results"]) == 2
        assert replay["agent_id"] == agent_id
        assert replay["completed_at"] is not None
        # Each replay result is named after its source
        names = {r["test_name"] for r in replay["results"]}
        assert names == {"Replay of call_a", "Replay of call_b"}
        # Both replays got a ScriptedUserSimulator with the source's user turns
        assert len(captured_simulators) == 2
        for sim in captured_simulators:
            # Each source had 2 user turns: "I need to cancel.", "ORD-99"
            assert sim._user_turns == ["I need to cancel.", "ORD-99"]
            # And the simulator was driven to exhaustion
            assert sim._index == 2
