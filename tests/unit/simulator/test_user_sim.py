"""Tests for voicetest.simulator.user_sim module."""

import pytest

from voicetest.models.results import Message


class TestSimulatorResponse:
    """Tests for SimulatorResponse."""

    def test_create_continue_response(self):
        from voicetest.simulator.user_sim import SimulatorResponse

        response = SimulatorResponse(
            message="I need help with my bill",
            should_end=False,
            reasoning="User is asking for help",
        )

        assert response.message == "I need help with my bill"
        assert response.should_end is False
        assert response.reasoning == "User is asking for help"

    def test_create_end_response(self):
        from voicetest.simulator.user_sim import SimulatorResponse

        response = SimulatorResponse(
            message="", should_end=True, reasoning="User's goal has been achieved"
        )

        assert response.message == ""
        assert response.should_end is True


class TestUserSimulator:
    """Tests for UserSimulator."""

    def test_create_simulator(self):
        from voicetest.simulator.user_sim import UserSimulator

        user_prompt = """
## Identity
Your name is John.

## Goal
Get help with billing.

## Personality
Polite but impatient.
"""
        simulator = UserSimulator(user_prompt)

        assert simulator.user_prompt == user_prompt

    def test_format_transcript_empty(self):
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator("test prompt")
        result = simulator._format_transcript([])

        assert "(conversation not started)" in result.lower() or result == ""

    def test_format_transcript_with_messages(self):
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator("test prompt")
        messages = [
            Message(role="user", content="Hello"),
            Message(role="assistant", content="Hi there!"),
            Message(role="user", content="I need help"),
        ]

        result = simulator._format_transcript(messages)

        assert "USER: Hello" in result
        assert "ASSISTANT: Hi there!" in result
        assert "USER: I need help" in result

    def test_parse_persona_extracts_identity(self):
        from voicetest.simulator.user_sim import UserSimulator

        user_prompt = """
## Identity
Your name is Sarah. Your account number is 12345.

## Goal
Check account balance.

## Personality
Friendly.
"""
        simulator = UserSimulator(user_prompt)
        persona = simulator._parse_persona()

        assert "Sarah" in persona.get("identity", "")
        assert "12345" in persona.get("identity", "")

    def test_parse_persona_extracts_goal(self):
        from voicetest.simulator.user_sim import UserSimulator

        user_prompt = """
## Identity
John

## Goal
Return a defective product and get a refund.

## Personality
Frustrated.
"""
        simulator = UserSimulator(user_prompt)
        persona = simulator._parse_persona()

        assert "refund" in persona.get("goal", "").lower()

    def test_parse_persona_extracts_personality(self):
        from voicetest.simulator.user_sim import UserSimulator

        user_prompt = """
## Identity
Jane

## Goal
Ask a question

## Personality
Very patient and understanding. Speaks slowly and clearly.
"""
        simulator = UserSimulator(user_prompt)
        persona = simulator._parse_persona()

        assert "patient" in persona.get("personality", "").lower()


class TestUserSimulatorGenerate:
    """Tests for UserSimulator.generate method.

    These tests verify the structure of responses without making
    actual LLM calls.
    """

    @pytest.mark.asyncio
    async def test_generate_returns_response(self):
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator(
            "## Identity\nJohn\n\n## Goal\nSay hello\n\n## Personality\nFriendly"
        )

        # Use mock mode for testing
        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(
                message="Hello, I need some help",
                should_end=False,
                reasoning="Initiating conversation",
            )
        ]

        response = await simulator.generate([])

        assert isinstance(response, SimulatorResponse)
        assert isinstance(response.message, str)
        assert isinstance(response.should_end, bool)
        assert isinstance(response.reasoning, str)

    @pytest.mark.asyncio
    async def test_generate_with_transcript_context(self):
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator(
            "## Identity\nJohn\n\n## Goal\nGet refund\n\n## Personality\nPolite"
        )

        transcript = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello! How can I help?"),
        ]

        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(
                message="I'd like a refund for my order",
                should_end=False,
                reasoning="Working towards goal",
            )
        ]

        response = await simulator.generate(transcript)

        assert isinstance(response, SimulatorResponse)

    @pytest.mark.asyncio
    async def test_generate_can_signal_end(self):
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator("## Identity\nJohn\n\n## Goal\nSay bye\n\n## Personality\nBrief")

        simulator._mock_mode = True
        simulator._mock_responses = [
            SimulatorResponse(
                message="", should_end=True, reasoning="Goal achieved, ending conversation"
            )
        ]

        response = await simulator.generate([])

        assert response.should_end is True
