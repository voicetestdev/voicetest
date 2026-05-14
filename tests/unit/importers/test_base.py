"""Tests for voicetest.importers.base module."""

from voicetest.importers.base import ImporterInfo
from voicetest.importers.base import SourceImporter


class TestSourceImporterProtocol:
    """Tests for the SourceImporter protocol."""

    def test_protocol_is_runtime_checkable(self):
        # Protocol should be runtime checkable
        assert hasattr(SourceImporter, "__protocol_attrs__")


class TestImporterInfo:
    """Tests for ImporterInfo class."""

    def test_create_importer_info(self):
        info = ImporterInfo(
            source_type="retell",
            description="Import Retell Conversation Flow JSON",
            file_patterns=["*.json"],
        )
        assert info.source_type == "retell"
        assert info.description == "Import Retell Conversation Flow JSON"
        assert info.file_patterns == ["*.json"]
