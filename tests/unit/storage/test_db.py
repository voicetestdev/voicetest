"""Tests for DuckDB connection and schema management."""

from voicetest.storage.db import get_connection, get_db_path, init_schema


class TestGetDbPath:
    """Tests for database path resolution."""

    def test_default_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("VOICETEST_DB_PATH", raising=False)

        path = get_db_path()

        assert path == tmp_path / ".voicetest" / "data.duckdb"

    def test_env_override(self, tmp_path, monkeypatch):
        custom_path = tmp_path / "custom" / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(custom_path))

        path = get_db_path()

        assert path == custom_path


class TestGetConnection:
    """Tests for database connection."""

    def test_creates_db_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()

        assert db_path.exists()
        conn.close()

    def test_creates_parent_directories(self, tmp_path, monkeypatch):
        db_path = tmp_path / "nested" / "dirs" / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()

        assert db_path.parent.exists()
        conn.close()


class TestInitSchema:
    """Tests for schema initialization."""

    def test_creates_agents_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()
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
        assert "created_at" in columns
        assert "updated_at" in columns
        conn.close()

    def test_creates_test_cases_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()
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
        conn.close()

    def test_creates_runs_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()
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
        conn.close()

    def test_creates_results_table(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()
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
        conn.close()

    def test_idempotent(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        conn = get_connection()
        init_schema(conn)
        init_schema(conn)

        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables " "WHERE table_schema = 'main'"
        ).fetchall()

        assert len(tables) >= 4
        conn.close()
