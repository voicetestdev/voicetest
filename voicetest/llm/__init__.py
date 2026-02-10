"""Centralized LLM call handling.

All LLM calls should go through this module to ensure consistent
retry behavior, error handling, and future enhancements.
"""

from voicetest.llm.base import (
    OnTokenCallback,
    _call_llm_streaming,
    _call_llm_sync,
    _invoke_callback,
    call_llm,
)
from voicetest.retry import OnErrorCallback


__all__ = [
    "call_llm",
    "OnTokenCallback",
    "OnErrorCallback",
    "_call_llm_sync",
    "_call_llm_streaming",
    "_invoke_callback",
]
