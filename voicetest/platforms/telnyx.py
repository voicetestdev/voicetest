"""Telnyx AI assistant platform client.

Handles credential loading and SDK client creation.
Requires: telnyx package.
"""

from __future__ import annotations

from collections.abc import Callable
import os
from typing import TYPE_CHECKING
from typing import Any

import telnyx

from voicetest.exporters.telnyx import export_telnyx_config
from voicetest.importers.telnyx import TelnyxImporter


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph
    from voicetest.platforms.base import SourceImporter


class TelnyxPlatformClient:
    """Telnyx AI platform client implementing PlatformClient protocol."""

    @property
    def platform_name(self) -> str:
        """Platform identifier."""
        return "telnyx"

    @property
    def env_key(self) -> str:
        """Environment variable name for API key."""
        return "TELNYX_API_KEY"

    @property
    def required_env_keys(self) -> list[str]:
        """All environment variable names required for this platform."""
        return [self.env_key]

    def get_importer(self) -> SourceImporter:
        """Get the importer for this platform."""
        return TelnyxImporter()

    def get_exporter(self) -> Callable[[AgentGraph], dict[str, Any]]:
        """Get the exporter function for this platform."""
        return export_telnyx_config

    def get_client(self, api_key: str | None = None) -> telnyx.Telnyx:
        """Get a configured Telnyx SDK client.

        Args:
            api_key: Telnyx API key. Defaults to TELNYX_API_KEY env var.

        Returns:
            Configured Telnyx client.

        Raises:
            ValueError: If no API key available.
        """
        key = api_key or os.environ.get(self.env_key)
        if not key:
            raise ValueError(f"{self.env_key} not set")
        return telnyx.Telnyx(api_key=key)

    def list_agents(self, client: telnyx.Telnyx) -> list[dict[str, Any]]:
        """List AI assistants from Telnyx.

        Args:
            client: Telnyx SDK client.

        Returns:
            List of dicts with id and name fields.
        """
        response = client.ai.assistants.list()
        assistants = response.data if hasattr(response, "data") else []
        return [
            {
                "id": getattr(a, "id", ""),
                "name": getattr(a, "name", "") or getattr(a, "id", ""),
            }
            for a in assistants
        ]

    def get_agent(self, client: telnyx.Telnyx, agent_id: str) -> dict[str, Any]:
        """Get an AI assistant configuration by ID.

        Args:
            client: Telnyx SDK client.
            agent_id: Assistant ID.

        Returns:
            Assistant configuration dict.
        """
        response = client.ai.assistants.retrieve(agent_id)
        assistant = response if not hasattr(response, "data") else response.data

        result: dict[str, Any] = {}
        for field in [
            "id",
            "name",
            "instructions",
            "model",
            "greeting",
            "voice_settings",
            "transcription",
            "telephony_settings",
            "dynamic_variables",
            "tools",
        ]:
            value = getattr(assistant, field, None)
            if value is not None:
                result[field] = value

        return result

    def create_agent(
        self, client: telnyx.Telnyx, config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create an AI assistant in Telnyx.

        Args:
            client: Telnyx SDK client.
            config: Assistant configuration.
            name: Optional name override.

        Returns:
            Dict with id, name, and platform fields.
        """
        create_params: dict[str, Any] = {
            "instructions": config.get("instructions", ""),
            "model": config.get("model", "openai/gpt-4o"),
            "name": name or config.get("name", "Voicetest Assistant"),
        }

        for field in [
            "greeting",
            "voice_settings",
            "transcription",
            "telephony_settings",
            "dynamic_variables",
            "tools",
        ]:
            if field in config:
                create_params[field] = config[field]

        response = client.ai.assistants.create(**create_params)
        assistant = response if not hasattr(response, "data") else response.data
        assistant_id = getattr(assistant, "id", "")

        return {
            "id": assistant_id,
            "name": name or config.get("name", assistant_id),
            "platform": self.platform_name,
        }

    def delete_agent(self, client: telnyx.Telnyx, agent_id: str) -> None:
        """Delete an AI assistant from Telnyx.

        Args:
            client: Telnyx SDK client.
            agent_id: Assistant ID.
        """
        client.ai.assistants.delete(agent_id)

    def update_agent(
        self, client: telnyx.Telnyx, agent_id: str, config: dict[str, Any]
    ) -> dict[str, Any]:
        """Update an AI assistant in Telnyx.

        Args:
            client: Telnyx SDK client.
            agent_id: Assistant ID.
            config: Updated configuration.

        Returns:
            Dict with id, name, and platform fields.
        """
        update_params: dict[str, Any] = {}

        for field in [
            "instructions",
            "model",
            "name",
            "greeting",
            "voice_settings",
            "transcription",
            "telephony_settings",
            "dynamic_variables",
            "tools",
        ]:
            if field in config:
                update_params[field] = config[field]

        response = client.ai.assistants.update(agent_id, **update_params)
        assistant = response if not hasattr(response, "data") else response.data
        assistant_name = getattr(assistant, "name", "") or agent_id

        return {
            "id": agent_id,
            "name": assistant_name,
            "platform": self.platform_name,
        }

    @property
    def supports_update(self) -> bool:
        """Telnyx supports updating assistants in place."""
        return True

    @property
    def remote_id_key(self) -> str:
        """Key for tracking remote assistant IDs."""
        return "telnyx_assistant_id"


def get_client(api_key: str | None = None) -> telnyx.Telnyx:
    """Get a configured Telnyx SDK client.

    Args:
        api_key: Telnyx API key. Defaults to TELNYX_API_KEY env var.

    Returns:
        Configured Telnyx client.

    Raises:
        ValueError: If no API key available.
    """
    return TelnyxPlatformClient().get_client(api_key)
