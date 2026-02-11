"""Generic test cases for common voice agent scenarios."""

from voicetest.generic_tests.adversarial import get_abusive_test
from voicetest.generic_tests.adversarial import get_jailbreak_test
from voicetest.generic_tests.adversarial import get_off_topic_test
from voicetest.generic_tests.greeting import get_greeting_test
from voicetest.generic_tests.hangup import get_hangup_test


__all__ = [
    "get_abusive_test",
    "get_greeting_test",
    "get_hangup_test",
    "get_jailbreak_test",
    "get_off_topic_test",
]


def get_all_generic_tests():
    """Return all available generic test cases."""
    return [
        get_greeting_test(),
        get_hangup_test(),
        get_jailbreak_test(),
        get_off_topic_test(),
        get_abusive_test(),
    ]
