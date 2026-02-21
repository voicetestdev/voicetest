"""User persona simulator.

Generates user messages based on Identity/Goal/Personality prompts
using an LLM to simulate realistic user behavior.
"""

from collections.abc import Awaitable
from collections.abc import Callable
from dataclasses import dataclass
import re

import dspy

from voicetest.llm import call_llm
from voicetest.models.results import Message
from voicetest.retry import OnErrorCallback


# Callback type for token updates: receives token string and source ("agent" or "user")
OnTokenCallback = Callable[[str, str], Awaitable[None] | None]


async def _invoke_callback(callback: Callable, *args) -> None:
    """Invoke callback, handling both sync and async."""
    result = callback(*args)
    if result is not None and hasattr(result, "__await__"):
        await result


class UserSimSignature(dspy.Signature):
    """Simulate a real phone caller. Respond briefly and naturally, the way people actually talk
    on the phone. No introductions, pleasantries, or formalities unless the persona demands it.
    On the first turn, say a standard greeting, hello etc unless instructed otherwise in persona."""

    persona: str = dspy.InputField(desc="User persona (identity, goal, personality)")
    conversation_history: str = dspy.InputField(
        desc="Prior conversation (excluding latest agent message)"
    )
    current_agent_message: str = dspy.InputField(
        desc="The agent's most recent message to respond to"
    )
    turn_number: int = dspy.InputField(desc="Current turn number (1 = first turn)")

    should_continue: bool = dspy.OutputField(
        desc="True if user should keep talking. False ONLY if the user's stated goal "
        "has been fully achieved AND the agent has confirmed completion. "
        "An agent asking 'anything else?' is NOT sufficient — the user must have "
        "gotten what they called for. Always True on turn 1."
    )
    message: str = dspy.OutputField(
        desc="User's next spoken response — short and natural like a real phone call. "
        "Empty string only if should_continue is False."
    )
    reasoning: str = dspy.OutputField(desc="Why the user said this or ended")


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

    def __init__(self, user_prompt: str, model: str):
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

    async def generate(
        self,
        transcript: list[Message],
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> SimulatorResponse:
        """Generate next user message based on conversation so far.

        Args:
            transcript: Conversation history.
            on_token: Optional callback for streaming tokens.
            on_error: Optional callback for retryable errors.

        Returns:
            SimulatorResponse with message, should_end flag, and reasoning.
        """
        # Mock mode for testing
        if self._mock_mode and self._mock_responses:
            response = self._mock_responses[self._mock_index % len(self._mock_responses)]
            self._mock_index += 1
            return response

        return await self._generate_with_llm(transcript, on_token, on_error)

    async def _generate_with_llm(
        self,
        transcript: list[Message],
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> SimulatorResponse:
        """Generate response using LLM.

        Args:
            transcript: Conversation history.
            on_token: Optional callback for streaming tokens.
            on_error: Optional callback for retryable errors.

        Returns:
            SimulatorResponse with message, should_end flag, and reasoning.
        """
        user_prompt = self.user_prompt
        turn_number = len([m for m in transcript if m.role == "user"]) + 1

        # Split transcript into history and current agent message
        current_agent_message = ""
        history_transcript = transcript
        if transcript and transcript[-1].role == "assistant":
            current_agent_message = transcript[-1].content
            history_transcript = transcript[:-1]

        conversation_history = self._format_transcript(history_transcript)

        # Wrap on_token to add source="user"
        async def user_token_callback(token: str) -> None:
            await _invoke_callback(on_token, token, "user")

        result = await call_llm(
            self.model,
            UserSimSignature,
            on_token=user_token_callback if on_token else None,
            stream_field="message" if on_token else None,
            on_error=on_error,
            persona=user_prompt,
            conversation_history=conversation_history,
            current_agent_message=current_agent_message or "(agent has not spoken yet)",
            turn_number=turn_number,
        )

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
