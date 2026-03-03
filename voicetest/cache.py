"""Pluggable DSPy cache backend.

DSPy caches LLM responses via `dspy.cache.disk_cache`, which supports
dict-like access (__contains__, __getitem__, __setitem__). This module
provides an S3-backed implementation so cached responses survive
container restarts and can be shared across team members.
"""

import logging
from typing import Any
from typing import Protocol
from typing import runtime_checkable

import boto3
from botocore.exceptions import ClientError
import cloudpickle
import dspy


logger = logging.getLogger(__name__)


@runtime_checkable
class CacheBackend(Protocol):
    """Dict-like interface matching DSPy's disk_cache access pattern."""

    def __contains__(self, key: str) -> bool: ...
    def __getitem__(self, key: str) -> Any: ...
    def __setitem__(self, key: str, value: Any) -> None: ...


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


def configure_cache(backend: CacheBackend) -> None:
    """Replace DSPy's disk cache with a custom backend.

    Sets `dspy.cache.disk_cache` to the provided backend and ensures
    disk caching is enabled so DSPy actually reads/writes through it.
    """
    dspy.cache.disk_cache = backend
    dspy.cache.enable_disk_cache = True


def setup_cache_from_settings(cache_settings: Any) -> None:
    """Configure DSPy cache from voicetest CacheSettings.

    If backend is "s3" and a bucket is configured, creates an
    S3CacheBackend and installs it. Otherwise does nothing
    (DSPy uses its built-in local disk cache).
    """
    if cache_settings.backend != "s3":
        return
    if not cache_settings.s3_bucket:
        logger.warning("Cache backend set to 's3' but no s3_bucket configured, using disk cache")
        return

    backend = S3CacheBackend(
        bucket=cache_settings.s3_bucket,
        prefix=cache_settings.s3_prefix,
        region=cache_settings.s3_region,
    )
    configure_cache(backend)
    logger.info(
        "DSPy cache configured with S3 backend: s3://%s/%s",
        cache_settings.s3_bucket,
        cache_settings.s3_prefix,
    )
