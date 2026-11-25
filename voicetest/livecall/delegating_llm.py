from __future__ import annotations

import asyncio
from collections.abc import Callable
from collections.abc import Iterator
import sys

from livekit.agents import llm as livekit_llm
from livekit.agents.llm.llm import APIConnectOptions


def chat_texts(chat_ctx: livekit_llm.ChatContext) -> Iterator[tuple[str, str]]:
    for item in chat_ctx.items:
        if isinstance(item, livekit_llm.ChatMessage) and item.text_content:
            yield item.role, item.text_content


class DelegatingLLM(livekit_llm.LLM):
    def __init__(self) -> None:
        super().__init__()
        self._on_response: Callable[[str], None] | None = None

    def set_on_response(self, callback: Callable[[str], None]) -> None:
        """Set callback for immediate transcript output when a turn's text is ready."""
        self._on_response = callback

    def chat(
        self,
        *,
        chat_ctx: livekit_llm.ChatContext,
        tools: list[livekit_llm.FunctionTool | livekit_llm.RawFunctionTool] | None = None,
        conn_options: APIConnectOptions | None = None,
        parallel_tool_calls: bool | None = None,
        tool_choice: livekit_llm.ToolChoice | None = None,
        extra_kwargs: dict | None = None,
    ) -> DelegatingLLMStream:
        stream = self._stream(chat_ctx, conn_options or APIConnectOptions())
        stream._on_response = self._on_response
        return stream

    def _stream(
        self, chat_ctx: livekit_llm.ChatContext, conn_options: APIConnectOptions
    ) -> DelegatingLLMStream:
        raise NotImplementedError


class DelegatingLLMStream(livekit_llm.LLMStream):
    log_prefix = "delegating-llm"

    def __init__(
        self,
        llm: DelegatingLLM,
        chat_ctx: livekit_llm.ChatContext,
        conn_options: APIConnectOptions,
    ):
        super().__init__(llm=llm, chat_ctx=chat_ctx, tools=[], conn_options=conn_options)
        self._chat_ctx = chat_ctx
        self._on_response: Callable[[str], None] | None = None

    async def _respond(self) -> str | None:
        raise NotImplementedError

    def _log(self, message: str) -> None:
        print(f"[{self.log_prefix}] {message}", file=sys.stderr, flush=True)

    async def _run(self) -> None:
        # Shielded so LiveKit's speech interruption doesn't abort the model call
        # mid-flight; the underlying call can't be cheaply cancelled anyway.
        try:
            response_text = await asyncio.shield(self._respond())
        except asyncio.CancelledError:
            self._log("_run cancelled while responding")
            return
        except Exception as e:
            self._log(f"respond error: {type(e).__name__}: {e}")
            raise

        if not response_text:
            return

        # The stdout pipe to the parent may be broken if the call ended before
        # the response arrived.
        if self._on_response:
            try:
                self._on_response(response_text)
            except BrokenPipeError:
                self._log("on_response: stdout pipe broken, skipping")

        self._event_ch.send_nowait(
            livekit_llm.ChatChunk(
                id="chunk",
                delta=livekit_llm.ChoiceDelta(role="assistant", content=response_text),
            )
        )
