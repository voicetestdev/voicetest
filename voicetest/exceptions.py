"""Voicetest exception types."""


class QuotaExhaustedError(Exception):
    """Raised when the LLM provider's usage quota is exhausted.

    Unlike transient rate limits (too many requests per second),
    quota exhaustion means no more requests will be accepted until
    the quota resets. Retrying is pointless.

    Known trigger: Claude Code CLI returns
    ``You've hit your limit · resets 3pm (America/New_York)``

    Attributes:
        reset_message: Human-readable reset time from the provider
            (e.g., "3pm (America/New_York)").
    """

    def __init__(self, message: str, reset_message: str | None = None):
        super().__init__(message)
        self.reset_message = reset_message
