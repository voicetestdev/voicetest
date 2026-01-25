"""Platform registry for discovering and selecting platform clients."""

from __future__ import annotations

from collections.abc import Callable
import os
from typing import TYPE_CHECKING, Any

from voicetest.platforms.base import PlatformClient, SourceImporter


if TYPE_CHECKING:
    from voicetest.models.agent import AgentGraph
    from voicetest.settings import Settings


class PlatformRegistry:
    """Registry of platform clients for dependency injection."""

    def __init__(self):
        self._clients: dict[str, PlatformClient] = {}

    def register(self, client: PlatformClient) -> None:
        """Register a platform client.

        Args:
            client: Platform client implementing PlatformClient protocol.
        """
        self._clients[client.platform_name] = client

    def get(self, platform: str) -> PlatformClient:
        """Get a platform client by name.

        Args:
            platform: Platform identifier (e.g., 'retell', 'vapi', 'livekit').

        Returns:
            The registered platform client.

        Raises:
            ValueError: If platform is not registered.
        """
        if platform not in self._clients:
            raise ValueError(f"Unknown platform: {platform}")
        return self._clients[platform]

    def list_platforms(self) -> list[str]:
        """List all registered platform names.

        Returns:
            List of platform identifiers.
        """
        return list(self._clients.keys())

    def has_platform(self, platform: str) -> bool:
        """Check if a platform is registered.

        Args:
            platform: Platform identifier.

        Returns:
            True if platform is registered.
        """
        return platform in self._clients

    def get_env_key(self, platform: str) -> str:
        """Get the primary environment variable key for a platform's API key.

        Args:
            platform: Platform identifier.

        Returns:
            Environment variable name (e.g., 'RETELL_API_KEY').

        Raises:
            ValueError: If platform is not registered.
        """
        return self.get(platform).env_key

    def get_required_env_keys(self, platform: str) -> list[str]:
        """Get all environment variable keys required for a platform.

        Args:
            platform: Platform identifier.

        Returns:
            List of environment variable names.

        Raises:
            ValueError: If platform is not registered.
        """
        return self.get(platform).required_env_keys

    def is_configured(self, platform: str, settings: Settings | None = None) -> bool:
        """Check if all required environment variables are set for a platform.

        Args:
            platform: Platform identifier.
            settings: Optional settings object to check. If None, only checks env vars.

        Returns:
            True if all required environment variables are set.

        Raises:
            ValueError: If platform is not registered.
        """
        required_keys = self.get_required_env_keys(platform)
        for key in required_keys:
            has_in_settings = settings and settings.env.get(key)
            has_in_env = os.environ.get(key)
            if not (has_in_settings or has_in_env):
                return False
        return True

    def get_api_key(self, platform: str, settings: Settings | None = None) -> str | None:
        """Get the primary API key for a platform from settings or environment.

        Args:
            platform: Platform identifier.
            settings: Optional settings object to check first.

        Returns:
            API key string, or None if not configured.

        Raises:
            ValueError: If platform is not registered.
        """
        env_key = self.get_env_key(platform)
        if settings:
            key = settings.env.get(env_key)
            if key:
                return key
        return os.environ.get(env_key)

    def get_importer(self, platform: str) -> SourceImporter | None:
        """Get the importer for a platform.

        Args:
            platform: Platform identifier.

        Returns:
            Importer instance, or None if platform doesn't support import.

        Raises:
            ValueError: If platform is not registered.
        """
        return self.get(platform).get_importer()

    def get_exporter(self, platform: str) -> Callable[[AgentGraph], dict[str, Any]] | None:
        """Get the exporter function for a platform.

        Args:
            platform: Platform identifier.

        Returns:
            Exporter function, or None if platform doesn't support export.

        Raises:
            ValueError: If platform is not registered.
        """
        return self.get(platform).get_exporter()
