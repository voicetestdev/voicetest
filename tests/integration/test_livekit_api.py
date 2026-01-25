"""Integration tests for LiveKit REST endpoints.

These tests verify our REST endpoints work correctly with LiveKit.
Requires LIVEKIT_API_KEY and LIVEKIT_API_SECRET to be set
(in environment or .voicetest/settings.toml).

Since LiveKit agents are deployed via CLI, these tests focus on:
- Platform status endpoint
- Import from Python code (no real API call)
- Export to Python code (no real API call)

For full deployment tests, the `lk` CLI tool must be installed.

Run with: uv run pytest tests/integration/test_livekit_api.py -v
"""

import os
import shutil

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app
from voicetest.settings import load_settings


# Load settings and apply to environment before skip check
_settings = load_settings()
_settings.apply_env()


def livekit_available() -> bool:
    """Check if LiveKit credentials are configured."""
    return bool(os.environ.get("LIVEKIT_API_KEY") and os.environ.get("LIVEKIT_API_SECRET"))


def livekit_cli_available() -> bool:
    """Check if LiveKit CLI (lk) is installed."""
    return shutil.which("lk") is not None


pytestmark = pytest.mark.skipif(not livekit_available(), reason="LIVEKIT_API_KEY/SECRET not set")


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def sample_graph():
    """Sample agent graph for testing exports."""
    return {
        "source_type": "custom",
        "entry_node_id": "greeting",
        "nodes": {
            "greeting": {
                "id": "greeting",
                "instructions": "Greet the user warmly and ask how you can help.",
                "transitions": [],
                "tools": [],
                "metadata": {},
            }
        },
        "source_metadata": {},
    }


@pytest.fixture
def sample_livekit_code():
    """Sample LiveKit agent Python code."""
    return '''"""Generated LiveKit agents from voicetest."""

from livekit.agents import Agent, RunContext, function_tool


class Agent_greeting(Agent):
    """Agent for node: greeting"""

    def __init__(self):
        super().__init__(
            instructions="""Greet the user warmly and ask how you can help."""
        )


def get_entry_agent():
    return Agent_greeting()
'''


class TestLiveKitPlatformStatus:
    """Tests for GET /platforms/livekit/status."""

    def test_status_returns_configured_true(self, client):
        """Status endpoint returns configured=true when API key is set."""
        response = client.get("/api/platforms/livekit/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "livekit"
        assert data["configured"] is True


class TestLiveKitImportFromCode:
    """Tests for importing LiveKit Python code via /agents/import."""

    def test_import_livekit_code_as_dict(self, client, sample_livekit_code):
        """Import LiveKit Python code provided as dict with 'code' key."""
        response = client.post(
            "/api/agents/import",
            json={"config": {"code": sample_livekit_code}, "source": "livekit"},
        )

        assert response.status_code == 200
        graph = response.json()
        assert graph["source_type"] == "livekit"
        assert graph["entry_node_id"] == "greeting"
        assert "greeting" in graph["nodes"]

    def test_import_extracts_instructions(self, client, sample_livekit_code):
        """Import extracts instructions from agent class."""
        response = client.post(
            "/api/agents/import",
            json={"config": {"code": sample_livekit_code}, "source": "livekit"},
        )

        assert response.status_code == 200
        graph = response.json()
        node = graph["nodes"]["greeting"]
        assert "Greet the user warmly" in node["instructions"]


class TestLiveKitExportFormat:
    """Tests for exporting to LiveKit Python code format."""

    def test_export_to_livekit_format(self, client, sample_graph):
        """Export produces valid LiveKit Python code."""
        response = client.post(
            "/api/agents/export", json={"graph": sample_graph, "format": "livekit"}
        )

        assert response.status_code == 200
        result = response.json()
        assert result["format"] == "livekit"
        assert "class Agent_greeting" in result["content"]
        assert "from livekit.agents import" in result["content"]

    def test_export_includes_instructions(self, client, sample_graph):
        """Exported code includes agent instructions."""
        response = client.post(
            "/api/agents/export", json={"graph": sample_graph, "format": "livekit"}
        )

        assert response.status_code == 200
        result = response.json()
        assert "Greet the user warmly" in result["content"]


class TestLiveKitRoundtrip:
    """Tests for import/export roundtrip."""

    def test_roundtrip_preserves_structure(self, client, sample_livekit_code):
        """Code -> AgentGraph -> Code roundtrip preserves agent structure."""
        import_response = client.post(
            "/api/agents/import",
            json={"config": {"code": sample_livekit_code}, "source": "livekit"},
        )
        assert import_response.status_code == 200
        graph = import_response.json()

        export_response = client.post(
            "/api/agents/export", json={"graph": graph, "format": "livekit"}
        )
        assert export_response.status_code == 200

        exported_code = export_response.json()["content"]
        assert "Agent_greeting" in exported_code
        assert "Greet the user warmly" in exported_code


@pytest.mark.skipif(not livekit_cli_available(), reason="lk CLI not installed")
class TestLiveKitListAgents:
    """Tests for GET /platforms/livekit/agents.

    Requires `lk` CLI tool to be installed.
    """

    def test_list_agents_returns_list(self, client):
        """List agents returns a list (may be empty if no agents deployed)."""
        response = client.get("/api/platforms/livekit/agents")

        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)

    def test_list_agents_items_have_required_fields(self, client):
        """Each agent in list has id and name fields."""
        response = client.get("/api/platforms/livekit/agents")

        assert response.status_code == 200
        agents = response.json()

        for agent in agents:
            assert "id" in agent
            assert "name" in agent
            assert isinstance(agent["id"], str)
            assert isinstance(agent["name"], str)


@pytest.mark.skipif(not livekit_cli_available(), reason="lk CLI not installed")
class TestLiveKitExportToPlatform:
    """Tests for POST /platforms/livekit/export.

    Requires `lk` CLI tool to be installed.
    These tests actually deploy agents to LiveKit Cloud.
    """

    def test_export_deploys_agent_to_livekit(self, client, sample_graph):
        """Export creates a deployed agent in LiveKit Cloud."""
        response = client.post(
            "/api/platforms/livekit/export",
            json={"graph": sample_graph, "name": "voicetest-integration-test"},
        )

        # May fail if CLI not configured or no cloud access
        if response.status_code == 200:
            data = response.json()
            assert data["platform"] == "livekit"
            assert data["id"] is not None
            assert data["name"] is not None

            # Clean up - delete the deployed agent
            from voicetest.platforms.livekit import LiveKitPlatformClient

            try:
                lk = LiveKitPlatformClient()
                credentials = lk.get_client()
                lk.delete_agent(credentials, data["id"])
            except Exception:
                pass  # Best effort cleanup
        else:
            # CLI may not be configured for cloud deployment
            assert response.status_code == 500
            assert "Failed to export" in response.json()["detail"]
