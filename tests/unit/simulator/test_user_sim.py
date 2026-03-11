"""Tests for voicetest.simulator.user_sim module."""

from unittest.mock import patch

import dspy
import pytest

from voicetest.models.results import Message


class TestSimulatorResponse:
    """Tests for SimulatorResponse."""

    def test_create_response(self):
        from voicetest.simulator.user_sim import SimulatorResponse

        response = SimulatorResponse(message="I need help with my bill")

        assert response.message == "I need help with my bill"

    def test_no_should_end_field(self):
        from voicetest.simulator.user_sim import SimulatorResponse

        response = SimulatorResponse(message="test")
        assert not hasattr(response, "should_end")


class TestUserSimSignature:
    """Tests for UserSimSignature structure."""

    def test_only_message_output_field(self):
        """UserSimSignature should only produce a message — no end detection."""
        from voicetest.simulator.user_sim import UserSimSignature

        output_fields = {k for k, v in UserSimSignature.output_fields.items()}
        assert output_fields == {"message"}

    def test_no_should_continue_field(self):
        from voicetest.simulator.user_sim import UserSimSignature

        assert "should_continue" not in UserSimSignature.output_fields
        assert "should_continue" not in UserSimSignature.input_fields

    def test_no_reasoning_field(self):
        from voicetest.simulator.user_sim import UserSimSignature

        assert "reasoning" not in UserSimSignature.output_fields


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
        simulator = UserSimulator(user_prompt, "openai/gpt-4o-mini")

        assert simulator.user_prompt == user_prompt

    def test_format_transcript_empty(self):
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator("test prompt", "openai/gpt-4o-mini")
        result = simulator._format_transcript([])

        assert "(conversation not started)" in result.lower() or result == ""

    def test_format_transcript_with_messages(self):
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator("test prompt", "openai/gpt-4o-mini")
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
        simulator = UserSimulator(user_prompt, "openai/gpt-4o-mini")
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
        simulator = UserSimulator(user_prompt, "openai/gpt-4o-mini")
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
        simulator = UserSimulator(user_prompt, "openai/gpt-4o-mini")
        persona = simulator._parse_persona()

        assert "patient" in persona.get("personality", "").lower()


class TestUserSimulatorGenerate:
    """Tests for UserSimulator.generate method."""

    @pytest.mark.asyncio
    async def test_generate_returns_response(self):
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator(
            "## Identity\nJohn\n\n## Goal\nSay hello\n\n## Personality\nFriendly",
            "openai/gpt-4o-mini",
        )

        simulator._mock_mode = True
        simulator._mock_responses = [SimulatorResponse(message="Hello, I need some help")]

        response = await simulator.generate([])

        assert isinstance(response, SimulatorResponse)
        assert isinstance(response.message, str)

    @pytest.mark.asyncio
    async def test_generate_with_transcript_context(self):
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator(
            "## Identity\nJohn\n\n## Goal\nGet refund\n\n## Personality\nPolite",
            "openai/gpt-4o-mini",
        )

        transcript = [
            Message(role="user", content="Hi"),
            Message(role="assistant", content="Hello! How can I help?"),
        ]

        simulator._mock_mode = True
        simulator._mock_responses = [SimulatorResponse(message="I'd like a refund for my order")]

        response = await simulator.generate(transcript)

        assert isinstance(response, SimulatorResponse)

    @pytest.mark.asyncio
    async def test_mock_returns_none_when_exhausted(self):
        """Mock mode returns None when all responses have been consumed."""
        from voicetest.simulator.user_sim import SimulatorResponse
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator(
            "## Identity\nJohn\n\n## Goal\nSay bye\n\n## Personality\nBrief",
            "openai/gpt-4o-mini",
        )

        simulator._mock_mode = True
        simulator._mock_responses = [SimulatorResponse(message="Hello")]

        response1 = await simulator.generate([])
        assert response1 is not None
        assert response1.message == "Hello"

        response2 = await simulator.generate([])
        assert response2 is None

    @pytest.mark.asyncio
    async def test_llm_path_returns_message(self):
        """The LLM path returns a SimulatorResponse with just the message."""
        from voicetest.simulator.user_sim import UserSimulator

        simulator = UserSimulator(
            "## Identity\nJohn\n\n## Goal\nSay hello\n\n## Personality\nFriendly",
            "openai/gpt-4o-mini",
        )

        async def mock_call_llm(model, sig, **kwargs):
            return dspy.Prediction(message="Thanks, bye!")

        with patch("voicetest.simulator.user_sim.call_llm", side_effect=mock_call_llm):
            response = await simulator.generate(
                [
                    Message(role="assistant", content="Goodbye!"),
                ]
            )

        assert response.message == "Thanks, bye!"
