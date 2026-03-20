"""Tests for ClaudeCodeLM provider."""

import json
import subprocess
from unittest.mock import MagicMock
from unittest.mock import patch

import pytest


class TestClaudeCodeLMInit:
    """Test ClaudeCodeLM initialization."""

    def test_raises_when_cli_not_found(self):
        """Should raise RuntimeError when claude CLI is not installed."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with (
            patch("shutil.which", return_value=None),
            pytest.raises(RuntimeError, match="Claude Code CLI not found"),
        ):
            ClaudeCodeLM()

    def test_default_model_is_sonnet(self):
        """Should default to sonnet variant."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = ClaudeCodeLM()
            assert lm.variant == "sonnet"

    def test_parses_model_variant_from_string(self):
        """Should parse variant from model string like claudecode/opus."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = ClaudeCodeLM(model="claudecode/opus")
            assert lm.variant == "opus"

    def test_handles_model_without_prefix(self):
        """Should use model string directly if no slash present."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = ClaudeCodeLM(model="haiku")
            assert lm.variant == "haiku"


class TestClaudeCodeLMCall:
    """Test ClaudeCodeLM.__call__ method."""

    def test_calls_claude_cli_with_correct_args(self):
        """Should invoke claude CLI with correct arguments."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "Hello, world!"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(model="claudecode/sonnet", cache=False)
            lm("What is 2+2?")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "claude"
            assert "-p" in args
            assert "--output-format" in args
            assert "json" in args
            assert "--model" in args
            assert "sonnet" in args
            assert "User: What is 2+2?" in args

    def test_clears_anthropic_api_key_from_env(self):
        """Should remove ANTHROPIC_API_KEY to use Max quota."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch.dict("os.environ", {"ANTHROPIC_API_KEY": "sk-test-key"}),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(cache=False)
            lm("prompt")

            # Check the env kwarg doesn't contain ANTHROPIC_API_KEY
            call_kwargs = mock_run.call_args[1]
            assert "env" in call_kwargs
            assert "ANTHROPIC_API_KEY" not in call_kwargs["env"]

    def test_returns_list_with_content_dict(self):
        """Should return response in DSPy expected format."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "The answer is 4."})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            result = lm("What is 2+2?")

            assert isinstance(result, list)
            assert len(result) == 1
            assert result[0]["text"] == "The answer is 4."

    def test_raises_on_nonzero_exit_code(self):
        """Should raise RuntimeError when CLI returns non-zero exit code with invalid JSON."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "not valid json"
        mock_result.stderr = "Error: API key not found"

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(RuntimeError, match="Claude Code failed"):
                lm("test prompt")

    def test_raises_on_is_error_in_json_response(self):
        """Should raise RuntimeError when JSON response has is_error=true."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps(
            {
                "is_error": True,
                "result": "Credit balance is too low",
            }
        )

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(RuntimeError, match="Credit balance is too low"):
                lm("test prompt")

    def test_raises_on_timeout(self):
        """Should propagate TimeoutExpired from subprocess."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120)),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(subprocess.TimeoutExpired):
                lm("test prompt")

    def test_uses_correct_variant_in_command(self):
        """Should use the variant specified in model string."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(model="claudecode/haiku", cache=False)
            lm("prompt")

            args = mock_run.call_args[0][0]
            model_idx = args.index("--model")
            assert args[model_idx + 1] == "haiku"

    def test_passes_custom_timeout(self):
        """Should pass custom timeout to subprocess."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(cache=False)
            lm("prompt", timeout=300)

            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["timeout"] == 300


class TestClaudeCodeLMCallEdgeCases:
    """Test edge cases for ClaudeCodeLM.__call__ method."""

    def test_handles_multiline_prompt(self):
        """Should handle prompts with newlines correctly."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        prompt = "Line 1\nLine 2\nLine 3"

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(cache=False)
            lm(prompt)

            args = mock_run.call_args[0][0]
            # Prompt goes through _messages_to_prompt which adds "User: " prefix
            assert f"User: {prompt}" in args

    def test_handles_special_characters_in_prompt(self):
        """Should handle prompts with special characters."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        prompt = "Test with 'quotes' and \"double quotes\" and $dollars"

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(cache=False)
            lm(prompt)

            args = mock_run.call_args[0][0]
            # Prompt goes through _messages_to_prompt which adds "User: " prefix
            assert f"User: {prompt}" in args

    def test_handles_empty_result(self):
        """Should handle empty result from CLI."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": ""})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            result = lm("prompt")

            assert result[0]["text"] == ""

    def test_raises_on_invalid_json_response(self):
        """Should raise error when CLI returns invalid JSON."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "not valid json"

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(json.JSONDecodeError):
                lm("prompt")

    def test_subprocess_called_with_capture_and_text(self):
        """Should call subprocess with capture_output=True and text=True."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(cache=False)
            lm("prompt")

            kwargs = mock_run.call_args[1]
            assert kwargs["capture_output"] is True
            assert kwargs["text"] is True

    def test_error_includes_stderr_content(self):
        """Should include stderr content in error message."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = "not valid json"
        mock_result.stderr = "Specific error: authentication failed"

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(RuntimeError) as exc_info:
                lm("prompt")

            assert "authentication failed" in str(exc_info.value)


class TestClaudeCodeLMModelVariants:
    """Test all supported model variants."""

    @pytest.mark.parametrize(
        "model_string,expected_variant",
        [
            ("claudecode/sonnet", "sonnet"),
            ("claudecode/opus", "opus"),
            ("claudecode/haiku", "haiku"),
            ("sonnet", "sonnet"),
            ("opus", "opus"),
            ("haiku", "haiku"),
        ],
    )
    def test_model_variant_parsing(self, model_string, expected_variant):
        """Should correctly parse variant from model string."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = ClaudeCodeLM(model=model_string)
            assert lm.variant == expected_variant


class TestCreateLmFactory:
    """Test _create_lm factory function."""

    def test_creates_claudecode_lm_for_claudecode_prefix(self):
        """Should create ClaudeCodeLM when model starts with claudecode/."""
        from voicetest.llm.base import _create_lm
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = _create_lm("claudecode/sonnet")
            assert isinstance(lm, ClaudeCodeLM)

    def test_creates_dspy_lm_for_other_models(self):
        """Should create standard dspy.LM for non-claudecode models."""
        import dspy

        from voicetest.llm.base import _create_lm

        lm = _create_lm("openai/gpt-4o-mini")
        assert isinstance(lm, dspy.LM)
        assert not hasattr(lm, "variant")

    def test_factory_passes_full_model_string_to_claudecode(self):
        """Should pass the full model string to ClaudeCodeLM."""
        from voicetest.llm.base import _create_lm
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = _create_lm("claudecode/opus")
            assert isinstance(lm, ClaudeCodeLM)
            assert lm.variant == "opus"

    def test_factory_with_anthropic_model(self):
        """Should create dspy.LM for anthropic/ models."""
        import dspy

        from voicetest.llm.base import _create_lm

        lm = _create_lm("anthropic/claude-3-5-sonnet-20241022")
        assert isinstance(lm, dspy.LM)


class TestClaudeCodeLMIntegrationWithCallLlm:
    """Test ClaudeCodeLM integration with call_llm function."""

    @pytest.mark.asyncio
    async def test_call_llm_uses_claudecode_provider(self):
        """call_llm should use ClaudeCodeLM when model starts with claudecode/."""
        import dspy

        from voicetest.llm import call_llm

        class TestSignature(dspy.Signature):
            """Test signature."""

            question: str = dspy.InputField()
            answer: str = dspy.OutputField()

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "The answer is 42."})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
            patch.object(
                dspy.Predict,
                "__call__",
                return_value=dspy.Prediction(answer="42"),
            ),
        ):
            result = await call_llm(
                "claudecode/sonnet",
                TestSignature,
                predictor_class=dspy.Predict,
                question="What is the answer?",
            )

            assert result.answer == "42"


class TestClaudeCodeLMCaching:
    """Test DSPy cache integration for ClaudeCodeLM."""

    @pytest.fixture(autouse=True)
    def _fresh_cache(self, tmp_path):
        """Use a fresh temporary DSPy cache so tests don't pollute each other."""
        import dspy

        original_cache = dspy.cache
        dspy.cache = dspy.clients.cache.Cache(
            enable_disk_cache=True,
            enable_memory_cache=True,
            disk_cache_dir=str(tmp_path / "dspy_cache"),
        )
        yield
        dspy.cache = original_cache

    def test_cache_hit_skips_cli_call(self):
        """Identical prompts should return cached result without calling CLI twice."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "cached response"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM()
            # First call — cache miss, hits CLI
            result1 = lm(prompt="cache_test_unique_1")
            assert mock_run.call_count == 1
            # Second identical call — cache hit, no CLI call
            result2 = lm(prompt="cache_test_unique_1")
            assert mock_run.call_count == 1
            assert result1 == result2

    def test_different_prompts_are_cached_separately(self):
        """Different prompts should each call CLI once."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"result": f"response {call_count}"})
            return result

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", side_effect=mock_subprocess_run),
        ):
            lm = ClaudeCodeLM()
            r1 = lm(prompt="cache_test_a")
            r2 = lm(prompt="cache_test_b")
            assert call_count == 2
            assert r1[0]["text"] != r2[0]["text"]

    def test_cache_disabled_calls_cli_every_time(self):
        """When cache=False, CLI should be called every time."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = json.dumps({"result": "response"})

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result) as mock_run,
        ):
            lm = ClaudeCodeLM(cache=False)
            lm(prompt="cache_test_disabled")
            lm(prompt="cache_test_disabled")
            assert mock_run.call_count == 2

    def test_cache_salt_differentiates_cache_keys(self):
        """Different metadata should produce different cache keys."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        call_count = 0

        def mock_subprocess_run(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            result = MagicMock()
            result.returncode = 0
            result.stdout = json.dumps({"result": f"response {call_count}"})
            return result

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", side_effect=mock_subprocess_run),
        ):
            lm1 = ClaudeCodeLM(metadata={"_cache_salt": "salt_a"})
            lm2 = ClaudeCodeLM(metadata={"_cache_salt": "salt_b"})
            lm1(prompt="cache_test_salt")
            lm2(prompt="cache_test_salt")
            # Different salts → different cache keys → both hit CLI
            assert call_count == 2


class TestCreateLmCachePassthrough:
    """Test that _create_lm passes cache options to ClaudeCodeLM."""

    def test_cache_salt_passed_to_claudecode(self):
        """_create_lm should pass cache_salt as metadata to ClaudeCodeLM."""
        from voicetest.llm.base import _create_lm
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = _create_lm("claudecode/sonnet", cache_salt="abc123")
            assert isinstance(lm, ClaudeCodeLM)
            assert lm.kwargs.get("metadata", {}).get("_cache_salt") == "abc123"

    def test_no_cache_passed_to_claudecode(self):
        """_create_lm should pass no_cache as cache=False to ClaudeCodeLM."""
        from voicetest.llm.base import _create_lm
        from voicetest.llm.claudecode import ClaudeCodeLM

        with patch("shutil.which", return_value="/usr/local/bin/claude"):
            lm = _create_lm("claudecode/sonnet", no_cache=True)
            assert isinstance(lm, ClaudeCodeLM)
            assert lm.cache is False


class TestClaudeCodeLMQuotaExhausted:
    """Test quota exhaustion detection from Claude Code CLI."""

    def test_detects_hit_your_limit(self):
        """Should raise QuotaExhaustedError for the known Claude Code quota message."""
        from voicetest.exceptions import QuotaExhaustedError
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps(
            {
                "is_error": True,
                "result": "You've hit your limit · resets 3pm (America/New_York)",
            }
        )

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(QuotaExhaustedError) as exc_info:
                lm("test prompt")

            assert "quota exhausted" in str(exc_info.value).lower()

    def test_parses_reset_time_from_message(self):
        """Should extract reset time into reset_message attribute."""
        from voicetest.exceptions import QuotaExhaustedError
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps(
            {
                "is_error": True,
                "result": "You've hit your limit · resets 3pm (America/New_York)",
            }
        )

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(QuotaExhaustedError) as exc_info:
                lm("test prompt")

            assert exc_info.value.reset_message == "3pm (America/New_York)"

    def test_detection_is_case_insensitive(self):
        """Should detect 'hit your limit' regardless of case."""
        from voicetest.exceptions import QuotaExhaustedError
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps(
            {
                "is_error": True,
                "result": "You've HIT YOUR LIMIT · resets 5pm (America/Chicago)",
            }
        )

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(QuotaExhaustedError):
                lm("test prompt")

    def test_other_errors_still_raise_runtime_error(self):
        """Non-quota is_error responses should still raise RuntimeError."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = json.dumps(
            {
                "is_error": True,
                "result": "Credit balance is too low",
            }
        )

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", return_value=mock_result),
        ):
            lm = ClaudeCodeLM(cache=False)
            with pytest.raises(RuntimeError, match="Credit balance is too low"):
                lm("test prompt")


class TestPackageExports:
    """Test that package exports match the original llm.py module."""

    def test_call_llm_exported(self):
        """call_llm should be importable from voicetest.llm."""
        from voicetest.llm import call_llm

        assert callable(call_llm)

    def test_on_token_callback_exported(self):
        """OnTokenCallback should be importable from voicetest.llm."""
        from voicetest.llm import OnTokenCallback

        assert OnTokenCallback is not None

    def test_on_error_callback_exported(self):
        """OnErrorCallback should be importable from voicetest.llm."""
        from voicetest.llm import OnErrorCallback

        assert OnErrorCallback is not None

    def test_private_functions_exported(self):
        """Private functions should still be accessible for tests."""
        from voicetest.llm import _call_llm_streaming
        from voicetest.llm import _call_llm_sync
        from voicetest.llm import _invoke_callback

        assert callable(_call_llm_sync)
        assert callable(_call_llm_streaming)
        assert callable(_invoke_callback)
