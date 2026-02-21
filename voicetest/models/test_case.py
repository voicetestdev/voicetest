"""Test case models for defining voice agent tests.

Test cases define user personas, success metrics, and flow constraints
for evaluating agent behavior. Format matches Retell AI exported tests.
"""

from typing import Any
from typing import Literal

from pydantic import BaseModel
from pydantic import Field


TestType = Literal["llm", "rule"]


class RunOptions(BaseModel):
    """Options for test execution.

    LLM model strings use LiteLLM format: "provider/model"
    Examples: "groq/llama-3.1-8b-instant", "openai/gpt-4o-mini"

    Model fields are Optional - None means not configured (will use defaults).
    """

    max_turns: int = 20
    timeout_seconds: float = 60.0
    verbose: bool = False
    flow_judge: bool = False
    streaming: bool = False
    test_model_precedence: bool = False
    split_transitions: bool = False
    audio_eval: bool = False
    pattern_engine: str = "fnmatch"

    # LLM model configuration (None = not configured, use defaults)
    agent_model: str | None = None
    simulator_model: str | None = None
    judge_model: str | None = None


class TestCase(BaseModel):
    """Single test case definition.

    Two test types are supported:

    1. LLM tests (type="llm"): Use an LLM judge to evaluate semantic metrics.
       {
           "name": "Billing inquiry",
           "user_prompt": "Ask about a charge on your bill...",
           "metrics": ["Agent was helpful and professional"],
           "type": "llm"
       }

    2. Rule tests (type="rule"): Use deterministic pattern matching.
       {
           "name": "Greeting check",
           "user_prompt": "Say hello",
           "includes": ["welcome", "help"],
           "excludes": ["goodbye"],
           "patterns": ["REF-[A-Z0-9]+"],
           "type": "rule"
       }

    Legacy type values "simulation" and "unit" are mapped to "llm" and "rule".
    """

    name: str
    user_prompt: str
    dynamic_variables: dict[str, Any] = Field(default_factory=dict)
    tool_mocks: list[Any] = Field(default_factory=list)
    type: str = "llm"
    llm_model: str | None = None
    creation_timestamp: int | None = None
    user_modified_timestamp: int | None = None

    # LLM test fields
    metrics: list[str] = Field(default_factory=list)

    # Rule test fields
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
