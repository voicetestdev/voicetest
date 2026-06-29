"""Result models for test execution output."""

from datetime import datetime
from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


class AudioMetadata(BaseModel):
    """Audio/observer fields carried alongside a transcript message.

    Stored under Message.metadata["audio"]. heard is the observer-transcribed
    text of the actually-published audio, distinct from content (the intended
    text). latency_ms is time-to-first-audio for the turn; audio_ref points at
    captured audio."""

    heard: str | None = None
    latency_ms: int | None = None
    audio_ref: str | None = None


class Message(BaseModel):
    """Single message in a conversation transcript."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def audio(self) -> AudioMetadata:
        """Return the audio sub-model, falling back to the legacy flat heard key."""
        raw = self.metadata.get("audio")
        if isinstance(raw, AudioMetadata):
            return raw
        if isinstance(raw, dict):
            return AudioMetadata.model_validate(raw)
        legacy = self.metadata.get("heard")
        if legacy is not None:
            return AudioMetadata(heard=legacy)
        return AudioMetadata()

    def set_audio(self, audio: AudioMetadata) -> None:
        """Store the audio sub-model under the reserved metadata key."""
        self.metadata["audio"] = audio.model_dump(exclude_none=True)


class ToolCall(BaseModel):
    """Record of a tool invocation during conversation."""

    name: str
    arguments: dict[str, Any]
    result: str | None = None


class MetricResult(BaseModel):
    """Evaluation result for a single metric criterion."""

    metric: str
    passed: bool
    reasoning: str
    score: float | None = None
    threshold: float | None = None
    confidence: float | None = None


class ModelsUsed(BaseModel):
    """Models used during test execution."""

    agent: str
    simulator: str
    judge: str


class ModelOverride(BaseModel):
    """Record of a model override."""

    role: str  # "agent", "simulator", or "judge"
    requested: str  # what was originally requested
    actual: str  # what actually ran
    reason: str  # why override happened


class TestResult(BaseModel):
    """Result of running a single test case."""

    test_id: str | None = None
    test_name: str
    status: Literal["pass", "fail", "error", "imported", "cancelled"]
    source_kind: Literal["simulated", "live", "imported"] = "simulated"
    transcript: list[Message] = Field(default_factory=list)
    metric_results: list[MetricResult] = Field(default_factory=list)
    audio_metric_results: list[MetricResult] = Field(default_factory=list)
    nodes_visited: list[str] = Field(default_factory=list)
    tools_called: list[ToolCall] = Field(default_factory=list)
    constraint_violations: list[str] = Field(default_factory=list)
    turn_count: int = 0
    duration_ms: int = 0
    end_reason: str = ""
    error_message: str | None = None
    models_used: ModelsUsed | None = None
    model_overrides: list[ModelOverride] = Field(default_factory=list)


class TestRun(BaseModel):
    """Aggregated results from multiple test cases."""

    run_id: str
    started_at: datetime
    completed_at: datetime | None = None
    results: list[TestResult] = Field(default_factory=list)

    @property
    def passed_count(self) -> int:
        """Count of tests with status 'pass'."""
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed_count(self) -> int:
        """Count of tests with status 'fail'."""
        return sum(1 for r in self.results if r.status == "fail")
