"""Tests for the UserSimulator -> LiveKit LLM adapter."""

from livekit.agents import llm as lk_llm
import pytest

from voicetest.livecall.simulator_adapter import SimulatorLLM
from voicetest.livecall.simulator_adapter import to_voicetest_transcript
from voicetest.simulator.user_sim import SimulatorResponse


def _ctx(*messages):
    ctx = lk_llm.ChatContext.empty()
    for role, content in messages:
        ctx.add_message(role=role, content=content)
    return ctx


class FakeSimulator:
    def __init__(self, message):
        self._message = message
        self.received = None

    async def generate(self, transcript, on_token=None, on_error=None):
        self.received = transcript
        if self._message is None:
            return None
        return SimulatorResponse(message=self._message)


class TestToVoicetestTranscript:
    def test_flips_session_roles_to_voicetest_convention(self):
        ctx = _ctx(("user", "hi from agent"), ("assistant", "caller reply"))

        transcript = to_voicetest_transcript(ctx)

        assert [(m.role, m.content) for m in transcript] == [
            ("assistant", "hi from agent"),
            ("user", "caller reply"),
        ]

    def test_skips_non_conversational_items(self):
        ctx = _ctx(("system", "you are a caller"), ("user", "hello"))

        transcript = to_voicetest_transcript(ctx)

        assert [(m.role, m.content) for m in transcript] == [("assistant", "hello")]


class TestSimulatorLLM:
    @pytest.mark.asyncio
    async def test_generates_from_flipped_transcript_and_emits_chunk(self):
        simulator = FakeSimulator("I need to book a flight")
        sim_llm = SimulatorLLM(simulator)
        emitted = []
        sim_llm.set_on_response(emitted.append)
        ctx = _ctx(("user", "How can I help?"))

        stream = sim_llm.chat(chat_ctx=ctx)
        chunks = [c async for c in stream]

        assert [(m.role, m.content) for m in simulator.received] == [
            ("assistant", "How can I help?"),
        ]
        content = "".join(c.delta.content for c in chunks if c.delta and c.delta.content)
        assert content == "I need to book a flight"
        assert emitted == ["I need to book a flight"]

    @pytest.mark.asyncio
    async def test_exhausted_simulator_emits_no_chunk(self):
        sim_llm = SimulatorLLM(FakeSimulator(None))
        emitted = []
        sim_llm.set_on_response(emitted.append)
        ctx = _ctx(("user", "How can I help?"))

        stream = sim_llm.chat(chat_ctx=ctx)
        chunks = [c async for c in stream]

        assert chunks == []
        assert emitted == []
