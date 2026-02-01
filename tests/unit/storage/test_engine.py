"""Tests for SQLAlchemy engine factory."""

import os

from sqlalchemy import Engine, inspect
from sqlalchemy.orm import Session, sessionmaker

from voicetest.storage.engine import create_db_engine, get_session_factory
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
