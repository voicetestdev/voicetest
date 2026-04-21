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

from cachetools import LRUCache
import cloudpickle
import dspy
from dspy.clients.cache import Cache


try:
    import boto3
    from botocore.exceptions import ClientError

    _HAS_BOTO3 = True
except ImportError:
    _HAS_BOTO3 = False


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


def _require_boto3() -> None:
    if not _HAS_BOTO3:
        raise ImportError("boto3 is required for S3 cache backend. Install it with: uv add boto3")


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
        _require_boto3()
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

    def __delitem__(self, key: str) -> None:
        try:
            self._client.delete_object(Bucket=self.bucket, Key=self._s3_key(key))
        except ClientError as e:
            logger.warning("Failed to delete cache key %s: %s", key, e)


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
        _require_boto3()
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


def _reconstruct_last_request(lm: Any) -> tuple[dict | None, str | None]:
    """Rebuild the request dict + fn_identifier used as the cache key on the LM's
    most recent call. Returns (None, None) if reconstruction is impossible.

    Two paths:

    - ClaudeCodeLM (voicetest/llm/claudecode.py) records `_last_request` and
      `_last_cache_fn_identifier` on each call because it overrides __call__ and
      does not populate lm.history.
    - Standard dspy.LM populates lm.history via `_process_lm_response`; we
      replicate dspy.LM.forward's request construction from the history entry.
    """
    last_request = getattr(lm, "_last_request", None)
    if last_request is not None:
        fn_identifier = getattr(lm, "_last_cache_fn_identifier", None)
        if fn_identifier is None:
            return None, None
        return dict(last_request), fn_identifier

    if not getattr(lm, "history", None):
        return None, None
    entry = lm.history[-1]

    forward_kwargs = dict(entry.get("kwargs", {}))
    forward_kwargs.pop("cache", None)
    merged = {**lm.kwargs, **forward_kwargs}
    if merged.get("rollout_id") is None:
        merged.pop("rollout_id", None)

    # history stores the original messages/prompt args — forward() converts
    # `prompt=` into messages before building the cache request.
    messages = entry.get("messages")
    if messages is None:
        prompt = entry.get("prompt")
        if prompt is None:
            return None, None
        messages = [{"role": "user", "content": prompt}]

    request = {"model": lm.model, "messages": messages, **merged}
    if lm.model_type == "chat":
        fn_identifier = "dspy.clients.lm.litellm_completion"
    elif lm.model_type == "text":
        fn_identifier = "dspy.clients.lm.litellm_text_completion"
    else:
        fn_identifier = "dspy.clients.lm.litellm_responses_completion"
    return request, fn_identifier


def try_evict_last_call(lm: Any) -> bool:
    """Best-effort: evict the cache entry for this LM's most recent call.

    Used when a cached completion is poisoned (parses to None for a required field);
    eviction lets the next run re-roll against a clean cache instead of replaying
    the bad string forever.

    Returns True if at least one cache layer had the entry removed.
    """
    try:
        request, fn_identifier = _reconstruct_last_request(lm)
        if request is None or fn_identifier is None:
            return False
        request["_fn_identifier"] = fn_identifier

        key = dspy.cache.cache_key(
            request,
            ignored_args_for_cache_key=["api_key", "api_base", "base_url"],
        )

        evicted = False
        try:
            del dspy.cache.memory_cache[key]
            evicted = True
        except KeyError:
            pass
        try:
            del dspy.cache.disk_cache[key]
            evicted = True
        except (KeyError, Exception) as e:  # noqa: BLE001 — disk backends raise varied errors
            logger.debug("Disk cache eviction miss/failure for key %s: %s", key, e)
        return evicted
    except Exception as e:  # noqa: BLE001 — eviction is best-effort
        logger.warning("Failed to reconstruct cache key for eviction: %s", e)
        return False


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
