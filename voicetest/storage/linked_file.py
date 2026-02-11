"""Shared file operations for linked resources (agents, tests).

Provides ETag computation, file reading/writing for JSON-based
resources that live on the filesystem and are referenced by path.
"""

import json
from pathlib import Path


def compute_etag(resource_id: str, version: float | str) -> str:
    """Compute a quoted ETag string from resource ID and version (mtime or timestamp)."""
    return f'"{resource_id}-{version}"'


def check_file(path: str, resource_id: str) -> tuple[float, str]:
    """Check that a file exists and return its (mtime, etag).

    Raises FileNotFoundError if the file does not exist.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    mtime = p.stat().st_mtime
    etag = compute_etag(resource_id, mtime)
    return mtime, etag


def read_json(path: str) -> list | dict:
    """Read and parse a JSON file.

    Raises FileNotFoundError if the file does not exist.
    Raises json.JSONDecodeError if the file is not valid JSON.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"File not found: {path}")

    return json.loads(p.read_text())


def write_json(path: str, data: list | dict) -> None:
    """Write data to a JSON file with pretty formatting."""
    p = Path(path)
    p.write_text(json.dumps(data, indent=2) + "\n")
