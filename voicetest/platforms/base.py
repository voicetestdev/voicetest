"""Base protocol and types for platform clients."""

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph


@runtime_checkable
class SourceImporter(Protocol):
    """Protocol for source importers."""

    @property
    def source_type(self) -> str:
        """Source type identifier."""
        ...

    def can_import(self, path_or_config: Any) -> bool:
        """Check if this importer can handle the given input."""
        ...

    def import_agent(self, path_or_config: Any) -> "AgentGraph":
        """Import agent configuration to AgentGraph."""
        ...


@runtime_checkable
class PlatformClient(Protocol):
    """Protocol for platform SDK clients with lazy key loading.

    Platform clients handle credential management and SDK initialization
    for voice agent platforms like Retell, VAPI, LiveKit, and Bland.
    """

    @property
    def platform_name(self) -> str:
        """Platform identifier (retell, vapi, livekit, bland)."""
        ...

    @property
    def env_key(self) -> str:
        """Primary environment variable name for API key."""
        ...

    @property
    def required_env_keys(self) -> list[str]:
        """All environment variable names required for this platform.

        Most platforms need just one key, but some (like LiveKit)
        require multiple (API key + secret).

        Returns:
            List of required environment variable names.
        """
        ...

    def get_importer(self) -> SourceImporter | None:
        """Get the importer for this platform.

        Returns:
            Importer instance, or None if platform doesn't support import.
        """
        ...

    def get_exporter(self) -> Callable[["AgentGraph"], dict[str, Any]] | None:
        """Get the exporter function for this platform.

        Returns:
            Exporter function, or None if platform doesn't support export.
        """
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

    @property
    def supports_update(self) -> bool:
        """Whether this platform supports updating agents in place.

        Returns:
            True if update_agent() is implemented, False otherwise.
        """
        ...

    @property
    def remote_id_key(self) -> str | None:
        """Key in source_metadata that holds the remote agent ID.

        For example, 'conversation_flow_id' for Retell, 'assistant_id' for VAPI.

        Returns:
            Metadata key string, or None if platform doesn't track remote IDs.
        """
        ...

    def update_agent(self, client: Any, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update an existing agent on the platform.

        Args:
            client: SDK client from get_client().
            agent_id: Platform-specific agent identifier.
            config: Agent configuration (from exporter).

        Returns:
            Dict with at least {"id": ..., "name": ...}.

        Raises:
            NotImplementedError: If platform doesn't support updates.
        """
        ...
