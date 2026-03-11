"""Integration tests for live voice calls running inside Docker.

These tests verify the agent worker subprocess works correctly in the Docker environment.

Run with: uv run pytest tests/integration/test_calls_docker.py -v
Requires: docker compose -f docker-compose.dev.yml up -d
"""

import json
import subprocess
import time

import pytest


def docker_compose_running() -> bool:
    """Check if docker compose services are running."""
    try:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.dev.yml", "ps", "--format", "json"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return False
        # Check if backend is running
        services = result.stdout.strip()
        return "backend" in services and "running" in services.lower()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


pytestmark = pytest.mark.skipif(
    not docker_compose_running(),
    reason="Docker compose not running. Start with: docker compose -f docker-compose.dev.yml up -d",
)


class TestAgentWorkerInDocker:
    """Tests for agent worker subprocess inside Docker container."""

    @pytest.fixture
    def simple_graph_json(self) -> str:
        """Create a simple agent graph JSON for testing."""
        graph = {
            "source_type": "custom",
            "entry_node_id": "greeting",
            "nodes": {
                "greeting": {
                    "id": "greeting",
                    "state_prompt": "You are a helpful assistant. Say hello.",
                    "transitions": [],
                    "tools": [],
                    "metadata": {},
                }
            },
        }
        return json.dumps(graph)

    def test_agent_worker_starts_in_docker(self, simple_graph_json):
        """Agent worker subprocess starts and outputs status inside Docker."""
        # Run agent worker inside the backend container
        cmd = [
            "docker",
            "compose",
            "-f",
            "docker-compose.dev.yml",
            "exec",
            "-T",  # No TTY
            "backend",
            "uv",
            "run",
            "python",
            "-m",
            "voicetest.agent_worker",
            "--room",
            "test-room-docker",
            "--url",
            "ws://livekit:7880",
            "--token",
            "invalid-token",  # Will fail to connect but should start
            "--backend",
            "local",
            "--whisper-url",
            "http://whisper:8000/v1",
            "--kokoro-url",
            "http://kokoro:8880/v1",
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send graph JSON and wait for output
        stdout, stderr = process.communicate(input=simple_graph_json, timeout=30)

        print(f"stdout: {stdout}")
        print(f"stderr: {stderr}")

        # Should output status messages
        assert stdout, f"No stdout. stderr: {stderr}"
        lines = [line for line in stdout.strip().split("\n") if line.strip()]
        assert len(lines) > 0, f"No output lines. stderr: {stderr}"

        # First JSON line should be connecting status
        first_msg = json.loads(lines[0])
        assert first_msg["type"] == "status", f"Unexpected first message: {first_msg}"
        assert first_msg["status"] == "connecting", f"Expected connecting status: {first_msg}"

    def test_agent_worker_connects_to_livekit_in_docker(self, simple_graph_json):
        """Agent worker connects to LiveKit server inside Docker network."""
        # First generate a valid token using the backend
        token_cmd = [
            "docker",
            "compose",
            "-f",
            "docker-compose.dev.yml",
            "exec",
            "-T",
            "backend",
            "uv",
            "run",
            "python",
            "-c",
            """
from livekit import api as livekit_api
grant = livekit_api.VideoGrants(
    room_join=True,
    room="test-room-docker-connect",
    can_publish=True,
    can_subscribe=True,
    can_publish_data=True,
    agent=True,
)
token = (
    livekit_api.AccessToken("devkey", "secret")
    .with_identity("agent")
    .with_grants(grant)
)
print(token.to_jwt())
""",
        ]

        token_result = subprocess.run(
            token_cmd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert token_result.returncode == 0, f"Failed to generate token: {token_result.stderr}"
        token = token_result.stdout.strip().split("\n")[-1]  # Get last line (the token)

        # Now run agent worker with valid token
        cmd = [
            "docker",
            "compose",
            "-f",
            "docker-compose.dev.yml",
            "exec",
            "-T",
            "backend",
            "uv",
            "run",
            "python",
            "-m",
            "voicetest.agent_worker",
            "--room",
            "test-room-docker-connect",
            "--url",
            "ws://livekit:7880",
            "--token",
            token,
            "--backend",
            "local",
            "--whisper-url",
            "http://whisper:8000/v1",
            "--kokoro-url",
            "http://kokoro:8880/v1",
        ]

        process = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Send graph JSON
        process.stdin.write(simple_graph_json)
        process.stdin.close()

        # Read output with timeout, looking for status messages
        statuses = []
        errors = []
        start_time = time.time()
        timeout = 30

        try:
            while time.time() - start_time < timeout:
                line = process.stdout.readline()
                if not line:
                    if process.poll() is not None:
                        break
                    time.sleep(0.1)
                    continue

                line = line.strip()
                if not line:
                    continue

                print(f"Output: {line}")

                try:
                    msg = json.loads(line)
                    if msg.get("type") == "status":
                        statuses.append(msg["status"])
                        if msg["status"] == "active":
                            break
                    elif msg.get("type") == "error":
                        errors.append(msg["message"])
                        break
                except json.JSONDecodeError:
                    pass

        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

        # Get stderr
        stderr = process.stderr.read()
        print(f"stderr: {stderr}")

        # Verify statuses
        assert "connecting" in statuses, (
            f"Expected 'connecting'. Got: {statuses}. Errors: {errors}. stderr: {stderr}"
        )
        assert "connected" in statuses or "active" in statuses, (
            f"Expected 'connected' or 'active'. Got: {statuses}. Errors: {errors}. stderr: {stderr}"
        )


class TestCallAPIInDocker:
    """Tests for the call REST API through Docker."""

    def test_livekit_status_endpoint(self, sync_api_client):
        """LiveKit status endpoint returns available=true."""
        response = sync_api_client.get("/api/livekit/status")

        assert response.status_code == 200
        data = response.json()
        assert data["available"] is True, f"LiveKit not available: {data}"

    def test_start_call_endpoint(self, sync_api_client):
        """Start call endpoint returns connection info."""
        # Create demo agent (auto-cleaned by sync_api_client fixture)
        demo_data = sync_api_client.create_demo_agent()
        agent_id = demo_data["agent_id"]

        # Now start a call
        response = sync_api_client.post(f"/api/agents/{agent_id}/calls/start")

        assert response.status_code == 200, f"Failed to start call: {response.text}"
        data = response.json()

        assert "call_id" in data
        assert "room_name" in data
        assert "livekit_url" in data
        assert "token" in data

        # End the call
        call_id = data["call_id"]
        end_response = sync_api_client.post(f"/api/calls/{call_id}/end")
        assert end_response.status_code == 200

    def test_call_produces_agent_worker_output(self, sync_api_client):
        """Starting a call spawns agent worker that produces output."""
        # Create demo agent (auto-cleaned by sync_api_client fixture)
        demo_data = sync_api_client.create_demo_agent()
        agent_id = demo_data["agent_id"]

        # Start call
        start_response = sync_api_client.post(f"/api/agents/{agent_id}/calls/start")
        assert start_response.status_code == 200
        call_id = start_response.json()["call_id"]

        # Wait a moment for the agent to start
        time.sleep(2)

        # Check call status
        status_response = sync_api_client.get(f"/api/calls/{call_id}")
        assert status_response.status_code == 200
        call_data = status_response.json()

        print(f"Call status: {call_data}")

        # The call should be in connecting or active status
        assert call_data["status"] in ["connecting", "active", "ended"], (
            f"Unexpected call status: {call_data['status']}"
        )

        # End the call
        sync_api_client.post(f"/api/calls/{call_id}/end")

    def test_backend_logs_show_agent_worker_spawn(self, sync_api_client):
        """Backend logs should show agent-worker spawn command."""
        # Create demo agent (auto-cleaned by sync_api_client fixture)
        demo_data = sync_api_client.create_demo_agent()
        agent_id = demo_data["agent_id"]

        # Start call
        start_response = sync_api_client.post(f"/api/agents/{agent_id}/calls/start")
        assert start_response.status_code == 200
        call_id = start_response.json()["call_id"]

        # Wait for subprocess to start
        time.sleep(2)

        # Check docker logs for agent-worker output
        logs_result = subprocess.run(
            [
                "docker",
                "compose",
                "-f",
                "docker-compose.dev.yml",
                "logs",
                "backend",
                "--tail",
                "50",
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )

        print(f"Backend logs:\n{logs_result.stdout}")

        # Look for our spawn log line
        assert "[agent-worker]" in logs_result.stdout, (
            f"Expected agent-worker log. Logs:\n{logs_result.stdout}"
        )

        # End the call
        sync_api_client.post(f"/api/calls/{call_id}/end")
