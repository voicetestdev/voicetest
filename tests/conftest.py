"""Root pytest configuration for voicetest tests."""

import json
from pathlib import Path

import pytest


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
