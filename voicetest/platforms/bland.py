"""Bland AI client management.

Handles credential loading and SDK client creation.
Requires: pip install voicetest[platforms]
"""

from __future__ import annotations

from collections.abc import Callable
import os
from typing import TYPE_CHECKING
from typing import Any

from bland.client import BlandAI
import httpx

from voicetest.exporters.bland import export_bland_config
from voicetest.importers.bland import BlandImporter


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph
    from voicetest.platforms.base import SourceImporter

BLAND_API_BASE = "https://api.bland.ai/v1"


class BlandPlatformClient:
    """Bland AI platform client implementing PlatformClient protocol."""

    @property
    def platform_name(self) -> str:
        """Platform identifier."""
        return "bland"

    @property
    def env_key(self) -> str:
        """Environment variable name for API key."""
        return "BLAND_API_KEY"

    @property
    def required_env_keys(self) -> list[str]:
        """All environment variable names required for this platform."""
        return [self.env_key]

    def get_importer(self) -> SourceImporter:
        """Get the importer for this platform."""
        return BlandImporter()

    def get_exporter(self) -> Callable[[AgentGraph], dict[str, Any]]:
        """Get the exporter function for this platform."""
        return export_bland_config

    def get_client(self, api_key: str | None = None) -> BlandAI:
        """Get a configured Bland AI SDK client.

        Args:
            api_key: Bland API key. Defaults to BLAND_API_KEY env var.

        Returns:
            Configured BlandAI client.

        Raises:
            ValueError: If no API key available.
        """
        key = api_key or os.environ.get(self.env_key)
        if not key:
            raise ValueError(f"{self.env_key} not set")
        return BlandAI(api_key=key)

    def _get_api_key(self, client: BlandAI) -> str:
        """Extract API key from client for direct API calls."""
        return client._client_wrapper.api_key

    def list_agents(self, client: BlandAI) -> list[dict[str, Any]]:
        """List web agents from Bland AI.

        Note: Uses direct HTTP call due to SDK issues.

        Args:
            client: Bland AI SDK client.

        Returns:
            List of dicts with id and name fields.
        """
        api_key = self._get_api_key(client)
        response = httpx.get(
            f"{BLAND_API_BASE}/agents",
            headers={"Authorization": api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()
        return [
            {
                "id": agent.get("agent_id", ""),
                "name": agent.get("prompt", "")[:50] or agent.get("agent_id", ""),
            }
            for agent in data.get("agents", [])
        ]

    def get_agent(self, client: BlandAI, agent_id: str) -> dict[str, Any]:
        """Get a web agent configuration by ID.

        Note: Bland doesn't have a GET individual agent endpoint, so we
        fetch the list and find the agent by ID.

        Args:
            client: Bland AI SDK client.
            agent_id: Web agent ID.

        Returns:
            Agent configuration dict.

        Raises:
            ValueError: If agent not found.
        """
        api_key = self._get_api_key(client)
        response = httpx.get(
            f"{BLAND_API_BASE}/agents",
            headers={"Authorization": api_key},
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        for agent in data.get("agents", []):
            if agent.get("agent_id") == agent_id:
                return {
                    "prompt": agent.get("prompt", ""),
                    "voice": agent.get("voice"),
                    "webhook": agent.get("webhook"),
                    "first_sentence": agent.get("first_sentence"),
                    "max_duration": agent.get("max_duration"),
                    "model": agent.get("model"),
                    "tools": agent.get("tools"),
                }

        raise ValueError(f"Agent {agent_id} not found")

    def create_agent(
        self, client: BlandAI, config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create a web agent in Bland AI.

        Args:
            client: Bland AI SDK client.
            config: Agent configuration with prompt, tools, etc.
            name: Optional name (used in prompt prefix if provided).

        Returns:
            Dict with id, name, and platform fields.
        """
        api_key = self._get_api_key(client)

        prompt = config.get("prompt", "")
        if name and not prompt.startswith(name):
            prompt = f"Agent: {name}\n\n{prompt}"

        payload: dict[str, Any] = {"prompt": prompt}

        if config.get("first_sentence"):
            payload["first_sentence"] = config["first_sentence"]
        if config.get("tools"):
            payload["tools"] = config["tools"]
        if config.get("model"):
            payload["model"] = config["model"]
        if config.get("voice"):
            payload["voice"] = config["voice"]
        if config.get("webhook"):
            payload["webhook"] = config["webhook"]
        if config.get("max_duration"):
            payload["max_duration"] = config["max_duration"]

        response = httpx.post(
            f"{BLAND_API_BASE}/agents",
            headers={"Authorization": api_key, "Content-Type": "application/json"},
            json=payload,
            timeout=30.0,
        )
        response.raise_for_status()
        data = response.json()

        agent_id = data.get("agent_id") or data.get("agent", {}).get("agent_id", "")
        return {
            "id": agent_id,
            "name": name or agent_id,
            "platform": self.platform_name,
        }

    def delete_agent(self, client: BlandAI, agent_id: str) -> None:
        """Delete a web agent from Bland AI.

        Uses POST /v1/agents/{agent_id}/delete endpoint.

        Args:
            client: Bland AI SDK client.
            agent_id: Web agent ID.

        Raises:
            httpx.HTTPStatusError: If deletion fails.
        """
        api_key = self._get_api_key(client)
        response = httpx.post(
            f"{BLAND_API_BASE}/agents/{agent_id}/delete",
            headers={"Authorization": api_key},
            timeout=30.0,
        )
        response.raise_for_status()

    @property
    def supports_update(self) -> bool:
        """Bland does not support updating agents in place."""
        return False

    @property
    def remote_id_key(self) -> None:
        """Bland does not track remote agent IDs."""
        return None

    def update_agent(
        self, client: BlandAI, agent_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Not supported for Bland AI.

        Raises:
            NotImplementedError: Always, as Bland doesn't support updates.
        """
        raise NotImplementedError("Bland AI does not support updating agents in place")


def get_client(api_key: str | None = None) -> BlandAI:
    """Get a configured Bland AI SDK client.

    Args:
        api_key: Bland API key. Defaults to BLAND_API_KEY env var.

    Returns:
        Configured BlandAI client.

    Raises:
        ValueError: If no API key available.
    """
    return BlandPlatformClient().get_client(api_key)
