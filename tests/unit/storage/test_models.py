"""Tests for SQLAlchemy ORM models."""

from datetime import UTC
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from voicetest.storage.models import Agent
from voicetest.storage.models import Base
from voicetest.storage.models import Result
from voicetest.storage.models import Run
from voicetest.storage.models import TestCase


@pytest.fixture
def engine():
    """Create an in-memory SQLite engine for testing."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


@pytest.fixture
def session(engine):
    """Create a session for testing."""
    with Session(engine) as session:
        yield session


class TestAgentModel:
    """Tests for Agent SQLAlchemy model."""

    def test_create_agent_minimal(self, session):
        agent = Agent(
            id="agent-1",
            name="Test Agent",
            source_type="retell",
        )
        session.add(agent)
        session.commit()

        loaded = session.get(Agent, "agent-1")
        assert loaded is not None
        assert loaded.name == "Test Agent"
        assert loaded.source_type == "retell"
        assert loaded.source_path is None
        assert loaded.graph_json is None
        assert loaded.metrics_config is None

    def test_create_agent_with_all_fields(self, session):
        metrics = {"threshold": 0.8, "global_metrics": []}
        agent = Agent(
            id="agent-2",
            name="Full Agent",
            source_type="custom",
            source_path="/path/to/agent.json",
            graph_json='{"nodes": {}}',
            metrics_config=metrics,
        )
        session.add(agent)
        session.commit()

        loaded = session.get(Agent, "agent-2")
        assert loaded.source_path == "/path/to/agent.json"
        assert loaded.graph_json == '{"nodes": {}}'
        assert loaded.metrics_config == metrics

    def test_agent_timestamps_auto_set(self, session):
        agent = Agent(
            id="agent-3",
            name="Timestamped Agent",
            source_type="test",
        )
        session.add(agent)
        session.commit()

        loaded = session.get(Agent, "agent-3")
        assert loaded.created_at is not None
        assert loaded.updated_at is not None

    def test_agent_to_dict(self, session):
        agent = Agent(
            id="agent-4",
            name="Dict Agent",
            source_type="retell",
            graph_json='{"test": true}',
        )
        session.add(agent)
        session.commit()

        loaded = session.get(Agent, "agent-4")
        d = loaded.to_dict()

        assert d["id"] == "agent-4"
        assert d["name"] == "Dict Agent"
        assert d["source_type"] == "retell"
        assert d["graph_json"] == '{"test": true}'
        assert "created_at" in d
        assert "updated_at" in d


class TestTestCaseModel:
    """Tests for TestCase SQLAlchemy model."""

    def test_create_test_case_minimal(self, session):
        agent = Agent(id="agent-tc", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        tc = TestCase(
            id="tc-1",
            agent_id="agent-tc",
            name="Basic Test",
            user_prompt="Say hello",
        )
        session.add(tc)
        session.commit()

        loaded = session.get(TestCase, "tc-1")
        assert loaded.name == "Basic Test"
        assert loaded.user_prompt == "Say hello"
        assert loaded.type == "llm"

    def test_create_test_case_with_json_fields(self, session):
        agent = Agent(id="agent-tc2", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        tc = TestCase(
            id="tc-2",
            agent_id="agent-tc2",
            name="Complex Test",
            user_prompt="Test prompt",
            metrics=["metric1", "metric2"],
            dynamic_variables={"name": "Alice", "age": 30},
            tool_mocks=[{"tool": "search", "response": "result"}],
            includes=["include1"],
            excludes=["exclude1"],
            patterns=["pattern1"],
        )
        session.add(tc)
        session.commit()

        loaded = session.get(TestCase, "tc-2")
        assert loaded.metrics == ["metric1", "metric2"]
        assert loaded.dynamic_variables == {"name": "Alice", "age": 30}
        assert loaded.tool_mocks == [{"tool": "search", "response": "result"}]
        assert loaded.includes == ["include1"]
        assert loaded.excludes == ["exclude1"]
        assert loaded.patterns == ["pattern1"]

    def test_test_case_agent_relationship(self, session):
        agent = Agent(id="agent-rel", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        tc = TestCase(
            id="tc-rel",
            agent_id="agent-rel",
            name="Rel Test",
            user_prompt="Test",
        )
        session.add(tc)
        session.commit()

        loaded = session.get(TestCase, "tc-rel")
        assert loaded.agent is not None
        assert loaded.agent.name == "Agent"

    def test_test_case_to_dict(self, session):
        agent = Agent(id="agent-dict", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        tc = TestCase(
            id="tc-dict",
            agent_id="agent-dict",
            name="Dict Test",
            user_prompt="Prompt",
            metrics=["m1"],
        )
        session.add(tc)
        session.commit()

        loaded = session.get(TestCase, "tc-dict")
        d = loaded.to_dict()

        assert d["id"] == "tc-dict"
        assert d["agent_id"] == "agent-dict"
        assert d["name"] == "Dict Test"
        assert d["metrics"] == ["m1"]


class TestRunModel:
    """Tests for Run SQLAlchemy model."""

    def test_create_run(self, session):
        agent = Agent(id="agent-run", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        run = Run(
            id="run-1",
            agent_id="agent-run",
        )
        session.add(run)
        session.commit()

        loaded = session.get(Run, "run-1")
        assert loaded.agent_id == "agent-run"
        assert loaded.started_at is not None
        assert loaded.completed_at is None

    def test_run_completion(self, session):
        agent = Agent(id="agent-run2", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        run = Run(id="run-2", agent_id="agent-run2")
        session.add(run)
        session.commit()

        run.completed_at = datetime.now(UTC)
        session.commit()

        loaded = session.get(Run, "run-2")
        assert loaded.completed_at is not None

    def test_run_agent_relationship(self, session):
        agent = Agent(id="agent-run-rel", name="Run Agent", source_type="test")
        session.add(agent)
        session.commit()

        run = Run(id="run-rel", agent_id="agent-run-rel")
        session.add(run)
        session.commit()

        loaded = session.get(Run, "run-rel")
        assert loaded.agent.name == "Run Agent"


class TestResultModel:
    """Tests for Result SQLAlchemy model."""

    def test_create_result_minimal(self, session):
        agent = Agent(id="agent-res", name="Agent", source_type="test")
        session.add(agent)
        run = Run(id="run-res", agent_id="agent-res")
        session.add(run)
        session.commit()

        result = Result(
            id="result-1",
            run_id="run-res",
            test_case_id="tc-1",
        )
        session.add(result)
        session.commit()

        loaded = session.get(Result, "result-1")
        assert loaded.run_id == "run-res"
        assert loaded.test_case_id == "tc-1"

    def test_create_result_with_all_fields(self, session):
        agent = Agent(id="agent-res2", name="Agent", source_type="test")
        session.add(agent)
        run = Run(id="run-res2", agent_id="agent-res2")
        session.add(run)
        session.commit()

        transcript = [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "Hi"},
        ]
        metrics = [{"metric": "greeting", "passed": True, "reasoning": "Said hello"}]
        models_used = {"judge": "gpt-4", "agent": "gpt-3.5-turbo"}

        result = Result(
            id="result-2",
            run_id="run-res2",
            test_case_id="tc-2",
            test_name="Test Name",
            status="pass",
            duration_ms=1500,
            turn_count=2,
            end_reason="completed",
            transcript_json=transcript,
            metrics_json=metrics,
            nodes_visited=["greeting", "farewell"],
            tools_called=[{"name": "search", "args": {}}],
            models_used=models_used,
        )
        session.add(result)
        session.commit()

        loaded = session.get(Result, "result-2")
        assert loaded.test_name == "Test Name"
        assert loaded.status == "pass"
        assert loaded.duration_ms == 1500
        assert loaded.turn_count == 2
        assert loaded.end_reason == "completed"
        assert loaded.transcript_json == transcript
        assert loaded.metrics_json == metrics
        assert loaded.nodes_visited == ["greeting", "farewell"]
        assert loaded.tools_called == [{"name": "search", "args": {}}]
        assert loaded.models_used == models_used

    def test_result_run_relationship(self, session):
        agent = Agent(id="agent-res-rel", name="Agent", source_type="test")
        session.add(agent)
        run = Run(id="run-res-rel", agent_id="agent-res-rel")
        session.add(run)
        session.commit()

        result = Result(
            id="result-rel",
            run_id="run-res-rel",
            test_case_id="tc-rel",
        )
        session.add(result)
        session.commit()

        loaded = session.get(Result, "result-rel")
        assert loaded.run is not None
        assert loaded.run.id == "run-res-rel"

    def test_run_results_cascade_delete(self, session):
        agent = Agent(id="agent-cascade", name="Agent", source_type="test")
        session.add(agent)
        run = Run(id="run-cascade", agent_id="agent-cascade")
        session.add(run)
        session.commit()

        result1 = Result(id="res-c1", run_id="run-cascade", test_case_id="tc-1")
        result2 = Result(id="res-c2", run_id="run-cascade", test_case_id="tc-2")
        session.add_all([result1, result2])
        session.commit()

        assert len(session.get(Run, "run-cascade").results) == 2

        session.delete(session.get(Run, "run-cascade"))
        session.commit()

        assert session.get(Result, "res-c1") is None
        assert session.get(Result, "res-c2") is None

    def test_result_to_dict(self, session):
        agent = Agent(id="agent-res-dict", name="Agent", source_type="test")
        session.add(agent)
        run = Run(id="run-res-dict", agent_id="agent-res-dict")
        session.add(run)
        session.commit()

        result = Result(
            id="result-dict",
            run_id="run-res-dict",
            test_case_id="tc-dict",
            test_name="Dict Test",
            status="pass",
            transcript_json=[{"role": "user", "content": "Hi"}],
        )
        session.add(result)
        session.commit()

        loaded = session.get(Result, "result-dict")
        d = loaded.to_dict()

        assert d["id"] == "result-dict"
        assert d["run_id"] == "run-res-dict"
        assert d["test_case_id"] == "tc-dict"
        assert d["test_name"] == "Dict Test"
        assert d["status"] == "pass"
        assert d["transcript_json"] == [{"role": "user", "content": "Hi"}]


class TestAgentTestCasesRelationship:
    """Tests for Agent to TestCases relationship."""

    def test_agent_has_test_cases(self, session):
        agent = Agent(id="agent-tcs", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        tc1 = TestCase(id="tc-a1", agent_id="agent-tcs", name="Test 1", user_prompt="P1")
        tc2 = TestCase(id="tc-a2", agent_id="agent-tcs", name="Test 2", user_prompt="P2")
        session.add_all([tc1, tc2])
        session.commit()

        loaded = session.get(Agent, "agent-tcs")
        assert len(loaded.test_cases) == 2
        names = [tc.name for tc in loaded.test_cases]
        assert "Test 1" in names
        assert "Test 2" in names


class TestAgentRunsRelationship:
    """Tests for Agent to Runs relationship."""

    def test_agent_has_runs(self, session):
        agent = Agent(id="agent-runs", name="Agent", source_type="test")
        session.add(agent)
        session.commit()

        run1 = Run(id="run-a1", agent_id="agent-runs")
        run2 = Run(id="run-a2", agent_id="agent-runs")
        session.add_all([run1, run2])
        session.commit()

        loaded = session.get(Agent, "agent-runs")
        assert len(loaded.runs) == 2
