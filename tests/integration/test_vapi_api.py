"""Integration tests for VAPI API.

These tests interact with the real VAPI API and require VAPI_API_KEY.
Run with: uv run pytest tests/integration/test_vapi_api.py -v
"""

import json
import os

import pytest

from voicetest.platforms import vapi


def vapi_available() -> bool:
    """Check if VAPI credentials are configured."""
    return bool(os.environ.get("VAPI_API_KEY"))


pytestmark = pytest.mark.skipif(not vapi_available(), reason="VAPI_API_KEY not set")


@pytest.fixture
def client():
    """Get a configured VAPI client."""
    return vapi.get_client()


@pytest.fixture
async def test_assistant(client):
    """Create a test assistant and clean up after."""
    from voicetest import api
    from voicetest.demo import get_demo_agent

    demo_agent = get_demo_agent()
    graph = await api.import_agent(demo_agent)
    exported_json = await api.export_agent(graph, format="vapi-assistant")
    exported = json.loads(exported_json)

    exported["name"] = "voicetest-integration-test"

    assistant = client.assistants.create(**exported)
    assistant_id = assistant.id

    yield assistant_id

    client.assistants.delete(assistant_id)


class TestVAPIAssistants:
    """Tests for VAPI assistants API."""

    def test_list_assistants(self, client):
        """Test listing assistants."""
        assistants = client.assistants.list()

        assert isinstance(assistants, list)

    @pytest.mark.asyncio
    async def test_get_assistant(self, client, test_assistant):
        """Test retrieving a specific assistant."""
        assistant = client.assistants.get(test_assistant)

        assert assistant.id == test_assistant

    @pytest.mark.asyncio
    async def test_assistant_has_model_config(self, client, test_assistant):
        """Test that retrieved assistant has model configuration."""
        assistant = client.assistants.get(test_assistant)

        assert assistant.model is not None


class TestVAPIImportExportRoundtrip:
    """Tests for importing from and exporting to VAPI."""

    @pytest.mark.asyncio
    async def test_import_assistant(self, client, test_assistant):
        """Test importing a VAPI assistant into voicetest."""
        from voicetest import api

        assistant = client.assistants.get(test_assistant)
        assistant_dict = assistant.model_dump()

        graph = await api.import_agent(assistant_dict)

        assert graph.source_type == "vapi"
        assert len(graph.nodes) > 0

    @pytest.mark.asyncio
    async def test_export_to_vapi_assistant_format(self, client, test_assistant):
        """Test exporting voicetest graph to VAPI assistant format."""
        from voicetest import api

        assistant = client.assistants.get(test_assistant)
        assistant_dict = assistant.model_dump()

        graph = await api.import_agent(assistant_dict)
        exported_json = await api.export_agent(graph, format="vapi-assistant")
        exported = json.loads(exported_json)

        assert "model" in exported or "firstMessage" in exported

    @pytest.mark.asyncio
    async def test_export_to_vapi_squad_format(self, client, test_assistant):
        """Test exporting voicetest graph to VAPI squad format."""
        from voicetest import api

        assistant = client.assistants.get(test_assistant)
        assistant_dict = assistant.model_dump()

        graph = await api.import_agent(assistant_dict)
        exported_json = await api.export_agent(graph, format="vapi-squad")
        exported = json.loads(exported_json)

        assert "members" in exported


class TestVAPIExportValidation:
    """Tests that validate exported formats are accepted by the VAPI API."""

    @pytest.mark.asyncio
    async def test_exported_assistant_accepted_by_vapi_api(self, client):
        """Test that our VAPI assistant export is accepted by the VAPI API.

        This is the key validation test - it creates a real assistant in VAPI
        using our exported format, verifies it was accepted, then cleans up.
        This catches schema mismatches between our export and what VAPI
        actually accepts.
        """
        from voicetest import api
        from voicetest.demo import get_demo_agent

        demo_agent = get_demo_agent()
        graph = await api.import_agent(demo_agent)
        exported_json = await api.export_agent(graph, format="vapi-assistant")
        exported = json.loads(exported_json)

        exported["name"] = "voicetest-ci-validation"

        created_assistant = None
        try:
            created_assistant = client.assistants.create(**exported)
            assert created_assistant.id is not None
            assert created_assistant.model is not None

        finally:
            if created_assistant:
                client.assistants.delete(created_assistant.id)
