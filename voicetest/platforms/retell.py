"""Retell AI client management.

Handles credential loading and SDK client creation.
Requires: pip install voicetest[platforms]
"""

import os
from typing import Any

from retell import Retell


class RetellPlatformClient:
    """Retell platform client implementing PlatformClient protocol."""

    @property
    def platform_name(self) -> str:
        """Platform identifier."""
        return "retell"

    @property
    def env_key(self) -> str:
        """Environment variable name for API key."""
        return "RETELL_API_KEY"

    def get_client(self, api_key: str | None = None) -> Retell:
        """Get a configured Retell SDK client.

        Args:
            api_key: Retell API key. Defaults to RETELL_API_KEY env var.

        Returns:
            Configured Retell client.

        Raises:
            ValueError: If no API key available.
        """
        key = api_key or os.environ.get(self.env_key)
        if not key:
            raise ValueError(f"{self.env_key} not set")
        return Retell(api_key=key)

    def list_agents(self, client: Retell) -> list[dict[str, Any]]:
        """List conversation flows from Retell.

        Args:
            client: Retell SDK client.

        Returns:
            List of dicts with id and name fields.
        """
        flows = client.conversation_flow.list()
        return [
            {
                "id": flow.conversation_flow_id,
                "name": getattr(flow, "conversation_flow_name", None) or flow.conversation_flow_id,
            }
            for flow in flows
        ]

    def get_agent(self, client: Retell, agent_id: str) -> dict[str, Any]:
        """Get a conversation flow by ID.

        Args:
            client: Retell SDK client.
            agent_id: Conversation flow ID.

        Returns:
            Flow configuration dict.
        """
        flow = client.conversation_flow.retrieve(agent_id)
        return flow.model_dump()

    def create_agent(
        self, client: Retell, config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create a conversation flow in Retell.

        Note: Retell API does not support naming flows on creation.

        Args:
            client: Retell SDK client.
            config: Flow configuration (from export_retell_cf).
            name: Ignored - Retell doesn't support naming on create.

        Returns:
            Dict with id, name, and platform fields.
        """
        flow = client.conversation_flow.create(**config)
        return {
            "id": flow.conversation_flow_id,
            "name": name or flow.conversation_flow_id,
            "platform": self.platform_name,
        }

    def delete_agent(self, client: Retell, agent_id: str) -> None:
        """Delete a conversation flow from Retell.

        Args:
            client: Retell SDK client.
            agent_id: Conversation flow ID.
        """
        client.conversation_flow.delete(agent_id)


def get_client(api_key: str | None = None) -> Retell:
    """Get a configured Retell SDK client.

    Args:
        api_key: Retell API key. Defaults to RETELL_API_KEY env var.

    Returns:
        Configured Retell client.

    Raises:
        ValueError: If no API key available.
    """
    return RetellPlatformClient().get_client(api_key)
