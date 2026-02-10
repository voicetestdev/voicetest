"""Integration tests for live voice calls.

Tests the agent worker subprocess and call management.

Run with: uv run pytest tests/integration/test_calls.py -v
"""

import json
import select
import subprocess
import sys
from unittest.mock import MagicMock

import pytest

from voicetest.models.agent import AgentGraph


def livekit_server_available() -> bool:
    """Check if LiveKit server is reachable at localhost:7880."""
    import socket

    try:
        with socket.create_connection(("localhost", 7880), timeout=1):
            return True
    except (TimeoutError, OSError):
        return False


@pytest.fixture
def simple_graph() -> AgentGraph:
    """Create a simple agent graph for testing."""
    return AgentGraph(
        source_type="custom",
        entry_node_id="greeting",
        nodes={
            "greeting": {
                "id": "greeting",
                "state_prompt": "You are a helpful assistant. Say hello.",
                "transitions": [],
                "tools": [],
                "metadata": {},
            }
        },
    )


class TestAgentWorkerSubprocess:
    """Tests for the agent worker subprocess startup."""

    def test_agent_worker_starts_and_outputs_status(self, simple_graph):
        """Agent worker subprocess starts and outputs connecting status."""
        graph_json = simple_graph.model_dump_json()

        # Run agent worker with invalid token (will fail to connect but should start)
        cmd = [
            sys.executable,
            "-m",
            "voicetest.agent_worker",
            "--room",
            "test-room",
            "--url",
            "ws://localhost:7880",
            "--token",
            "invalid-token",
            "--backend",
            "local",
            "--ollama-url",
            "http://localhost:11434/v1",
            "--whisper-url",
            "http://localhost:8001/v1",
            "--kokoro-url",
            "http://localhost:8002/v1",
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send graph JSON to stdin
        stdout, stderr = process.communicate(input=graph_json, timeout=10)

        # Should output status messages
        assert stdout, f"No stdout. stderr: {stderr}"
        lines = stdout.strip().split("\n")
        assert len(lines) > 0, f"No output lines. stderr: {stderr}"

        # First line should be connecting status
        first_msg = json.loads(lines[0])
        assert first_msg["type"] == "status"
        assert first_msg["status"] == "connecting"

    def test_agent_worker_handles_invalid_graph(self):
        """Agent worker exits with error for invalid graph JSON."""
        cmd = [
            sys.executable,
            "-m",
            "voicetest.agent_worker",
            "--room",
            "test-room",
            "--url",
            "ws://localhost:7880",
            "--token",
            "test-token",
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send invalid JSON
        stdout, stderr = process.communicate(input="not-valid-json", timeout=10)

        # Should output error
        assert stdout
        msg = json.loads(stdout.strip().split("\n")[0])
        assert msg["type"] == "error"
        assert "Invalid agent graph" in msg["message"]
        assert process.returncode == 1

    def test_agent_worker_handles_empty_stdin(self):
        """Agent worker exits with error when no graph is provided."""
        cmd = [
            sys.executable,
            "-m",
            "voicetest.agent_worker",
            "--room",
            "test-room",
            "--url",
            "ws://localhost:7880",
            "--token",
            "test-token",
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send empty stdin
        stdout, stderr = process.communicate(input="", timeout=10)

        # Should output error
        assert stdout
        msg = json.loads(stdout.strip().split("\n")[0])
        assert msg["type"] == "error"
        assert "No agent graph" in msg["message"]
        assert process.returncode == 1


@pytest.mark.skipif(not livekit_server_available(), reason="LiveKit server not running")
class TestAgentWorkerWithLiveKit:
    """Tests that require a running LiveKit server."""

    def test_agent_worker_connects_to_livekit(self, simple_graph):
        """Agent worker connects to LiveKit and becomes active."""
        from livekit import api as livekit_api

        # Generate a valid token
        grant = livekit_api.VideoGrants(
            room_join=True,
            room="test-room-integration",
            can_publish=True,
            can_subscribe=True,
            can_publish_data=True,
            agent=True,
        )
        token = (
            livekit_api.AccessToken("devkey", "secret").with_identity("agent").with_grants(grant)
        )
        token_jwt = token.to_jwt()

        graph_json = simple_graph.model_dump_json()

        cmd = [
            sys.executable,
            "-m",
            "voicetest.agent_worker",
            "--room",
            "test-room-integration",
            "--url",
            "ws://localhost:7880",
            "--token",
            token_jwt,
            "--backend",
            "local",
            "--ollama-url",
            "http://localhost:11434/v1",
            "--whisper-url",
            "http://localhost:8001/v1",
            "--kokoro-url",
            "http://localhost:8002/v1",
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send graph and close stdin
        process.stdin.write(graph_json)
        process.stdin.close()

        # Read output lines with timeout
        statuses = []

        try:
            while True:
                # Use select to wait for output with timeout
                readable, _, _ = select.select([process.stdout], [], [], 1.0)
                if readable:
                    line = process.stdout.readline()
                    if not line:
                        break
                    try:
                        msg = json.loads(line.strip())
                        if msg.get("type") == "status":
                            statuses.append(msg["status"])
                            print(f"Status: {msg['status']}")
                            if msg["status"] == "active":
                                break
                        elif msg.get("type") == "error":
                            print(f"Error: {msg['message']}")
                            break
                    except json.JSONDecodeError:
                        pass

                # Check timeout
                if (not statuses or "active" not in statuses) and process.poll() is not None:
                    break
        except Exception as e:
            print(f"Exception reading output: {e}")
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

        # Get any remaining stderr
        stderr = process.stderr.read()
        if stderr:
            print(f"stderr: {stderr}")

        # Verify we got expected statuses
        assert "connecting" in statuses, (
            f"Expected 'connecting' status. Got: {statuses}. stderr: {stderr}"
        )
        assert "connected" in statuses or "active" in statuses, (
            f"Expected 'connected' or 'active' status. Got: {statuses}. stderr: {stderr}"
        )


class TestCallManager:
    """Tests for CallManager class."""

    @pytest.fixture
    def call_manager(self):
        """Create a CallManager for testing."""
        from voicetest.calls import CallManager, LiveKitConfig

        config = LiveKitConfig(
            url="ws://localhost:7880",
            public_url="ws://localhost:7880",
            api_key="devkey",
            api_secret="secret",
            voice_backend="local",
            ollama_url="http://localhost:11434/v1",
            whisper_url="http://localhost:8001/v1",
            kokoro_url="http://localhost:8002/v1",
        )
        return CallManager(config)

    @pytest.fixture
    def mock_call_repo(self):
        """Create a mock call repository."""
        repo = MagicMock()
        repo.create.return_value = {
            "id": "test-call-id",
            "agent_id": "test-agent-id",
            "room_name": "test-room",
            "status": "connecting",
            "started_at": "2024-01-01T00:00:00Z",
        }
        repo.update_status.return_value = None
        repo.update_transcript.return_value = None
        repo.end_call.return_value = {"id": "test-call-id", "status": "ended"}
        return repo

    def test_generate_token(self, call_manager):
        """CallManager generates valid JWT tokens."""
        token = call_manager.generate_token("test-room", "user", is_agent=False)

        assert token
        assert isinstance(token, str)
        # JWT tokens have 3 parts separated by dots
        assert len(token.split(".")) == 3

    def test_generate_agent_token(self, call_manager):
        """CallManager generates agent tokens with agent grant."""
        token = call_manager.generate_token("test-room", "agent", is_agent=True)

        assert token
        # Decode and verify (without verification since we don't have the secret here)
        import base64

        payload = token.split(".")[1]
        # Add padding if needed
        payload += "=" * (4 - len(payload) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(payload))

        assert decoded.get("video", {}).get("agent") is True

    @pytest.mark.skipif(not livekit_server_available(), reason="LiveKit server not running")
    @pytest.mark.asyncio
    async def test_create_room(self, call_manager):
        """CallManager can create a LiveKit room."""
        room_name = "test-room-create"

        # Should not raise
        await call_manager.create_room(room_name)

    @pytest.mark.skipif(not livekit_server_available(), reason="LiveKit server not running")
    @pytest.mark.asyncio
    async def test_start_call_spawns_subprocess(self, call_manager, mock_call_repo, simple_graph):
        """start_call spawns an agent worker subprocess."""
        call_info = await call_manager.start_call(
            agent_id="test-agent",
            graph=simple_graph,
            call_repo=mock_call_repo,
        )

        assert call_info["call_id"]
        assert call_info["room_name"]
        assert call_info["livekit_url"] == "ws://localhost:7880"
        assert call_info["token"]

        # Verify subprocess was started
        active_call = call_manager.get_active_call(call_info["call_id"])
        assert active_call is not None
        assert active_call.process is not None

        # Clean up
        await call_manager.end_call(call_info["call_id"], mock_call_repo)

    @pytest.mark.skipif(not livekit_server_available(), reason="LiveKit server not running")
    @pytest.mark.asyncio
    async def test_end_call_terminates_subprocess(self, call_manager, mock_call_repo, simple_graph):
        """end_call terminates the agent worker subprocess."""
        call_info = await call_manager.start_call(
            agent_id="test-agent",
            graph=simple_graph,
            call_repo=mock_call_repo,
        )

        active_call = call_manager.get_active_call(call_info["call_id"])
        process = active_call.process

        # End the call
        await call_manager.end_call(call_info["call_id"], mock_call_repo)

        # Process should be terminated
        assert process.poll() is not None

        # Active call should be removed
        assert call_manager.get_active_call(call_info["call_id"]) is None
