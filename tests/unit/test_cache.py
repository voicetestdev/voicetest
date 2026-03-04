"""Tests for the pluggable DSPy cache backend."""

from unittest.mock import MagicMock
from unittest.mock import patch

from botocore.exceptions import ClientError
import cloudpickle
import dspy
from dspy.clients.cache import Cache
import pytest

from voicetest.cache import CacheBackend
from voicetest.cache import S3Cache
from voicetest.cache import S3CacheBackend
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


class TestS3Cache:
    """Tests for S3Cache (dspy.clients.Cache subclass)."""

    def test_is_subclass_of_dspy_cache(self):
        """S3Cache is a proper subclass of dspy.clients.Cache."""
        assert issubclass(S3Cache, Cache)

    def test_uses_s3_backend_as_disk_cache(self):
        """S3Cache sets self.disk_cache to an S3CacheBackend."""
        with patch("voicetest.cache.boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()
            cache = S3Cache(
                s3_bucket="my-bucket",
                s3_prefix="pfx/",
                s3_region="us-east-1",
            )
        assert isinstance(cache.disk_cache, S3CacheBackend)
        assert cache.disk_cache.bucket == "my-bucket"
        assert cache.disk_cache.prefix == "pfx/"
        assert cache.enable_disk_cache is True

    def test_memory_cache_enabled_by_default(self):
        """S3Cache enables memory cache by default."""
        with patch("voicetest.cache.boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()
            cache = S3Cache(s3_bucket="b")
        assert cache.enable_memory_cache is True

    def test_memory_cache_can_be_disabled(self):
        """S3Cache respects enable_memory_cache=False."""
        with patch("voicetest.cache.boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()
            cache = S3Cache(s3_bucket="b", enable_memory_cache=False)
        assert cache.enable_memory_cache is False

    def test_get_and_put_use_s3_backend(self):
        """End-to-end: put stores to S3, get retrieves from S3."""
        s3_client = MagicMock()
        cache = S3Cache(s3_bucket="b", s3_prefix="c/", s3_client=s3_client)

        request = {"messages": [{"role": "user", "content": "hello"}]}
        value = MagicMock()
        value.usage = {"tokens": 10}

        # Put into cache
        cache.put(request, value)

        # The S3 client should have received a put_object call
        s3_client.put_object.assert_called_once()

        # Simulate S3 returning the stored value on get
        stored_body = s3_client.put_object.call_args[1]["Body"]
        s3_client.head_object.return_value = {}
        s3_client.get_object.return_value = {"Body": MagicMock(read=lambda: stored_body)}

        # Clear memory cache to force disk (S3) read
        cache.reset_memory_cache()

        result = cache.get(request)
        assert result is not None

    def test_inherits_cache_key_generation(self):
        """S3Cache uses the base class cache_key method."""
        with patch("voicetest.cache.boto3") as mock_boto3:
            mock_boto3.client.return_value = MagicMock()
            cache = S3Cache(s3_bucket="b")
        # cache_key should work exactly like the base class
        key = cache.cache_key({"messages": [{"role": "user", "content": "test"}]})
        assert isinstance(key, str)
        assert len(key) == 64  # SHA256 hex digest

    def test_passes_s3_client_to_backend(self):
        """S3Cache forwards the s3_client parameter to S3CacheBackend."""
        mock_client = MagicMock()
        cache = S3Cache(s3_bucket="b", s3_client=mock_client)
        assert cache.disk_cache._client is mock_client


class TestSetupCacheFromSettings:
    """Tests for setup_cache_from_settings()."""

    def test_disk_backend_does_nothing(self):
        settings = CacheSettings(cache_backend="disk")
        with patch("voicetest.cache.S3Cache") as mock_cls:
            setup_cache_from_settings(settings)
            mock_cls.assert_not_called()

    def test_s3_backend_without_bucket_warns(self, caplog):
        settings = CacheSettings(cache_backend="s3", s3_bucket="")
        with patch("voicetest.cache.S3Cache") as mock_cls:
            setup_cache_from_settings(settings)
            mock_cls.assert_not_called()
            assert "no s3_bucket configured" in caplog.text

    def test_s3_backend_with_bucket_sets_dspy_cache(self):
        settings = CacheSettings(
            cache_backend="s3",
            s3_bucket="my-bucket",
            s3_prefix="cache/",
            s3_region="us-west-2",
        )
        original_cache = dspy.cache
        try:
            with patch("voicetest.cache.S3Cache") as mock_cls:
                mock_cache = MagicMock()
                mock_cls.return_value = mock_cache
                setup_cache_from_settings(settings)
                mock_cls.assert_called_once_with(
                    s3_bucket="my-bucket",
                    s3_prefix="cache/",
                    s3_region="us-west-2",
                )
        finally:
            dspy.cache = original_cache

    def test_s3_backend_assigns_to_dspy_cache(self):
        settings = CacheSettings(
            cache_backend="s3",
            s3_bucket="my-bucket",
        )
        original_cache = dspy.cache
        try:
            with patch("voicetest.cache.S3Cache") as mock_cls:
                mock_cache = MagicMock()
                mock_cls.return_value = mock_cache
                setup_cache_from_settings(settings)
                assert dspy.cache is mock_cache
        finally:
            dspy.cache = original_cache
