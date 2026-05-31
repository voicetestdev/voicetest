"""Centralized path validation for user-supplied filesystem paths.

The allowed base defaults to "/" (unrestricted) and can be narrowed via the
VOICETEST_ALLOWED_BASE environment variable.
"""

import os
from pathlib import Path

from fastapi import HTTPException


def _allowed_base() -> Path:
    """Read VOICETEST_ALLOWED_BASE each call so tests can monkeypatch it."""
    return Path(os.environ.get("VOICETEST_ALLOWED_BASE", "/")).resolve()


def resolve_path(raw: str, base: Path | None = None) -> Path:
    """Normalize, resolve, and validate an absolute path against a base directory."""
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="Path must not be empty")

    if base is None:
        base = _allowed_base()
    resolved = Path(os.path.normpath(raw)).resolve()

    if not resolved.is_relative_to(base):
        raise HTTPException(
            status_code=400,
            detail=f"Path is outside allowed directory: {raw}",
        )

    return resolved


def resolve_within(raw: str, base: Path) -> Path:
    """Resolve a relative path segment within a base directory."""
    resolved = (base / raw).resolve()

    if not resolved.is_relative_to(base.resolve()):
        raise HTTPException(
            status_code=400,
            detail="Invalid path",
        )

    return resolved


def resolve_file(raw: str) -> Path:
    """Resolve a user-supplied path and validate it points to an existing regular file."""
    resolved = resolve_path(raw)

    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {raw}")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {raw}")

    return resolved
