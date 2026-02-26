"""Tests for platform integration endpoints and sync functionality."""

import pytest


class TestPlatformEndpoints:
    """Tests for platform integration endpoints."""

    @pytest.fixture
    def db_client(self, platform_client):
        """Use platform_client (with cleared API keys and temp settings dir)."""
        return platform_client

    def test_get_platform_status_retell_not_configured(self, db_client):
        """Platform status returns false when API key not configured."""
        response = db_client.get("/api/platforms/retell/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "retell"
        assert data["configured"] is False

    def test_get_platform_status_vapi_not_configured(self, db_client):
        """Platform status returns false when API key not configured."""
        response = db_client.get("/api/platforms/vapi/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "vapi"
        assert data["configured"] is False

    def test_get_platform_status_invalid_platform(self, db_client):
        """Invalid platform name returns 400."""
        response = db_client.get("/api/platforms/invalid/status")
        assert response.status_code == 400
        assert "Invalid platform" in response.json()["detail"]

    def test_configure_platform_retell(self, db_client):
        """Configure platform sets API key in settings."""
        response = db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-retell-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "retell"
        assert data["configured"] is True

        # Verify status now shows configured
        status_response = db_client.get("/api/platforms/retell/status")
        assert status_response.json()["configured"] is True

    def test_configure_platform_already_configured_returns_409(self, db_client):
        """Configure returns 409 when API key already set."""
        # First configuration succeeds
        db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-key-1"},
        )

        # Second configuration fails
        response = db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-key-2"},
        )
        assert response.status_code == 409
        assert "already configured" in response.json()["detail"]

    def test_list_retell_agents_not_configured(self, db_client):
        """List agents returns 400 when API key not configured."""
        response = db_client.get("/api/platforms/retell/agents")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_list_vapi_agents_not_configured(self, db_client):
        """List agents returns 400 when API key not configured."""
        response = db_client.get("/api/platforms/vapi/agents")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_list_retell_agents_mocked(self, db_client, monkeypatch):
        """List Retell agents with mocked client."""
        from unittest.mock import MagicMock

        from voicetest.platforms.retell import RetellPlatformClient

        # Configure platform first
        db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-retell-key"},
        )

        # Mock the client
        mock_flow = MagicMock()
        mock_flow.conversation_flow_id = "flow-123"
        mock_flow.conversation_flow_name = "Test Flow"

        mock_client = MagicMock()
        mock_client.conversation_flow.list.return_value = [mock_flow]

        monkeypatch.setattr(
            RetellPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        response = db_client.get("/api/platforms/retell/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["id"] == "flow-123"
        assert agents[0]["name"] == "Test Flow"

    def test_list_vapi_agents_mocked(self, db_client, monkeypatch):
        """List VAPI agents with mocked client."""
        from unittest.mock import MagicMock

        from voicetest.platforms.vapi import VapiPlatformClient

        # Configure platform first
        db_client.post(
            "/api/platforms/vapi/configure",
            json={"api_key": "test-vapi-key"},
        )

        # Mock the client
        mock_asst = MagicMock()
        mock_asst.id = "asst-456"
        mock_asst.name = "Test Assistant"

        mock_client = MagicMock()
        mock_client.assistants.list.return_value = [mock_asst]

        monkeypatch.setattr(
            VapiPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        response = db_client.get("/api/platforms/vapi/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["id"] == "asst-456"
        assert agents[0]["name"] == "Test Assistant"

    def test_import_retell_agent_not_configured(self, db_client):
        """Import agent returns 400 when API key not configured."""
        response = db_client.post("/api/platforms/retell/agents/flow-123/import", json={})
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_export_to_retell_not_configured(self, db_client, sample_retell_config):
        """Export to platform returns 400 when API key not configured."""
        # First import to get a graph
        import_response = db_client.post(
            "/api/agents/import", json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = db_client.post(
            "/api/platforms/retell/export",
            json={"graph": graph, "name": "Test Export"},
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_export_to_vapi_not_configured(self, db_client, sample_retell_config):
        """Export to platform returns 400 when API key not configured."""
        import_response = db_client.post(
            "/api/agents/import", json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = db_client.post(
            "/api/platforms/vapi/export",
            json={"graph": graph, "name": "Test Export"},
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_platform_status_configured_via_env(self, db_client, monkeypatch):
        """Platform shows as configured when API key is in environment."""
        monkeypatch.setenv("RETELL_API_KEY", "env-api-key")

        response = db_client.get("/api/platforms/retell/status")
        assert response.status_code == 200
        assert response.json()["configured"] is True

    def test_get_platform_status_livekit_not_configured(self, db_client):
        """LiveKit platform status returns false when API key not configured."""
        response = db_client.get("/api/platforms/livekit/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "livekit"
        assert data["configured"] is False

    def test_list_livekit_agents_not_configured(self, db_client):
        """List LiveKit agents returns 400 when API key not configured."""
        response = db_client.get("/api/platforms/livekit/agents")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_import_livekit_agent_not_configured(self, db_client):
        """Import LiveKit agent returns 400 when API key not configured."""
        response = db_client.post("/api/platforms/livekit/agents/agent-123/import", json={})
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_export_to_livekit_not_configured(self, db_client, sample_retell_config):
        """Export to LiveKit returns 400 when API key not configured."""
        import_response = db_client.post(
            "/api/agents/import", json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = db_client.post(
            "/api/platforms/livekit/export",
            json={"graph": graph, "name": "Test Export"},
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]


class TestSyncToPlatform:
    """Tests for sync-to-platform functionality."""

    @pytest.fixture
    def db_client(self, platform_client):
        """Use platform_client (with cleared API keys and temp settings dir)."""
        return platform_client

    def _create_agent_with_graph(self, db_client, graph, name):
        """Helper to create an agent with a specific graph using the repository."""
        from voicetest.rest import get_agent_repo

        repo = get_agent_repo()
        return repo.create(
            name=name,
            source_type=graph.source_type,
            graph_json=graph.model_dump_json(),
        )

    def test_sync_status_no_platform_source(self, db_client):
        """Sync status returns can_sync=False for non-platform agents."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="custom",
        )

        agent = self._create_agent_with_graph(db_client, graph, "Custom Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert "not a supported platform" in status["reason"]

    def test_sync_status_platform_no_remote_id(self, db_client):
        """Sync status returns can_sync=False when agent has no remote ID."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent No ID")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert status["platform"] == "retell"
        assert "No remote ID" in status["reason"]

    def test_sync_status_platform_not_configured(self, db_client):
        """Sync status returns needs_configuration=True when platform not configured."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert status["platform"] == "retell"
        assert status["remote_id"] == "flow-123"
        assert status["needs_configuration"] is True
        assert "not configured" in status["reason"]

    def test_sync_status_can_sync(self, db_client, monkeypatch):
        """Sync status returns can_sync=True when all conditions met."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        monkeypatch.setenv("RETELL_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is True
        assert status["platform"] == "retell"
        assert status["remote_id"] == "flow-123"

    def test_sync_status_bland_not_supported(self, db_client, monkeypatch):
        """Sync status returns can_sync=False for Bland (doesn't support updates)."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        monkeypatch.setenv("BLAND_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="bland",
            source_metadata={"agent_id": "agent-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Bland Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert status["platform"] == "bland"
        assert "does not support syncing" in status["reason"]

    def test_sync_agent_not_found(self, db_client):
        """Sync returns 404 for non-existent agent."""
        import json

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
        )

        response = db_client.post(
            "/api/agents/nonexistent/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert response.status_code == 404

    def test_sync_platform_not_supported(self, db_client):
        """Sync returns 400 for non-platform source."""
        import json

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="custom",
        )

        agent = self._create_agent_with_graph(db_client, graph, "Custom Agent")
        agent_id = agent["id"]

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 400
        assert "not a supported platform" in sync_response.json()["detail"]

    def test_sync_no_remote_id(self, db_client, monkeypatch):
        """Sync returns 400 when agent has no remote ID."""
        import json

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        monkeypatch.setenv("RETELL_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 400
        assert "No remote ID" in sync_response.json()["detail"]

    def test_sync_retell_success_mocked(self, db_client, monkeypatch):
        """Sync to Retell calls update_agent correctly."""
        import json
        from unittest.mock import MagicMock

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.platforms.retell import RetellPlatformClient

        monkeypatch.setenv("RETELL_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        mock_flow = MagicMock()
        mock_flow.conversation_flow_id = "flow-123"
        mock_flow.conversation_flow_name = "Updated Flow"

        mock_client = MagicMock()
        mock_client.conversation_flow.update.return_value = mock_flow

        monkeypatch.setattr(
            RetellPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 200

        result = sync_response.json()
        assert result["id"] == "flow-123"
        assert result["platform"] == "retell"
        assert result["synced"] is True

        mock_client.conversation_flow.update.assert_called_once()

    def test_sync_vapi_success_mocked(self, db_client, monkeypatch):
        """Sync to VAPI calls update_agent correctly."""
        import json
        from unittest.mock import MagicMock

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.platforms.vapi import VapiPlatformClient

        monkeypatch.setenv("VAPI_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="vapi",
            source_metadata={"assistant_id": "asst-456"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "VAPI Agent")
        agent_id = agent["id"]

        mock_assistant = MagicMock()
        mock_assistant.id = "asst-456"
        mock_assistant.name = "Updated Assistant"

        mock_client = MagicMock()
        mock_client.assistants.update.return_value = mock_assistant

        monkeypatch.setattr(
            VapiPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 200

        result = sync_response.json()
        assert result["id"] == "asst-456"
        assert result["platform"] == "vapi"
        assert result["synced"] is True

        mock_client.assistants.update.assert_called_once()


class TestPlatformSupportsUpdate:
    """Tests for platform supports_update property."""

    def test_retell_supports_update(self):
        """Retell platform supports updates."""
        from voicetest.platforms.retell import RetellPlatformClient

        client = RetellPlatformClient()
        assert client.supports_update is True
        assert client.remote_id_key == "conversation_flow_id"

    def test_vapi_supports_update(self):
        """VAPI platform supports updates."""
        from voicetest.platforms.vapi import VapiPlatformClient

        client = VapiPlatformClient()
        assert client.supports_update is True
        assert client.remote_id_key == "assistant_id"

    def test_livekit_supports_update(self):
        """LiveKit platform supports updates."""
        from voicetest.platforms.livekit import LiveKitPlatformClient

        client = LiveKitPlatformClient()
        assert client.supports_update is True
        assert client.remote_id_key == "agent_id"

    def test_bland_does_not_support_update(self):
        """Bland platform does not support updates."""
        from voicetest.platforms.bland import BlandPlatformClient

        client = BlandPlatformClient()
        assert client.supports_update is False
        assert client.remote_id_key is None

    def test_bland_update_agent_raises(self):
        """Bland update_agent raises NotImplementedError."""
        from voicetest.platforms.bland import BlandPlatformClient

        client = BlandPlatformClient()
        with pytest.raises(NotImplementedError) as exc_info:
            client.update_agent(None, "agent-123", {})
        assert "does not support" in str(exc_info.value)


class TestPlatformRegistrySupportsUpdate:
    """Tests for PlatformRegistry supports_update method."""

    def test_registry_supports_update_retell(self):
        """Registry returns True for Retell."""
        from voicetest.platforms.registry import PlatformRegistry
        from voicetest.platforms.retell import RetellPlatformClient

        registry = PlatformRegistry()
        registry.register(RetellPlatformClient())

        assert registry.supports_update("retell") is True

    def test_registry_supports_update_bland(self):
        """Registry returns False for Bland."""
        from voicetest.platforms.bland import BlandPlatformClient
        from voicetest.platforms.registry import PlatformRegistry

        registry = PlatformRegistry()
        registry.register(BlandPlatformClient())

        assert registry.supports_update("bland") is False

    def test_registry_get_remote_id_key(self):
        """Registry returns correct remote ID key."""
        from voicetest.platforms.registry import PlatformRegistry
        from voicetest.platforms.retell import RetellPlatformClient
        from voicetest.platforms.vapi import VapiPlatformClient

        registry = PlatformRegistry()
        registry.register(RetellPlatformClient())
        registry.register(VapiPlatformClient())

        assert registry.get_remote_id_key("retell") == "conversation_flow_id"
        assert registry.get_remote_id_key("vapi") == "assistant_id"

    def test_registry_supports_update_unknown_platform(self):
        """Registry raises ValueError for unknown platform."""
        from voicetest.platforms.registry import PlatformRegistry

        registry = PlatformRegistry()

        with pytest.raises(ValueError) as exc_info:
            registry.supports_update("unknown")
        assert "Unknown platform" in str(exc_info.value)
