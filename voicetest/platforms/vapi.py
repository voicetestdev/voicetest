"""VAPI AI client management.

Handles credential loading and SDK client creation.
Requires: pip install voicetest[platforms]
"""

import os

from vapi import Vapi


def get_client(api_key: str | None = None) -> Vapi:
    """Get a configured VAPI SDK client.

    Args:
        api_key: VAPI API key. Defaults to VAPI_API_KEY env var.

    Returns:
        Configured Vapi client.

    Raises:
        ValueError: If no API key available.
    """
    key = api_key or os.environ.get("VAPI_API_KEY")
    if not key:
        raise ValueError("VAPI_API_KEY not set")

    return Vapi(token=key)
