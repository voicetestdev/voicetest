"""Integration tests for Retell API.

These tests interact with the real Retell API and require RETELL_API_KEY.
Run with: uv run pytest tests/integration/test_retell_api.py -v
"""

import json
import os

import pytest

from voicetest.platforms import retell


def retell_available() -> bool:
    """Check if Retell credentials are configured."""
    return bool(os.environ.get("RETELL_API_KEY"))


pytestmark = pytest.mark.skipif(not retell_available(), reason="RETELL_API_KEY not set")


@pytest.fixture
def client():
    """Get a configured Retell client."""
    return retell.get_client()


@pytest.fixture
async def test_flow(client):
    """Create a test conversation flow and clean up after."""
    from voicetest import api
    from voicetest.demo import get_demo_agent

    demo_agent = get_demo_agent()
    graph = await api.import_agent(demo_agent)
    exported_json = await api.export_agent(graph, format="retell-cf")
    exported = json.loads(exported_json)

    flow = client.conversation_flow.create(**exported)
    flow_id = flow.conversation_flow_id

    yield flow_id

    client.conversation_flow.delete(flow_id)


class TestRetellConversationFlows:
    """Tests for Retell conversation flow API."""

    def test_list_conversation_flows(self, client):
        """Test listing conversation flows."""
        flows = list(client.conversation_flow.list())

        assert isinstance(flows, list)

    @pytest.mark.asyncio
    async def test_get_conversation_flow(self, client, test_flow):
        """Test retrieving a specific conversation flow."""
        flow = client.conversation_flow.retrieve(test_flow)

        assert flow.conversation_flow_id == test_flow
        assert flow.start_node_id is not None
        assert flow.nodes is not None

    @pytest.mark.asyncio
    async def test_conversation_flow_has_nodes(self, client, test_flow):
        """Test that retrieved flow has node structure."""
        flow = client.conversation_flow.retrieve(test_flow)

        assert len(flow.nodes) > 0
        for node in flow.nodes:
            assert node.id is not None
            assert node.instruction is not None


class TestRetellImportExportRoundtrip:
    """Tests for importing from and exporting to Retell."""

    @pytest.mark.asyncio
    async def test_import_conversation_flow(self, client, test_flow):
        """Test importing a Retell conversation flow into voicetest."""
        from voicetest import api

        flow = client.conversation_flow.retrieve(test_flow)
        flow_dict = flow.model_dump()

        graph = await api.import_agent(flow_dict)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == flow.start_node_id
        assert len(graph.nodes) == len(flow.nodes)

    @pytest.mark.asyncio
    async def test_export_to_retell_cf_format(self, client, test_flow):
        """Test exporting voicetest graph to Retell CF format."""
        from voicetest import api

        flow = client.conversation_flow.retrieve(test_flow)
        flow_dict = flow.model_dump()

        graph = await api.import_agent(flow_dict)
        exported_json = await api.export_agent(graph, format="retell-cf")
        exported = json.loads(exported_json)

        assert "start_node_id" in exported
        assert "nodes" in exported
        assert exported["start_node_id"] == flow.start_node_id

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_structure(self, client, test_flow):
        """Test that import/export roundtrip preserves flow structure."""
        from voicetest import api

        flow = client.conversation_flow.retrieve(test_flow)
        flow_dict = flow.model_dump()

        graph = await api.import_agent(flow_dict)
        exported_json = await api.export_agent(graph, format="retell-cf")
        exported = json.loads(exported_json)

        assert len(exported["nodes"]) == len(flow.nodes)

        original_node_ids = {n.id for n in flow.nodes}
        exported_node_ids = {n["id"] for n in exported["nodes"]}
        assert original_node_ids == exported_node_ids


class TestRetellExportValidation:
    """Tests that validate exported formats are accepted by the Retell API."""

    @pytest.mark.asyncio
    async def test_exported_cf_accepted_by_retell_api(self, client):
        """Test that our Retell CF export is accepted by the Retell API.

        This is the key validation test - it creates a real conversation flow
        in Retell using our exported format, verifies it was accepted, then
        cleans up. This catches schema mismatches between our export and what
        Retell actually accepts.
        """
        from voicetest import api
        from voicetest.demo import get_demo_agent

        demo_agent = get_demo_agent()
        graph = await api.import_agent(demo_agent)
        exported_json = await api.export_agent(graph, format="retell-cf")
        exported = json.loads(exported_json)

        created_flow = None
        try:
            created_flow = client.conversation_flow.create(**exported)
            assert created_flow.conversation_flow_id is not None
            assert created_flow.nodes is not None

        finally:
            if created_flow:
                client.conversation_flow.delete(created_flow.conversation_flow_id)
