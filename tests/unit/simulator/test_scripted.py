"""Tests for ScriptedUserSimulator."""

import pytest

from voicetest.models.results import Message
from voicetest.simulator.scripted import ScriptedUserSimulator
from voicetest.simulator.user_sim import SimulatorResponse


def _transcript() -> list[Message]:
    """Mixed-role source transcript."""
    return [
        Message(role="assistant", content="Hi, how can I help?"),
        Message(role="user", content="I need to cancel my order."),
        Message(role="assistant", content="What's the order number?"),
        Message(role="user", content="ORD-12345."),
        Message(role="assistant", content="Cancelled. Anything else?"),
        Message(role="user", content="No, thanks."),
    ]


class TestScriptedUserSimulator:
    @pytest.mark.asyncio
    async def test_yields_user_turns_in_order(self):
        sim = ScriptedUserSimulator(_transcript())

        first = await sim.generate([])
        second = await sim.generate([])
        third = await sim.generate([])

        assert first.message == "I need to cancel my order."
        assert second.message == "ORD-12345."
        assert third.message == "No, thanks."

    @pytest.mark.asyncio
    async def test_returns_none_when_exhausted(self):
        sim = ScriptedUserSimulator(_transcript())

        # Consume the 3 user turns
        for _ in range(3):
            assert await sim.generate([]) is not None

        assert await sim.generate([]) is None

    @pytest.mark.asyncio
    async def test_ignores_assistant_turns_from_source(self):
        """Assistant-role messages in the source don't enter the script —
        the live agent's responses replace them."""
        only_assistant = [
            Message(role="assistant", content="One"),
            Message(role="assistant", content="Two"),
        ]
        sim = ScriptedUserSimulator(only_assistant)

        assert await sim.generate([]) is None

    @pytest.mark.asyncio
    async def test_empty_transcript(self):
        sim = ScriptedUserSimulator([])

        assert await sim.generate([]) is None

    @pytest.mark.asyncio
    async def test_returns_simulator_response_type(self):
        sim = ScriptedUserSimulator(_transcript())

        response = await sim.generate([])

        assert isinstance(response, SimulatorResponse)

    @pytest.mark.asyncio
    async def test_does_not_consult_live_transcript(self):
        """The scripted simulator yields the next recorded user turn regardless
        of what the live conversation contains."""
        sim = ScriptedUserSimulator(_transcript())

        # Live transcript contains a totally different conversation
        live_transcript = [
            Message(role="assistant", content="Live agent says something different"),
        ]

        response = await sim.generate(live_transcript)

        assert response.message == "I need to cancel my order."

    @pytest.mark.asyncio
    async def test_emits_on_token_callback(self):
        sim = ScriptedUserSimulator(_transcript())

        captured: list[tuple[str, str]] = []

        async def on_token(token: str, source: str) -> None:
            captured.append((token, source))

        await sim.generate([], on_token=on_token)

        assert len(captured) == 1
        assert captured[0] == ("I need to cancel my order.", "user")

    @pytest.mark.asyncio
    async def test_no_callback_when_token_handler_absent(self):
        """Sanity check: passing on_token=None doesn't blow up."""
        sim = ScriptedUserSimulator(_transcript())

        response = await sim.generate([])

        assert response is not None
