"""Centralized path validation for user-supplied filesystem paths.

All user-provided paths (API requests, CLI args, linked files, URL segments)
flow through resolve_path(), resolve_file(), or resolve_within() to normalize,
resolve, and validate against an allowed base directory.

The allowed base defaults to "/" (unrestricted) and can be narrowed via the
VOICETEST_ALLOWED_BASE environment variable.
"""

import os
from pathlib import Path

from fastapi import HTTPException


_ALLOWED_BASE = Path(os.environ.get("VOICETEST_ALLOWED_BASE", "/")).resolve()


def resolve_path(raw: str, base: Path = _ALLOWED_BASE) -> Path:
    """Normalize, resolve, and validate an absolute path against a base directory.

    Collapses '..' segments via normpath, resolves symlinks to a canonical
    absolute path, and rejects paths outside the given base directory.

    For user-supplied absolute filesystem paths (API requests, CLI args).
    """
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="Path must not be empty")

    resolved = Path(os.path.normpath(raw)).resolve()

    if not resolved.is_relative_to(base):
        raise HTTPException(
            status_code=400,
            detail=f"Path is outside allowed directory: {raw}",
        )

    return resolved


def resolve_within(raw: str, base: Path) -> Path:
    """Resolve a relative path segment within a base directory.

    Joins raw with base, resolves to a canonical path, and rejects
    results that escape the base (e.g. via '..' traversal). For URL
    path segments served relative to a known root directory.
    """
    resolved = (base / raw).resolve()

    if not resolved.is_relative_to(base.resolve()):
        raise HTTPException(
            status_code=400,
            detail="Invalid path",
        )

    return resolved


def resolve_file(raw: str) -> Path:
    """Resolve a user-supplied path and validate it points to an existing regular file.

    Delegates to resolve_path() for normalization and base-directory checks,
    then verifies the target exists and is a regular file.
    """
    resolved = resolve_path(raw)

    if not resolved.exists():
        raise HTTPException(status_code=400, detail=f"File not found: {raw}")
    if not resolved.is_file():
        raise HTTPException(status_code=400, detail=f"Path is not a file: {raw}")

    return resolved
