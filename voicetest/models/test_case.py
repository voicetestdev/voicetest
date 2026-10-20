"""Test case models for defining voice agent tests."""

from typing import Any
from typing import Literal
from typing import get_args

from pydantic import BaseModel
from pydantic import Field

from voicetest.models.events import JUDGE_INPUT_TRANSCRIPT
from voicetest.models.events import JudgeInput


TestType = Literal["llm", "rule"]
StartSpeaker = Literal["agent", "user"]
DEFAULT_START_SPEAKER: StartSpeaker = "agent"


def resolve_start_speaker(
    override: str | None,
    template: str | None,
    global_default: str | None,
) -> StartSpeaker:
    return next(
        (c for c in (override, template, global_default) if c in get_args(StartSpeaker)),
        DEFAULT_START_SPEAKER,
    )


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
    judge_input: JudgeInput = JUDGE_INPUT_TRANSCRIPT
    start_speaker: StartSpeaker | None = None
    default_start_speaker: StartSpeaker | None = None

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
