"""Base protocol and types for platform clients."""

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class PlatformClient(Protocol):
    """Protocol for platform SDK clients with lazy key loading.

    Platform clients handle credential management and SDK initialization
    for voice agent platforms like Retell, VAPI, and LiveKit.
    """

    @property
    def platform_name(self) -> str:
        """Platform identifier (retell, vapi, livekit)."""
        ...

    @property
    def env_key(self) -> str:
        """Environment variable name for API key."""
        ...

    def get_client(self, api_key: str | None = None) -> Any:
        """Get SDK client, loading key from env if not provided.

        Args:
            api_key: API key. Defaults to loading from environment.

        Returns:
            Configured SDK client.

        Raises:
            ValueError: If no API key available.
        """
        ...

    def list_agents(self, client: Any) -> list[dict[str, Any]]:
        """List agents from the platform.

        Args:
            client: SDK client from get_client().

        Returns:
            List of dicts with at least {"id": ..., "name": ...}.
        """
        ...

    def get_agent(self, client: Any, agent_id: str) -> dict[str, Any]:
        """Get agent config by ID.

        Args:
            client: SDK client from get_client().
            agent_id: Platform-specific agent identifier.

        Returns:
            Agent configuration dict.
        """
        ...

    def create_agent(
        self, client: Any, config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create agent on platform.

        Args:
            client: SDK client from get_client().
            config: Agent configuration (from exporter).
            name: Optional name for the agent.

        Returns:
            Dict with at least {"id": ..., "name": ...}.
        """
        ...

    def delete_agent(self, client: Any, agent_id: str) -> None:
        """Delete agent from platform.

        Args:
            client: SDK client from get_client().
            agent_id: Platform-specific agent identifier.
        """
        ...
