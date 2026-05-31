"""Voicetest exception types."""


class QuotaExhaustedError(Exception):
    """Raised when the LLM provider's usage quota is exhausted."""

    def __init__(self, message: str, reset_message: str | None = None):
        super().__init__(message)
        self.reset_message = reset_message


class StaleGraphSchemaError(Exception):
    """Raised when a stored graph_json predates a required schema change.

    Surfaces as a 400 with an actionable message at the REST layer.
    Run `voicetest migrate-node-types` to bring stored graphs forward."""
