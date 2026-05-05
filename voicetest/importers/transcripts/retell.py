"""Retell call transcript adapter.

Accepts Retell call records in the shape produced by the Retell API
(`GET /v2/get-call/{call_id}`) and the post-call webhook payload — both
contain the same call object structure. Produces voicetest TestResult
objects ready to be persisted as imported run results.

Input shapes accepted:
  - Single call object: {"call_id": ..., "transcript_object": [...], ...}
  - Array of call objects: [{...}, {...}]
  - Webhook payload: {"event": "call_ended", "call": {...}}
  - Array of webhook payloads
"""

from __future__ import annotations

from collections.abc import Iterable
import json
from pathlib import Path
from typing import Any

from voicetest.models.results import Message
from voicetest.models.results import TestResult


# Retell uses role="agent" for the bot; voicetest uses "assistant".
_ROLE_MAP = {
    "agent": "assistant",
    "user": "user",
    "system": "system",
    "tool": "tool",
}


def parse_retell_file(path: Path) -> list[TestResult]:
    """Parse a Retell transcript file (JSON) into TestResult objects.

    Raises:
        ValueError: file is not parseable or contains no recognizable calls.
    """
    raw = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Not valid JSON: {e}") from e

    return parse_retell(data)


def parse_retell(data: Any) -> list[TestResult]:
    """Parse a Retell payload (single call, array, or webhook envelope)."""
    calls = list(_iter_call_objects(data))
    if not calls:
        raise ValueError("No Retell call objects found in payload.")
    return [_call_to_result(c) for c in calls]


def _iter_call_objects(data: Any) -> Iterable[dict]:
    """Yield each call object regardless of envelope shape."""
    if isinstance(data, list):
        for item in data:
            yield from _iter_call_objects(item)
        return

    if not isinstance(data, dict):
        return

    # Webhook envelope: {"event": "call_ended", "call": {...}}
    if "call" in data and isinstance(data["call"], dict) and _looks_like_call(data["call"]):
        yield data["call"]
        return

    # Direct call object
    if _looks_like_call(data):
        yield data


def _looks_like_call(obj: dict) -> bool:
    return "transcript_object" in obj or "call_id" in obj


def _call_to_result(call: dict) -> TestResult:
    transcript_object = call.get("transcript_object") or []
    messages = [_turn_to_message(t) for t in transcript_object if _turn_has_content(t)]

    duration_ms = call.get("duration_ms")
    if duration_ms is None:
        start_ts = call.get("start_timestamp")
        end_ts = call.get("end_timestamp")
        if isinstance(start_ts, int) and isinstance(end_ts, int):
            duration_ms = end_ts - start_ts
    if not isinstance(duration_ms, int):
        duration_ms = 0

    end_reason = call.get("disconnection_reason") or call.get("call_status") or ""
    test_name = call.get("call_id") or "imported call"

    return TestResult(
        test_id=call.get("call_id"),
        test_name=test_name,
        status="imported",
        transcript=messages,
        turn_count=len(messages),
        duration_ms=duration_ms,
        end_reason=str(end_reason),
    )


def _turn_to_message(turn: dict) -> Message:
    role = _ROLE_MAP.get(turn.get("role", "user"), "user")
    content = turn.get("content") or ""
    return Message(role=role, content=content)


def _turn_has_content(turn: Any) -> bool:
    return isinstance(turn, dict) and bool(turn.get("content"))
