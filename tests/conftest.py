"""Root pytest configuration for voicetest tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolate_db(tmp_path, monkeypatch):
    """Give every test its own temporary database.

    Prevents test runs from polluting the local .voicetest/data.duckdb
    or ~/.voicetest/data.duckdb. Each test gets a fresh, empty DB.
    Tests that need to verify path-resolution behavior can still
    override via their own monkeypatch calls.
    """
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))


@pytest.fixture
def fixtures_dir() -> Path:
    """Return path to shared test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_graph_dict(fixtures_dir: Path) -> dict:
    """Load sample graph as a dict (for API/integration tests)."""
    return json.loads((fixtures_dir / "graphs" / "simple_graph.json").read_text())


@pytest.fixture
def sample_graph(sample_graph_dict: dict):
    """Load sample graph as a Pydantic model."""
    from voicetest.models.agent import AgentGraph

    return AgentGraph.model_validate(sample_graph_dict)


@pytest.fixture
def logic_split_graph_dict(fixtures_dir: Path) -> dict:
    """Load graph with logic split node as a dict."""
    return json.loads((fixtures_dir / "graphs" / "graph_with_logic_split.json").read_text())


@pytest.fixture
def logic_split_graph(logic_split_graph_dict: dict):
    """Load graph with logic split node as a Pydantic model.

    Contains: greeting → router (logic split) → premium | standard → farewell.
    The router node has equation transitions and an always (else) fallback.
    """
    from voicetest.models.agent import AgentGraph

    return AgentGraph.model_validate(logic_split_graph_dict)
