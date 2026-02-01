"""Tests for DuckDB connection and schema management."""

from pathlib import Path

from voicetest.config import get_db_path
from voicetest.container import get_db_connection
from voicetest.storage.db import create_connection, init_schema


class TestGetDbPath:
    """Tests for database path resolution."""

    def test_project_mode_when_voicetest_dir_exists(self, tmp_path, monkeypatch):
        """When .voicetest/ exists in CWD, use local path."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("VOICETEST_DB_PATH", raising=False)
        (tmp_path / ".voicetest").mkdir()

        path = get_db_path()

        assert path == tmp_path / ".voicetest" / "data.duckdb"

    def test_global_mode_when_no_voicetest_dir(self, tmp_path, monkeypatch):
        """When no .voicetest/ in CWD, fall back to global ~/.voicetest/."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("VOICETEST_DB_PATH", raising=False)

        path = get_db_path()

        assert path == Path.home() / ".voicetest" / "data.duckdb"

    def test_env_override(self, tmp_path, monkeypatch):
        custom_path = tmp_path / "custom" / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(custom_path))

        path = get_db_path()

        assert path == custom_path


class TestCreateConnection:
    """Tests for database connection factory."""

    def test_creates_db_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        create_connection()

        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path, monkeypatch):
        db_path = tmp_path / "nested" / "dirs" / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        create_connection()

        assert db_path.parent.exists()


class TestGetDbConnection:
    """Tests for singleton connection from container."""

    def test_returns_same_connection(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn1 = get_db_connection()
        conn2 = get_db_connection()

        assert conn1 is conn2


class TestInitSchema:
    """Tests for schema initialization."""

    def test_creates_agents_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_db_connection()
        init_schema(conn)

        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'agents' ORDER BY ordinal_position"
        ).fetchall()
        columns = [r[0] for r in result]

        assert "id" in columns
        assert "name" in columns
        assert "source_type" in columns
        assert "source_path" in columns
        assert "graph_json" in columns
        assert "metrics_config" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

    def test_creates_test_cases_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_db_connection()
        init_schema(conn)

        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'test_cases' ORDER BY ordinal_position"
        ).fetchall()
        columns = [r[0] for r in result]

        assert "id" in columns
        assert "agent_id" in columns
        assert "name" in columns
        assert "user_prompt" in columns
        assert "metrics" in columns

    def test_creates_runs_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_db_connection()
        init_schema(conn)

        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'runs' ORDER BY ordinal_position"
        ).fetchall()
        columns = [r[0] for r in result]

        assert "id" in columns
        assert "agent_id" in columns
        assert "started_at" in columns
        assert "completed_at" in columns

    def test_creates_results_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_db_connection()
        init_schema(conn)

        result = conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name = 'results' ORDER BY ordinal_position"
        ).fetchall()
        columns = [r[0] for r in result]

        assert "id" in columns
        assert "run_id" in columns
        assert "test_case_id" in columns
        assert "status" in columns
        assert "transcript_json" in columns

    def test_idempotent(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_db_connection()
        init_schema(conn)
        init_schema(conn)

        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables " "WHERE table_schema = 'main'"
        ).fetchall()

        assert len(tables) >= 4
