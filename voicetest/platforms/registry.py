"""Platform registry for discovering and selecting platform clients."""

from voicetest.platforms.base import PlatformClient


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
        """Get the environment variable key for a platform's API key.

        Args:
            platform: Platform identifier.

        Returns:
            Environment variable name (e.g., 'RETELL_API_KEY').

        Raises:
            ValueError: If platform is not registered.
        """
        return self.get(platform).env_key
