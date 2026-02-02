"""Run executor protocol and implementations.

This module defines a protocol for executing test runs, allowing different
backends (BackgroundTasks, SQS, etc.) to be swapped in.
"""

from dataclasses import dataclass
from typing import Protocol

from voicetest.models.test_case import RunOptions


@dataclass
class RunJob:
    """Job data for executing a test run."""

    run_id: str
    agent_id: str
    test_records: list[dict]
    result_ids: dict[str, str]
    options: RunOptions


class RunExecutor(Protocol):
    """Protocol for submitting test runs for execution."""

    def submit(self, job: RunJob) -> None:
        """Submit a run job for execution.

        Args:
            job: The run job containing all data needed for execution.
        """
        ...


# Default executor factory - can be overridden for custom implementations
_executor_factory: "type[RunExecutor] | None" = None


def set_executor_factory(factory: "type[RunExecutor] | None") -> None:
    """Set a custom executor factory.

    Args:
        factory: Executor class to use, or None to reset to default.
    """
    global _executor_factory
    _executor_factory = factory


def get_executor_factory() -> "type[RunExecutor] | None":
    """Get the current executor factory.

    Returns:
        The configured executor factory, or None for default.
    """
    return _executor_factory
