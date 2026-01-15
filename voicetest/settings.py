"""Settings management for voicetest.

Settings are stored in .voicetest.toml in the current directory.
Both CLI and web UI read/write the same file.
"""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field

SETTINGS_FILE = ".voicetest.toml"


class ModelSettings(BaseModel):
    """LLM model configuration."""

    agent: str = Field(default="openai/gpt-4o-mini", description="Model for agent responses")
    simulator: str = Field(default="openai/gpt-4o-mini", description="Model for user simulation")
    judge: str = Field(default="openai/gpt-4o-mini", description="Model for evaluation")


class RunSettings(BaseModel):
    """Test run configuration."""

    max_turns: int = Field(default=20, description="Maximum conversation turns")
    verbose: bool = Field(default=False, description="Verbose output")


class Settings(BaseModel):
    """Voicetest settings."""

    models: ModelSettings = Field(default_factory=ModelSettings)
    run: RunSettings = Field(default_factory=RunSettings)

    def save(self, path: Path | None = None) -> None:
        """Save settings to TOML file."""
        path = path or Path(SETTINGS_FILE)
        content = _to_toml(self)
        path.write_text(content)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Load settings from TOML file, or return defaults if not found."""
        path = path or Path(SETTINGS_FILE)
        if not path.exists():
            return cls()

        with open(path, "rb") as f:
            data = tomllib.load(f)

        return cls.model_validate(data)


def _to_toml(settings: Settings) -> str:
    """Convert settings to TOML string."""
    lines = []

    lines.append("[models]")
    lines.append(f'agent = "{settings.models.agent}"')
    lines.append(f'simulator = "{settings.models.simulator}"')
    lines.append(f'judge = "{settings.models.judge}"')
    lines.append("")

    lines.append("[run]")
    lines.append(f"max_turns = {settings.run.max_turns}")
    lines.append(f"verbose = {str(settings.run.verbose).lower()}")
    lines.append("")

    return "\n".join(lines)


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from .voicetest.toml."""
    return Settings.load(path)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Save settings to .voicetest.toml."""
    settings.save(path)
