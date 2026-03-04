"""Pluggable DSPy cache backend.

DSPy supports custom cache implementations via subclassing
``dspy.clients.Cache``. This module provides ``S3Cache``, a subclass
that swaps the default ``diskcache.FanoutCache`` disk layer for an
S3-backed store so cached responses survive container restarts and can
be shared across team members.
"""

import logging
import threading
from typing import Any
from typing import Protocol
from typing import runtime_checkable

import boto3
from botocore.exceptions import ClientError
from cachetools import LRUCache
import cloudpickle
import dspy
from dspy.clients.cache import Cache


logger = logging.getLogger(__name__)


@runtime_checkable
class CacheBackend(Protocol):
    """Dict-like interface matching DSPy's disk_cache access pattern."""

    def __contains__(self, key: str) -> bool:
        pass

    def __getitem__(self, key: str) -> Any:
        pass

    def __setitem__(self, key: str, value: Any) -> None:
        pass


class S3CacheBackend:
    """S3-backed cache backend using cloudpickle for serialization.

    S3 key format: {prefix}{cache_key}
    Error handling: GET/HEAD failures → cache miss, PUT failures → log + skip.
    """

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
        client: Any = None,
    ):
        self.bucket = bucket
        self.prefix = prefix
        self._client = client or boto3.client("s3", region_name=region)

    def _s3_key(self, key: str) -> str:
        return f"{self.prefix}{key}"

    def __contains__(self, key: str) -> bool:
        try:
            self._client.head_object(Bucket=self.bucket, Key=self._s3_key(key))
            return True
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("404", "NoSuchKey"):
                return False
            logger.warning("Cache check failed for key %s: %s", key, e)
            return False

    def __getitem__(self, key: str) -> Any:
        try:
            response = self._client.get_object(Bucket=self.bucket, Key=self._s3_key(key))
            return cloudpickle.loads(response["Body"].read())
        except ClientError as e:
            raise KeyError(key) from e

    def __setitem__(self, key: str, value: Any) -> None:
        try:
            self._client.put_object(
                Bucket=self.bucket,
                Key=self._s3_key(key),
                Body=cloudpickle.dumps(value),
                ContentType="application/octet-stream",
            )
        except (ClientError, Exception):
            logger.warning("Failed to write cache key %s", key)


class S3Cache(Cache):
    """DSPy Cache subclass that uses S3 for persistent storage.

    Replaces the default ``diskcache.FanoutCache`` with an
    ``S3CacheBackend`` while preserving the in-memory LRU cache,
    thread safety, cache key generation, and all other base class
    behavior.
    """

    def __init__(
        self,
        s3_bucket: str,
        s3_prefix: str = "",
        s3_region: str | None = None,
        s3_client: Any = None,
        enable_memory_cache: bool = True,
        memory_max_entries: int = 1_000_000,
        **kwargs: Any,
    ):
        # Skip Cache.__init__ — it would create a FanoutCache we don't need.
        # Instead, set up the attributes it would have created.
        self.enable_disk_cache = True
        self.enable_memory_cache = enable_memory_cache
        if self.enable_memory_cache:
            self.memory_cache = LRUCache(maxsize=memory_max_entries)
        else:
            self.memory_cache = {}
        self.disk_cache = S3CacheBackend(
            bucket=s3_bucket,
            prefix=s3_prefix,
            region=s3_region,
            client=s3_client,
        )
        self._lock = threading.RLock()


def setup_cache_from_settings(cache_settings: Any) -> None:
    """Configure DSPy cache from voicetest CacheSettings.

    If backend is "s3" and a bucket is configured, creates an
    S3Cache and assigns it to ``dspy.cache``. Otherwise does nothing
    (DSPy uses its built-in local disk cache).
    """
    if cache_settings.cache_backend != "s3":
        return
    if not cache_settings.s3_bucket:
        logger.warning("Cache backend set to 's3' but no s3_bucket configured, using disk cache")
        return

    dspy.cache = S3Cache(
        s3_bucket=cache_settings.s3_bucket,
        s3_prefix=cache_settings.s3_prefix,
        s3_region=cache_settings.s3_region,
    )
    logger.info(
        "DSPy cache configured with S3 backend: s3://%s/%s",
        cache_settings.s3_bucket,
        cache_settings.s3_prefix,
    )
