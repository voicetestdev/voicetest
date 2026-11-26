"""LiveKit LLM plugin that delegates to ConversationEngine.

This module provides VoicetestLLM, a LiveKit-compatible LLM that uses
the same ConversationEngine as the test runner. This ensures tests and
live calls behave identically.
"""

from __future__ import annotations

from livekit.agents import llm as livekit_llm
from livekit.agents.llm.llm import APIConnectOptions

from voicetest.engine.conversation import ConversationEngine
from voicetest.livecall.delegating_llm import DelegatingLLM
from voicetest.livecall.delegating_llm import DelegatingLLMStream
from voicetest.livecall.delegating_llm import chat_texts


class VoicetestLLM(DelegatingLLM):
    """LiveKit LLM that delegates to ConversationEngine.

    This LLM plugin wraps the ConversationEngine to provide identical
    behavior between test runs and live calls."""

    def __init__(self, engine: ConversationEngine):
        """Initialize with a ConversationEngine."""
        super().__init__()
        self._engine = engine

    def _stream(
        self, chat_ctx: livekit_llm.ChatContext, conn_options: APIConnectOptions
    ) -> VoicetestLLMStream:
        return VoicetestLLMStream(self, self._engine, chat_ctx, conn_options)


class VoicetestLLMStream(DelegatingLLMStream):
    """Stream adapter for ConversationEngine responses."""

    log_prefix = "voicetest-llm"

    def __init__(
        self,
        llm: VoicetestLLM,
        engine: ConversationEngine,
        chat_ctx: livekit_llm.ChatContext,
        conn_options: APIConnectOptions,
    ):
        """Initialize the stream."""
        super().__init__(llm, chat_ctx, conn_options)
        self._engine = engine

    async def _respond(self) -> str | None:
        user_messages = [text for role, text in chat_texts(self._chat_ctx) if role == "user"]
        if not user_messages:
            return None
        await self._engine.add_user_message(user_messages[-1])
        result = await self._engine.advance()
        return result.response
