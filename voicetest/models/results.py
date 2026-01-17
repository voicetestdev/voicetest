"""Result models for test execution output.

These models capture the complete results of test runs including
transcripts, metric evaluations, and flow tracking.
"""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Message(BaseModel):
    """Single message in a conversation transcript."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    timestamp: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


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

    test_id: str
    test_name: str
    status: Literal["pass", "fail", "error"]
    transcript: list[Message] = Field(default_factory=list)
    metric_results: list[MetricResult] = Field(default_factory=list)
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
