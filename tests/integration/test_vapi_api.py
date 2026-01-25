"""Integration tests for VAPI REST endpoints.

These tests verify our REST endpoints work correctly with the real VAPI API.
Requires VAPI_API_KEY to be set (in environment or .voicetest/settings.toml).

Run with: uv run pytest tests/integration/test_vapi_api.py -v
"""

import os

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app
from voicetest.settings import load_settings


# Load settings and apply to environment before skip check
_settings = load_settings()
_settings.apply_env()


def vapi_available() -> bool:
    """Check if VAPI credentials are configured."""
    return bool(os.environ.get("VAPI_API_KEY"))


pytestmark = pytest.mark.skipif(not vapi_available(), reason="VAPI_API_KEY not set")


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
def created_assistant(client, sample_graph):
    """Create a test assistant in VAPI and clean up after."""
    response = client.post(
        "/api/platforms/vapi/export",
        json={"graph": sample_graph, "name": "voicetest-integration-test"},
    )
    assert response.status_code == 200
    assistant_id = response.json()["id"]

    yield assistant_id

    from voicetest.platforms.vapi import get_client

    get_client().assistants.delete(assistant_id)


class TestVAPIPlatformStatus:
    """Tests for GET /platforms/vapi/status."""

    def test_status_returns_configured_true(self, client):
        """Status endpoint returns configured=true when API key is set."""
        response = client.get("/api/platforms/vapi/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "vapi"
        assert data["configured"] is True


class TestVAPIListAgents:
    """Tests for GET /platforms/vapi/agents."""

    def test_list_agents_returns_list(self, client):
        """List agents returns a list of assistants."""
        response = client.get("/api/platforms/vapi/agents")

        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)

    def test_list_agents_items_have_required_fields(self, client, created_assistant):
        """Each agent in list has id and name fields."""
        response = client.get("/api/platforms/vapi/agents")

        assert response.status_code == 200
        agents = response.json()

        # Find our created assistant
        assistant_ids = [a["id"] for a in agents]
        assert created_assistant in assistant_ids

        for agent in agents:
            assert "id" in agent
            assert "name" in agent
            assert isinstance(agent["id"], str)
            assert isinstance(agent["name"], str)


class TestVAPIImportAgent:
    """Tests for POST /platforms/vapi/agents/{id}/import."""

    def test_import_agent_returns_graph(self, client, created_assistant):
        """Import endpoint returns a valid AgentGraph."""
        response = client.post(
            f"/api/platforms/vapi/agents/{created_assistant}/import",
            json={},
        )

        assert response.status_code == 200
        graph = response.json()
        assert graph["source_type"] == "vapi"
        assert len(graph["nodes"]) > 0

    def test_import_preserves_node_instructions(self, client, created_assistant):
        """Imported graph preserves the node instructions."""
        response = client.post(
            f"/api/platforms/vapi/agents/{created_assistant}/import",
            json={},
        )

        assert response.status_code == 200
        graph = response.json()

        # VAPI imports create a single node with the system prompt
        nodes = list(graph["nodes"].values())
        assert len(nodes) > 0
        assert "instructions" in nodes[0]

    def test_import_nonexistent_assistant_returns_error(self, client):
        """Import of non-existent assistant returns 500."""
        response = client.post(
            "/api/platforms/vapi/agents/nonexistent-assistant-id/import",
            json={},
        )

        assert response.status_code == 500


class TestVAPIExportAgent:
    """Tests for POST /platforms/vapi/export."""

    def test_export_creates_assistant_in_vapi(self, client, sample_graph):
        """Export creates a real assistant in VAPI."""
        response = client.post(
            "/api/platforms/vapi/export",
            json={"graph": sample_graph, "name": "voicetest-export-test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "vapi"
        assert data["id"] is not None
        assert data["name"] is not None

        # Clean up
        from voicetest.platforms.vapi import get_client

        get_client().assistants.delete(data["id"])

    def test_export_uses_provided_name(self, client, sample_graph):
        """Export uses the name provided in the request."""
        test_name = "voicetest-named-export-test"
        response = client.post(
            "/api/platforms/vapi/export",
            json={"graph": sample_graph, "name": test_name},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_name

        # Clean up
        from voicetest.platforms.vapi import get_client

        get_client().assistants.delete(data["id"])

    def test_export_roundtrip(self, client, sample_graph):
        """Exported assistant can be imported back."""
        # Export
        export_response = client.post(
            "/api/platforms/vapi/export",
            json={"graph": sample_graph, "name": "voicetest-roundtrip-test"},
        )
        assert export_response.status_code == 200
        assistant_id = export_response.json()["id"]

        try:
            # Import back
            import_response = client.post(
                f"/api/platforms/vapi/agents/{assistant_id}/import",
                json={},
            )
            assert import_response.status_code == 200

            graph = import_response.json()
            assert graph["source_type"] == "vapi"
            assert len(graph["nodes"]) > 0

        finally:
            from voicetest.platforms.vapi import get_client

            get_client().assistants.delete(assistant_id)
