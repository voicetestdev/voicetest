"""Tests for LinkedFile utility functions."""

import json

import pytest

from voicetest.storage.linked_file import check_file
from voicetest.storage.linked_file import compute_etag
from voicetest.storage.linked_file import read_json
from voicetest.storage.linked_file import write_json


class TestComputeEtag:
    """Tests for ETag computation."""

    def test_returns_quoted_string(self):
        etag = compute_etag("abc-123", 1234567890.0)
        assert etag.startswith('"')
        assert etag.endswith('"')

    def test_includes_resource_id_and_mtime(self):
        etag = compute_etag("agent-42", 1700000000.5)
        assert "agent-42" in etag
        assert "1700000000.5" in etag

    def test_deterministic(self):
        etag1 = compute_etag("id-1", 100.0)
        etag2 = compute_etag("id-1", 100.0)
        assert etag1 == etag2

    def test_different_for_different_mtime(self):
        etag1 = compute_etag("id-1", 100.0)
        etag2 = compute_etag("id-1", 200.0)
        assert etag1 != etag2


class TestCheckFile:
    """Tests for file existence and mtime checking."""

    def test_returns_mtime_and_etag(self, tmp_path):
        f = tmp_path / "test.json"
        f.write_text("{}")

        mtime, etag = check_file(str(f), "res-1")

        assert isinstance(mtime, float)
        assert mtime > 0
        assert '"res-1-' in etag

    def test_raises_for_missing_file(self, tmp_path):
        missing = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            check_file(str(missing), "res-1")

    def test_etag_changes_when_file_changes(self, tmp_path):
        import time

        f = tmp_path / "test.json"
        f.write_text('{"v": 1}')
        _, etag1 = check_file(str(f), "res-1")

        time.sleep(0.05)
        f.write_text('{"v": 2}')
        _, etag2 = check_file(str(f), "res-1")

        assert etag1 != etag2


class TestReadJson:
    """Tests for JSON file reading."""

    def test_reads_valid_json(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('[{"name": "test"}]')

        data = read_json(str(f))

        assert data == [{"name": "test"}]

    def test_reads_dict(self, tmp_path):
        f = tmp_path / "data.json"
        f.write_text('{"key": "value"}')

        data = read_json(str(f))

        assert data == {"key": "value"}

    def test_raises_for_missing_file(self, tmp_path):
        missing = tmp_path / "missing.json"

        with pytest.raises(FileNotFoundError):
            read_json(str(missing))

    def test_raises_for_invalid_json(self, tmp_path):
        f = tmp_path / "bad.json"
        f.write_text("not json at all")

        with pytest.raises(json.JSONDecodeError):
            read_json(str(f))


class TestWriteJson:
    """Tests for JSON file writing."""

    def test_writes_list(self, tmp_path):
        f = tmp_path / "out.json"

        write_json(str(f), [{"name": "a"}, {"name": "b"}])

        data = json.loads(f.read_text())
        assert len(data) == 2
        assert data[0]["name"] == "a"

    def test_writes_dict(self, tmp_path):
        f = tmp_path / "out.json"

        write_json(str(f), {"key": "value"})

        data = json.loads(f.read_text())
        assert data == {"key": "value"}

    def test_overwrites_existing(self, tmp_path):
        f = tmp_path / "out.json"
        f.write_text('[{"old": true}]')

        write_json(str(f), [{"replaced": True}])

        data = json.loads(f.read_text())
        assert data == [{"replaced": True}]

    def test_output_is_formatted(self, tmp_path):
        f = tmp_path / "out.json"

        write_json(str(f), [{"name": "test"}])

        text = f.read_text()
        assert "\n" in text
