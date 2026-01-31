"""Parameterized integration tests for all platform REST endpoints.

These tests verify that all platforms implement the same interface consistently.
Each platform must pass the same tests to prevent interface drift.

Requires platform API keys to be set (in environment or .voicetest/settings.toml).

Run with: uv run pytest tests/integration/test_platforms.py -v
"""

import os

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app
from voicetest.settings import load_settings


# Load settings and apply to environment before tests
_settings = load_settings()
_settings.apply_env()


# Platform configuration
PLATFORMS = ["retell", "vapi", "livekit", "bland"]

PLATFORM_ENV_KEYS = {
    "retell": ["RETELL_API_KEY"],
    "vapi": ["VAPI_API_KEY"],
    "livekit": ["LIVEKIT_API_KEY", "LIVEKIT_API_SECRET"],
    "bland": ["BLAND_API_KEY"],
}

# Platforms that support creating new agents via API
# (LiveKit uses CLI-based deployment which may not be configured)
PLATFORMS_SUPPORT_CREATE = ["retell", "vapi", "bland"]

# Platforms that support full roundtrip (create + get individual agent)
PLATFORMS_SUPPORT_ROUNDTRIP = ["retell", "vapi", "bland"]


def platform_available(platform: str) -> bool:
    """Check if all required env vars for a platform are set."""
    keys = PLATFORM_ENV_KEYS.get(platform, [])
    return all(os.environ.get(key) for key in keys)


def get_available_platforms() -> list[str]:
    """Get list of platforms with credentials configured."""
    return [p for p in PLATFORMS if platform_available(p)]


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


# sample_graph_dict_dict fixture is inherited from tests/conftest.py


# Skip entire module if no platforms are configured
pytestmark = pytest.mark.skipif(
    not get_available_platforms(), reason="No platform API keys configured"
)


class TestPlatformStatus:
    """Tests for GET /platforms/{platform}/status endpoint."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_status_returns_platform_name(self, client, platform):
        """Status endpoint returns correct platform name."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        response = client.get(f"/api/platforms/{platform}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == platform

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_status_returns_configured_true(self, client, platform):
        """Status endpoint returns configured=true when API key is set."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        response = client.get(f"/api/platforms/{platform}/status")

        assert response.status_code == 200
        data = response.json()
        assert data["configured"] is True


class TestPlatformListAgents:
    """Tests for GET /platforms/{platform}/agents endpoint."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_list_agents_returns_list(self, client, platform):
        """List agents returns a list (may be empty)."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        response = client.get(f"/api/platforms/{platform}/agents")

        assert response.status_code == 200
        agents = response.json()
        assert isinstance(agents, list)

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_list_agents_items_have_required_fields(self, client, platform):
        """Each agent in list has id and name string fields."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        response = client.get(f"/api/platforms/{platform}/agents")

        assert response.status_code == 200
        agents = response.json()

        for agent in agents:
            assert "id" in agent, "Agent missing 'id' field"
            assert "name" in agent, "Agent missing 'name' field"
            assert isinstance(agent["id"], str), "Agent 'id' must be string"
            assert isinstance(agent["name"], str), "Agent 'name' must be string"


class TestPlatformImportAgent:
    """Tests for POST /platforms/{platform}/agents/{id}/import endpoint."""

    @pytest.mark.parametrize("platform", PLATFORMS)
    def test_import_nonexistent_agent_returns_error(self, client, platform):
        """Import of non-existent agent returns error status."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        response = client.post(
            f"/api/platforms/{platform}/agents/nonexistent-agent-id-12345/import",
            json={},
        )

        # Should return an error (4xx or 5xx)
        assert response.status_code >= 400


class TestPlatformExportAgent:
    """Tests for POST /platforms/{platform}/export endpoint."""

    @pytest.mark.parametrize("platform", PLATFORMS_SUPPORT_CREATE)
    def test_export_creates_agent(self, client, platform, sample_graph_dict):
        """Export creates an agent and returns expected response structure."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        response = client.post(
            f"/api/platforms/{platform}/export",
            json={"graph": sample_graph_dict, "name": f"voicetest-integration-{platform}"},
        )

        assert response.status_code == 200
        data = response.json()

        # Verify response structure
        assert "id" in data, "Export response missing 'id'"
        assert "name" in data, "Export response missing 'name'"
        assert "platform" in data, "Export response missing 'platform'"
        assert data["platform"] == platform
        assert isinstance(data["id"], str)
        assert isinstance(data["name"], str)

        # Clean up created agent
        _cleanup_agent(platform, data["id"])

    @pytest.mark.parametrize("platform", PLATFORMS_SUPPORT_CREATE)
    def test_export_uses_provided_name(self, client, platform, sample_graph_dict):
        """Export uses the name provided in the request."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        test_name = f"voicetest-named-{platform}"
        response = client.post(
            f"/api/platforms/{platform}/export",
            json={"graph": sample_graph_dict, "name": test_name},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == test_name

        # Clean up
        _cleanup_agent(platform, data["id"])


class TestPlatformRoundtrip:
    """Tests for export then import roundtrip."""

    @pytest.mark.parametrize("platform", PLATFORMS_SUPPORT_ROUNDTRIP)
    def test_roundtrip_preserves_structure(self, client, platform, sample_graph_dict):
        """Exported agent can be imported back with structure preserved."""
        if not platform_available(platform):
            pytest.skip(f"{platform} not configured")

        # Export
        export_response = client.post(
            f"/api/platforms/{platform}/export",
            json={"graph": sample_graph_dict, "name": f"voicetest-roundtrip-{platform}"},
        )
        assert export_response.status_code == 200
        agent_id = export_response.json()["id"]

        try:
            # Import back
            import_response = client.post(
                f"/api/platforms/{platform}/agents/{agent_id}/import",
                json={},
            )
            assert import_response.status_code == 200

            graph = import_response.json()

            # Verify graph structure
            assert "source_type" in graph
            assert "entry_node_id" in graph
            assert "nodes" in graph
            assert graph["source_type"] == platform
            assert len(graph["nodes"]) > 0

            # Verify nodes have required fields
            for _node_id, node in graph["nodes"].items():
                assert "id" in node
                assert "state_prompt" in node
                assert "transitions" in node
                assert "tools" in node

        finally:
            _cleanup_agent(platform, agent_id)


class TestPlatformListEndpoint:
    """Tests for GET /platforms endpoint."""

    def test_list_platforms_returns_all_registered(self, client):
        """List platforms returns all registered platforms."""
        response = client.get("/api/platforms")

        assert response.status_code == 200
        platforms = response.json()
        assert isinstance(platforms, list)

        platform_names = [p["name"] for p in platforms]
        for expected in PLATFORMS:
            assert expected in platform_names, f"Platform {expected} not in list"

    def test_list_platforms_items_have_required_fields(self, client):
        """Each platform in list has required fields."""
        response = client.get("/api/platforms")

        assert response.status_code == 200
        platforms = response.json()

        for platform in platforms:
            assert "name" in platform
            assert "configured" in platform
            assert "env_key" in platform
            assert "required_env_keys" in platform
            assert isinstance(platform["name"], str)
            assert isinstance(platform["configured"], bool)
            assert isinstance(platform["env_key"], str)
            assert isinstance(platform["required_env_keys"], list)


def _cleanup_agent(platform: str, agent_id: str) -> None:
    """Clean up a created agent after test."""
    if platform == "retell":
        from voicetest.platforms.retell import get_client

        get_client().conversation_flow.delete(conversation_flow_id=agent_id)
    elif platform == "vapi":
        from voicetest.platforms.vapi import get_client

        get_client().assistants.delete(agent_id)
    elif platform == "livekit":
        import contextlib

        from voicetest.platforms.livekit import LiveKitPlatformClient

        client_mgr = LiveKitPlatformClient()
        client = client_mgr.get_client()
        with contextlib.suppress(Exception):
            client_mgr.delete_agent(client, agent_id)
    elif platform == "bland":
        from voicetest.platforms.bland import BlandPlatformClient

        client_mgr = BlandPlatformClient()
        client = client_mgr.get_client()
        client_mgr.delete_agent(client, agent_id)
