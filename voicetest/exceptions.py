"""Voicetest exception types."""


class QuotaExhaustedError(Exception):
    """Raised when the LLM provider's usage quota is exhausted."""

    def __init__(self, message: str, reset_message: str | None = None):
        super().__init__(message)
        self.reset_message = reset_message
