"""Tests for the agent worker's opening turn."""

import pytest

from voicetest.engine.conversation import TurnResult
from voicetest.livecall.agent_worker import opening_turn


class FakeEngine:
    def __init__(self, response):
        self._response = response
        self.advance_calls = 0

    async def advance(self):
        self.advance_calls += 1
        return TurnResult(response=self._response)


class TestOpeningTurn:
    @pytest.mark.asyncio
    async def test_advances_once_and_emits_greeting(self):
        engine = FakeEngine("Hi, how can I help?")
        emitted = []

        text = await opening_turn(engine, emitted.append)

        assert engine.advance_calls == 1
        assert text == "Hi, how can I help?"
        assert emitted == ["Hi, how can I help?"]

    @pytest.mark.asyncio
    async def test_empty_response_emits_nothing(self):
        engine = FakeEngine("")
        emitted = []

        text = await opening_turn(engine, emitted.append)

        assert text is None
        assert emitted == []
