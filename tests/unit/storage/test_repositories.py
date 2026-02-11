"""Tests for repository classes."""

from datetime import UTC
from datetime import datetime
import json
from uuid import NAMESPACE_URL
from uuid import uuid5

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import AgentNode
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import TestResult
from voicetest.models.results import TestRun
from voicetest.models.test_case import TestCase
from voicetest.storage.models import Base
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository


@pytest.fixture
def engine(tmp_path):
    """Create a fresh database engine with schema."""
    db_path = tmp_path / "test.duckdb"
    engine = create_engine(f"duckdb:///{db_path}")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a session for testing."""
    with Session(engine) as session:
        yield session


@pytest.fixture
def agent_repo(session):
    """Create agent repository."""
    return AgentRepository(session)


@pytest.fixture
def test_case_repo(session):
    """Create test case repository."""
    return TestCaseRepository(session)


@pytest.fixture
def run_repo(session):
    """Create run repository."""
    return RunRepository(session)


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

    def test_load_graph_linked_returns_path(self, agent_repo, sample_graph, tmp_path):
        """Linked files always return Path for import via registry."""
        from pathlib import Path

        agent_file = tmp_path / "agent.json"
        agent_file.write_text(sample_graph.model_dump_json())

        record = agent_repo.create(
            name="Linked",
            source_type="agentgraph",
            source_path=str(agent_file),
        )

        result = agent_repo.load_graph(record)

        assert isinstance(result, Path)
        assert result == agent_file

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
        from voicetest.models.agent import GlobalMetric
        from voicetest.models.agent import MetricsConfig

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
        from voicetest.models.agent import GlobalMetric
        from voicetest.models.agent import MetricsConfig

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
        from voicetest.models.agent import GlobalMetric
        from voicetest.models.agent import MetricsConfig

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

    def test_create_pending_result(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])

        result_id = run_repo.create_pending_result(run_record["id"], "tc-1", "Pending Test")

        assert result_id is not None
        run = run_repo.get_with_results(run_record["id"])
        assert len(run["results"]) == 1
        assert run["results"][0]["status"] == "running"
        assert run["results"][0]["test_name"] == "Pending Test"
        assert run["results"][0]["transcript_json"] == []

    def test_update_transcript(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])
        result_id = run_repo.create_pending_result(run_record["id"], "tc-1", "Test")

        transcript = [
            Message(role="assistant", content="Hello"),
            Message(role="user", content="Hi there"),
        ]
        run_repo.update_transcript(result_id, transcript)

        run = run_repo.get_with_results(run_record["id"])
        assert len(run["results"][0]["transcript_json"]) == 2
        assert run["results"][0]["transcript_json"][0]["content"] == "Hello"

    def test_mark_result_error(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])
        result_id = run_repo.create_pending_result(run_record["id"], "tc-1", "Test")

        run_repo.mark_result_error(result_id, "Connection timeout")

        run = run_repo.get_with_results(run_record["id"])
        assert run["results"][0]["status"] == "error"
        assert run["results"][0]["error_message"] == "Connection timeout"

    def test_mark_result_cancelled(self, run_repo, agent_repo):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])
        result_id = run_repo.create_pending_result(run_record["id"], "tc-1", "Test")

        run_repo.mark_result_cancelled(result_id)

        run = run_repo.get_with_results(run_record["id"])
        assert run["results"][0]["status"] == "cancelled"
        assert run["results"][0]["error_message"] == "Cancelled before starting"

    def test_complete_result(self, run_repo, agent_repo, sample_run):
        agent = agent_repo.create(name="Agent", source_type="test", graph_json="{}")
        run_record = run_repo.create(agent["id"])
        result_id = run_repo.create_pending_result(run_record["id"], "tc-1", "Test")

        result = sample_run.results[0]
        run_repo.complete_result(result_id, result)

        run = run_repo.get_with_results(run_record["id"])
        assert run["results"][0]["status"] == "pass"
        assert run["results"][0]["duration_ms"] == 1500
        assert run["results"][0]["turn_count"] == 3
        assert len(run["results"][0]["transcript_json"]) == 2


class TestAgentRepositoryEdgeCases:
    """Edge case tests for AgentRepository."""

    def test_load_graph_no_source_raises(self, agent_repo):
        record = agent_repo.create(
            name="Empty Agent",
            source_type="test",
        )

        with pytest.raises(ValueError, match="has neither source_path nor graph_json"):
            agent_repo.load_graph(record)

    def test_get_metrics_config_nonexistent_agent(self, agent_repo):
        config = agent_repo.get_metrics_config("nonexistent-id")

        assert config is not None
        assert config.threshold == 0.7
        assert config.global_metrics == []

    def test_update_nonexistent_agent(self, agent_repo):
        result = agent_repo.update("nonexistent-id", name="New Name")
        assert result is None

    def test_update_metrics_config_nonexistent_agent(self, agent_repo):
        from voicetest.models.agent import MetricsConfig

        result = agent_repo.update_metrics_config("nonexistent-id", MetricsConfig())
        assert result is None


class TestTestCaseRepositoryEdgeCases:
    """Edge case tests for TestCaseRepository."""

    def test_get_nonexistent(self, test_case_repo):
        found = test_case_repo.get("nonexistent-id")
        assert found is None

    def test_update_nonexistent(self, test_case_repo, sample_test_case):
        result = test_case_repo.update("nonexistent-id", sample_test_case)
        assert result is None

    def test_delete_nonexistent(self, test_case_repo):
        test_case_repo.delete("nonexistent-id")


class TestLinkedTests:
    """Tests for file-based linked test case operations."""

    @pytest.fixture
    def tests_file(self, tmp_path):
        """Create a test file with sample test cases."""
        f = tmp_path / "tests.json"
        data = [
            {
                "name": "Greeting Test",
                "user_prompt": "Say hello",
                "metrics": ["Greets user"],
                "type": "llm",
            },
            {
                "name": "Billing Test",
                "user_prompt": "Ask about billing",
                "metrics": ["Provides billing info"],
                "type": "llm",
                "dynamic_variables": {"account": "12345"},
            },
        ]
        f.write_text(json.dumps(data, indent=2))
        return f

    @pytest.fixture
    def agent_with_tests(self, agent_repo, tests_file):
        """Create an agent linked to a test file."""
        return agent_repo.create(
            name="Linked Agent",
            source_type="linked",
            tests_paths=[str(tests_file)],
        )

    def test_list_for_agent_with_linked_merges_db_and_file(
        self, test_case_repo, agent_repo, agent_with_tests, tests_file
    ):
        db_test = TestCase(name="DB Test", user_prompt="from database")
        test_case_repo.create(agent_with_tests["id"], db_test)

        results = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )

        names = [t["name"] for t in results]
        assert "DB Test" in names
        assert "Greeting Test" in names
        assert "Billing Test" in names
        assert len(results) == 3

    def test_linked_tests_have_deterministic_ids(
        self, test_case_repo, agent_with_tests, tests_file
    ):
        results1 = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )
        results2 = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )

        ids1 = [t["id"] for t in results1]
        ids2 = [t["id"] for t in results2]
        assert ids1 == ids2

    def test_linked_tests_have_source_path_and_index(
        self, test_case_repo, agent_with_tests, tests_file
    ):
        results = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )

        linked = [t for t in results if t.get("source_path")]
        assert len(linked) == 2
        assert linked[0]["source_path"] == str(tests_file)
        assert linked[0]["source_index"] == 0
        assert linked[1]["source_index"] == 1

    def test_linked_tests_id_uses_uuid5(self, test_case_repo, agent_with_tests, tests_file):
        results = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )

        linked = [t for t in results if t.get("source_path")]
        expected_id = str(uuid5(NAMESPACE_URL, f"{tests_file}:Greeting Test"))
        assert linked[0]["id"] == expected_id

    def test_list_with_empty_tests_paths(self, test_case_repo, agent_repo):
        agent = agent_repo.create(name="No Links", source_type="test", graph_json="{}")
        db_test = TestCase(name="Only DB", user_prompt="hi")
        test_case_repo.create(agent["id"], db_test)

        results = test_case_repo.list_for_agent_with_linked(agent["id"], [])

        assert len(results) == 1
        assert results[0]["name"] == "Only DB"

    def test_list_with_none_tests_paths(self, test_case_repo, agent_repo):
        agent = agent_repo.create(name="No Links", source_type="test", graph_json="{}")

        results = test_case_repo.list_for_agent_with_linked(agent["id"], None)

        assert len(results) == 0

    def test_list_with_missing_file_skips(self, test_case_repo, agent_repo, tmp_path):
        agent = agent_repo.create(name="Bad Link", source_type="test", graph_json="{}")
        missing = str(tmp_path / "missing.json")

        results = test_case_repo.list_for_agent_with_linked(agent["id"], [missing])

        assert len(results) == 0

    def test_update_linked(self, test_case_repo, agent_with_tests, tests_file):
        results = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )
        linked = [t for t in results if t.get("source_path")]
        test_id = linked[0]["id"]

        updated_case = TestCase(
            name="Updated Greeting",
            user_prompt="Say hi differently",
            metrics=["Greets user warmly"],
        )
        updated = test_case_repo.update_linked(test_id, updated_case, str(tests_file), 0)

        assert updated["name"] == "Updated Greeting"
        assert updated["user_prompt"] == "Say hi differently"

        file_data = json.loads(tests_file.read_text())
        assert file_data[0]["name"] == "Updated Greeting"
        assert file_data[1]["name"] == "Billing Test"

    def test_delete_linked(self, test_case_repo, agent_with_tests, tests_file):
        results = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )
        linked = [t for t in results if t.get("source_path")]
        test_id = linked[0]["id"]

        test_case_repo.delete_linked(test_id, str(tests_file), 0)

        file_data = json.loads(tests_file.read_text())
        assert len(file_data) == 1
        assert file_data[0]["name"] == "Billing Test"

    def test_create_in_file(self, test_case_repo, agent_with_tests, tests_file):
        new_test = TestCase(
            name="Transfer Test",
            user_prompt="Transfer me to billing",
            metrics=["Transfers correctly"],
        )

        result = test_case_repo.create_in_file(str(tests_file), agent_with_tests["id"], new_test)

        assert result["name"] == "Transfer Test"
        assert result["source_path"] == str(tests_file)
        assert result["source_index"] == 2

        file_data = json.loads(tests_file.read_text())
        assert len(file_data) == 3
        assert file_data[2]["name"] == "Transfer Test"

    def test_linked_tests_include_all_fields(self, test_case_repo, agent_with_tests, tests_file):
        results = test_case_repo.list_for_agent_with_linked(
            agent_with_tests["id"], [str(tests_file)]
        )

        linked = [t for t in results if t.get("source_path")]
        billing = next(t for t in linked if t["name"] == "Billing Test")

        assert billing["dynamic_variables"] == {"account": "12345"}
        assert billing["type"] == "llm"
        assert billing["metrics"] == ["Provides billing info"]


class TestAgentRepositoryTestsPaths:
    """Tests for tests_paths field on Agent."""

    def test_create_with_tests_paths(self, agent_repo, tmp_path):
        tests_file = tmp_path / "tests.json"
        tests_file.write_text("[]")

        record = agent_repo.create(
            name="Agent",
            source_type="linked",
            tests_paths=[str(tests_file)],
        )

        assert record["tests_paths"] == [str(tests_file)]

    def test_create_without_tests_paths(self, agent_repo):
        record = agent_repo.create(
            name="Agent",
            source_type="test",
            graph_json="{}",
        )

        assert record["tests_paths"] is None

    def test_update_tests_paths(self, agent_repo, tmp_path):
        record = agent_repo.create(
            name="Agent",
            source_type="test",
            graph_json="{}",
        )

        tests_file = tmp_path / "tests.json"
        tests_file.write_text("[]")

        updated = agent_repo.update(record["id"], tests_paths=[str(tests_file)])

        assert updated["tests_paths"] == [str(tests_file)]


class TestRunRepositoryEdgeCases:
    """Edge case tests for RunRepository."""

    def test_get_with_results_nonexistent(self, run_repo):
        result = run_repo.get_with_results("nonexistent-id")
        assert result is None

    def test_complete_nonexistent(self, run_repo):
        run_repo.complete("nonexistent-id")

    def test_delete_nonexistent(self, run_repo):
        run_repo.delete("nonexistent-id")
