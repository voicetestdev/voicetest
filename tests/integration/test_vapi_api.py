"""Integration tests for VAPI API.

These tests interact with the real VAPI API and require VAPI_API_KEY.
Run with: uv run pytest tests/integration/test_vapi_api.py -v

To set up test data, create an assistant in your VAPI dashboard
and set VAPI_TEST_ASSISTANT_ID to its ID.
"""

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
def test_assistant_id():
    """Get the test assistant ID."""
    assistant_id = os.environ.get("VAPI_TEST_ASSISTANT_ID")
    if not assistant_id:
        pytest.skip("VAPI_TEST_ASSISTANT_ID not set")
    return assistant_id


class TestVAPIAssistants:
    """Tests for VAPI assistants API."""

    def test_list_assistants(self, client):
        """Test listing assistants."""
        assistants = client.assistants.list()

        assert isinstance(assistants, list)

    def test_get_assistant(self, client, test_assistant_id):
        """Test retrieving a specific assistant."""
        assistant = client.assistants.get(test_assistant_id)

        assert assistant.id == test_assistant_id

    def test_assistant_has_model_config(self, client, test_assistant_id):
        """Test that retrieved assistant has model configuration."""
        assistant = client.assistants.get(test_assistant_id)

        assert assistant.model is not None


class TestVAPIImportExportRoundtrip:
    """Tests for importing from and exporting to VAPI."""

    @pytest.mark.asyncio
    async def test_import_assistant(self, client, test_assistant_id):
        """Test importing a VAPI assistant into voicetest."""
        from voicetest import api

        assistant = client.assistants.get(test_assistant_id)
        assistant_dict = assistant.model_dump()

        graph = await api.import_agent(assistant_dict)

        assert graph.source_type == "vapi"
        assert len(graph.nodes) > 0

    @pytest.mark.asyncio
    async def test_export_to_vapi_assistant_format(self, client, test_assistant_id):
        """Test exporting voicetest graph to VAPI assistant format."""
        import json

        from voicetest import api

        assistant = client.assistants.get(test_assistant_id)
        assistant_dict = assistant.model_dump()

        graph = await api.import_agent(assistant_dict)
        exported_json = await api.export_agent(graph, format="vapi-assistant")
        exported = json.loads(exported_json)

        assert "model" in exported or "firstMessage" in exported

    @pytest.mark.asyncio
    async def test_export_to_vapi_squad_format(self, client, test_assistant_id):
        """Test exporting voicetest graph to VAPI squad format."""
        import json

        from voicetest import api

        assistant = client.assistants.get(test_assistant_id)
        assistant_dict = assistant.model_dump()

        graph = await api.import_agent(assistant_dict)
        exported_json = await api.export_agent(graph, format="vapi-squad")
        exported = json.loads(exported_json)

        assert "members" in exported
