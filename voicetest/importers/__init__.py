"""Source importers for different voice agent platforms."""

from voicetest.importers.base import ImporterInfo, SourceImporter
from voicetest.importers.custom import CustomImporter
from voicetest.importers.registry import ImporterRegistry, get_registry
from voicetest.importers.retell import RetellImporter
from voicetest.importers.retell_llm import RetellLLMImporter


def _setup_importers() -> None:
    """Register built-in importers."""
    registry = get_registry()
    registry.register(RetellImporter())
    registry.register(RetellLLMImporter())
    registry.register(CustomImporter())


_setup_importers()

__all__ = [
    "CustomImporter",
    "ImporterInfo",
    "ImporterRegistry",
    "RetellImporter",
    "RetellLLMImporter",
    "SourceImporter",
    "get_registry",
]
