"""Retell AI client management.

Handles credential loading and SDK client creation.
Requires: pip install voicetest[platforms]
"""

import os

from retell import Retell


def get_client(api_key: str | None = None) -> Retell:
    """Get a configured Retell SDK client.

    Args:
        api_key: Retell API key. Defaults to RETELL_API_KEY env var.

    Returns:
        Configured Retell client.

    Raises:
        ValueError: If no API key available.
    """
    key = api_key or os.environ.get("RETELL_API_KEY")
    if not key:
        raise ValueError("RETELL_API_KEY not set")

    return Retell(api_key=key)
