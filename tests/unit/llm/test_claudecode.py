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
            lm = ClaudeCodeLM(model="claudecode/sonnet")
            lm("What is 2+2?")

            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            assert args[0] == "claude"
            assert "-p" in args
            assert "--output-format" in args
            assert "json" in args
            assert "--model" in args
            assert "sonnet" in args
            assert "What is 2+2?" in args

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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
            with pytest.raises(RuntimeError, match="Credit balance is too low"):
                lm("test prompt")

    def test_raises_on_timeout(self):
        """Should propagate TimeoutExpired from subprocess."""
        from voicetest.llm.claudecode import ClaudeCodeLM

        with (
            patch("shutil.which", return_value="/usr/local/bin/claude"),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired("claude", 120)),
        ):
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM(model="claudecode/haiku")
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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
            lm(prompt)

            args = mock_run.call_args[0][0]
            assert prompt in args

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
            lm = ClaudeCodeLM()
            lm(prompt)

            args = mock_run.call_args[0][0]
            assert prompt in args

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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
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
            lm = ClaudeCodeLM()
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
                question="What is the answer?",
            )

            assert result.answer == "42"


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
