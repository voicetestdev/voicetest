"""Shared fixtures for integration tests that hit a running server.

Unit tests use _isolate_db (root conftest) which swaps VOICETEST_DB_PATH for
a temp file. That works because the test and the app share the same process.

Integration tests that connect to a *running* server over HTTP can't use that
trick — the server has its own DB connection. This module provides tracked
client fixtures that record every agent created via the REST API and delete
them during teardown, regardless of whether the test passed or failed.
"""

import contextlib
import socket

import httpx
import pytest


def _server_reachable(host: str = "127.0.0.1", port: int = 8000) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            s.connect((host, port))
        return True
    except (TimeoutError, ConnectionRefusedError, OSError):
        return False


# ---------------------------------------------------------------------------
# Async variant (for @pytest.mark.asyncio tests)
# ---------------------------------------------------------------------------


class TrackedClient:
    """Async HTTP client that records created agent IDs for auto-cleanup."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self._client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self._agent_ids: list[str] = []

    async def create_agent(self, name: str, config: dict) -> dict:
        """POST /api/agents and track the created agent for cleanup."""
        resp = await self._client.post(
            "/api/agents",
            json={"name": name, "config": config},
        )
        resp.raise_for_status()
        data = resp.json()
        self._agent_ids.append(data["id"])
        return data

    async def create_demo_agent(self) -> dict:
        """POST /api/demo and track the created agent for cleanup."""
        resp = await self._client.post("/api/demo")
        resp.raise_for_status()
        data = resp.json()
        self._agent_ids.append(data["agent_id"])
        return data

    async def get(self, url: str, **kwargs):
        return await self._client.get(url, **kwargs)

    async def post(self, url: str, **kwargs):
        return await self._client.post(url, **kwargs)

    async def put(self, url: str, **kwargs):
        return await self._client.put(url, **kwargs)

    async def delete(self, url: str, **kwargs):
        return await self._client.delete(url, **kwargs)

    async def cleanup(self):
        """Delete all tracked agents, then close the HTTP client."""
        for agent_id in self._agent_ids:
            with contextlib.suppress(Exception):
                await self._client.delete(f"/api/agents/{agent_id}")
        self._agent_ids.clear()
        await self._client.aclose()


@pytest.fixture
async def api_client():
    """Async TrackedClient that auto-cleans agents on teardown.

    Skips the test if the backend server is not running on port 8000.
    """
    if not _server_reachable():
        pytest.skip("Backend server not running on port 8000")

    client = TrackedClient()
    try:
        yield client
    finally:
        await client.cleanup()


# ---------------------------------------------------------------------------
# Sync variant (for non-async tests that hit a running server)
# ---------------------------------------------------------------------------


class SyncTrackedClient:
    """Sync HTTP client that records created agent IDs for auto-cleanup."""

    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self._client = httpx.Client(base_url=base_url, timeout=30.0)
        self._agent_ids: list[str] = []

    def create_agent(self, name: str, config: dict) -> dict:
        """POST /api/agents and track the created agent for cleanup."""
        resp = self._client.post(
            "/api/agents",
            json={"name": name, "config": config},
        )
        resp.raise_for_status()
        data = resp.json()
        self._agent_ids.append(data["id"])
        return data

    def create_demo_agent(self) -> dict:
        """POST /api/demo and track the created agent for cleanup."""
        resp = self._client.post("/api/demo")
        resp.raise_for_status()
        data = resp.json()
        self._agent_ids.append(data["agent_id"])
        return data

    def get(self, url: str, **kwargs):
        return self._client.get(url, **kwargs)

    def post(self, url: str, **kwargs):
        return self._client.post(url, **kwargs)

    def put(self, url: str, **kwargs):
        return self._client.put(url, **kwargs)

    def delete(self, url: str, **kwargs):
        return self._client.delete(url, **kwargs)

    def cleanup(self):
        """Delete all tracked agents, then close the HTTP client."""
        for agent_id in self._agent_ids:
            with contextlib.suppress(Exception):
                self._client.delete(f"/api/agents/{agent_id}")
        self._agent_ids.clear()
        self._client.close()


@pytest.fixture
def sync_api_client():
    """Sync TrackedClient that auto-cleans agents on teardown.

    Skips the test if the backend server is not running on port 8000.
    """
    if not _server_reachable():
        pytest.skip("Backend server not running on port 8000")

    client = SyncTrackedClient()
    try:
        yield client
    finally:
        client.cleanup()
