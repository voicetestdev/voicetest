"""LiveKit LLM plugin that delegates to UserSimulator.

This module provides SimulatorLLM, a LiveKit-compatible LLM that drives the
caller side of a live call from the same UserSimulator used by text runs. It is
the symmetric twin of VoicetestLLM: where that adapter wraps the agent's
ConversationEngine, this one wraps the simulated user.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import sys

from livekit.agents import llm as livekit_llm
from livekit.agents.llm.llm import APIConnectOptions

from voicetest.models.results import Message
from voicetest.simulator.user_sim import UserSimulator


def to_voicetest_transcript(chat_ctx: livekit_llm.ChatContext) -> list[Message]:
    """Map a caller AgentSession's chat_ctx to voicetest roles.

    LiveKit labels roles from this session's own point of view: the agent under
    test is heard via STT and tagged 'user', and the caller's own turns are
    tagged 'assistant'. Voicetest's convention is the opposite (agent =
    assistant, caller = user), so the roles are flipped for the simulator."""
    transcript: list[Message] = []
    for item in chat_ctx.items:
        if not isinstance(item, livekit_llm.ChatMessage):
            continue
        text = item.text_content
        if not text:
            continue
        if item.role == "user":
            transcript.append(Message(role="assistant", content=text))
        elif item.role == "assistant":
            transcript.append(Message(role="user", content=text))
    return transcript


class SimulatorLLM(livekit_llm.LLM):
    """LiveKit LLM that delegates to UserSimulator.

    Drives the caller cascade's next spoken turn from the persona simulator,
    keeping identical user behavior between text runs and live calls."""

    def __init__(self, simulator: UserSimulator):
        """Initialize with a UserSimulator."""
        super().__init__()
        self._simulator = simulator
        self._on_response: Callable[[str], None] | None = None

    def set_on_response(self, callback: Callable[[str], None]) -> None:
        """Set callback for immediate transcript output when the caller speaks."""
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
    ) -> SimulatorLLMStream:
        """Process a chat turn using the UserSimulator."""
        stream = SimulatorLLMStream(
            self, self._simulator, chat_ctx, conn_options or APIConnectOptions()
        )
        stream._on_response = self._on_response
        return stream


class SimulatorLLMStream(livekit_llm.LLMStream):
    """Stream adapter for UserSimulator responses."""

    def __init__(
        self,
        llm: SimulatorLLM,
        simulator: UserSimulator,
        chat_ctx: livekit_llm.ChatContext,
        conn_options: APIConnectOptions,
    ):
        """Initialize the stream."""
        super().__init__(
            llm=llm,
            chat_ctx=chat_ctx,
            tools=[],
            conn_options=conn_options,
        )
        self._simulator = simulator
        self._chat_ctx = chat_ctx
        self._on_response: Callable[[str], None] | None = None

    async def _run(self) -> None:
        """Run the stream, producing the caller's next turn from the simulator."""
        transcript = to_voicetest_transcript(self._chat_ctx)

        # Shield from cancellation so LiveKit's speech interruption doesn't abort
        # the simulator LLM call mid-flight, matching VoicetestLLM.
        try:
            response = await asyncio.shield(self._simulator.generate(transcript))
        except asyncio.CancelledError:
            print(
                "[simulator-llm] _run cancelled during generate",
                file=sys.stderr,
                flush=True,
            )
            return
        except Exception as e:
            print(
                f"[simulator-llm] generate error: {type(e).__name__}: {e}",
                file=sys.stderr,
                flush=True,
            )
            raise

        # A None response means the simulator is exhausted (goal reached / nothing
        # left to say); emit no turn so the worker can begin teardown.
        if response is None:
            return

        response_text = response.message

        # Immediately output transcript so the consumer shows it right away,
        # without waiting for TTS. Guarded because the stdout pipe to the parent
        # may be broken if the call ended before the response arrived.
        if response_text and self._on_response:
            try:
                self._on_response(response_text)
            except BrokenPipeError:
                print(
                    "[simulator-llm] on_response: stdout pipe broken, skipping",
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
