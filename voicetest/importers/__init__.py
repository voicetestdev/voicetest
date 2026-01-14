"""Source importers for different voice agent platforms."""

from voicetest.importers.base import ImporterInfo, SourceImporter
from voicetest.importers.custom import CustomImporter
from voicetest.importers.registry import ImporterRegistry, get_registry
from voicetest.importers.retell import RetellImporter


def _setup_importers() -> None:
    """Register built-in importers."""
    registry = get_registry()
    registry.register(RetellImporter())
    registry.register(CustomImporter())


_setup_importers()

__all__ = [
    "CustomImporter",
    "ImporterInfo",
    "ImporterRegistry",
    "RetellImporter",
    "SourceImporter",
    "get_registry",
]
