"""Run-execution job dataclass."""

from dataclasses import dataclass

from voicetest.models.test_case import RunOptions


@dataclass
class RunJob:
    """Job data for executing a test run."""

    run_id: str
    agent_id: str
    test_records: list[dict]
    result_ids: dict[str, str]
    options: RunOptions
