"""Tests for voicetest.services.discovery module."""

import pytest

from voicetest.services.discovery import DiscoveryService


@pytest.fixture
def svc(container):
    return container.resolve(DiscoveryService)


class TestListImporters:
    def test_returns_non_empty(self, svc):
        importers = svc.list_importers()
        assert len(importers) > 0

    def test_each_has_source_type(self, svc):
        for imp in svc.list_importers():
            assert imp.source_type

    def test_includes_retell(self, svc):
        types = {imp.source_type for imp in svc.list_importers()}
        assert "retell" in types

    def test_includes_custom(self, svc):
        types = {imp.source_type for imp in svc.list_importers()}
        assert "custom" in types


class TestListExportFormats:
    def test_returns_non_empty(self, svc):
        formats = svc.list_export_formats()
        assert len(formats) > 0

    def test_each_has_required_keys(self, svc):
        for fmt in svc.list_export_formats():
            assert "id" in fmt
            assert "name" in fmt
            assert "description" in fmt
            assert "ext" in fmt

    def test_includes_mermaid(self, svc):
        ids = {f["id"] for f in svc.list_export_formats()}
        assert "mermaid" in ids


class TestListPlatforms:
    def test_returns_list(self, svc):
        platforms = svc.list_platforms()
        assert isinstance(platforms, list)

    def test_each_has_name(self, svc):
        for p in svc.list_platforms():
            assert "name" in p
            assert "configured" in p
