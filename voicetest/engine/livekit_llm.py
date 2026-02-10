"""LiveKit LLM plugin that delegates to ConversationEngine.

This module provides VoicetestLLM, a LiveKit-compatible LLM that uses
the same ConversationEngine as the test runner. This ensures tests and
live calls behave identically.
"""

from collections.abc import AsyncIterable

from livekit.agents import llm as livekit_llm

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

    def chat(
        self,
        *,
        chat_ctx: livekit_llm.ChatContext,
        tools: list[livekit_llm.FunctionTool] | None = None,
        conn_options: livekit_llm.LLMOptions | None = None,
        parallel_tool_calls: bool | None = None,
        tool_choice: livekit_llm.ToolChoice | None = None,
        extra_body: dict | None = None,
    ) -> "VoicetestLLMStream":
        """Process a chat turn using the ConversationEngine.

        Args:
            chat_ctx: LiveKit chat context with message history.
            tools: Available tools (not used - engine handles tools).
            conn_options: Connection options.
            parallel_tool_calls: Whether to allow parallel tool calls.
            tool_choice: Tool choice preference.
            extra_body: Extra body parameters.

        Returns:
            VoicetestLLMStream that yields the response.
        """
        return VoicetestLLMStream(self._engine, chat_ctx)


class VoicetestLLMStream(livekit_llm.LLMStream):
    """Stream adapter for ConversationEngine responses."""

    def __init__(self, engine: ConversationEngine, chat_ctx: livekit_llm.ChatContext):
        """Initialize the stream.

        Args:
            engine: The ConversationEngine to use.
            chat_ctx: LiveKit chat context.
        """
        super().__init__(
            chat_ctx=chat_ctx,
            tools=[],
            conn_options=livekit_llm.LLMOptions(),
        )
        self._engine = engine
        self._chat_ctx = chat_ctx
        self._response_text = ""

    def _extract_user_message(self) -> str:
        """Extract the latest user message from the chat context."""
        for msg in reversed(self._chat_ctx.items):
            if isinstance(msg, livekit_llm.ChatMessage) and msg.role == "user":
                if isinstance(msg.content, str):
                    return msg.content
                elif isinstance(msg.content, list):
                    for part in msg.content:
                        if isinstance(part, str):
                            return part
        return ""

    async def _run(self) -> None:
        """Run the stream, processing the turn through the engine."""
        user_message = self._extract_user_message()

        if not user_message:
            return

        # Add user message to engine transcript
        self._engine.add_user_message(user_message)

        # Collect tokens for streaming
        tokens: list[str] = []

        async def collect_token(token: str) -> None:
            tokens.append(token)

        # Process turn through engine (same logic as test runner)
        result = await self._engine.process_turn(
            user_message,
            on_token=collect_token,
        )

        self._response_text = result.response

        # Emit response as chunks for LiveKit TTS
        for token in tokens:
            chunk = livekit_llm.ChatChunk(
                id="chunk",
                choices=[
                    livekit_llm.Choice(
                        delta=livekit_llm.ChoiceDelta(
                            role="assistant",
                            content=token,
                        ),
                        index=0,
                    )
                ],
            )
            self._event_ch.send_nowait(chunk)

    async def gather(self) -> livekit_llm.ChatChunk:
        """Wait for the stream to complete and return the full response."""
        await self._run()

        return livekit_llm.ChatChunk(
            id="final",
            choices=[
                livekit_llm.Choice(
                    delta=livekit_llm.ChoiceDelta(
                        role="assistant",
                        content=self._response_text,
                    ),
                    index=0,
                )
            ],
        )

    async def __anext__(self) -> livekit_llm.ChatChunk:
        """Get the next chunk from the stream."""
        return await self._event_ch.recv()

    def __aiter__(self) -> AsyncIterable[livekit_llm.ChatChunk]:
        """Iterate over chunks."""
        return self

    @property
    def chat_ctx(self) -> livekit_llm.ChatContext:
        """Return the chat context."""
        return self._chat_ctx

    @property
    def tools(self) -> list[livekit_llm.FunctionTool]:
        """Return available tools."""
        return []
