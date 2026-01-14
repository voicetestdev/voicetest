"""Generic greeting test case."""

from voicetest.models.test_case import TestCase


def get_greeting_test() -> TestCase:
    """Create a test for greeting behavior.

    Tests that the agent provides an appropriate greeting
    when starting a conversation.
    """
    return TestCase(
        id="generic-greeting",
        name="Greeting behavior",
        user_prompt="""
## Identity
Your name is Test User.

## Goal
Say hello and see how the agent greets you.

## Personality
Neutral and brief. You just want to see the initial greeting.
""",
        metrics=[
            "Agent greeted the user appropriately",
            "Agent asked how they can help or offered assistance",
            "Agent tone was professional and friendly",
        ],
        max_turns=3,
    )
