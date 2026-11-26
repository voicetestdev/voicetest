"""LiveKit LLM plugin that delegates to UserSimulator.

This module provides SimulatorLLM, a LiveKit-compatible LLM that drives the
caller side of a live call from the same UserSimulator used by text runs. It is
the symmetric twin of VoicetestLLM: where that adapter wraps the agent's
ConversationEngine, this one wraps the simulated user.
"""

from __future__ import annotations

from livekit.agents import llm as livekit_llm
from livekit.agents.llm.llm import APIConnectOptions

from voicetest.livecall.delegating_llm import DelegatingLLM
from voicetest.livecall.delegating_llm import DelegatingLLMStream
from voicetest.livecall.delegating_llm import chat_texts
from voicetest.models.results import Message
from voicetest.simulator.user_sim import UserSimulator


_SESSION_TO_VOICETEST_ROLE = {"user": "assistant", "assistant": "user"}


def to_voicetest_transcript(chat_ctx: livekit_llm.ChatContext) -> list[Message]:
    """Map a caller AgentSession's chat_ctx to voicetest roles.

    LiveKit labels roles from this session's own point of view: the agent under
    test is heard via STT and tagged 'user', and the caller's own turns are
    tagged 'assistant'. Voicetest's convention is the opposite (agent =
    assistant, caller = user), so the roles are flipped for the simulator."""
    return [
        Message(role=_SESSION_TO_VOICETEST_ROLE[role], content=text)
        for role, text in chat_texts(chat_ctx)
        if role in _SESSION_TO_VOICETEST_ROLE
    ]


class SimulatorLLM(DelegatingLLM):
    """LiveKit LLM that delegates to UserSimulator.

    Drives the caller cascade's next spoken turn from the persona simulator,
    keeping identical user behavior between text runs and live calls."""

    def __init__(self, simulator: UserSimulator):
        """Initialize with a UserSimulator."""
        super().__init__()
        self._simulator = simulator

    def _stream(
        self, chat_ctx: livekit_llm.ChatContext, conn_options: APIConnectOptions
    ) -> SimulatorLLMStream:
        return SimulatorLLMStream(self, self._simulator, chat_ctx, conn_options)


class SimulatorLLMStream(DelegatingLLMStream):
    """Stream adapter for UserSimulator responses."""

    log_prefix = "simulator-llm"

    def __init__(
        self,
        llm: SimulatorLLM,
        simulator: UserSimulator,
        chat_ctx: livekit_llm.ChatContext,
        conn_options: APIConnectOptions,
    ):
        """Initialize the stream."""
        super().__init__(llm, chat_ctx, conn_options)
        self._simulator = simulator

    async def _respond(self) -> str | None:
        # A None response means the simulator is exhausted (goal reached / nothing
        # left to say); emit no turn so the worker can begin teardown.
        response = await self._simulator.generate(to_voicetest_transcript(self._chat_ctx))
        return response.message if response else None
