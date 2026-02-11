"""Tests for data persistence module."""

from datetime import UTC
from datetime import datetime

import pytest

from voicetest.data import DataStore
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import TestResult
from voicetest.models.results import TestRun


@pytest.fixture
def store(tmp_path):
    """Create a data store with temp directory."""
    return DataStore(data_dir=tmp_path)


@pytest.fixture
def sample_graph():
    """Create a sample agent graph."""
    return AgentGraph(
        source_type="test",
        entry_node_id="greeting",
        nodes={
            "greeting": AgentNode(
                id="greeting",
                name="Greeting",
                state_prompt="Say hello",
                transitions=[],
            )
        },
    )


@pytest.fixture
def sample_run():
    """Create a sample test run."""
    return TestRun(
        run_id="run-123",
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        results=[
            TestResult(
                test_id="test-1",
                test_name="Test One",
                status="pass",
                turn_count=3,
                transcript=[
                    Message(role="assistant", content="Hello"),
                    Message(role="user", content="Hi"),
                ],
                metric_results=[
                    MetricResult(metric="Greeted user", passed=True, reasoning="Said hello"),
                ],
                nodes_visited=["greeting"],
            ),
            TestResult(
                test_id="test-2",
                test_name="Test Two",
                status="fail",
                turn_count=1,
                transcript=[Message(role="assistant", content="Error")],
                error_message="Something went wrong",
            ),
        ],
    )


class TestAgentPersistence:
    """Tests for agent save/load."""

    def test_save_and_get_agent(self, store, sample_graph):
        agent_id = store.save_agent(sample_graph, name="My Agent")

        loaded = store.get_agent(agent_id)

        assert loaded is not None
        assert loaded.source_type == "test"
        assert loaded.entry_node_id == "greeting"
        assert len(loaded.nodes) == 1

    def test_list_agents(self, store, sample_graph):
        store.save_agent(sample_graph, name="Agent 1")
        store.save_agent(sample_graph, name="Agent 2")

        agents = store.list_agents()

        assert len(agents) == 2
        names = [a["name"] for a in agents]
        assert "Agent 1" in names
        assert "Agent 2" in names

    def test_get_nonexistent_agent(self, store):
        result = store.get_agent("nonexistent")
        assert result is None


class TestRunPersistence:
    """Tests for run save/load."""

    def test_save_and_get_run(self, store, sample_run):
        store.save_run(sample_run, agent_id="agent-123")

        run = store.get_run("run-123")

        assert run is not None
        assert run["id"] == "run-123"
        assert run["total_tests"] == 2
        assert run["passed"] == 1
        assert run["failed"] == 1

    def test_get_run_results(self, store, sample_run):
        store.save_run(sample_run)

        results = store.get_run_results("run-123")

        assert len(results) == 2
        test_ids = [r["test_id"] for r in results]
        assert "test-1" in test_ids
        assert "test-2" in test_ids

    def test_list_runs(self, store, sample_run):
        store.save_run(sample_run)

        runs = store.list_runs()

        assert len(runs) == 1
        assert runs[0]["id"] == "run-123"


class TestQuery:
    """Tests for SQL query interface."""

    def test_query_agents(self, store, sample_graph):
        store.save_agent(sample_graph, name="Agent A")
        store.save_agent(sample_graph, name="Agent B")

        results = store.query("SELECT name, source_type FROM agents")

        assert len(results) == 2

    def test_query_runs_with_filter(self, store, sample_run):
        store.save_run(sample_run)

        results = store.query("SELECT * FROM runs WHERE passed > 0")

        assert len(results) == 1
        assert results[0]["passed"] == 1

    def test_query_join(self, store, sample_graph):
        agent_id = store.save_agent(sample_graph, name="Test Agent")
        run = TestRun(
            run_id="run-456",
            started_at=datetime.now(UTC),
            results=[],
        )
        store.save_run(run, agent_id=agent_id)

        results = store.query("""
            SELECT r.id as run_id, a.name as agent_name
            FROM runs r
            LEFT JOIN agents a ON r.agent_id = a.id
            WHERE r.id = 'run-456'
        """)

        assert len(results) == 1
        assert results[0]["agent_name"] == "Test Agent"
