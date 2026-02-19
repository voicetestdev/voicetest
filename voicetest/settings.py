"""Settings management for voicetest.

Settings are stored in .voicetest/settings.toml (project-local or global).
Both CLI and web UI read/write the same file.
"""

import os
from pathlib import Path
import tomllib

from pydantic import BaseModel
from pydantic import Field

from voicetest.config import get_settings_path


# Default model used when settings are not configured
DEFAULT_MODEL = "groq/llama-3.1-8b-instant"


class ModelSettings(BaseModel):
    """LLM model configuration. None means not configured (use defaults or test overrides)."""

    agent: str | None = Field(default=None, description="Model for agent responses")
    simulator: str | None = Field(default=None, description="Model for user simulation")
    judge: str | None = Field(default=None, description="Model for evaluation")


class AudioSettings(BaseModel):
    """TTS/STT service configuration for audio evaluation."""

    tts_url: str = Field(default="http://localhost:8002/v1")
    stt_url: str = Field(default="http://localhost:8001/v1")


class RunSettings(BaseModel):
    """Test run configuration."""

    max_turns: int = Field(default=20, description="Maximum conversation turns")
    verbose: bool = Field(default=False, description="Verbose output")
    flow_judge: bool = Field(default=False, description="Run flow judge to validate transitions")
    streaming: bool = Field(default=False, description="Stream tokens as they are generated")
    test_model_precedence: bool = Field(
        default=False,
        description="When enabled, test-specific llm_model overrides global settings",
    )
    split_transitions: bool = Field(
        default=False,
        description="Evaluate transitions separately from response generation (debugging)",
    )
    audio_eval: bool = Field(
        default=False,
        description="Auto-run TTS→STT audio evaluation on every test",
    )


class Settings(BaseModel):
    """Voicetest settings."""

    models: ModelSettings = Field(default_factory=ModelSettings)
    run: RunSettings = Field(default_factory=RunSettings)
    audio: AudioSettings = Field(default_factory=AudioSettings)
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

    # Only write [models] section if any model is configured
    model_lines = []
    if settings.models.agent is not None:
        model_lines.append(f'agent = "{settings.models.agent}"')
    if settings.models.simulator is not None:
        model_lines.append(f'simulator = "{settings.models.simulator}"')
    if settings.models.judge is not None:
        model_lines.append(f'judge = "{settings.models.judge}"')
    if model_lines:
        lines.append("[models]")
        lines.extend(model_lines)
        lines.append("")

    lines.append("[run]")
    lines.append(f"max_turns = {settings.run.max_turns}")
    lines.append(f"verbose = {str(settings.run.verbose).lower()}")
    lines.append(f"flow_judge = {str(settings.run.flow_judge).lower()}")
    lines.append(f"streaming = {str(settings.run.streaming).lower()}")
    lines.append(f"test_model_precedence = {str(settings.run.test_model_precedence).lower()}")
    lines.append(f"split_transitions = {str(settings.run.split_transitions).lower()}")
    lines.append(f"audio_eval = {str(settings.run.audio_eval).lower()}")
    lines.append("")

    lines.append("[audio]")
    lines.append(f'tts_url = "{settings.audio.tts_url}"')
    lines.append(f'stt_url = "{settings.audio.stt_url}"')
    lines.append("")

    if settings.env:
        lines.append("[env]")
        for key, value in sorted(settings.env.items()):
            lines.append(f'{key} = "{value}"')
        lines.append("")

    return "\n".join(lines)


def resolve_model(
    settings_value: str | None = None,
    role_default: str | None = None,
    test_model_precedence: bool = False,
) -> str:
    """Resolve which model to use for a given role."""
    if test_model_precedence and role_default:
        return role_default
    if settings_value:
        return settings_value
    if role_default:
        return role_default
    return DEFAULT_MODEL


def load_settings(path: Path | None = None) -> Settings:
    """Load settings from .voicetest.toml."""
    return Settings.load(path)


def save_settings(settings: Settings, path: Path | None = None) -> None:
    """Save settings to .voicetest.toml."""
    settings.save(path)
