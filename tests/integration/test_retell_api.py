"""Integration tests for Retell API.

These tests interact with the real Retell API and require RETELL_API_KEY.
Run with: uv run pytest tests/integration/test_retell_api.py -v

To set up test data, create a conversation flow in your Retell dashboard
and set RETELL_TEST_FLOW_ID to its ID.
"""

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
def test_flow_id():
    """Get the test conversation flow ID."""
    flow_id = os.environ.get("RETELL_TEST_FLOW_ID")
    if not flow_id:
        pytest.skip("RETELL_TEST_FLOW_ID not set")
    return flow_id


class TestRetellConversationFlows:
    """Tests for Retell conversation flow API."""

    def test_list_conversation_flows(self, client):
        """Test listing conversation flows."""
        flows = list(client.conversation_flow.list())

        assert isinstance(flows, list)

    def test_get_conversation_flow(self, client, test_flow_id):
        """Test retrieving a specific conversation flow."""
        flow = client.conversation_flow.retrieve(test_flow_id)

        assert flow.conversation_flow_id == test_flow_id
        assert flow.start_node_id is not None
        assert flow.nodes is not None

    def test_conversation_flow_has_nodes(self, client, test_flow_id):
        """Test that retrieved flow has node structure."""
        flow = client.conversation_flow.retrieve(test_flow_id)

        assert len(flow.nodes) > 0
        for node in flow.nodes:
            assert node.id is not None
            assert node.instruction is not None


class TestRetellImportExportRoundtrip:
    """Tests for importing from and exporting to Retell."""

    @pytest.mark.asyncio
    async def test_import_conversation_flow(self, client, test_flow_id):
        """Test importing a Retell conversation flow into voicetest."""
        from voicetest import api

        flow = client.conversation_flow.retrieve(test_flow_id)
        flow_dict = flow.model_dump()

        graph = await api.import_agent(flow_dict)

        assert graph.source_type == "retell"
        assert graph.entry_node_id == flow.start_node_id
        assert len(graph.nodes) == len(flow.nodes)

    @pytest.mark.asyncio
    async def test_export_to_retell_cf_format(self, client, test_flow_id):
        """Test exporting voicetest graph to Retell CF format."""
        import json

        from voicetest import api

        flow = client.conversation_flow.retrieve(test_flow_id)
        flow_dict = flow.model_dump()

        graph = await api.import_agent(flow_dict)
        exported_json = await api.export_agent(graph, format="retell-cf")
        exported = json.loads(exported_json)

        assert "start_node_id" in exported
        assert "nodes" in exported
        assert exported["start_node_id"] == flow.start_node_id

    @pytest.mark.asyncio
    async def test_roundtrip_preserves_structure(self, client, test_flow_id):
        """Test that import/export roundtrip preserves flow structure."""
        import json

        from voicetest import api

        flow = client.conversation_flow.retrieve(test_flow_id)
        flow_dict = flow.model_dump()

        graph = await api.import_agent(flow_dict)
        exported_json = await api.export_agent(graph, format="retell-cf")
        exported = json.loads(exported_json)

        assert len(exported["nodes"]) == len(flow.nodes)

        original_node_ids = {n.id for n in flow.nodes}
        exported_node_ids = {n["id"] for n in exported["nodes"]}
        assert original_node_ids == exported_node_ids
