"""Repository classes for CRUD operations on each entity."""

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import duckdb

from voicetest.models.agent import AgentGraph, MetricsConfig
from voicetest.models.results import TestResult
from voicetest.models.test_case import TestCase


def _serialize_value(value):
    """Convert datetime objects to ISO strings for JSON serialization."""
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _result_to_dicts(result) -> list[dict]:
    """Convert DuckDB result to list of dicts with JSON-safe values."""
    columns = [desc[0] for desc in result.description]
    return [
        {col: _serialize_value(val) for col, val in zip(columns, row, strict=True)}
        for row in result.fetchall()
    ]


class AgentRepository:
    """CRUD operations for agents."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def list_all(self) -> list[dict]:
        """List all agents."""
        result = self.conn.execute(
            "SELECT id, name, source_type, source_path, graph_json, metrics_config, "
            "created_at, updated_at FROM agents ORDER BY created_at DESC"
        )
        return self._to_dicts(result)

    def get(self, agent_id: str) -> dict | None:
        """Get agent by ID."""
        result = self.conn.execute(
            "SELECT id, name, source_type, source_path, graph_json, metrics_config, "
            "created_at, updated_at FROM agents WHERE id = ?",
            [agent_id],
        )
        rows = self._to_dicts(result)
        return rows[0] if rows else None

    def create(
        self,
        name: str,
        source_type: str,
        source_path: str | None = None,
        graph_json: str | None = None,
        metrics_config: MetricsConfig | None = None,
    ) -> dict:
        """Create a new agent."""
        agent_id = str(uuid4())
        now = datetime.now(UTC)
        metrics_json = metrics_config.model_dump_json() if metrics_config else None

        self.conn.execute(
            "INSERT INTO agents (id, name, source_type, source_path, graph_json, "
            "metrics_config, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [agent_id, name, source_type, source_path, graph_json, metrics_json, now, now],
        )

        return self.get(agent_id)

    def update(
        self,
        agent_id: str,
        name: str | None = None,
        source_path: str | None = None,
        graph_json: str | None = None,
    ) -> dict | None:
        """Update an agent."""
        updates = []
        params = []

        if name is not None:
            updates.append("name = ?")
            params.append(name)
        if source_path is not None:
            updates.append("source_path = ?")
            params.append(source_path)
        if graph_json is not None:
            updates.append("graph_json = ?")
            params.append(graph_json)

        if not updates:
            return self.get(agent_id)

        updates.append("updated_at = ?")
        params.append(datetime.now(UTC))
        params.append(agent_id)

        self.conn.execute(
            f"UPDATE agents SET {', '.join(updates)} WHERE id = ?",
            params,
        )

        return self.get(agent_id)

    def update_metrics_config(
        self,
        agent_id: str,
        metrics_config: MetricsConfig,
    ) -> dict | None:
        """Update an agent's metrics configuration."""
        now = datetime.now(UTC)
        metrics_json = metrics_config.model_dump_json()

        self.conn.execute(
            "UPDATE agents SET metrics_config = ?, updated_at = ? WHERE id = ?",
            [metrics_json, now, agent_id],
        )

        return self.get(agent_id)

    def get_metrics_config(self, agent_id: str) -> MetricsConfig:
        """Get an agent's metrics configuration.

        Returns the stored configuration or a default if none exists.
        """
        agent = self.get(agent_id)
        if not agent:
            return MetricsConfig()

        if agent.get("metrics_config"):
            return MetricsConfig.model_validate_json(agent["metrics_config"])

        return MetricsConfig()

    def delete(self, agent_id: str) -> None:
        """Delete an agent."""
        self.conn.execute("DELETE FROM agents WHERE id = ?", [agent_id])

    def load_graph(self, agent: dict) -> AgentGraph:
        """Load the AgentGraph for an agent.

        For linked agents (source_path set), reads from disk.
        For imported agents (graph_json set), parses the stored JSON.
        """
        if agent.get("source_path"):
            path = Path(agent["source_path"])
            if not path.exists():
                raise FileNotFoundError(f"Agent file not found: {path}")
            return AgentGraph.model_validate_json(path.read_text())

        if agent.get("graph_json"):
            return AgentGraph.model_validate_json(agent["graph_json"])

        raise ValueError(f"Agent {agent['id']} has neither source_path nor graph_json")

    def _to_dicts(self, result) -> list[dict]:
        """Convert DuckDB result to list of dicts with JSON-safe values."""
        return _result_to_dicts(result)


class TestCaseRepository:
    """CRUD operations for test cases."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def list_for_agent(self, agent_id: str) -> list[dict]:
        """List all test cases for an agent."""
        result = self.conn.execute(
            "SELECT id, agent_id, name, user_prompt, metrics, dynamic_variables, "
            "tool_mocks, type, llm_model, includes, excludes, patterns, "
            "created_at, updated_at "
            "FROM test_cases WHERE agent_id = ? ORDER BY created_at",
            [agent_id],
        )
        return self._to_dicts(result)

    def get(self, test_id: str) -> dict | None:
        """Get test case by ID."""
        result = self.conn.execute(
            "SELECT id, agent_id, name, user_prompt, metrics, dynamic_variables, "
            "tool_mocks, type, llm_model, includes, excludes, patterns, "
            "created_at, updated_at "
            "FROM test_cases WHERE id = ?",
            [test_id],
        )
        rows = self._to_dicts(result)
        return rows[0] if rows else None

    def create(self, agent_id: str, test_case: TestCase) -> dict:
        """Create a new test case."""
        test_id = str(uuid4())
        now = datetime.now(UTC)

        self.conn.execute(
            "INSERT INTO test_cases (id, agent_id, name, user_prompt, metrics, "
            "dynamic_variables, tool_mocks, type, llm_model, includes, excludes, "
            "patterns, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                test_id,
                agent_id,
                test_case.name,
                test_case.user_prompt,
                json.dumps(test_case.metrics),
                json.dumps(test_case.dynamic_variables),
                json.dumps(test_case.tool_mocks),
                test_case.type,
                test_case.llm_model,
                json.dumps(test_case.includes),
                json.dumps(test_case.excludes),
                json.dumps(test_case.patterns),
                now,
                now,
            ],
        )

        return self.get(test_id)

    def update(self, test_id: str, test_case: TestCase) -> dict | None:
        """Update a test case."""
        now = datetime.now(UTC)

        self.conn.execute(
            "UPDATE test_cases SET name = ?, user_prompt = ?, metrics = ?, "
            "dynamic_variables = ?, tool_mocks = ?, type = ?, llm_model = ?, "
            "includes = ?, excludes = ?, patterns = ?, updated_at = ? WHERE id = ?",
            [
                test_case.name,
                test_case.user_prompt,
                json.dumps(test_case.metrics),
                json.dumps(test_case.dynamic_variables),
                json.dumps(test_case.tool_mocks),
                test_case.type,
                test_case.llm_model,
                json.dumps(test_case.includes),
                json.dumps(test_case.excludes),
                json.dumps(test_case.patterns),
                now,
                test_id,
            ],
        )

        return self.get(test_id)

    def delete(self, test_id: str) -> None:
        """Delete a test case."""
        self.conn.execute("DELETE FROM test_cases WHERE id = ?", [test_id])

    def to_model(self, record: dict) -> TestCase:
        """Convert a database record to a TestCase model."""
        return TestCase(
            name=record["name"],
            user_prompt=record["user_prompt"],
            metrics=json.loads(record["metrics"]) if record["metrics"] else [],
            dynamic_variables=(
                json.loads(record["dynamic_variables"]) if record["dynamic_variables"] else {}
            ),
            tool_mocks=json.loads(record["tool_mocks"]) if record["tool_mocks"] else [],
            type=record["type"] or "llm",
            llm_model=record["llm_model"],
            includes=json.loads(record["includes"]) if record.get("includes") else [],
            excludes=json.loads(record["excludes"]) if record.get("excludes") else [],
            patterns=json.loads(record["patterns"]) if record.get("patterns") else [],
        )

    def _to_dicts(self, result) -> list[dict]:
        """Convert DuckDB result to list of dicts with JSON-safe values."""
        return _result_to_dicts(result)


class RunRepository:
    """CRUD operations for runs and results."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self.conn = conn

    def list_all(self, limit: int = 50) -> list[dict]:
        """List all runs."""
        result = self.conn.execute(
            "SELECT id, agent_id, started_at, completed_at "
            "FROM runs ORDER BY started_at DESC LIMIT ?",
            [limit],
        )
        return self._to_dicts(result)

    def list_for_agent(self, agent_id: str, limit: int = 50) -> list[dict]:
        """List runs for a specific agent."""
        result = self.conn.execute(
            "SELECT id, agent_id, started_at, completed_at "
            "FROM runs WHERE agent_id = ? ORDER BY started_at DESC LIMIT ?",
            [agent_id, limit],
        )
        return self._to_dicts(result)

    def get_with_results(self, run_id: str) -> dict | None:
        """Get a run with all its results."""
        run_result = self.conn.execute(
            "SELECT id, agent_id, started_at, completed_at " "FROM runs WHERE id = ?",
            [run_id],
        )
        runs = self._to_dicts(run_result)
        if not runs:
            return None

        run = runs[0]

        results_result = self.conn.execute(
            "SELECT id, run_id, test_case_id, test_name, status, duration_ms, turn_count, "
            "end_reason, error_message, transcript_json, metrics_json, "
            "nodes_visited, tools_called, models_used, created_at "
            "FROM results WHERE run_id = ? ORDER BY created_at",
            [run_id],
        )
        run["results"] = self._to_dicts(results_result)

        return run

    def create(self, agent_id: str) -> dict:
        """Create a new run."""
        run_id = str(uuid4())
        now = datetime.now(UTC)

        self.conn.execute(
            "INSERT INTO runs (id, agent_id, started_at) VALUES (?, ?, ?)",
            [run_id, agent_id, now],
        )

        return {"id": run_id, "agent_id": agent_id, "started_at": now, "completed_at": None}

    def add_result(self, run_id: str, test_case_id: str, result: TestResult) -> None:
        """Add a result to a run."""
        result_id = str(uuid4())
        now = datetime.now(UTC)

        transcript_json = json.dumps([m.model_dump() for m in result.transcript])
        metrics_json = (
            json.dumps([m.model_dump() for m in result.metric_results])
            if result.metric_results
            else None
        )
        nodes_json = json.dumps(result.nodes_visited) if result.nodes_visited else None
        tools_json = (
            json.dumps([t.model_dump() for t in result.tools_called])
            if result.tools_called
            else None
        )
        models_json = result.models_used.model_dump_json() if result.models_used else None

        self.conn.execute(
            "INSERT INTO results (id, run_id, test_case_id, test_name, status, duration_ms, "
            "turn_count, end_reason, error_message, transcript_json, metrics_json, "
            "nodes_visited, tools_called, models_used, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                result_id,
                run_id,
                test_case_id,
                result.test_name,
                result.status,
                result.duration_ms,
                result.turn_count,
                result.end_reason,
                result.error_message,
                transcript_json,
                metrics_json,
                nodes_json,
                tools_json,
                models_json,
                now,
            ],
        )

    def create_pending_result(self, run_id: str, test_case_id: str, test_name: str) -> str:
        """Create a pending result for an in-progress test."""
        result_id = str(uuid4())
        now = datetime.now(UTC)

        self.conn.execute(
            "INSERT INTO results (id, run_id, test_case_id, test_name, status, "
            "transcript_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [result_id, run_id, test_case_id, test_name, "running", "[]", now],
        )
        return result_id

    def update_transcript(self, result_id: str, transcript: list) -> None:
        """Update the transcript for an in-progress result."""
        transcript_json = json.dumps([m.model_dump() for m in transcript])
        self.conn.execute(
            "UPDATE results SET transcript_json = ? WHERE id = ?",
            [transcript_json, result_id],
        )

    def mark_result_error(self, result_id: str, error_message: str) -> None:
        """Mark a result as error with a message."""
        self.conn.execute(
            "UPDATE results SET status = ?, error_message = ? WHERE id = ?",
            ["error", error_message, result_id],
        )

    def mark_result_cancelled(self, result_id: str) -> None:
        """Mark a result as cancelled before it started."""
        self.conn.execute(
            "UPDATE results SET status = ?, error_message = ? WHERE id = ?",
            ["cancelled", "Cancelled before starting", result_id],
        )

    def complete_result(self, result_id: str, result: "TestResult") -> None:
        """Update a pending result with final data."""
        transcript_json = json.dumps([m.model_dump() for m in result.transcript])
        metrics_json = (
            json.dumps([m.model_dump() for m in result.metric_results])
            if result.metric_results
            else None
        )
        nodes_json = json.dumps(result.nodes_visited) if result.nodes_visited else None
        tools_json = (
            json.dumps([t.model_dump() for t in result.tools_called])
            if result.tools_called
            else None
        )
        models_json = result.models_used.model_dump_json() if result.models_used else None

        self.conn.execute(
            "UPDATE results SET status = ?, duration_ms = ?, turn_count = ?, "
            "end_reason = ?, error_message = ?, transcript_json = ?, metrics_json = ?, "
            "nodes_visited = ?, tools_called = ?, models_used = ? WHERE id = ?",
            [
                result.status,
                result.duration_ms,
                result.turn_count,
                result.end_reason,
                result.error_message,
                transcript_json,
                metrics_json,
                nodes_json,
                tools_json,
                models_json,
                result_id,
            ],
        )

    def complete(self, run_id: str) -> None:
        """Mark a run as completed."""
        now = datetime.now(UTC)
        self.conn.execute(
            "UPDATE runs SET completed_at = ? WHERE id = ?",
            [now, run_id],
        )

    def delete(self, run_id: str) -> None:
        """Delete a run and all its results."""
        self.conn.execute("DELETE FROM results WHERE run_id = ?", [run_id])
        self.conn.execute("DELETE FROM runs WHERE id = ?", [run_id])

    def _to_dicts(self, result) -> list[dict]:
        """Convert DuckDB result to list of dicts with JSON-safe values."""
        return _result_to_dicts(result)
