"""Tests for database path resolution and engine creation."""

from pathlib import Path

from sqlalchemy import Engine
from sqlalchemy import inspect

from voicetest.config import get_db_path
from voicetest.container import get_container
from voicetest.container import reset_container
from voicetest.storage.engine import create_db_engine


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


class TestCreateDbEngine:
    """Tests for SQLAlchemy engine creation."""

    def test_creates_db_file(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        create_db_engine()

        assert db_path.exists()

    def test_creates_parent_directories(self, tmp_path, monkeypatch):
        db_path = tmp_path / "nested" / "dirs" / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        create_db_engine()

        assert db_path.parent.exists()


class TestGetEngine:
    """Tests for singleton engine from container."""

    def test_returns_same_engine(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        reset_container()

        container = get_container()
        engine1 = container.resolve(Engine)
        engine2 = container.resolve(Engine)

        assert engine1 is engine2
        reset_container()


class TestSchema:
    """Tests for schema initialization via SQLAlchemy models."""

    def test_creates_all_tables(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        engine = create_db_engine()
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agents" in tables
        assert "test_cases" in tables
        assert "runs" in tables
        assert "results" in tables

    def test_idempotent(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        create_db_engine()
        engine = create_db_engine()

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert len(tables) >= 4

    def test_model_columns_match_schema(self, tmp_path, monkeypatch):
        """Verify SQLAlchemy model columns match the database schema.

        This catches mismatches between models.py and db.py schema definitions.
        """
        from sqlalchemy import text

        from voicetest.storage.models import Agent
        from voicetest.storage.models import Result
        from voicetest.storage.models import Run
        from voicetest.storage.models import TestCase as TestCaseModel

        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        engine = create_db_engine()

        models = {
            "agents": Agent,
            "test_cases": TestCaseModel,
            "runs": Run,
            "results": Result,
        }

        with engine.connect() as conn:
            for table_name, model in models.items():
                result = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = :table_name"
                    ),
                    {"table_name": table_name},
                ).fetchall()
                db_columns = {row[0] for row in result}
                model_columns = {col.name for col in model.__table__.columns}

                missing_in_db = model_columns - db_columns
                assert not missing_in_db, (
                    f"Table '{table_name}' missing columns defined in model: {missing_in_db}"
                )
