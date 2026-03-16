"""Tests for dependency injection container."""

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session
from sqlalchemy.orm import sessionmaker

from voicetest.container import create_container
from voicetest.container import get_container
from voicetest.container import get_session
from voicetest.container import reset_container
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository


@pytest.fixture(autouse=True)
def reset_container_fixture():
    """Reset container before each test."""
    reset_container()
    yield
    reset_container()


@pytest.fixture
def container():
    """Create a fresh container with test database."""
    return create_container()


class TestContainerEngine:
    """Tests for engine registration."""

    def test_engine_is_singleton(self, container):
        engine1 = container.resolve(Engine)
        engine2 = container.resolve(Engine)
        assert engine1 is engine2

    def test_engine_creates_schema(self, container):
        from sqlalchemy import inspect

        engine = container.resolve(Engine)
        inspector = inspect(engine)
        tables = inspector.get_table_names()

        assert "agents" in tables
        assert "test_cases" in tables
        assert "runs" in tables
        assert "results" in tables


class TestContainerSessionFactory:
    """Tests for session factory registration."""

    def test_session_factory_is_singleton(self, container):
        factory1 = container.resolve(sessionmaker)
        factory2 = container.resolve(sessionmaker)
        assert factory1 is factory2

    def test_session_factory_creates_sessions(self, container):
        factory = container.resolve(sessionmaker)
        session = factory()
        assert isinstance(session, Session)
        session.close()


class TestContainerSession:
    """Tests for session registration."""

    def test_session_is_available(self, container):
        session = container.resolve(Session)
        assert isinstance(session, Session)


class TestContainerRepositories:
    """Tests for repository registration."""

    def test_agent_repository_is_available(self, container):
        repo = container.resolve(AgentRepository)
        assert isinstance(repo, AgentRepository)

    def test_test_case_repository_is_available(self, container):
        repo = container.resolve(TestCaseRepository)
        assert isinstance(repo, TestCaseRepository)

    def test_run_repository_is_available(self, container):
        repo = container.resolve(RunRepository)
        assert isinstance(repo, RunRepository)

    def test_repositories_use_same_session(self, container):
        """DuckDB uses singleton sessions, so all repos share one session."""
        agent_repo = container.resolve(AgentRepository)
        test_case_repo = container.resolve(TestCaseRepository)
        run_repo = container.resolve(RunRepository)

        assert agent_repo.session is test_case_repo.session
        assert test_case_repo.session is run_repo.session


class TestSessionScopeByBackend:
    """Tests for conditional session scope (singleton vs transient)."""

    def test_is_postgres_url_detection(self):
        """_is_postgres_url correctly identifies PostgreSQL connection strings."""
        from voicetest.container import _is_postgres_url

        assert _is_postgres_url("postgresql://user:pass@host/db")
        assert _is_postgres_url("postgres://user:pass@host/db")
        assert _is_postgres_url("postgresql://user:pass@ep-cool.neon.tech/db")
        assert not _is_postgres_url("duckdb:///path/to/file.duckdb")
        assert not _is_postgres_url("sqlite:///:memory:")
        assert not _is_postgres_url(None)
        assert not _is_postgres_url("")

    def test_duckdb_sessions_are_singleton(self, container):
        """DuckDB (no DATABASE_URL) uses singleton sessions."""
        session1 = container.resolve(Session)
        session2 = container.resolve(Session)
        assert session1 is session2

    def test_postgres_sessions_are_transient(self, tmp_path, monkeypatch):
        """PostgreSQL DATABASE_URL produces transient (non-shared) sessions."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")

        from unittest.mock import patch

        from voicetest.container import create_container as _create_container

        # Keep mock active through resolution — engine factory is lazy.
        with patch("voicetest.container.create_db_engine") as mock_engine_fn:
            from sqlalchemy import create_engine as sa_create_engine

            sqlite_engine = sa_create_engine("sqlite:///:memory:")
            mock_engine_fn.return_value = sqlite_engine

            pg_container = _create_container()

            session1 = pg_container.resolve(Session)
            session2 = pg_container.resolve(Session)

        assert session1 is not session2

    def test_postgres_repos_get_independent_sessions(self, tmp_path, monkeypatch):
        """With PostgreSQL, each repository gets its own session."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/testdb")

        from unittest.mock import patch

        from voicetest.container import create_container as _create_container

        with patch("voicetest.container.create_db_engine") as mock_engine_fn:
            from sqlalchemy import create_engine as sa_create_engine

            sqlite_engine = sa_create_engine("sqlite:///:memory:")
            mock_engine_fn.return_value = sqlite_engine

            pg_container = _create_container()

            agent_repo = pg_container.resolve(AgentRepository)
            test_case_repo = pg_container.resolve(TestCaseRepository)
            run_repo = pg_container.resolve(RunRepository)

        assert agent_repo.session is not test_case_repo.session
        assert test_case_repo.session is not run_repo.session


class TestGetSession:
    """Tests for get_session helper."""

    def test_get_session_returns_session(self):
        session = get_session()
        assert isinstance(session, Session)


class TestGetContainer:
    """Tests for get_container singleton."""

    def test_get_container_returns_same_instance(self):
        container1 = get_container()
        container2 = get_container()
        assert container1 is container2

    def test_reset_container_creates_new_instance(self):
        container1 = get_container()
        reset_container()
        container2 = get_container()
        assert container1 is not container2
