"""Tests for voicetest.services.discovery module."""

from voicetest.services import get_discovery_service


class TestListImporters:
    def test_returns_non_empty(self):
        svc = get_discovery_service()
        importers = svc.list_importers()
        assert len(importers) > 0

    def test_each_has_source_type(self):
        svc = get_discovery_service()
        for imp in svc.list_importers():
            assert imp.source_type

    def test_includes_retell(self):
        svc = get_discovery_service()
        types = {imp.source_type for imp in svc.list_importers()}
        assert "retell" in types

    def test_includes_custom(self):
        svc = get_discovery_service()
        types = {imp.source_type for imp in svc.list_importers()}
        assert "custom" in types


class TestListExportFormats:
    def test_returns_non_empty(self):
        svc = get_discovery_service()
        formats = svc.list_export_formats()
        assert len(formats) > 0

    def test_each_has_required_keys(self):
        svc = get_discovery_service()
        for fmt in svc.list_export_formats():
            assert "id" in fmt
            assert "name" in fmt
            assert "description" in fmt
            assert "ext" in fmt

    def test_includes_mermaid(self):
        svc = get_discovery_service()
        ids = {f["id"] for f in svc.list_export_formats()}
        assert "mermaid" in ids


class TestListPlatforms:
    def test_returns_list(self):
        svc = get_discovery_service()
        platforms = svc.list_platforms()
        assert isinstance(platforms, list)

    def test_each_has_name(self):
        svc = get_discovery_service()
        for p in svc.list_platforms():
            assert "name" in p
            assert "configured" in p
