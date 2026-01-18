"""Integration tests for WebSocket connections.

These tests require a running backend server.
Run with: uv run voicetest serve & uv run pytest tests/integration/test_websocket.py -v
"""

import pytest


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
    async def test_websocket_real_connection_receives_state(self, sample_retell_config):
        """Test that a real WebSocket connection receives state message.

        This simulates what the browser does when connecting from a different origin.
        Requires backend running on port 8000.
        """
        import asyncio
        import json
        import socket

        import httpx
        import websockets

        # Check if server is running
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.settimeout(1)
                s.connect(("127.0.0.1", 8000))
        except (TimeoutError, ConnectionRefusedError):
            pytest.skip(
                "Backend server not running on port 8000. Start with: uv run voicetest serve"
            )

        base_url = "http://127.0.0.1:8000"
        ws_url = "ws://127.0.0.1:8000"

        async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
            # Create an agent
            agent_resp = await client.post(
                "/api/agents",
                json={"name": "WS Real Test", "config": sample_retell_config},
            )
            assert agent_resp.status_code == 200, f"Failed to create agent: {agent_resp.text}"
            agent_id = agent_resp.json()["id"]

            # Create a test case
            test_resp = await client.post(
                f"/api/agents/{agent_id}/tests",
                json={"name": "Test 1", "user_prompt": "Hello", "metrics": []},
            )
            assert test_resp.status_code == 200
            test_id = test_resp.json()["id"]

            # Start a run
            run_resp = await client.post(
                f"/api/agents/{agent_id}/runs",
                json={"test_ids": [test_id]},
            )
            assert run_resp.status_code == 200
            run_id = run_resp.json()["id"]

            # Connect via real WebSocket (simulating browser)
            ws_endpoint = f"{ws_url}/api/runs/{run_id}/ws"
            try:
                async with websockets.connect(ws_endpoint, open_timeout=5) as ws:
                    # Should receive state message
                    msg = await asyncio.wait_for(ws.recv(), timeout=5)
                    data = json.loads(msg)

                    assert data["type"] == "state", f"Expected state message, got: {data}"
                    assert data["run"]["id"] == run_id
                    assert "results" in data["run"]
                    result_count = len(data["run"]["results"])
                    print(f"WebSocket test passed! Received state with {result_count} results")
            except Exception as e:
                pytest.fail(f"WebSocket connection failed: {type(e).__name__}: {e}")

            # Clean up - delete the agent
            await client.delete(f"/api/agents/{agent_id}")
