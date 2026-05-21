"""Tests for dependency injection container."""

from unittest.mock import patch

import pytest
from sqlalchemy import Engine
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import inspect
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from voicetest.container import _is_postgres_url
from voicetest.container import create_container
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository
from voicetest.web.calls import CallManager


@pytest.fixture
def fresh_container():
    """Create a fresh container with test database."""
    return create_container()


class TestContainerEngine:
    """Tests for engine registration."""

    def test_engine_is_singleton(self, fresh_container):
        engine1 = fresh_container.resolve(Engine)
        engine2 = fresh_container.resolve(Engine)
        assert engine1 is engine2

    def test_engine_creates_schema(self, fresh_container):
        engine = fresh_container.resolve(Engine)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agents" in tables
        assert "test_cases" in tables
        assert "runs" in tables
        assert "results" in tables


class TestContainerSessionFactory:
    """Tests for session factory registration."""

    def test_session_factory_is_singleton(self, fresh_container):
        factory1 = fresh_container.resolve(sessionmaker)
        factory2 = fresh_container.resolve(sessionmaker)
        assert factory1 is factory2

    def test_session_factory_creates_sessions(self, fresh_container):
        factory = fresh_container.resolve(sessionmaker)
        session = factory()
        assert isinstance(session, Session)
        session.close()


class TestContainerSession:
    """Tests for session registration."""

    def test_session_is_available(self, fresh_container):
        session = fresh_container.resolve(Session)
        assert isinstance(session, Session)


class TestContainerRepositories:
    """Tests for repository registration."""

    def test_agent_repository_is_available(self, fresh_container):
        repo = fresh_container.resolve(AgentRepository)
        assert isinstance(repo, AgentRepository)

    def test_test_case_repository_is_available(self, fresh_container):
        repo = fresh_container.resolve(TestCaseRepository)
        assert isinstance(repo, TestCaseRepository)

    def test_run_repository_is_available(self, fresh_container):
        repo = fresh_container.resolve(RunRepository)
        assert isinstance(repo, RunRepository)

    def test_repositories_use_same_session(self, fresh_container):
        """DuckDB uses singleton sessions, so all repos share one session."""
        agent_repo = fresh_container.resolve(AgentRepository)
        test_case_repo = fresh_container.resolve(TestCaseRepository)
        run_repo = fresh_container.resolve(RunRepository)

        assert agent_repo.session is test_case_repo.session
        assert test_case_repo.session is run_repo.session


class TestSessionScopeByBackend:
    """Tests for conditional session scope (singleton vs transient)."""

    def test_is_postgres_url_detection(self):
        """_is_postgres_url correctly identifies PostgreSQL connection strings."""

        assert _is_postgres_url("postgresql://user:pass@host/db")
        assert _is_postgres_url("postgres://user:pass@host/db")
        assert _is_postgres_url("postgresql://user:pass@ep-cool.neon.tech/db")
        assert not _is_postgres_url("duckdb:///path/to/file.duckdb")
        assert not _is_postgres_url("sqlite:///:memory:")
        assert not _is_postgres_url(None)
        assert not _is_postgres_url("")

    def test_duckdb_sessions_are_singleton(self, fresh_container):
        """DuckDB (no DATABASE_URL) uses singleton sessions."""
        session1 = fresh_container.resolve(Session)
        session2 = fresh_container.resolve(Session)
        assert session1 is session2

    def test_postgres_sessions_are_transient(self, tmp_path, monkeypatch):
        """PostgreSQL DATABASE_URL produces transient (non-shared) sessions."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")

        # Keep mock active through resolution — engine factory is lazy.
        with patch("voicetest.container.create_db_engine") as mock_engine_fn:
            sqlite_engine = sa_create_engine("sqlite:///:memory:")
            mock_engine_fn.return_value = sqlite_engine

            pg_container = create_container()

            session1 = pg_container.resolve(Session)
            session2 = pg_container.resolve(Session)

        assert session1 is not session2

    def test_postgres_repos_get_independent_sessions(self, tmp_path, monkeypatch):
        """With PostgreSQL, each repository gets its own session."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")

        with patch("voicetest.container.create_db_engine") as mock_engine_fn:
            sqlite_engine = sa_create_engine("sqlite:///:memory:")
            mock_engine_fn.return_value = sqlite_engine

            pg_container = create_container()

            agent_repo = pg_container.resolve(AgentRepository)
            test_case_repo = pg_container.resolve(TestCaseRepository)
            run_repo = pg_container.resolve(RunRepository)

        assert agent_repo.session is not test_case_repo.session
        assert test_case_repo.session is not run_repo.session


class TestLiveCallManagerResolution:
    """Regression coverage for CallManager / LiveKit wiring.

    Hit by `GET /api/livekit/status`: the endpoint resolves CallManager
    via the container, and any broken DI on CallManager surfaces as a
    500. A `LiveKitConfig | None` constructor arg with no matching
    registration produced `MissingDependencyError` in production.
    """

    def test_call_manager_resolves_from_container(self, fresh_container):
        manager = fresh_container.resolve(CallManager)
        assert isinstance(manager, CallManager)
        # The manager must carry a populated LiveKitConfig so the
        # /livekit/status endpoint can introspect connection settings.
        assert manager.config is not None
        assert manager.config.url
