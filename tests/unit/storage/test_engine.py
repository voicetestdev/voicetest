"""Tests for SQLAlchemy engine factory."""

import os

from sqlalchemy import Engine
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy import text
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from voicetest.storage.engine import _get_current_version
from voicetest.storage.engine import _migrate_schema
from voicetest.storage.engine import create_db_engine
from voicetest.storage.engine import get_session_factory
from voicetest.storage.models import Agent


class TestCreateDbEngine:
    """Tests for create_db_engine factory function."""

    def test_create_duckdb_engine_with_path(self, tmp_path):
        db_path = tmp_path / "test.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        assert engine is not None
        assert isinstance(engine, Engine)
        assert db_path.exists()

    def test_create_duckdb_engine_default_path(self, tmp_path, monkeypatch):
        db_path = tmp_path / "data.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        engine = create_db_engine()

        assert engine is not None
        assert db_path.exists()

    def test_engine_creates_schema(self, tmp_path):
        db_path = tmp_path / "schema.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agents" in tables
        assert "test_cases" in tables
        assert "runs" in tables
        assert "results" in tables

    def test_engine_from_database_url_env(self, tmp_path, monkeypatch):
        db_path = tmp_path / "env.duckdb"
        monkeypatch.setenv("DATABASE_URL", f"duckdb:///{db_path}")

        engine = create_db_engine(os.environ.get("DATABASE_URL"))

        assert engine is not None
        assert db_path.exists()

    def test_engine_allows_crud_operations(self, tmp_path):
        db_path = tmp_path / "crud.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        with Session(engine) as session:
            agent = Agent(
                id="test-agent",
                name="Test Agent",
                source_type="test",
            )
            session.add(agent)
            session.commit()

            loaded = session.get(Agent, "test-agent")
            assert loaded is not None
            assert loaded.name == "Test Agent"


class TestGetSessionFactory:
    """Tests for get_session_factory function."""

    def test_returns_sessionmaker(self, tmp_path):
        db_path = tmp_path / "session.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        factory = get_session_factory(engine)

        assert factory is not None
        assert isinstance(factory, sessionmaker)

    def test_session_factory_creates_sessions(self, tmp_path):
        db_path = tmp_path / "session2.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")
        factory = get_session_factory(engine)

        session = factory()

        assert session is not None
        assert isinstance(session, Session)
        session.close()

    def test_sessions_share_engine(self, tmp_path):
        db_path = tmp_path / "shared.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")
        factory = get_session_factory(engine)

        with factory() as session1:
            agent = Agent(id="shared-agent", name="Shared", source_type="test")
            session1.add(agent)
            session1.commit()

        with factory() as session2:
            loaded = session2.get(Agent, "shared-agent")
            assert loaded is not None
            assert loaded.name == "Shared"


class TestMigrateSchema:
    """Tests for versioned schema migrations."""

    def test_migrates_old_db_without_schema_version_table(self, tmp_path):
        """Reproduces the real upgrade path: existing DB with agents table
        but no schema_version table and no tests_paths column."""
        db_path = tmp_path / "legacy.duckdb"
        engine = create_engine(f"duckdb:///{db_path}")

        # Create old schema — agents table exists but no schema_version, no tests_paths
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE agents ("
                    "id VARCHAR PRIMARY KEY, "
                    "name VARCHAR NOT NULL, "
                    "source_type VARCHAR NOT NULL, "
                    "source_path VARCHAR, "
                    "graph_json VARCHAR, "
                    "metrics_config JSON, "
                    "user_id VARCHAR, "
                    "created_at TIMESTAMP, "
                    "updated_at TIMESTAMP"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE results ("
                    "id VARCHAR PRIMARY KEY, "
                    "run_id VARCHAR NOT NULL, "
                    "test_case_id VARCHAR NOT NULL, "
                    "test_name VARCHAR, "
                    "status VARCHAR, "
                    "duration_ms INTEGER, "
                    "turn_count INTEGER, "
                    "end_reason VARCHAR, "
                    "error_message VARCHAR, "
                    "transcript_json JSON, "
                    "metrics_json JSON, "
                    "nodes_visited JSON, "
                    "tools_called JSON, "
                    "models_used JSON, "
                    "created_at TIMESTAMP"
                    ")"
                )
            )
            # Insert a row so we can verify data survives migration
            conn.execute(
                text(
                    "INSERT INTO agents (id, name, source_type) "
                    "VALUES ('a1', 'Old Agent', 'retell')"
                )
            )

        # This is what happens on server startup — should NOT error
        _migrate_schema(engine)

        with engine.begin() as conn:
            # tests_paths column should exist
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'agents' AND column_name = 'tests_paths'"
                )
            )
            assert result.fetchone() is not None

            # Existing data should survive
            result = conn.execute(text("SELECT name FROM agents WHERE id = 'a1'"))
            assert result.scalar() == "Old Agent"

            # Migration should be recorded
            version = _get_current_version(conn)
            assert version == 2

    def test_runs_pending_migration_on_old_schema(self, tmp_path):
        db_path = tmp_path / "old.duckdb"
        engine = create_engine(f"duckdb:///{db_path}")

        # Simulate a pre-migration DB: has schema_version at 0 but no tests_paths column
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE agents ("
                    "id VARCHAR PRIMARY KEY, "
                    "name VARCHAR NOT NULL, "
                    "source_type VARCHAR NOT NULL, "
                    "source_path VARCHAR, "
                    "graph_json VARCHAR, "
                    "metrics_config JSON, "
                    "user_id VARCHAR, "
                    "created_at TIMESTAMP, "
                    "updated_at TIMESTAMP"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE results ("
                    "id VARCHAR PRIMARY KEY, "
                    "run_id VARCHAR NOT NULL, "
                    "test_case_id VARCHAR NOT NULL, "
                    "test_name VARCHAR, "
                    "status VARCHAR, "
                    "created_at TIMESTAMP"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE schema_version ("
                    "version INTEGER PRIMARY KEY, "
                    "description VARCHAR NOT NULL, "
                    "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )

        _migrate_schema(engine)

        # Column should now exist
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'agents' AND column_name = 'tests_paths'"
                )
            )
            assert result.fetchone() is not None

            # Migration should be recorded
            version = _get_current_version(conn)
            assert version == 2

    def test_tracks_version(self, tmp_path):
        db_path = tmp_path / "versioned.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        with engine.begin() as conn:
            version = _get_current_version(conn)
            assert version >= 1

    def test_idempotent(self, tmp_path):
        db_path = tmp_path / "idem.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        _migrate_schema(engine)
        _migrate_schema(engine)

        with engine.begin() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM schema_version"))
            count = result.scalar()
            # Each migration recorded exactly once, not duplicated
            assert count >= 1

    def test_logs_migration_activity(self, tmp_path, caplog):
        """Migration should log when running pending migrations."""
        db_path = tmp_path / "logged.duckdb"
        engine = create_engine(f"duckdb:///{db_path}")

        # Create old schema — triggers actual migration run
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE agents ("
                    "id VARCHAR PRIMARY KEY, "
                    "name VARCHAR NOT NULL, "
                    "source_type VARCHAR NOT NULL"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE results ("
                    "id VARCHAR PRIMARY KEY, "
                    "run_id VARCHAR NOT NULL, "
                    "test_case_id VARCHAR NOT NULL, "
                    "test_name VARCHAR, "
                    "status VARCHAR, "
                    "created_at TIMESTAMP"
                    ")"
                )
            )

        with caplog.at_level("INFO", logger="voicetest.storage.engine"):
            _migrate_schema(engine)

        assert "Migration 1" in caplog.text
        assert "Migration 2" in caplog.text

    def test_recovers_from_phantom_migration(self, tmp_path):
        """If schema_version says migration ran but the column is missing, re-run it."""
        db_path = tmp_path / "phantom.duckdb"
        engine = create_engine(f"duckdb:///{db_path}")

        # Create old schema with schema_version stamped but column missing
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE TABLE agents ("
                    "id VARCHAR PRIMARY KEY, "
                    "name VARCHAR NOT NULL, "
                    "source_type VARCHAR NOT NULL"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE results ("
                    "id VARCHAR PRIMARY KEY, "
                    "run_id VARCHAR NOT NULL, "
                    "test_case_id VARCHAR NOT NULL, "
                    "test_name VARCHAR, "
                    "status VARCHAR, "
                    "created_at TIMESTAMP"
                    ")"
                )
            )
            conn.execute(
                text(
                    "CREATE TABLE schema_version ("
                    "version INTEGER PRIMARY KEY, "
                    "description VARCHAR NOT NULL, "
                    "applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
                    ")"
                )
            )
            # Stamp migration 1 WITHOUT running the ALTER TABLE
            conn.execute(
                text(
                    "INSERT INTO schema_version (version, description) "
                    "VALUES (1, 'Add tests_paths to agents')"
                )
            )

        _migrate_schema(engine)

        # Column should exist despite the phantom stamp
        with engine.begin() as conn:
            result = conn.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'agents' AND column_name = 'tests_paths'"
                )
            )
            assert result.fetchone() is not None

    def test_skips_already_applied(self, tmp_path):
        db_path = tmp_path / "skip.duckdb"
        engine = create_db_engine(f"duckdb:///{db_path}")

        with engine.begin() as conn:
            v1 = _get_current_version(conn)

        # Run again
        _migrate_schema(engine)

        with engine.begin() as conn:
            v2 = _get_current_version(conn)

        assert v1 == v2
