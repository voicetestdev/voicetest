"""Platform service: integration with external voice agent platforms."""

from typing import Any

from voicetest.models.agent import AgentGraph
from voicetest.platforms.registry import PlatformRegistry
from voicetest.services.agents import AgentService
from voicetest.settings import load_settings
from voicetest.settings import save_settings


class PlatformService:
    """Manages platform integrations (Retell, Vapi, LiveKit, Bland, Telnyx)."""

    def __init__(
        self,
        platform_registry: PlatformRegistry,
        agent_service: AgentService,
    ):
        self._registry = platform_registry
        self._agents = agent_service

    def list_platforms(self) -> list[dict]:
        """List all platforms with configuration status."""
        settings = load_settings()
        return [
            {
                "name": name,
                "configured": self._registry.is_configured(name, settings),
                "env_key": self._registry.get_env_key(name),
                "required_env_keys": self._registry.get_required_env_keys(name),
            }
            for name in self._registry.list_platforms()
        ]

    def get_status(self, platform: str) -> dict:
        """Check if a platform API key is configured.

        Raises:
            ValueError: If platform is invalid.
        """
        self._validate_platform(platform)
        return {
            "configured": self._is_configured(platform),
            "platform": platform,
        }

    def configure(self, platform: str, api_key: str, api_secret: str | None = None) -> dict:
        """Configure platform credentials.

        Raises:
            ValueError: If platform is invalid or already configured.
        """
        self._validate_platform(platform)

        if self._is_configured(platform):
            raise ValueError(
                f"{platform} credentials are already configured. Use Settings to change them."
            )

        required_keys = self._registry.get_required_env_keys(platform)
        settings = load_settings()

        env_key = self._registry.get_env_key(platform)
        settings.env[env_key] = api_key

        if api_secret and len(required_keys) > 1:
            secret_keys = [k for k in required_keys if k.endswith("_SECRET")]
            if secret_keys:
                settings.env[secret_keys[0]] = api_secret

        save_settings(settings)
        settings.apply_env()

        return {"configured": True, "platform": platform}

    def list_remote_agents(self, platform: str) -> list[dict]:
        """List agents from a remote platform.

        Raises:
            ValueError: If platform is invalid or not configured.
        """
        platform_client, client = self._get_configured_client(platform)
        return platform_client.list_agents(client)

    def import_from_platform(self, platform: str, agent_id: str) -> AgentGraph:
        """Import an agent from a remote platform by ID.

        Raises:
            ValueError: If platform is invalid, not configured, or import fails.
        """
        platform_client, client = self._get_configured_client(platform)
        config = platform_client.get_agent(client, agent_id)
        importer = self._registry.get_importer(platform)
        if not importer:
            raise ValueError(f"No importer for platform: {platform}")
        return importer.import_agent(config)

    def export_to_platform(self, platform: str, graph: AgentGraph, name: str | None = None) -> dict:
        """Export an agent graph to a remote platform.

        Returns:
            Dict with id, name, platform.

        Raises:
            ValueError: If platform is invalid, not configured, or export fails.
        """
        platform_client, client = self._get_configured_client(platform)
        exporter = self._registry.get_exporter(platform)
        if not exporter:
            raise ValueError(f"No exporter for platform: {platform}")
        config = exporter(graph)

        result = platform_client.create_agent(client, config, name)
        return {"id": result["id"], "name": result["name"], "platform": platform}

    def get_sync_status(self, agent_id: str) -> dict:
        """Check if an agent can be synced to its source platform."""
        try:
            _agent, graph = self._agents.load_graph(agent_id)
        except (FileNotFoundError, ValueError):
            return {"can_sync": False, "reason": "Agent graph not available"}

        source_metadata = graph.source_metadata or {}
        source_type = graph.source_type

        if not self._registry.has_platform(source_type):
            return {
                "can_sync": False,
                "reason": f"Source '{source_type}' is not a supported platform",
            }

        if not self._registry.supports_update(source_type):
            return {
                "can_sync": False,
                "reason": f"{source_type} does not support syncing",
                "platform": source_type,
            }

        remote_id_key = self._registry.get_remote_id_key(source_type)
        if not remote_id_key:
            return {
                "can_sync": False,
                "reason": f"{source_type} does not track remote IDs",
                "platform": source_type,
            }

        remote_id = source_metadata.get(remote_id_key)
        if not remote_id:
            return {
                "can_sync": False,
                "reason": f"No remote ID found (missing {remote_id_key} in source_metadata)",
                "platform": source_type,
            }

        if not self._is_configured(source_type):
            return {
                "can_sync": False,
                "reason": f"{source_type} API key not configured",
                "platform": source_type,
                "remote_id": remote_id,
                "needs_configuration": True,
            }

        return {"can_sync": True, "platform": source_type, "remote_id": remote_id}

    def sync_to_platform(self, agent_id: str, graph: AgentGraph) -> dict:
        """Sync an agent to its source platform.

        Returns:
            Dict with id, name, platform, synced.

        Raises:
            ValueError: If sync is not possible.
        """
        source_metadata = graph.source_metadata or {}
        source_type = graph.source_type

        if not self._registry.has_platform(source_type):
            raise ValueError(f"Source '{source_type}' is not a supported platform")

        if not self._registry.supports_update(source_type):
            raise ValueError(f"{source_type} does not support syncing")

        remote_id_key = self._registry.get_remote_id_key(source_type)
        if not remote_id_key:
            raise ValueError(f"{source_type} does not track remote IDs")

        remote_id = source_metadata.get(remote_id_key)
        if not remote_id:
            raise ValueError(f"No remote ID found (missing {remote_id_key} in source_metadata)")

        platform_client, client = self._get_configured_client(source_type)

        exporter = self._registry.get_exporter(source_type)
        if not exporter:
            raise ValueError(f"No exporter for platform: {source_type}")
        config = exporter(graph)

        result = platform_client.update_agent(client, remote_id, config)
        return {
            "id": result["id"],
            "name": result["name"],
            "platform": source_type,
            "synced": True,
        }

    def _validate_platform(self, platform: str) -> None:
        """Validate platform name."""
        if not self._registry.has_platform(platform):
            raise ValueError(f"Invalid platform: {platform}")

    def _is_configured(self, platform: str) -> bool:
        """Check if a platform is configured."""
        settings = load_settings()
        return self._registry.is_configured(platform, settings)

    def _get_configured_client(self, platform: str) -> tuple[Any, Any]:
        """Get validated, configured platform client and SDK client.

        Raises:
            ValueError: If platform invalid or not configured.
        """
        self._validate_platform(platform)
        if not self._is_configured(platform):
            raise ValueError(f"{platform} API key not configured")

        settings = load_settings()
        api_key = self._registry.get_api_key(platform, settings)
        platform_client = self._registry.get(platform)
        client = platform_client.get_client(api_key)
        return platform_client, client
