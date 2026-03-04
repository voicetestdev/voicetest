"""Tests for the pluggable DSPy cache backend."""

from unittest.mock import MagicMock
from unittest.mock import patch

from botocore.exceptions import ClientError
import cloudpickle
import pytest

from voicetest.cache import CacheBackend
from voicetest.cache import S3CacheBackend
from voicetest.cache import configure_cache
from voicetest.cache import setup_cache_from_settings
from voicetest.settings import CacheSettings


class TestCacheBackendProtocol:
    """Verify the CacheBackend protocol contract."""

    def test_dict_backend_satisfies_protocol(self):
        """A plain dict satisfies the CacheBackend protocol."""
        d: CacheBackend = {}
        d["key"] = "value"
        assert "key" in d
        assert d["key"] == "value"


class TestS3CacheBackend:
    """Tests for S3CacheBackend."""

    def _make_backend(self, client: MagicMock | None = None) -> S3CacheBackend:
        client = client or MagicMock()
        return S3CacheBackend(
            bucket="test-bucket",
            prefix="dspy-cache/",
            client=client,
        )

    def test_setitem_puts_object_to_s3(self):
        client = MagicMock()
        backend = self._make_backend(client)

        backend["abc123"] = {"response": "hello"}

        client.put_object.assert_called_once()
        call_kwargs = client.put_object.call_args[1]
        assert call_kwargs["Bucket"] == "test-bucket"
        assert call_kwargs["Key"] == "dspy-cache/abc123"
        assert call_kwargs["ContentType"] == "application/octet-stream"
        # Verify the body is cloudpickle-serialized
        stored_value = cloudpickle.loads(call_kwargs["Body"])
        assert stored_value == {"response": "hello"}

    def test_getitem_retrieves_from_s3(self):
        client = MagicMock()
        serialized = cloudpickle.dumps({"response": "hello"})
        client.get_object.return_value = {"Body": MagicMock(read=lambda: serialized)}
        backend = self._make_backend(client)

        result = backend["abc123"]

        client.get_object.assert_called_once_with(Bucket="test-bucket", Key="dspy-cache/abc123")
        assert result == {"response": "hello"}

    def test_contains_true_when_object_exists(self):
        client = MagicMock()
        client.head_object.return_value = {}
        backend = self._make_backend(client)

        assert "abc123" in backend

        client.head_object.assert_called_once_with(Bucket="test-bucket", Key="dspy-cache/abc123")

    def test_contains_false_when_object_missing(self):
        client = MagicMock()
        client.head_object.side_effect = ClientError(
            {"Error": {"Code": "404", "Message": "Not Found"}},
            "HeadObject",
        )
        backend = self._make_backend(client)

        assert "abc123" not in backend

    def test_getitem_raises_keyerror_on_missing(self):
        client = MagicMock()
        client.get_object.side_effect = ClientError(
            {"Error": {"Code": "NoSuchKey", "Message": "Not Found"}},
            "GetObject",
        )
        backend = self._make_backend(client)

        with pytest.raises(KeyError):
            _ = backend["missing"]

    def test_setitem_logs_and_skips_on_put_failure(self, caplog):
        client = MagicMock()
        client.put_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "S3 down"}},
            "PutObject",
        )
        backend = self._make_backend(client)

        # Should not raise
        backend["abc123"] = {"data": "value"}
        assert "Failed to write cache" in caplog.text

    def test_contains_false_on_unexpected_error(self, caplog):
        client = MagicMock()
        client.head_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Boom"}},
            "HeadObject",
        )
        backend = self._make_backend(client)

        assert "abc123" not in backend
        assert "Cache check failed" in caplog.text

    def test_default_prefix_is_empty(self):
        client = MagicMock()
        backend = S3CacheBackend(bucket="b", client=client)

        backend["key1"] = "val"
        call_kwargs = client.put_object.call_args[1]
        assert call_kwargs["Key"] == "key1"

    def test_creates_boto3_client_when_none_provided(self):
        with patch("voicetest.cache.boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()
            S3CacheBackend(bucket="b", region="us-west-2")
            mock_boto3.client.assert_called_once_with("s3", region_name="us-west-2")


class TestConfigureCache:
    """Tests for configure_cache()."""

    def test_replaces_disk_cache(self):
        backend: CacheBackend = {}
        backend["pre"] = "existing"

        with patch("voicetest.cache.dspy") as mock_dspy:
            mock_dspy.cache = MagicMock()
            configure_cache(backend)
            assert mock_dspy.cache.disk_cache is backend
            assert mock_dspy.cache.enable_disk_cache is True

    def test_preserves_memory_cache_setting(self):
        backend: CacheBackend = {}

        with patch("voicetest.cache.dspy") as mock_dspy:
            mock_dspy.cache = MagicMock()
            mock_dspy.cache.enable_memory_cache = True
            configure_cache(backend)
            # Should not modify memory cache setting
            assert mock_dspy.cache.enable_memory_cache is True


class TestSetupCacheFromSettings:
    """Tests for setup_cache_from_settings()."""

    def test_disk_backend_does_nothing(self):
        settings = CacheSettings(backend="disk")
        with patch("voicetest.cache.configure_cache") as mock_configure:
            setup_cache_from_settings(settings)
            mock_configure.assert_not_called()

    def test_s3_backend_without_bucket_warns(self, caplog):
        settings = CacheSettings(backend="s3", s3_bucket="")
        with patch("voicetest.cache.configure_cache") as mock_configure:
            setup_cache_from_settings(settings)
            mock_configure.assert_not_called()
            assert "no s3_bucket configured" in caplog.text

    def test_s3_backend_with_bucket_configures_cache(self):
        settings = CacheSettings(
            backend="s3",
            s3_bucket="my-bucket",
            s3_prefix="cache/",
            s3_region="us-west-2",
        )
        with (
            patch("voicetest.cache.S3CacheBackend") as mock_backend_cls,
            patch("voicetest.cache.configure_cache") as mock_configure,
        ):
            mock_backend = MagicMock()
            mock_backend_cls.return_value = mock_backend
            setup_cache_from_settings(settings)
            mock_backend_cls.assert_called_once_with(
                bucket="my-bucket",
                prefix="cache/",
                region="us-west-2",
            )
            mock_configure.assert_called_once_with(mock_backend)
