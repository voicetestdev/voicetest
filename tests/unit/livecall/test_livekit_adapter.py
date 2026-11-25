from livekit.agents import llm as lk_llm
import pytest

from voicetest.engine.conversation import TurnResult
from voicetest.livecall.livekit_adapter import VoicetestLLM


def _ctx(*messages):
    ctx = lk_llm.ChatContext.empty()
    for role, content in messages:
        ctx.add_message(role=role, content=content)
    return ctx


class FakeEngine:
    def __init__(self, response):
        self._response = response
        self.user_messages = []

    async def add_user_message(self, content):
        self.user_messages.append(content)

    async def advance(self):
        return TurnResult(response=self._response)


async def _run(llm, ctx):
    return [c async for c in llm.chat(chat_ctx=ctx)]


def _content(chunks):
    return "".join(c.delta.content for c in chunks if c.delta and c.delta.content)


class TestVoicetestLLM:
    @pytest.mark.asyncio
    async def test_sends_latest_user_message_and_emits_response(self):
        engine = FakeEngine("How can I help?")
        llm = VoicetestLLM(engine)
        emitted = []
        llm.set_on_response(emitted.append)

        chunks = await _run(llm, _ctx(("user", "hi"), ("assistant", "hello"), ("user", "help")))

        assert engine.user_messages == ["help"]
        assert _content(chunks) == "How can I help?"
        assert emitted == ["How can I help?"]

    @pytest.mark.asyncio
    async def test_no_user_message_skips_engine(self):
        engine = FakeEngine("unused")
        llm = VoicetestLLM(engine)

        chunks = await _run(llm, _ctx(("system", "instructions")))

        assert engine.user_messages == []
        assert chunks == []

    @pytest.mark.asyncio
    async def test_broken_stdout_pipe_still_emits_chunk(self):
        llm = VoicetestLLM(FakeEngine("Still here."))

        def broken(_text):
            raise BrokenPipeError

        llm.set_on_response(broken)

        chunks = await _run(llm, _ctx(("user", "hello?")))

        assert _content(chunks) == "Still here."
