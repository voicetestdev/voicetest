"""Data persistence using DuckDB + Parquet.

Stores agents, test cases, and run results in parquet files.
All files live in a data/ directory (configurable).
"""

from datetime import UTC, datetime
import json
from pathlib import Path
from uuid import uuid4

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from voicetest.models.agent import AgentGraph
from voicetest.models.results import TestRun


DEFAULT_DATA_DIR = Path("data")


class DataStore:
    """Persistent storage for voicetest data using DuckDB + Parquet."""

    def __init__(self, data_dir: Path | None = None):
        self.data_dir = data_dir or DEFAULT_DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect()

    def _agents_path(self) -> Path:
        return self.data_dir / "agents.parquet"

    def _runs_path(self) -> Path:
        return self.data_dir / "runs.parquet"

    def _results_path(self) -> Path:
        return self.data_dir / "results.parquet"

    # Agents

    def save_agent(self, graph: AgentGraph, name: str | None = None) -> str:
        """Save an agent graph. Returns the agent ID."""
        agent_id = str(uuid4())
        name = name or f"agent-{agent_id[:8]}"

        record = {
            "id": agent_id,
            "name": name,
            "source_type": graph.source_type,
            "entry_node_id": graph.entry_node_id,
            "node_count": len(graph.nodes),
            "graph_json": graph.model_dump_json(),
            "created_at": datetime.now(UTC).isoformat(),
        }

        self._append_record(self._agents_path(), record)
        return agent_id

    def get_agent(self, agent_id: str) -> AgentGraph | None:
        """Get an agent by ID."""
        path = self._agents_path()
        if not path.exists():
            return None

        result = self._conn.execute(
            f"SELECT graph_json FROM '{path}' WHERE id = ?", [agent_id]
        ).fetchone()

        if result:
            return AgentGraph.model_validate_json(result[0])
        return None

    def list_agents(self) -> list[dict]:
        """List all saved agents (metadata only)."""
        path = self._agents_path()
        if not path.exists():
            return []

        result = self._conn.execute(
            f"SELECT id, name, source_type, node_count, created_at "
            f"FROM '{path}' ORDER BY created_at DESC"
        )
        return self._to_dicts(result)

    # Test Runs

    def save_run(self, run: TestRun, agent_id: str | None = None) -> str:
        """Save a test run. Returns the run ID."""
        run_record = {
            "id": run.run_id,
            "agent_id": agent_id,
            "total_tests": len(run.results),
            "passed": run.passed_count,
            "failed": run.failed_count,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        }
        self._append_record(self._runs_path(), run_record)

        # Save individual results
        for result in run.results:
            metrics_json = None
            if result.metric_results:
                metrics_json = json.dumps([m.model_dump() for m in result.metric_results])
            nodes_json = None
            if result.nodes_visited:
                nodes_json = json.dumps(result.nodes_visited)
            result_record = {
                "id": str(uuid4()),
                "run_id": run.run_id,
                "test_id": result.test_id,
                "test_name": result.test_name,
                "status": result.status,
                "turn_count": result.turn_count,
                "transcript_json": json.dumps([m.model_dump() for m in result.transcript]),
                "metrics_json": metrics_json,
                "nodes_json": nodes_json,
                "error": result.error_message,
            }
            self._append_record(self._results_path(), result_record)

        return run.run_id

    def get_run(self, run_id: str) -> dict | None:
        """Get a run by ID (metadata only)."""
        path = self._runs_path()
        if not path.exists():
            return None

        result = self._conn.execute(f"SELECT * FROM '{path}' WHERE id = ?", [run_id])
        rows = self._to_dicts(result)
        return rows[0] if rows else None

    def get_run_results(self, run_id: str) -> list[dict]:
        """Get all results for a run."""
        path = self._results_path()
        if not path.exists():
            return []

        result = self._conn.execute(f"SELECT * FROM '{path}' WHERE run_id = ?", [run_id])
        return self._to_dicts(result)

    def list_runs(self, limit: int = 50) -> list[dict]:
        """List recent runs."""
        path = self._runs_path()
        if not path.exists():
            return []

        result = self._conn.execute(
            f"SELECT * FROM '{path}' ORDER BY started_at DESC LIMIT ?", [limit]
        )
        return self._to_dicts(result)

    # Query helpers

    def query(self, sql: str) -> list[dict]:
        """Run arbitrary SQL against the data files.

        Tables available: agents, runs, results
        """
        # Register parquet files as tables
        for name in ["agents", "runs", "results"]:
            path = self.data_dir / f"{name}.parquet"
            if path.exists():
                self._conn.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM '{path}'")

        result = self._conn.execute(sql)
        return self._to_dicts(result)

    def _to_dicts(self, result) -> list[dict]:
        """Convert DuckDB result to list of dicts."""
        columns = [desc[0] for desc in result.description]
        return [dict(zip(columns, row, strict=True)) for row in result.fetchall()]

    # Internal

    def _append_record(self, path: Path, record: dict) -> None:
        """Append a record to a parquet file."""
        # Convert record to table
        table = pa.Table.from_pylist([record])

        if path.exists():
            # Read existing and append
            existing = pq.read_table(path)
            # Align schemas (new columns get null for old rows)
            combined_schema = pa.unify_schemas([existing.schema, table.schema])
            existing = existing.cast(combined_schema)
            table = table.cast(combined_schema)
            table = pa.concat_tables([existing, table])

        pq.write_table(table, path)


# Module-level convenience functions

_store: DataStore | None = None


def get_store(data_dir: Path | None = None) -> DataStore:
    """Get the global data store instance."""
    global _store
    if _store is None or (data_dir and _store.data_dir != data_dir):
        _store = DataStore(data_dir)
    return _store


def save_agent(graph: AgentGraph, name: str | None = None) -> str:
    """Save an agent graph."""
    return get_store().save_agent(graph, name)


def get_agent(agent_id: str) -> AgentGraph | None:
    """Get an agent by ID."""
    return get_store().get_agent(agent_id)


def list_agents() -> list[dict]:
    """List all saved agents."""
    return get_store().list_agents()


def save_run(run: TestRun, agent_id: str | None = None) -> str:
    """Save a test run."""
    return get_store().save_run(run, agent_id)


def get_run(run_id: str) -> dict | None:
    """Get a run by ID."""
    return get_store().get_run(run_id)


def list_runs(limit: int = 50) -> list[dict]:
    """List recent runs."""
    return get_store().list_runs(limit)


def query(sql: str) -> list[dict]:
    """Run SQL against stored data."""
    return get_store().query(sql)
