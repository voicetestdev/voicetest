"""Discovery service for listing importers, exporters, and platforms."""

from voicetest.exporters.registry import ExporterRegistry
from voicetest.importers.base import ImporterInfo
from voicetest.importers.registry import ImporterRegistry
from voicetest.platforms.registry import PlatformRegistry


class DiscoveryService:
    """Lists available importers, export formats, and platforms."""

    def __init__(
        self,
        importer_registry: ImporterRegistry,
        exporter_registry: ExporterRegistry,
        platform_registry: PlatformRegistry,
    ):
        self._importers = importer_registry
        self._exporters = exporter_registry
        self._platforms = platform_registry

    def list_importers(self) -> list[ImporterInfo]:
        """List available importers with their capabilities."""
        return self._importers.list_importers()

    def list_export_formats(self) -> list[dict[str, str]]:
        """List available export formats.

        Returns:
            List of dicts with format id, name, description, and extension.
        """
        return [
            {
                "id": info.format_id,
                "name": info.name,
                "description": info.description,
                "ext": info.ext,
            }
            for info in self._exporters.list_formats()
        ]

    def list_platforms(self) -> list[dict]:
        """List available platforms with configuration status."""
        return [
            {
                "name": p.name,
                "configured": p.is_configured(),
                "env_key": p.env_key,
                "required_env_keys": p.required_env_keys,
            }
            for p in self._platforms.list_platforms()
        ]
