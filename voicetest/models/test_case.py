"""Test case models for defining voice agent tests.

Test cases define user personas, success metrics, and flow constraints
for evaluating agent behavior.
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
    """Single test case definition.

    The user_prompt follows Retell's Identity/Goal/Personality format:

    ## Identity
    Your name is Mike. Order number: 7891273.

    ## Goal
    Return package and get refund.

    ## Personality
    Patient but becomes frustrated if unresolved.
    """

    id: str
    name: str
    user_prompt: str
    metrics: list[str] = Field(default_factory=list)
    required_nodes: list[str] | None = None
    forbidden_nodes: list[str] | None = None
    function_mocks: dict[str, Any] | None = None
    max_turns: int = 20
