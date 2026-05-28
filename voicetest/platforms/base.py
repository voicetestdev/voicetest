"""Base protocol and types for platform clients."""

from collections.abc import Callable
from typing import TYPE_CHECKING
from typing import Any
from typing import Protocol
from typing import runtime_checkable

from voicetest.importers.base import SourceImporter


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph


@runtime_checkable
class PlatformClient(Protocol):
    """Protocol for platform SDK clients with lazy key loading."""

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
        """All environment variable names required for this platform."""
        ...

    def get_importer(self) -> SourceImporter | None:
        """Get the importer for this platform."""
        ...

    def get_exporter(self) -> Callable[["AgentGraph"], dict[str, Any]] | None:
        """Get the exporter function for this platform."""
        ...

    def get_client(self, api_key: str | None = None) -> Any:
        """Get SDK client, loading key from env if not provided."""
        ...

    def list_agents(self, client: Any) -> list[dict[str, Any]]:
        """List agents from the platform."""
        ...

    def get_agent(self, client: Any, agent_id: str) -> dict[str, Any]:
        """Get agent config by ID."""
        ...

    def create_agent(
        self, client: Any, config: dict[str, Any], name: str | None = None
    ) -> dict[str, Any]:
        """Create agent on platform."""
        ...

    def delete_agent(self, client: Any, agent_id: str) -> None:
        """Delete agent from platform."""
        ...

    @property
    def supports_update(self) -> bool:
        """Whether this platform supports updating agents in place."""
        ...

    @property
    def remote_id_key(self) -> str | None:
        """Key in source_metadata that holds the remote agent ID.

        For example, 'conversation_flow_id' for Retell, 'assistant_id' for VAPI."""
        ...

    def update_agent(self, client: Any, agent_id: str, config: dict[str, Any]) -> dict[str, Any]:
        """Update an existing agent on the platform."""
        ...
