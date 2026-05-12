"""Settings service for reading/writing .voicetest.toml configuration."""

from voicetest.settings import Settings
from voicetest.settings import load_settings
from voicetest.settings import save_settings


class SettingsService:
    """Manages application settings stored in .voicetest.toml.

    Single source of truth for settings access. Callers go through this
    service rather than calling load_settings() directly so apply_env() is
    guaranteed to run — endpoints making LLM calls need API keys from the
    settings env block in os.environ.
    """

    def get_settings(self) -> Settings:
        """Get current settings from .voicetest.toml with env vars applied."""
        settings = load_settings()
        settings.apply_env()
        return settings

    def update_settings(self, settings: Settings) -> Settings:
        """Update settings in .voicetest.toml."""
        save_settings(settings)
        return settings

    def get_defaults(self) -> Settings:
        """Get default settings (not from file)."""
        return Settings()
