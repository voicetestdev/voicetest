"""Centralized path validation for user-supplied filesystem paths.

All user-provided paths (API requests, CLI args, linked files) flow through
resolve_path() or resolve_file() to normalize, resolve, and validate against
an allowed base directory.

The allowed base defaults to "/" (unrestricted) and can be narrowed via the
VOICETEST_ALLOWED_BASE environment variable.
"""

import os
from pathlib import Path

from fastapi import HTTPException


_ALLOWED_BASE = Path(os.environ.get("VOICETEST_ALLOWED_BASE", "/")).resolve()


def resolve_path(raw: str) -> Path:
    """Normalize, resolve, and validate a path against the allowed base directory.

    Collapses '..' segments via normpath, resolves symlinks to a canonical
    absolute path, and rejects paths outside the allowed base.

    Use this for paths that may not exist on disk (e.g. unlink operations).
    """
    if not raw or not raw.strip():
        raise HTTPException(status_code=400, detail="Path must not be empty")

    resolved = Path(os.path.normpath(raw)).resolve()

    if not resolved.is_relative_to(_ALLOWED_BASE):
        raise HTTPException(
            status_code=400,
            detail=f"Path is outside allowed directory: {raw}",
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
