"""Tests for repository classes."""

from datetime import UTC, datetime

import pytest

from voicetest.models.agent import AgentGraph, AgentNode
from voicetest.models.results import Message, MetricResult, TestResult, TestRun
from voicetest.models.test_case import TestCase
from voicetest.storage.db import get_connection, init_schema
from voicetest.storage.repositories import (
    AgentRepository,
    RunRepository,
    TestCaseRepository,
)


@pytest.fixture
def db_conn(tmp_path, monkeypatch):
    """Create a fresh database connection with schema."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    conn = get_connection()
    init_schema(conn)
    yield conn
    conn.close()


@pytest.fixture
def agent_repo(db_conn):
    """Create agent repository."""
    return AgentRepository(db_conn)


@pytest.fixture
def test_case_repo(db_conn):
    """Create test case repository."""
    return TestCaseRepository(db_conn)


@pytest.fixture
def run_repo(db_conn):
    """Create run repository."""
    return RunRepository(db_conn)


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
                instructions="Say hello",
                transitions=[],
            )
        },
    )


@pytest.fixture
def sample_test_case():
    """Create a sample test case."""
    return TestCase(
        name="Basic Test",
        user_prompt="Say hello to me",
        metrics=["Greets user politely"],
        dynamic_variables={"name": "Alice"},
        tool_mocks=[],
        type="simulation",
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
                duration_ms=1500,
                end_reason="completed",
                transcript=[
                    Message(role="assistant", content="Hello"),
                    Message(role="user", content="Hi"),
                ],
                metric_results=[
                    MetricResult(metric="Greeted user", passed=True, reasoning="Said hello"),
                ],
                nodes_visited=["greeting"],
            ),
        ],
    )


class TestAgentRepository:
    """Tests for agent repository CRUD operations."""

    def test_create_imported_agent(self, agent_repo, sample_graph):
        record = agent_repo.create(
            name="Test Agent",
            source_type="retell",
            graph_json=sample_graph.model_dump_json(),
        )

        assert record["id"] is not None
        assert record["name"] == "Test Agent"
        assert record["source_type"] == "retell"
        assert record["source_path"] is None
        assert record["graph_json"] is not None

    def test_create_linked_agent(self, agent_repo, tmp_path):
        agent_file = tmp_path / "agent.json"
        agent_file.write_text("{}")

        record = agent_repo.create(
            name="Linked Agent",
            source_type="custom",
            source_path=str(agent_file),
        )

        assert record["id"] is not None
        assert record["source_path"] == str(agent_file)
        assert record["graph_json"] is None

    def test_list_all(self, agent_repo, sample_graph):
        agent_repo.create(name="Agent 1", source_type="retell", graph_json="{}")
        agent_repo.create(name="Agent 2", source_type="custom", graph_json="{}")

        agents = agent_repo.list_all()

        assert len(agents) == 2
        names = [a["name"] for a in agents]
        assert "Agent 1" in names
        assert "Agent 2" in names

    def test_get_existing(self, agent_repo, sample_graph):
        record = agent_repo.create(
            name="Find Me",
            source_type="retell",
            graph_json=sample_graph.model_dump_json(),
        )

        found = agent_repo.get(record["id"])

        assert found is not None
        assert found["name"] == "Find Me"

    def test_get_nonexistent(self, agent_repo):
        found = agent_repo.get("nonexistent-id")
        assert found is None

    def test_update(self, agent_repo, sample_graph):
        record = agent_repo.create(
            name="Original",
            source_type="retell",
            graph_json=sample_graph.model_dump_json(),
        )

        updated = agent_repo.update(record["id"], name="Updated Name")

        assert updated["name"] == "Updated Name"
        assert updated["updated_at"] is not None

    def test_delete(self, agent_repo, sample_graph):
        record = agent_repo.create(
            name="To Delete",
            source_type="retell",
            graph_json=sample_graph.model_dump_json(),
        )

        agent_repo.delete(record["id"])

        assert agent_repo.get(record["id"]) is None

    def test_load_graph_imported(self, agent_repo, sample_graph):
        record = agent_repo.create(
            name="Imported",
            source_type="retell",
            graph_json=sample_graph.model_dump_json(),
        )

        graph = agent_repo.load_graph(record)

        assert graph is not None
        assert graph.source_type == "test"
        assert graph.entry_node_id == "greeting"

    def test_load_graph_linked(self, agent_repo, sample_graph, tmp_path):
        agent_file = tmp_path / "agent.json"
        agent_file.write_text(sample_graph.model_dump_json())

        record = agent_repo.create(
            name="Linked",
            source_type="custom",
            source_path=str(agent_file),
        )

        graph = agent_repo.load_graph(record)

        assert graph is not None
        assert graph.source_type == "test"

    def test_load_graph_missing_file(self, agent_repo, tmp_path):
        missing_file = tmp_path / "missing.json"

        record = agent_repo.create(
            name="Bad Link",
            source_type="custom",
            source_path=str(missing_file),
        )

        with pytest.raises(FileNotFoundError):
            agent_repo.load_graph(record)

    def test_create_agent_with_metrics_config(self, agent_repo):
        from voicetest.models.agent import GlobalMetric, MetricsConfig

        metrics_config = MetricsConfig(
            threshold=0.8,
            global_metrics=[
                GlobalMetric(name="HIPAA", criteria="Check HIPAA compliance"),
            ],
        )

        record = agent_repo.create(
            name="Agent with metrics",
            source_type="test",
            graph_json="{}",
            metrics_config=metrics_config,
        )

        assert record["metrics_config"] is not None
        loaded = MetricsConfig.model_validate_json(record["metrics_config"])
        assert loaded.threshold == 0.8
        assert len(loaded.global_metrics) == 1
        assert loaded.global_metrics[0].name == "HIPAA"

    def test_update_metrics_config(self, agent_repo):
        from voicetest.models.agent import GlobalMetric, MetricsConfig

        record = agent_repo.create(
            name="Agent",
            source_type="test",
            graph_json="{}",
        )

        assert record["metrics_config"] is None

        new_config = MetricsConfig(
            threshold=0.9,
            global_metrics=[
                GlobalMetric(name="PCI", criteria="Check PCI compliance"),
            ],
        )

        updated = agent_repo.update_metrics_config(record["id"], new_config)

        assert updated["metrics_config"] is not None
        loaded = MetricsConfig.model_validate_json(updated["metrics_config"])
        assert loaded.threshold == 0.9
        assert loaded.global_metrics[0].name == "PCI"

    def test_get_metrics_config(self, agent_repo):
        from voicetest.models.agent import GlobalMetric, MetricsConfig

        metrics_config = MetricsConfig(
            threshold=0.75,
            global_metrics=[
                GlobalMetric(name="Test", criteria="Test criteria"),
            ],
        )

        record = agent_repo.create(
            name="Agent",
            source_type="test",
            graph_json="{}",
            metrics_config=metrics_config,
        )

        loaded = agent_repo.get_metrics_config(record["id"])
        assert loaded is not None
        assert loaded.threshold == 0.75
        assert len(loaded.global_metrics) == 1

    def test_get_metrics_config_default(self, agent_repo):
        record = agent_repo.create(
            name="Agent",
            source_type="test",
            graph_json="{}",
        )

        loaded = agent_repo.get_metrics_config(record["id"])
        assert loaded is not None
        assert loaded.threshold == 0.7
        assert loaded.global_metrics == []


class TestTestCaseRepository:
    """Tests for test case repository CRUD operations."""

    def test_create(self, test_case_repo, agent_repo, sample_test_case, sample_graph):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")

        record = test_case_repo.create(agent["id"], sample_test_case)

        assert record["id"] is not None
        assert record["agent_id"] == agent["id"]
        assert record["name"] == "Basic Test"
        assert record["user_prompt"] == "Say hello to me"

    def test_list_for_agent(self, test_case_repo, agent_repo, sample_test_case):
        agent1 = agent_repo.create(name="Agent 1", source_type="test", graph_json="{}")
        agent2 = agent_repo.create(name="Agent 2", source_type="test", graph_json="{}")

        test_case_repo.create(agent1["id"], sample_test_case)
        test_case_repo.create(agent1["id"], TestCase(name="Test 2", user_prompt="Hi"))
        test_case_repo.create(agent2["id"], TestCase(name="Other", user_prompt="Bye"))

        tests = test_case_repo.list_for_agent(agent1["id"])

        assert len(tests) == 2
        names = [t["name"] for t in tests]
        assert "Basic Test" in names
        assert "Test 2" in names
        assert "Other" not in names

    def test_get(self, test_case_repo, agent_repo, sample_test_case):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        record = test_case_repo.create(agent["id"], sample_test_case)

        found = test_case_repo.get(record["id"])

        assert found is not None
        assert found["name"] == "Basic Test"

    def test_update(self, test_case_repo, agent_repo, sample_test_case):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        record = test_case_repo.create(agent["id"], sample_test_case)

        updated_case = TestCase(
            name="Updated Test",
            user_prompt="New prompt",
            metrics=["New metric"],
        )
        updated = test_case_repo.update(record["id"], updated_case)

        assert updated["name"] == "Updated Test"
        assert updated["user_prompt"] == "New prompt"

    def test_delete(self, test_case_repo, agent_repo, sample_test_case):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        record = test_case_repo.create(agent["id"], sample_test_case)

        test_case_repo.delete(record["id"])

        assert test_case_repo.get(record["id"]) is None

    def test_to_model(self, test_case_repo, agent_repo, sample_test_case):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        record = test_case_repo.create(agent["id"], sample_test_case)

        model = test_case_repo.to_model(record)

        assert isinstance(model, TestCase)
        assert model.name == "Basic Test"
        assert model.user_prompt == "Say hello to me"
        assert model.metrics == ["Greets user politely"]
        assert model.dynamic_variables == {"name": "Alice"}


class TestRunRepository:
    """Tests for run repository CRUD operations."""

    def test_create(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")

        record = run_repo.create(agent["id"])

        assert record["id"] is not None
        assert record["agent_id"] == agent["id"]
        assert record["started_at"] is not None
        assert record["completed_at"] is None

    def test_list_all(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")

        run_repo.create(agent["id"])
        run_repo.create(agent["id"])

        runs = run_repo.list_all()

        assert len(runs) == 2

    def test_get_with_results(self, run_repo, agent_repo, sample_run):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])

        for result in sample_run.results:
            run_repo.add_result(run_record["id"], "test-case-1", result)
        run_repo.complete(run_record["id"])

        run = run_repo.get_with_results(run_record["id"])

        assert run is not None
        assert run["completed_at"] is not None
        assert len(run["results"]) == 1
        assert run["results"][0]["status"] == "pass"

    def test_add_result(self, run_repo, agent_repo, sample_run):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])
        result = sample_run.results[0]

        run_repo.add_result(run_record["id"], "tc-1", result)

        run = run_repo.get_with_results(run_record["id"])
        assert len(run["results"]) == 1
        assert run["results"][0]["test_name"] == "Test One"

    def test_complete(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])

        run_repo.complete(run_record["id"])

        run = run_repo.get_with_results(run_record["id"])
        assert run["completed_at"] is not None

    def test_list_for_agent(self, run_repo, agent_repo):
        agent1 = agent_repo.create(name="Agent 1", source_type="test", graph_json="{}")
        agent2 = agent_repo.create(name="Agent 2", source_type="test", graph_json="{}")

        run_repo.create(agent1["id"])
        run_repo.create(agent1["id"])
        run_repo.create(agent2["id"])

        runs = run_repo.list_for_agent(agent1["id"])

        assert len(runs) == 2

    def test_delete(self, run_repo, agent_repo, sample_run):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])

        for result in sample_run.results:
            run_repo.add_result(run_record["id"], "test-case-1", result)
        run_repo.complete(run_record["id"])

        run = run_repo.get_with_results(run_record["id"])
        assert run is not None
        assert len(run["results"]) == 1

        run_repo.delete(run_record["id"])

        deleted_run = run_repo.get_with_results(run_record["id"])
        assert deleted_run is None

        runs = run_repo.list_all()
        assert len(runs) == 0
