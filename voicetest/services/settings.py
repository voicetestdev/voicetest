"""Settings service for reading/writing .voicetest.toml configuration."""

from voicetest.settings import Settings
from voicetest.settings import load_settings
from voicetest.settings import save_settings


class SettingsService:
    """Manages application settings stored in .voicetest.toml."""

    def get_settings(self) -> Settings:
        """Get current settings from .voicetest.toml."""
        return load_settings()

    def update_settings(self, settings: Settings) -> Settings:
        """Update settings in .voicetest.toml."""
        save_settings(settings)
        return settings

    def get_defaults(self) -> Settings:
        """Get default settings (not from file)."""
        return Settings()
