"""Tests for dependency injection container."""

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

from voicetest.container import (
    create_container,
    get_container,
    get_session,
    reset_container,
)
from voicetest.storage.repositories import AgentRepository, RunRepository, TestCaseRepository


@pytest.fixture(autouse=True)
def reset_container_fixture():
    """Reset container before each test."""
    reset_container()
    yield
    reset_container()


@pytest.fixture
def container(tmp_path, monkeypatch):
    """Create a fresh container with test database."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    return create_container()


class TestContainerEngine:
    """Tests for engine registration."""

    def test_engine_is_singleton(self, container):
        engine1 = container.resolve(Engine)
        engine2 = container.resolve(Engine)
        assert engine1 is engine2

    def test_engine_creates_schema(self, container, tmp_path, monkeypatch):
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
        agent_repo = container.resolve(AgentRepository)
        test_case_repo = container.resolve(TestCaseRepository)
        run_repo = container.resolve(RunRepository)

        assert agent_repo.session is test_case_repo.session
        assert test_case_repo.session is run_repo.session


class TestGetSession:
    """Tests for get_session helper."""

    def test_get_session_returns_session(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        session = get_session()
        assert isinstance(session, Session)


class TestGetContainer:
    """Tests for get_container singleton."""

    def test_get_container_returns_same_instance(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        container1 = get_container()
        container2 = get_container()
        assert container1 is container2

    def test_reset_container_creates_new_instance(self, tmp_path, monkeypatch):
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))

        container1 = get_container()
        reset_container()
        container2 = get_container()
        assert container1 is not container2
