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
from voicetest.cache import try_evict_last_call
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

    def test_delitem_calls_delete_object(self):
        client = MagicMock()
        backend = self._make_backend(client)

        del backend["abc123"]

        client.delete_object.assert_called_once_with(Bucket="test-bucket", Key="dspy-cache/abc123")

    def test_delitem_logs_and_swallows_client_error(self, caplog):
        client = MagicMock()
        client.delete_object.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "Boom"}},
            "DeleteObject",
        )
        backend = self._make_backend(client)

        # Should not raise
        del backend["abc123"]
        assert "Failed to delete cache" in caplog.text

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
        with patch("boto3.client", return_value=MagicMock()) as mock_client:
            S3CacheBackend(bucket="b", region="us-west-2")
            mock_client.assert_called_once_with("s3", region_name="us-west-2")


class TestS3Cache:
    """Tests for S3Cache (dspy.clients.Cache subclass)."""

    def test_is_subclass_of_dspy_cache(self):
        """S3Cache is a proper subclass of dspy.clients.Cache."""
        assert issubclass(S3Cache, Cache)

    def test_uses_s3_backend_as_disk_cache(self):
        """S3Cache sets self.disk_cache to an S3CacheBackend."""
        with patch("boto3.client", return_value=MagicMock()):
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
        with patch("boto3.client", return_value=MagicMock()):
            cache = S3Cache(s3_bucket="b")
        assert cache.enable_memory_cache is True

    def test_memory_cache_can_be_disabled(self):
        """S3Cache respects enable_memory_cache=False."""
        with patch("boto3.client", return_value=MagicMock()):
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
        with patch("boto3.client", return_value=MagicMock()):
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


class TestTryEvictLastCall:
    """Tests for try_evict_last_call(): reconstructs the cache key that dspy.LM
    used and removes the entry from memory + disk cache."""

    def _fresh_cache(self, tmp_path) -> Cache:
        return Cache(
            enable_disk_cache=True,
            enable_memory_cache=True,
            disk_cache_dir=str(tmp_path / "dspy-cache"),
        )

    def _fake_lm(self, model: str = "openai/gpt-4o-mini", model_type: str = "chat"):
        """Build a minimal fake LM with just the attributes try_evict_last_call reads."""
        lm = MagicMock()
        lm.model = model
        lm.model_type = model_type
        lm.kwargs = {"temperature": None, "max_tokens": None}
        lm.history = []
        # Explicitly None — MagicMock auto-creates any accessed attribute, which
        # would send try_evict_last_call down the ClaudeCodeLM path by accident.
        lm._last_request = None
        lm._last_cache_fn_identifier = None
        return lm

    def _put_via_dspy(self, cache: Cache, lm, messages: list[dict], forward_kwargs: dict):
        """Put a cache entry under the exact key dspy.LM.forward would use."""
        merged = {**lm.kwargs, **forward_kwargs}
        if merged.get("rollout_id") is None:
            merged.pop("rollout_id", None)
        request = {
            "model": lm.model,
            "messages": messages,
            **merged,
            "_fn_identifier": "dspy.clients.lm.litellm_completion",
        }
        cache.put(
            request,
            "CACHED_RESPONSE",
            ignored_args_for_cache_key=["api_key", "api_base", "base_url"],
            enable_memory_cache=True,
        )
        return request

    def test_evicts_entry_matching_last_history_call(self, tmp_path):
        """try_evict_last_call reconstructs the same cache key dspy wrote under,
        so the entry is actually removed."""
        cache = self._fresh_cache(tmp_path)
        lm = self._fake_lm()
        messages = [{"role": "user", "content": "hello"}]
        forward_kwargs = {"temperature": None, "max_tokens": None}

        request = self._put_via_dspy(cache, lm, messages, forward_kwargs)

        lm.history = [
            {
                "prompt": None,
                "messages": messages,
                "kwargs": forward_kwargs,
            }
        ]

        # Confirm entry exists before eviction
        assert (
            cache.get(request, ignored_args_for_cache_key=["api_key", "api_base", "base_url"])
            == "CACHED_RESPONSE"
        )

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            evicted = try_evict_last_call(lm)
        finally:
            dspy.cache = original_cache

        assert evicted is True
        assert (
            cache.get(request, ignored_args_for_cache_key=["api_key", "api_base", "base_url"])
            is None
        )

    def test_returns_false_when_history_empty(self, tmp_path):
        cache = self._fresh_cache(tmp_path)
        lm = self._fake_lm()
        lm.history = []

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            assert try_evict_last_call(lm) is False
        finally:
            dspy.cache = original_cache

    def test_returns_false_when_entry_not_in_cache(self, tmp_path):
        """If the entry isn't in cache (already evicted, or never written),
        returns False but doesn't raise."""
        cache = self._fresh_cache(tmp_path)
        lm = self._fake_lm()
        lm.history = [
            {
                "prompt": None,
                "messages": [{"role": "user", "content": "hi"}],
                "kwargs": {"temperature": None, "max_tokens": None},
            }
        ]

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            assert try_evict_last_call(lm) is False
        finally:
            dspy.cache = original_cache

    def test_swallows_exceptions(self, tmp_path):
        """Eviction is best-effort — if something goes wrong reconstructing the
        key, it logs and returns False instead of raising."""
        cache = self._fresh_cache(tmp_path)
        lm = self._fake_lm()
        # Malformed history: missing 'messages' key → KeyError during reconstruction
        lm.history = [{"kwargs": {}}]

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            assert try_evict_last_call(lm) is False
        finally:
            dspy.cache = original_cache

    def _make_fake_response(self):
        """Minimal shape dspy._process_completion reads."""
        choice = MagicMock()
        choice.message.content = "hello world"
        choice.message.tool_calls = None
        choice.message.reasoning_content = None
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = {"total_tokens": 5}
        resp.model = "openai/gpt-4o-mini"
        resp._hidden_params = {}
        return resp

    def _install_fake_completion(self, monkeypatch):
        """Monkey-patch dspy.clients.lm.litellm_completion with a mock that masquerades
        as the real identifier (so request_cache computes the same _fn_identifier
        that production would)."""
        import dspy.clients.lm as dspy_lm_module

        call_count = {"n": 0}

        def fake_completion(request, num_retries, cache=None):
            call_count["n"] += 1
            return self._make_fake_response()

        # request_cache computes fn_identifier from fn.__module__ + fn.__qualname__ —
        # make the fake match the real function so the cache key computation agrees.
        fake_completion.__module__ = "dspy.clients.lm"
        fake_completion.__qualname__ = "litellm_completion"

        monkeypatch.setattr(dspy_lm_module, "litellm_completion", fake_completion)
        return call_count

    def test_end_to_end_eviction_with_prompt_arg(self, tmp_path, monkeypatch):
        """End-to-end proof with prompt= (history stores messages=None, tests the
        prompt→messages reconstruction path)."""
        cache = self._fresh_cache(tmp_path)
        call_count = self._install_fake_completion(monkeypatch)

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            lm = dspy.LM("openai/gpt-4o-mini")

            lm(prompt="test prompt")
            assert call_count["n"] == 1

            # Cache hit — completion not invoked again
            lm(prompt="test prompt")
            assert call_count["n"] == 1

            assert try_evict_last_call(lm) is True

            # Post-eviction: cache miss → completion invoked again. If our
            # reconstructed key didn't match what dspy wrote, this would still
            # be a cache hit and count would stay at 1.
            lm(prompt="test prompt")
            assert call_count["n"] == 2
        finally:
            dspy.cache = original_cache

    def test_end_to_end_eviction_with_messages_arg(self, tmp_path, monkeypatch):
        """End-to-end proof with messages= (history stores the messages list
        directly — tests the normal reconstruction path)."""
        cache = self._fresh_cache(tmp_path)
        call_count = self._install_fake_completion(monkeypatch)

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            lm = dspy.LM("openai/gpt-4o-mini")
            messages = [
                {"role": "system", "content": "you are helpful"},
                {"role": "user", "content": "hello"},
            ]

            lm(messages=messages)
            assert call_count["n"] == 1

            lm(messages=messages)
            assert call_count["n"] == 1  # cache hit

            assert try_evict_last_call(lm) is True

            lm(messages=messages)
            assert call_count["n"] == 2  # post-eviction miss
        finally:
            dspy.cache = original_cache

    def test_end_to_end_eviction_claudecode_lm(self, tmp_path, monkeypatch):
        """End-to-end proof for ClaudeCodeLM — it overrides __call__ and doesn't
        populate lm.history, so eviction must work via its _last_request hook.

        Heavily exercised by 3rd-party users (claudecode/ model strings)."""
        import subprocess

        from voicetest.llm.claudecode import ClaudeCodeLM

        cache = self._fresh_cache(tmp_path)

        # Bypass the 'claude' CLI availability check
        monkeypatch.setattr("voicetest.llm.claudecode.shutil.which", lambda _: "/fake/claude")

        run_count = {"n": 0}

        def fake_subprocess_run(*args, **kwargs):
            run_count["n"] += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = '{"result": "hello from claude", "is_error": false}'
            result.stderr = ""
            return result

        monkeypatch.setattr(subprocess, "run", fake_subprocess_run)

        original_cache = dspy.cache
        try:
            dspy.cache = cache
            lm = ClaudeCodeLM("claudecode/sonnet")

            # Call 1: cache miss → CLI subprocess invoked
            lm(prompt="hello")
            assert run_count["n"] == 1

            # Call 2: cache hit → CLI NOT invoked again
            lm(prompt="hello")
            assert run_count["n"] == 1

            # Evict — relies on ClaudeCodeLM's _last_request hook (lm.history is empty here)
            assert not lm.history  # sanity: ClaudeCodeLM truly bypasses history
            assert try_evict_last_call(lm) is True

            # Call 3: cache miss (evicted) → CLI invoked again
            lm(prompt="hello")
            assert run_count["n"] == 2
        finally:
            dspy.cache = original_cache
