"""Settings service for reading/writing .voicetest.toml configuration."""

from voicetest.config import get_settings_path
from voicetest.settings import Settings
from voicetest.settings import load_settings
from voicetest.settings import save_settings


class SettingsService:
    """Manages application settings stored in .voicetest.toml.

    Single source of truth for settings access. Callers go through this
    service rather than calling load_settings() directly so apply_env() is
    guaranteed to run — endpoints making LLM calls need API keys from the
    settings env block in os.environ.

    Registered as a Punq singleton; the parsed settings are cached with a
    file-mtime guard so the TOML isn't re-read on every call. `apply_env`
    still runs every call, since env may change underneath us.
    """

    def __init__(self) -> None:
        self._cached: Settings | None = None
        self._cached_mtime: float = 0.0

    def get_settings(self) -> Settings:
        """Get current settings from .voicetest.toml with env vars applied."""
        path = get_settings_path()
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            mtime = 0.0

        if self._cached is None or mtime != self._cached_mtime:
            self._cached = load_settings()
            self._cached_mtime = mtime
        self._cached.apply_env()
        return self._cached

    def update_settings(self, settings: Settings) -> Settings:
        """Update settings in .voicetest.toml."""
        save_settings(settings)
        # Refresh the cache to the just-written values (avoids a re-read).
        self._cached = settings
        try:
            self._cached_mtime = get_settings_path().stat().st_mtime
        except FileNotFoundError:
            self._cached_mtime = 0.0
        return settings

    def get_defaults(self) -> Settings:
        """Get default settings (not from file)."""
        return Settings()
