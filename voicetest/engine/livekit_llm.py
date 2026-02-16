"""LiveKit LLM plugin that delegates to ConversationEngine.

This module provides VoicetestLLM, a LiveKit-compatible LLM that uses
the same ConversationEngine as the test runner. This ensures tests and
live calls behave identically.
"""

import asyncio
from collections.abc import Callable
import sys

from livekit.agents import llm as livekit_llm
from livekit.agents.llm.llm import APIConnectOptions

from voicetest.engine.conversation import ConversationEngine


class VoicetestLLM(livekit_llm.LLM):
    """LiveKit LLM that delegates to ConversationEngine.

    This LLM plugin wraps the ConversationEngine to provide identical
    behavior between test runs and live calls.
    """

    def __init__(self, engine: ConversationEngine):
        """Initialize with a ConversationEngine.

        Args:
            engine: The ConversationEngine to delegate to.
        """
        super().__init__()
        self._engine = engine
        self._on_response: Callable[[str], None] | None = None

    def set_on_response(self, callback: Callable[[str], None]) -> None:
        """Set callback for immediate transcript output when LLM responds."""
        self._on_response = callback

    def chat(
        self,
        *,
        chat_ctx: livekit_llm.ChatContext,
        tools: list[livekit_llm.Tool] | None = None,
        conn_options: APIConnectOptions | None = None,
        parallel_tool_calls: bool | None = None,
        tool_choice: livekit_llm.ToolChoice | None = None,
        extra_kwargs: dict | None = None,
    ) -> "VoicetestLLMStream":
        """Process a chat turn using the ConversationEngine.

        Args:
            chat_ctx: LiveKit chat context with message history.
            tools: Available tools (not used - engine handles tools).
            conn_options: Connection options.
            parallel_tool_calls: Whether to allow parallel tool calls.
            tool_choice: Tool choice preference.
            extra_kwargs: Extra keyword arguments.

        Returns:
            VoicetestLLMStream that yields the response.
        """
        stream = VoicetestLLMStream(
            self, self._engine, chat_ctx, conn_options or APIConnectOptions()
        )
        stream._on_response = self._on_response
        return stream


class VoicetestLLMStream(livekit_llm.LLMStream):
    """Stream adapter for ConversationEngine responses."""

    def __init__(
        self,
        llm: VoicetestLLM,
        engine: ConversationEngine,
        chat_ctx: livekit_llm.ChatContext,
        conn_options: APIConnectOptions,
    ):
        """Initialize the stream.

        Args:
            llm: The parent LLM instance.
            engine: The ConversationEngine to use.
            chat_ctx: LiveKit chat context.
            conn_options: API connection options.
        """
        super().__init__(
            llm=llm,
            chat_ctx=chat_ctx,
            tools=[],
            conn_options=conn_options,
        )
        self._engine = engine
        self._chat_ctx = chat_ctx
        self._on_response: Callable[[str], None] | None = None

    def _extract_user_message(self) -> str:
        """Extract the latest user message from the chat context."""
        for msg in reversed(self._chat_ctx.items):
            if isinstance(msg, livekit_llm.ChatMessage) and msg.role == "user":
                text = msg.text_content
                if text:
                    return text
        return ""

    async def _run(self) -> None:
        """Run the stream, processing the turn through the engine."""
        user_message = self._extract_user_message()

        if not user_message:
            return

        # Add user message to engine transcript
        self._engine.add_user_message(user_message)

        # Process turn through engine without streaming. This uses the non-streaming
        # call_llm path which properly offloads blocking LLM calls (e.g. ClaudeCodeLM
        # subprocess) to a thread via asyncio.to_thread.
        # Shield from cancellation so LiveKit's speech interruption doesn't abort the
        # LLM call mid-flight. The LLM subprocess can't be cheaply cancelled anyway.
        try:
            result = await asyncio.shield(self._engine.process_turn(user_message))
        except asyncio.CancelledError:
            print(
                "[voicetest-llm] _run cancelled during process_turn",
                file=sys.stderr,
                flush=True,
            )
            return
        except Exception as e:
            print(
                f"[voicetest-llm] process_turn error: {type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )
            raise

        response_text = result.response

        # Immediately output transcript so the frontend shows it right away,
        # without waiting for TTS to finish generating and playing audio.
        # Wrapped in try/except because the stdout pipe to the parent process
        # may be broken if the call ended before the LLM response arrived.
        if response_text and self._on_response:
            try:
                self._on_response(response_text)
            except BrokenPipeError:
                print(
                    "[voicetest-llm] on_response: stdout pipe broken, skipping",
                    file=sys.stderr,
                    flush=True,
                )

        if response_text:
            chunk = livekit_llm.ChatChunk(
                id="chunk",
                delta=livekit_llm.ChoiceDelta(
                    role="assistant",
                    content=response_text,
                ),
            )
            self._event_ch.send_nowait(chunk)
