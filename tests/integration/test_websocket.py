"""Integration tests for WebSocket connections.

These tests require a running backend server.
Run with: uv run voicetest serve & uv run pytest tests/integration/test_websocket.py -v
"""

import asyncio
import json

import pytest
import websockets


@pytest.fixture
def sample_retell_config():
    """Sample Retell LLM config for testing."""
    return {
        "llm_id": "test-llm-123",
        "model": "gpt-4",
        "general_prompt": "You are a helpful assistant.",
        "states": [
            {
                "name": "greeting",
                "state_prompt": "Greet the user warmly.",
                "edges": [
                    {"description": "User asks a question", "destination_state_name": "answer"}
                ],
            },
            {
                "name": "answer",
                "state_prompt": "Answer the user's question.",
                "edges": [{"description": "Conversation ends", "destination_state_name": "end"}],
            },
            {
                "name": "end",
                "state_prompt": "Say goodbye.",
                "edges": [],
            },
        ],
        "starting_state": "greeting",
    }


class TestWebSocketRealConnection:
    """Integration tests for WebSocket using real network connections.

    These tests require a running server on port 8000.
    Run with: uv run voicetest serve & uv run pytest tests/integration/test_websocket.py -v
    """

    @pytest.mark.asyncio
    async def test_websocket_real_connection_receives_state(self, api_client, sample_retell_config):
        """Test that a real WebSocket connection receives state message.

        This simulates what the browser does when connecting from a different origin.
        Requires backend running on port 8000.
        """
        ws_url = "ws://127.0.0.1:8000"

        # Create an agent (auto-cleaned by api_client fixture)
        agent_data = await api_client.create_agent("WS Real Test", sample_retell_config)
        agent_id = agent_data["id"]

        # Create a test case
        test_resp = await api_client.post(
            f"/api/agents/{agent_id}/tests",
            json={"name": "Test 1", "user_prompt": "Hello", "metrics": []},
        )
        assert test_resp.status_code == 200
        test_id = test_resp.json()["id"]

        # Start a run
        run_resp = await api_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": [test_id]},
        )
        assert run_resp.status_code == 200
        run_id = run_resp.json()["id"]

        # Connect via real WebSocket (simulating browser)
        ws_endpoint = f"{ws_url}/api/runs/{run_id}/ws"
        async with websockets.connect(ws_endpoint, open_timeout=5) as ws:
            # Should receive state message
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)

            assert data["type"] == "state", f"Expected state message, got: {data}"
            assert data["run"]["id"] == run_id
            assert "results" in data["run"]
