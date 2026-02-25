"""Tests for voicetest.platforms.retell module."""

from voicetest.platforms.retell import RetellPlatformClient


# Accepted tool types for Retell's create/update API
API_TOOL_TYPES = {"custom", "check_availability_cal", "book_appointment_cal"}


class TestRetellPlatformClient:
    """Tests for RetellPlatformClient."""

    def test_filter_tools_for_api_removes_end_call(self):
        tools = [
            {"type": "custom", "name": "lookup", "url": "https://example.com"},
            {"type": "end_call", "name": "end_call", "description": "End the call"},
        ]
        filtered = RetellPlatformClient.filter_tools_for_api(tools)
        assert len(filtered) == 1
        assert filtered[0]["name"] == "lookup"

    def test_filter_tools_for_api_removes_transfer_call(self):
        tools = [
            {"type": "custom", "name": "lookup", "url": "https://example.com"},
            {"type": "transfer_call", "name": "transfer", "description": "Transfer"},
        ]
        filtered = RetellPlatformClient.filter_tools_for_api(tools)
        assert len(filtered) == 1
        assert filtered[0]["name"] == "lookup"

    def test_filter_tools_for_api_keeps_custom_tools(self):
        tools = [
            {"type": "custom", "name": "lookup", "url": "https://example.com"},
            {"type": "custom", "name": "book", "url": "https://example.com/book"},
        ]
        filtered = RetellPlatformClient.filter_tools_for_api(tools)
        assert len(filtered) == 2

    def test_filter_tools_for_api_keeps_cal_tools(self):
        tools = [
            {
                "type": "check_availability_cal",
                "name": "check",
                "cal_api_key": "key",
                "event_type_id": 1,
            },
            {
                "type": "book_appointment_cal",
                "name": "book",
                "cal_api_key": "key",
                "event_type_id": 1,
            },
        ]
        filtered = RetellPlatformClient.filter_tools_for_api(tools)
        assert len(filtered) == 2

    def test_filter_tools_for_api_empty_list(self):
        filtered = RetellPlatformClient.filter_tools_for_api([])
        assert filtered == []

    def test_filter_tools_for_api_all_builtin(self):
        tools = [
            {"type": "end_call", "name": "end_call"},
            {"type": "transfer_call", "name": "transfer"},
        ]
        filtered = RetellPlatformClient.filter_tools_for_api(tools)
        assert filtered == []

    def test_prepare_config_for_api_filters_tools(self):
        config = {
            "start_node_id": "greeting",
            "nodes": [],
            "tools": [
                {"type": "custom", "name": "lookup", "url": "https://example.com"},
                {"type": "end_call", "name": "end_call"},
            ],
        }
        prepared = RetellPlatformClient.prepare_config_for_api(config)
        assert len(prepared["tools"]) == 1
        assert prepared["tools"][0]["name"] == "lookup"

    def test_prepare_config_for_api_strips_readonly_fields(self):
        config = {
            "start_node_id": "greeting",
            "nodes": [],
            "tools": [],
            "conversation_flow_id": "cf_123",
            "version": 2,
        }
        prepared = RetellPlatformClient.prepare_config_for_api(config)
        assert "conversation_flow_id" not in prepared
        assert "version" not in prepared

    def test_filter_tools_for_api_removes_by_name(self):
        """Built-in tools should be filtered even if type is 'custom'."""
        tools = [
            {"type": "custom", "name": "lookup", "url": "https://example.com"},
            {"type": "custom", "name": "end_call", "description": ""},
            {"type": "custom", "name": "transfer_call_to_person", "description": "Transfer"},
        ]
        filtered = RetellPlatformClient.filter_tools_for_api(tools)
        assert len(filtered) == 1
        assert filtered[0]["name"] == "lookup"

    def test_prepare_config_for_api_preserves_other_fields(self):
        config = {
            "start_node_id": "greeting",
            "nodes": [{"id": "greeting"}],
            "tools": [],
            "model_choice": {"type": "cascading", "model": "gpt-4o"},
            "start_speaker": "agent",
        }
        prepared = RetellPlatformClient.prepare_config_for_api(config)
        assert prepared["start_node_id"] == "greeting"
        assert prepared["model_choice"]["type"] == "cascading"
        assert prepared["start_speaker"] == "agent"
