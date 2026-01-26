"""User persona simulator.

Generates user messages based on Identity/Goal/Personality prompts
using an LLM to simulate realistic user behavior.
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import re

import dspy
from dspy.streaming import StreamListener, streamify

from voicetest.models.results import Message
from voicetest.utils import DSPyAdapterMixin


# Callback type for token updates: receives token string and source ("agent" or "user")
OnTokenCallback = Callable[[str, str], Awaitable[None] | None]


async def _invoke_callback(callback: Callable, *args) -> None:
    """Invoke callback, handling both sync and async."""
    result = callback(*args)
    if result is not None and hasattr(result, "__await__"):
        await result


@dataclass
class SimulatorResponse:
    """Response from user simulator."""

    message: str
    should_end: bool
    reasoning: str


class UserSimulator(DSPyAdapterMixin):
    """LLM-based user persona simulator.

    Generates realistic user messages based on a persona definition
    following the Identity/Goal/Personality format.
    """

    def __init__(self, user_prompt: str, model: str = "openai/gpt-4o-mini", adapter=None):
        """Initialize the simulator.

        Args:
            user_prompt: Persona definition in Identity/Goal/Personality format.
            model: LLM model to use for generation.
            adapter: Optional DSPy adapter for structured output.
        """
        self.user_prompt = user_prompt
        self.model = model
        self._adapter = adapter

        # Mock mode for testing without LLM calls
        self._mock_mode = False
        self._mock_responses: list[SimulatorResponse] = []
        self._mock_index = 0

    async def generate(
        self,
        transcript: list[Message],
        on_token: OnTokenCallback | None = None,
    ) -> SimulatorResponse:
        """Generate next user message based on conversation so far.

        Args:
            transcript: Conversation history.
            on_token: Optional callback for streaming tokens.

        Returns:
            SimulatorResponse with message, should_end flag, and reasoning.
        """
        # Mock mode for testing
        if self._mock_mode and self._mock_responses:
            response = self._mock_responses[self._mock_index % len(self._mock_responses)]
            self._mock_index += 1
            return response

        # Real LLM generation
        response = await self._generate_with_llm(transcript, on_token)

        # Force first turn to continue - user shouldn't hang up without saying anything
        is_first_turn = len([m for m in transcript if m.role == "user"]) == 0
        if is_first_turn and response.should_end:
            # Retry with explicit instruction to start conversation
            response = await self._generate_opening_message(transcript, on_token)

        return response

    async def _generate_opening_message(
        self,
        transcript: list[Message],
        on_token: OnTokenCallback | None = None,
    ) -> SimulatorResponse:
        """Generate an opening message when the LLM incorrectly signals end on first turn."""
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
        agent_greeting = agent_said or "(agent has not spoken yet)"

        if on_token:
            # Streaming mode
            result = await self._generate_streaming(
                lm,
                OpeningMessageSignature,
                on_token,
                persona=user_prompt,
                agent_greeting=agent_greeting,
            )
        else:
            # Non-streaming mode
            ctx = self._dspy_context(lm)

            def run_predictor():
                with ctx:
                    predictor = dspy.Predict(OpeningMessageSignature)
                    return predictor(
                        persona=user_prompt,
                        agent_greeting=agent_greeting,
                    )

            result = await asyncio.to_thread(run_predictor)

        return SimulatorResponse(
            message=result.message,
            should_end=False,
            reasoning=result.reasoning,
        )

    async def _generate_with_llm(
        self,
        transcript: list[Message],
        on_token: OnTokenCallback | None = None,
    ) -> SimulatorResponse:
        """Generate response using LLM.

        This method uses DSPy for structured generation.

        Args:
            transcript: Conversation history.
            on_token: Optional callback for streaming tokens.

        Returns:
            SimulatorResponse with message, should_end flag, and reasoning.
        """
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

        if on_token:
            # Streaming mode
            result = await self._generate_streaming(
                lm,
                UserSimSignature,
                on_token,
                persona=user_prompt,
                conversation=conversation,
                turn_number=turn_number,
            )
        else:
            # Non-streaming mode
            ctx = self._dspy_context(lm)

            def run_predictor():
                with ctx:
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

    async def _generate_streaming(
        self,
        lm,
        signature_class: type,
        on_token: OnTokenCallback,
        **kwargs,
    ):
        """Generate response with streaming, yielding tokens via callback.

        Uses DSPy's streamify to get tokens as they're generated.
        """
        predictor = dspy.Predict(signature_class)
        stream_listeners = [StreamListener(signature_field_name="message")]

        streaming_predictor = streamify(
            predictor,
            stream_listeners=stream_listeners,
            is_async_program=False,
        )

        result = None
        with self._dspy_context(lm):
            async for chunk in streaming_predictor(**kwargs):
                if isinstance(chunk, dspy.Prediction):
                    result = chunk
                elif (
                    hasattr(chunk, "chunk")
                    and hasattr(chunk, "signature_field_name")
                    and chunk.signature_field_name == "message"
                ):
                    # StreamResponse with token data for message field
                    await _invoke_callback(on_token, chunk.chunk, "user")

        if result is None:
            raise RuntimeError("Streaming predictor did not return a Prediction")

        return result

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
