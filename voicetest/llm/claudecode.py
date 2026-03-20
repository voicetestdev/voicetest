"""Claude Code CLI LLM provider.

Uses Claude Code CLI with Max subscription quota by ensuring the API key
environment variable is not set.
"""

import json
import os
import re
import shutil
import subprocess
from typing import Any

import dspy
from dspy.adapters.chat_adapter import ChatAdapter
from dspy.clients.cache import request_cache

from voicetest.exceptions import QuotaExhaustedError


class ClaudeCodeLM(dspy.LM):
    """LLM provider using Claude Code CLI.

    This allows voicetest users with Claude Code installed to use it
    as their LLM backend without separate API key configuration.

    Uses Max subscription quota by clearing ANTHROPIC_API_KEY from the
    subprocess environment.

    Model strings:
        - claudecode/sonnet → Claude Sonnet
        - claudecode/opus → Claude Opus
        - claudecode/haiku → Claude Haiku
    """

    # Claude Code sessions add their own formatting context which interferes
    # with JSON/BAML adapters. Use ChatAdapter (text format) instead.
    preferred_adapter = ChatAdapter()

    def __init__(self, model: str = "claudecode/sonnet", **kwargs):
        # Initialize parent class with model string
        super().__init__(model=model, **kwargs)
        self.variant = model.split("/", 1)[1] if "/" in model else model
        self._check_available()

    def _check_available(self):
        if not shutil.which("claude"):
            raise RuntimeError(
                "Claude Code CLI not found. Install from https://claude.ai/claude-code"
            )

    def _messages_to_prompt(self, messages: list[dict[str, Any]]) -> str:
        """Convert chat messages to a single prompt string."""
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if isinstance(content, list):
                # Handle content blocks (e.g., [{"type": "text", "text": "..."}])
                text_parts = [
                    block.get("text", "") for block in content if block.get("type") == "text"
                ]
                content = "\n".join(text_parts)
            if role == "system":
                parts.append(f"System: {content}")
            elif role == "assistant":
                parts.append(f"Assistant: {content}")
            else:
                parts.append(f"User: {content}")
        return "\n\n".join(parts)

    def __call__(
        self,
        prompt: str | None = None,
        messages: list[dict[str, Any]] | None = None,
        **kwargs,
    ) -> list[dict[str, Any]]:
        """Send prompt to Claude Code CLI, with DSPy cache integration.

        Args:
            prompt: Direct prompt string (used if messages not provided)
            messages: Chat messages in OpenAI format (takes precedence)
            **kwargs: Additional arguments (timeout supported)

        Returns:
            List with single dict containing response
        """
        # Build the request dict for cache key computation
        messages = messages or [{"role": "user", "content": prompt}]
        request = {
            "model": self.model,
            "messages": messages,
            **self.kwargs,
        }

        completion = self._run_cli
        if self.cache:
            completion = request_cache(cache_arg_name="request")(completion)

        return completion(request=request, timeout=kwargs.get("timeout", 120))

    def _run_cli(
        self, request: dict[str, Any], timeout: int = 120, **kwargs
    ) -> list[dict[str, Any]]:
        """Execute the Claude CLI subprocess."""
        messages = request.get("messages", [])
        prompt_text = self._messages_to_prompt(messages)

        # Create environment without ANTHROPIC_API_KEY to use Max quota
        # Also unset CLAUDECODE to allow nested sessions
        env = os.environ.copy()
        env.pop("ANTHROPIC_API_KEY", None)
        env.pop("CLAUDECODE", None)

        result = subprocess.run(
            ["claude", "-p", "--output-format", "json", "--model", self.variant, prompt_text],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )

        # Try to parse JSON response (Claude Code outputs JSON even on errors)
        try:
            response = json.loads(result.stdout)
        except json.JSONDecodeError as err:
            if result.returncode != 0:
                raise RuntimeError(
                    f"Claude Code failed: {result.stderr or 'unknown error'}"
                ) from err
            raise

        # Check for error in JSON response
        if response.get("is_error"):
            error_msg = response.get("result", "unknown error")
            # "You've hit your limit · resets 3pm (America/New_York)"
            if "hit your limit" in error_msg.lower():
                reset_match = re.search(r"resets?\s+(.+)", error_msg)
                reset_message = reset_match.group(1) if reset_match else None
                detail = "Claude Code quota exhausted."
                if reset_message:
                    detail += f" Resets {reset_message}."
                raise QuotaExhaustedError(detail, reset_message=reset_message)
            raise RuntimeError(f"Claude Code error: {error_msg}")

        return [{"text": response["result"]}]
