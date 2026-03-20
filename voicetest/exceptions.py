"""Voicetest exception types."""


class RateLimitError(Exception):
    """Raised when the LLM provider returns a rate limit error.

    Attributes:
        reset_message: Human-readable reset time from the provider
            (e.g., "resets 3pm (America/New_York)").
    """

    def __init__(self, message: str, reset_message: str | None = None):
        super().__init__(message)
        self.reset_message = reset_message
