"""Test case models for defining voice agent tests.

Test cases define user personas, success metrics, and flow constraints
for evaluating agent behavior. Format matches Retell AI exported tests.
"""

from typing import Any

from pydantic import BaseModel, Field


class RunOptions(BaseModel):
    """Options for test execution.

    LLM model strings use LiteLLM format: "provider/model"
    Examples: "openai/gpt-4o-mini", "anthropic/claude-3-haiku-20240307"
    """

    max_turns: int = 20
    timeout_seconds: float = 60.0
    verbose: bool = False

    # LLM model configuration
    agent_model: str = "openai/gpt-4o-mini"
    simulator_model: str = "openai/gpt-4o-mini"
    judge_model: str = "openai/gpt-4o-mini"


class TestCase(BaseModel):
    """Single test case definition matching Retell AI export format.

    Example Retell export:
    {
        "name": "Refill callback test",
        "user_prompt": "When asked for name, provide Robert Wilson...",
        "metrics": ["Confirms identity, acknowledges refill, ends call."],
        "dynamic_variables": {"customer_id": "12345"},
        "tool_mocks": [],
        "type": "simulation",
        "llm_model": "gpt-4o-mini"
    }

    Note: metrics array only uses the first entry as evaluation criteria.
    """

    name: str
    user_prompt: str
    metrics: list[str] = Field(default_factory=list)
    dynamic_variables: dict[str, Any] = Field(default_factory=dict)
    tool_mocks: list[Any] = Field(default_factory=list)
    type: str = "simulation"
    llm_model: str | None = None
    creation_timestamp: int | None = None
    user_modified_timestamp: int | None = None
