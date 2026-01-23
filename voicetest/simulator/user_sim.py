"""User persona simulator.

Generates user messages based on Identity/Goal/Personality prompts
using an LLM to simulate realistic user behavior.
"""

import asyncio
from dataclasses import dataclass
import re

from voicetest.models.results import Message


@dataclass
class SimulatorResponse:
    """Response from user simulator."""

    message: str
    should_end: bool
    reasoning: str


class UserSimulator:
    """LLM-based user persona simulator.

    Generates realistic user messages based on a persona definition
    following the Identity/Goal/Personality format.
    """

    def __init__(self, user_prompt: str, model: str = "openai/gpt-4o-mini"):
        """Initialize the simulator.

        Args:
            user_prompt: Persona definition in Identity/Goal/Personality format.
            model: LLM model to use for generation.
        """
        self.user_prompt = user_prompt
        self.model = model

        # Mock mode for testing without LLM calls
        self._mock_mode = False
        self._mock_responses: list[SimulatorResponse] = []
        self._mock_index = 0

    async def generate(self, transcript: list[Message]) -> SimulatorResponse:
        """Generate next user message based on conversation so far.

        Args:
            transcript: Conversation history.

        Returns:
            SimulatorResponse with message, should_end flag, and reasoning.
        """
        # Mock mode for testing
        if self._mock_mode and self._mock_responses:
            response = self._mock_responses[self._mock_index % len(self._mock_responses)]
            self._mock_index += 1
            return response

        # Real LLM generation
        response = await self._generate_with_llm(transcript)

        # Force first turn to continue - user shouldn't hang up without saying anything
        is_first_turn = len([m for m in transcript if m.role == "user"]) == 0
        if is_first_turn and response.should_end:
            # Retry with explicit instruction to start conversation
            response = await self._generate_opening_message(transcript)

        return response

    async def _generate_opening_message(self, transcript: list[Message]) -> SimulatorResponse:
        """Generate an opening message when the LLM incorrectly signals end on first turn."""
        import dspy

        lm = dspy.LM(self.model)

        class OpeningMessageSignature(dspy.Signature):
            """Generate an opening message to start a conversation."""

            persona: str = dspy.InputField(desc="User persona (identity, goal, personality)")
            agent_greeting: str = dspy.InputField(desc="What the agent said (if anything)")

            message: str = dspy.OutputField(
                desc="User's opening message to start the conversation and work toward their goal"
            )
            reasoning: str = dspy.OutputField(desc="Why the user said this")

        agent_said = ""
        for msg in reversed(transcript):
            if msg.role == "assistant":
                agent_said = msg.content
                break

        user_prompt = self.user_prompt

        def run_predictor():
            with dspy.context(lm=lm):
                predictor = dspy.Predict(OpeningMessageSignature)
                return predictor(
                    persona=user_prompt,
                    agent_greeting=agent_said or "(agent has not spoken yet)",
                )

        result = await asyncio.to_thread(run_predictor)

        return SimulatorResponse(
            message=result.message,
            should_end=False,
            reasoning=result.reasoning,
        )

    async def _generate_with_llm(self, transcript: list[Message]) -> SimulatorResponse:
        """Generate response using LLM.

        This method uses DSPy for structured generation.
        """
        import dspy

        lm = dspy.LM(self.model)

        class UserSimSignature(dspy.Signature):
            """Generate next user message in a simulated conversation."""

            persona: str = dspy.InputField(desc="User persona (identity, goal, personality)")
            conversation: str = dspy.InputField(desc="Conversation history")
            turn_number: int = dspy.InputField(desc="Current turn number")

            should_continue: bool = dspy.OutputField(
                desc="True if user should continue, False if goal achieved or user would hang up"
            )
            message: str = dspy.OutputField(
                desc="User's next message (empty string if should_continue is False)"
            )
            reasoning: str = dspy.OutputField(desc="Why the user said this or ended")

        user_prompt = self.user_prompt
        conversation = self._format_transcript(transcript)
        turn_number = len([m for m in transcript if m.role == "user"]) + 1

        def run_predictor():
            with dspy.context(lm=lm):
                predictor = dspy.Predict(UserSimSignature)
                return predictor(
                    persona=user_prompt,
                    conversation=conversation,
                    turn_number=turn_number,
                )

        result = await asyncio.to_thread(run_predictor)

        return SimulatorResponse(
            message=result.message if result.should_continue else "",
            should_end=not result.should_continue,
            reasoning=result.reasoning,
        )

    def _format_transcript(self, transcript: list[Message]) -> str:
        """Format transcript for LLM input."""
        if not transcript:
            return "(conversation not started)"

        lines = []
        for msg in transcript:
            lines.append(f"{msg.role.upper()}: {msg.content}")
        return "\n".join(lines)

    def _parse_persona(self) -> dict[str, str]:
        """Parse Identity/Goal/Personality sections from user prompt.

        Returns:
            Dictionary with 'identity', 'goal', and 'personality' keys.
        """
        sections: dict[str, str] = {}

        # Pattern to match ## Section headers
        pattern = r"##\s*(Identity|Goal|Personality)\s*\n(.*?)(?=##|\Z)"
        matches = re.findall(pattern, self.user_prompt, re.IGNORECASE | re.DOTALL)

        for section_name, content in matches:
            sections[section_name.lower()] = content.strip()

        return sections
