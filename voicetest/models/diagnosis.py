"""Diagnosis models for post-run failure analysis and auto-fix.

These models represent the output of diagnosing why a test failed
and suggesting concrete prompt/transition changes to fix it.
"""

from pydantic import BaseModel
from pydantic import Field


class FaultLocation(BaseModel):
    """Location in the agent graph where a failure originates."""

    location_type: str  # "general_prompt" | "node_prompt" | "transition" | "missing_transition"
    node_id: str | None = None
    transition_target_id: str | None = None
    relevant_text: str
    explanation: str


class Diagnosis(BaseModel):
    """Root cause analysis of a test failure."""

    fault_locations: list[FaultLocation]
    root_cause: str
    transcript_evidence: str


class PromptChange(BaseModel):
    """A proposed text change to fix a diagnosed issue."""

    location_type: str  # "general_prompt" | "node_prompt" | "transition"
    node_id: str | None = None
    transition_target_id: str | None = None
    original_text: str
    proposed_text: str
    rationale: str


class FixSuggestion(BaseModel):
    """A set of proposed changes with summary and confidence."""

    changes: list[PromptChange]
    summary: str
    confidence: float  # 0.0-1.0


class DiagnosisResult(BaseModel):
    """Combined diagnosis and fix suggestion."""

    diagnosis: Diagnosis
    fix: FixSuggestion


class FixAttemptResult(BaseModel):
    """Result of applying a fix and re-running the test."""

    iteration: int
    changes_applied: list[PromptChange]
    test_passed: bool
    metric_results: list[dict]
    improved: bool
    original_scores: dict[str, float]
    new_scores: dict[str, float] = Field(default_factory=dict)
