"""Generic hangup test case."""

from voicetest.models.test_case import TestCase


def get_hangup_test() -> TestCase:
    """Create a test for call ending behavior.

    Tests that the agent handles end-of-call gracefully
    when the user indicates they want to end the conversation.
    """
    return TestCase(
        id="generic-hangup",
        name="Call ending behavior",
        user_prompt="""
## Identity
Your name is Test User.

## Goal
End the conversation politely after a brief interaction.

## Personality
Polite but clearly wants to end the call. Will say things like
"That's all I needed, thanks" or "I have to go now".
""",
        metrics=[
            "Agent acknowledged user's desire to end call",
            "Agent provided appropriate farewell",
            "Agent did not try to prolong conversation unnecessarily",
        ],
        max_turns=5,
    )
