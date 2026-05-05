"""Scripted user simulator — replays user turns from a recorded transcript.

Used by replay runs: instead of generating user messages with an LLM, this
simulator returns the next user turn from a pre-recorded source transcript.
The runner drives the conversation against the live agent the same way it
would for a normal test run; only the user side is scripted.

The class implements the same async generate() contract as UserSimulator
(satisfied by duck typing — ConversationRunner accepts either via the
generate() signature).
"""

from __future__ import annotations

from collections.abc import Awaitable
from collections.abc import Callable

from voicetest.llm import _invoke_callback
from voicetest.models.results import Message
from voicetest.retry import OnErrorCallback
from voicetest.simulator.user_sim import SimulatorResponse


# Same shape as UserSimulator's OnTokenCallback so the runner can pass either.
OnTokenCallback = Callable[[str, str], Awaitable[None] | None]


class ScriptedUserSimulator:
    """Replays user turns from a recorded transcript.

    Returns each user message from the source transcript in order. Once the
    recorded user turns are exhausted, returns None — signalling the runner
    that the conversation should end.

    This simulator does not consult the live conversation history when picking
    the next turn — it just yields the next recorded user message. If the live
    agent diverges from the recorded conversation (asks a different question
    in a different order), the recorded user turn may not fit perfectly. v1
    accepts that limitation; the regression signal is still useful because
    judging looks at whether the conversation as a whole reaches the same
    outcome.
    """

    def __init__(self, source_transcript: list[Message]):
        """Initialize from a source transcript.

        Args:
            source_transcript: The full transcript of the source call. Only
                user-role messages are extracted as the script; agent-role
                messages from the source are ignored — the live agent's
                responses replace them.
        """
        self._user_turns: list[str] = [m.content for m in source_transcript if m.role == "user"]
        self._index = 0

    async def generate(
        self,
        transcript: list[Message],
        on_token: OnTokenCallback | None = None,
        on_error: OnErrorCallback | None = None,
    ) -> SimulatorResponse | None:
        """Return the next scripted user turn, or None when exhausted.

        Args:
            transcript: The live conversation so far (unused — the script
                doesn't depend on what the live agent said).
            on_token: Optional token-streaming callback — emitted once with the
                full message so callers that wire UI streaming see the same
                token-flow shape.
            on_error: Unused — scripted replay has no retryable errors.
        """
        if self._index >= len(self._user_turns):
            return None

        message = self._user_turns[self._index]
        self._index += 1

        if on_token:
            # Emit the whole message as a single "token" so UI streaming hooks
            # don't have to special-case the scripted path. Source "user"
            # matches what UserSimulator passes for live LLM streaming.
            await _invoke_callback(on_token, message, "user")

        return SimulatorResponse(message=message)
