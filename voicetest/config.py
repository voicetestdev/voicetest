"""Path resolution for voicetest configuration and data.

Supports two modes:
- Project-local: .voicetest/ in current working directory
- Global: ~/.voicetest/ as fallback

The presence of .voicetest/ directory in CWD indicates project mode.
"""

import os
from pathlib import Path

VOICETEST_DIR = ".voicetest"
SETTINGS_FILE = "settings.toml"
DB_FILE = "data.duckdb"


def get_global_dir() -> Path:
    """Get the global voicetest directory (~/.voicetest/)."""
    return Path.home() / VOICETEST_DIR


def get_local_dir() -> Path | None:
    """Get the local voicetest directory if it exists."""
    local = Path.cwd() / VOICETEST_DIR
    return local if local.exists() else None


def get_voicetest_dir() -> Path:
    """Get the voicetest directory (local or global).

    Returns local .voicetest/ if it exists, otherwise global ~/.voicetest/.
    Creates global directory if needed.
    """
    local = get_local_dir()
    if local:
        return local

    global_dir = get_global_dir()
    global_dir.mkdir(parents=True, exist_ok=True)
    return global_dir


def get_settings_path() -> Path:
    """Get the settings file path.

    Resolution order:
    1. ./.voicetest/settings.toml (project)
    2. ~/.voicetest/settings.toml (global)

    Returns the path even if file doesn't exist yet.
    """
    local = get_local_dir()
    if local:
        return local / SETTINGS_FILE

    return get_global_dir() / SETTINGS_FILE


def get_db_path() -> Path:
    """Get the database file path.

    Resolution order:
    1. VOICETEST_DB_PATH env var (explicit override)
    2. ./.voicetest/data.duckdb (project)
    3. ~/.voicetest/data.duckdb (global)
    """
    if env_path := os.environ.get("VOICETEST_DB_PATH"):
        return Path(env_path)

    return get_voicetest_dir() / DB_FILE


def is_project_mode() -> bool:
    """Check if running in project-local mode."""
    return get_local_dir() is not None
