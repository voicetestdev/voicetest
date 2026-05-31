"""Platform registry for discovering and selecting platform clients."""

from __future__ import annotations

from collections.abc import Callable
import os
from typing import TYPE_CHECKING
from typing import Any

from voicetest.importers.base import SourceImporter
from voicetest.platforms.base import PlatformClient


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph
    from voicetest.settings import Settings


class PlatformRegistry:
    """Registry of platform clients for dependency injection."""

    def __init__(self):
        self._clients: dict[str, PlatformClient] = {}

    def register(self, client: PlatformClient) -> None:
        """Register a platform client."""
        self._clients[client.platform_name] = client

    def get(self, platform: str) -> PlatformClient:
        """Get a platform client by name."""
        if platform not in self._clients:
            raise ValueError(f"Unknown platform: {platform}")
        return self._clients[platform]

    def list_platforms(self) -> list[str]:
        """List all registered platform names."""
        return list(self._clients.keys())

    def has_platform(self, platform: str) -> bool:
        """Check if a platform is registered."""
        return platform in self._clients

    def get_env_key(self, platform: str) -> str:
        """Get the primary environment variable key for a platform's API key."""
        return self.get(platform).env_key

    def get_required_env_keys(self, platform: str) -> list[str]:
        """Get all environment variable keys required for a platform."""
        return self.get(platform).required_env_keys

    def is_configured(self, platform: str, settings: Settings | None = None) -> bool:
        """Check if all required environment variables are set for a platform."""
        required_keys = self.get_required_env_keys(platform)
        for key in required_keys:
            has_in_settings = settings and settings.env.get(key)
            has_in_env = os.environ.get(key)
            if not (has_in_settings or has_in_env):
                return False
        return True

    def get_api_key(self, platform: str, settings: Settings | None = None) -> str | None:
        """Get the primary API key for a platform from settings or environment."""
        env_key = self.get_env_key(platform)
        if settings:
            key = settings.env.get(env_key)
            if key:
                return key
        return os.environ.get(env_key)

    def get_importer(self, platform: str) -> SourceImporter | None:
        """Get the importer for a platform."""
        return self.get(platform).get_importer()

    def get_exporter(self, platform: str) -> Callable[[AgentGraph], dict[str, Any]] | None:
        """Get the exporter function for a platform."""
        return self.get(platform).get_exporter()

    def supports_update(self, platform: str) -> bool:
        """Check if a platform supports updating agents in place."""
        return self.get(platform).supports_update

    def get_remote_id_key(self, platform: str) -> str | None:
        """Get the source_metadata key for remote agent ID."""
        return self.get(platform).remote_id_key
