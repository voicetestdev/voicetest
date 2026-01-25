"""VAPI AI client management.

Handles credential loading and SDK client creation.
Requires: pip install voicetest[platforms]
"""

from __future__ import annotations

from collections.abc import Callable
import os
from typing import TYPE_CHECKING, Any

from vapi import Vapi


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph
    from voicetest.platforms.base import SourceImporter


class VapiPlatformClient:
    """VAPI platform client implementing PlatformClient protocol."""

    @property
    def platform_name(self) -> str:
        """Platform identifier."""
        return "vapi"

    @property
    def env_key(self) -> str:
        """Environment variable name for API key."""
        return "VAPI_API_KEY"

    @property
    def required_env_keys(self) -> list[str]:
        """All environment variable names required for this platform."""
        return [self.env_key]

    def get_importer(self) -> SourceImporter:
        """Get the importer for this platform."""
        from voicetest.importers.vapi import VapiImporter

        return VapiImporter()

    def get_exporter(self) -> Callable[[AgentGraph], dict[str, Any]]:
        """Get the exporter function for this platform."""
        from voicetest.exporters.vapi import export_vapi_assistant

        return export_vapi_assistant

    def get_client(self, api_key: str | None = None) -> Vapi:
        """Get a configured VAPI SDK client.

        Args:
            api_key: VAPI API key. Defaults to VAPI_API_KEY env var.

        Returns:
            Configured Vapi client.

        Raises:
            ValueError: If no API key available.
        """
        key = api_key or os.environ.get(self.env_key)
        if not key:
            raise ValueError(f"{self.env_key} not set")
        return Vapi(token=key)

    def list_agents(self, client: Vapi) -> list[dict[str, Any]]:
        """List assistants from VAPI.

        Args:
            client: VAPI SDK client.

        Returns:
            List of dicts with id and name fields.
        """
        assistants = client.assistants.list()
        return [
            {
                "id": asst.id,
                "name": asst.name or asst.id,
            }
            for asst in assistants
        ]

    def get_agent(self, client: Vapi, agent_id: str) -> dict[str, Any]:
        """Get an assistant by ID.

        Args:
            client: VAPI SDK client.
            agent_id: Assistant ID.

        Returns:
            Assistant configuration dict.
        """
        assistant = client.assistants.get(agent_id)
        return assistant.model_dump()

    def create_agent(
        self, client: Vapi, config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create an assistant in VAPI.

        Args:
            client: VAPI SDK client.
            config: Assistant configuration (from export_vapi_assistant).
            name: Optional name override for the assistant.

        Returns:
            Dict with id, name, and platform fields.
        """
        if name:
            config["name"] = name
        assistant = client.assistants.create(**config)
        return {
            "id": assistant.id,
            "name": assistant.name or assistant.id,
            "platform": self.platform_name,
        }

    def delete_agent(self, client: Vapi, agent_id: str) -> None:
        """Delete an assistant from VAPI.

        Args:
            client: VAPI SDK client.
            agent_id: Assistant ID.
        """
        client.assistants.delete(agent_id)


def get_client(api_key: str | None = None) -> Vapi:
    """Get a configured VAPI SDK client.

    Args:
        api_key: VAPI API key. Defaults to VAPI_API_KEY env var.

    Returns:
        Configured Vapi client.

    Raises:
        ValueError: If no API key available.
    """
    return VapiPlatformClient().get_client(api_key)
