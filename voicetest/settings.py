"""Settings management for voicetest.

Settings are stored in .voicetest/settings.toml (project-local or global).
Both CLI and web UI read/write the same file.
"""

import os
from pathlib import Path
import tomllib

from pydantic import BaseModel, Field

from voicetest.config import get_settings_path


class ModelSettings(BaseModel):
    """LLM model configuration."""

    agent: str = Field(default="groq/llama-3.1-8b-instant", description="Model for agent responses")
    simulator: str = Field(
        default="groq/llama-3.1-8b-instant", description="Model for user simulation"
    )
    judge: str = Field(default="groq/llama-3.1-8b-instant", description="Model for evaluation")


class RunSettings(BaseModel):
    """Test run configuration."""

    max_turns: int = Field(default=20, description="Maximum conversation turns")
    verbose: bool = Field(default=False, description="Verbose output")
    flow_judge: bool = Field(default=False, description="Run flow judge to validate transitions")
    streaming: bool = Field(default=False, description="Stream tokens as they are generated")


class Settings(BaseModel):
    """Voicetest settings."""

    models: ModelSettings = Field(default_factory=ModelSettings)
    run: RunSettings = Field(default_factory=RunSettings)
    env: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set (e.g., API keys for LLM providers)",
    )

    def apply_env(self) -> None:
        """Apply configured environment variables.

        Sets environment variables from settings. Useful for API keys.
        Only sets variables that are configured - does not clear existing env vars.
        """
        for key, value in self.env.items():
            if value:
                os.environ[key] = value

    def save(self, path: Path | None = None) -> None:
        """Save settings to TOML file."""
        path = path or get_settings_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        content = _to_toml(self)
        path.write_text(content)

    @classmethod
    def load(cls, path: Path | None = None) -> "Settings":
        """Load settings from TOML file, or return defaults if not found."""
        path = path or get_settings_path()
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
    lines.append(f"flow_judge = {str(settings.run.flow_judge).lower()}")
    lines.append(f"streaming = {str(settings.run.streaming).lower()}")
    lines.append("")

    if settings.env:
        lines.append("[env]")
        for key, value in sorted(settings.env.items()):
            lines.append(f'{key} = "{value}"')
        lines.append("")

    return "\n".join(lines)


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from .voicetest.toml."""
    return Settings.load(path)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Save settings to .voicetest.toml."""
    settings.save(path)
