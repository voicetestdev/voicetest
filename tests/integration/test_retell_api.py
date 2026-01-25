"""Integration tests for Retell REST endpoints.

These tests verify our REST endpoints work correctly with the real Retell API.
Requires RETELL_API_KEY to be set (in environment or .voicetest/settings.toml).

Run with: uv run pytest tests/integration/test_retell_api.py -v
"""

import os

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app
from voicetest.settings import load_settings


# Load settings and apply to environment before skip check
_settings = load_settings()
_settings.apply_env()


def retell_available() -> bool:
    """Check if Retell credentials are configured."""
    return bool(os.environ.get("RETELL_API_KEY"))


pytestmark = pytest.mark.skipif(not retell_available(), reason="RETELL_API_KEY not set")


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
def created_flow(client, sample_graph):
    """Create a test flow in Retell and clean up after."""
    response = client.post(
        "/api/platforms/retell/export",
        json={"graph": sample_graph, "name": "voicetest-integration-test"},
    )
    assert response.status_code == 200
    flow_id = response.json()["id"]

    yield flow_id

    from voicetest.platforms.retell import get_client

    get_client().conversation_flow.delete(flow_id)


class TestRetellPlatformStatus:
    """Tests for GET /platforms/retell/status."""

    def test_status_returns_configured_true(self, client):
        """Status endpoint returns configured=true when API key is set."""
        response = client.get("/api/platforms/retell/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "retell"
        assert data["configured"] is True


class TestRetellListAgents:
    """Tests for GET /platforms/retell/agents."""

    def test_list_agents_returns_list(self, client):
        """List agents returns a list of conversation flows."""
        response = client.get("/api/platforms/retell/agents")

        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)

    def test_list_agents_items_have_required_fields(self, client, created_flow):
        """Each agent in list has id and name fields."""
        response = client.get("/api/platforms/retell/agents")

        assert response.status_code == 200
        agents = response.json()

        # Find our created flow
        flow_ids = [a["id"] for a in agents]
        assert created_flow in flow_ids

        for agent in agents:
            assert "id" in agent
            assert "name" in agent
            assert isinstance(agent["id"], str)
            assert isinstance(agent["name"], str)


class TestRetellImportAgent:
    """Tests for POST /platforms/retell/agents/{id}/import."""

    def test_import_agent_returns_graph(self, client, created_flow):
        """Import endpoint returns a valid AgentGraph."""
        response = client.post(
            f"/api/platforms/retell/agents/{created_flow}/import",
            json={},
        )

        assert response.status_code == 200
        graph = response.json()
        assert graph["source_type"] == "retell"
        assert graph["entry_node_id"] == "greeting"
        assert "greeting" in graph["nodes"]

    def test_import_preserves_node_structure(self, client, created_flow):
        """Imported graph preserves the node structure."""
        response = client.post(
            f"/api/platforms/retell/agents/{created_flow}/import",
            json={},
        )

        assert response.status_code == 200
        graph = response.json()
        node = graph["nodes"]["greeting"]
        assert "instructions" in node
        assert "Greet the user" in node["instructions"]

    def test_import_nonexistent_flow_returns_error(self, client):
        """Import of non-existent flow returns 500."""
        response = client.post(
            "/api/platforms/retell/agents/nonexistent-flow-id/import",
            json={},
        )

        assert response.status_code == 500


class TestRetellExportAgent:
    """Tests for POST /platforms/retell/export."""

    def test_export_creates_flow_in_retell(self, client, sample_graph):
        """Export creates a real conversation flow in Retell."""
        response = client.post(
            "/api/platforms/retell/export",
            json={"graph": sample_graph, "name": "voicetest-export-test"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "retell"
        assert data["id"] is not None
        assert data["name"] is not None

        # Clean up
        from voicetest.platforms.retell import get_client

        get_client().conversation_flow.delete(data["id"])

    def test_export_returns_provided_name_in_response(self, client, sample_graph):
        """Export returns the provided name in response.

        Note: Retell doesn't support naming flows on create.
        """
        test_name = "voicetest-named-export-test"
        response = client.post(
            "/api/platforms/retell/export",
            json={"graph": sample_graph, "name": test_name},
        )

        assert response.status_code == 200
        data = response.json()
        # Name is echoed back even though Retell doesn't store it
        assert data["name"] == test_name

        # Clean up
        from voicetest.platforms.retell import get_client

        get_client().conversation_flow.delete(data["id"])

    def test_export_roundtrip(self, client, sample_graph):
        """Exported flow can be imported back with same structure."""
        # Export
        export_response = client.post(
            "/api/platforms/retell/export",
            json={"graph": sample_graph, "name": "voicetest-roundtrip-test"},
        )
        assert export_response.status_code == 200
        flow_id = export_response.json()["id"]

        try:
            # Import back
            import_response = client.post(
                f"/api/platforms/retell/agents/{flow_id}/import",
                json={},
            )
            assert import_response.status_code == 200

            graph = import_response.json()
            assert graph["entry_node_id"] == sample_graph["entry_node_id"]
            assert "greeting" in graph["nodes"]

        finally:
            from voicetest.platforms.retell import get_client

            get_client().conversation_flow.delete(flow_id)
