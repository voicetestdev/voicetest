"""Test case models for defining voice agent tests."""

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


TestType = Literal["llm", "rule"]


class RunOptions(BaseModel):
    """Options for test execution."""

    max_turns: int = 50
    turn_timeout_seconds: float = 60.0
    verbose: bool = False
    flow_judge: bool = False
    streaming: bool = False
    test_model_precedence: bool = False
    audio_eval: bool = False
    no_cache: bool = False
    pattern_engine: str = "fnmatch"

    agent_model: str | None = None
    simulator_model: str | None = None
    judge_model: str | None = None


class TestCase(BaseModel):
    """Single test case definition."""

    name: str
    user_prompt: str
    dynamic_variables: dict[str, Any] = Field(default_factory=dict)
    tool_mocks: list[Any] = Field(default_factory=list)
    type: str = "llm"
    llm_model: str | None = None
    creation_timestamp: int | None = None
    user_modified_timestamp: int | None = None

    metrics: list[str] = Field(default_factory=list)

    includes: list[str] = Field(default_factory=list)
    excludes: list[str] = Field(default_factory=list)
    patterns: list[str] = Field(default_factory=list)

    @property
    def effective_type(self) -> TestType:
        """Get normalized test type, mapping legacy values."""
        if self.type in ("simulation", "llm"):
            return "llm"
        if self.type in ("unit", "rule"):
            return "rule"
        return "llm"
