"""Shared test runner logic for CLI and TUI.

This module provides the core test execution logic that both the
command-line interface and the TUI share.
"""

from collections.abc import AsyncIterator
from datetime import datetime
import json
from pathlib import Path
import uuid

from voicetest import api
from voicetest.models.agent import AgentGraph
from voicetest.models.results import TestResult, TestRun
from voicetest.models.test_case import RunOptions, TestCase
from voicetest.retry import OnErrorCallback


async def load_agent(
    agent_path: Path,
    source: str | None = None,
) -> AgentGraph:
    """Load an agent from a definition file.

    Args:
        agent_path: Path to agent definition file.
        source: Source type override (auto-detect if None).

    Returns:
        Loaded AgentGraph.
    """
    return await api.import_agent(agent_path, source=source)


def load_test_cases(tests_path: Path) -> list[TestCase]:
    """Load test cases from a JSON file.

    Args:
        tests_path: Path to test cases JSON file.

    Returns:
        List of TestCase objects.
    """
    data = json.loads(tests_path.read_text())
    return [TestCase.model_validate(tc) for tc in data]


async def run_all_tests(
    graph: AgentGraph,
    test_cases: list[TestCase],
    options: RunOptions | None = None,
    mock_mode: bool = False,
) -> TestRun:
    """Run all test cases and return aggregated results.

    Args:
        graph: Agent graph to test.
        test_cases: List of test cases.
        options: Run options.
        mock_mode: Use mock responses for testing.

    Returns:
        TestRun with all results.
    """
    return await api.run_tests(graph, test_cases, options, _mock_mode=mock_mode)


async def run_tests_streaming(
    graph: AgentGraph,
    test_cases: list[TestCase],
    options: RunOptions | None = None,
    mock_mode: bool = False,
    on_error: OnErrorCallback | None = None,
) -> AsyncIterator[TestResult]:
    """Run tests and yield results as they complete.

    This is useful for TUI to show live progress.

    Args:
        graph: Agent graph to test.
        test_cases: List of test cases.
        options: Run options.
        mock_mode: Use mock responses for testing.
        on_error: Optional callback for retry notifications.

    Yields:
        TestResult as each test completes.
    """
    for test_case in test_cases:
        result = await api.run_test(
            graph, test_case, options, _mock_mode=mock_mode, on_error=on_error
        )
        yield result


class TestRunContext:
    """Context for a test run, shared between CLI and TUI."""

    def __init__(
        self,
        agent_path: Path,
        tests_path: Path,
        source: str | None = None,
        options: RunOptions | None = None,
        mock_mode: bool = False,
    ):
        self.agent_path = agent_path
        self.tests_path = tests_path
        self.source = source
        self.options = options or RunOptions()
        self.mock_mode = mock_mode

        self.graph: AgentGraph | None = None
        self.test_cases: list[TestCase] = []
        self.results: list[TestResult] = []

    async def load(self) -> None:
        """Load agent and test cases."""
        self.graph = await load_agent(self.agent_path, self.source)
        self.test_cases = load_test_cases(self.tests_path)

    def filter_tests(self, test_names: list[str]) -> None:
        """Filter test cases to only include those with matching names."""
        self.test_cases = [tc for tc in self.test_cases if tc.name in test_names]

    async def run_all(self, on_error: OnErrorCallback | None = None) -> TestRun:
        """Run all tests at once."""
        if not self.graph:
            await self.load()

        # Use streaming internally to support on_error callback
        run_id = str(uuid.uuid4())
        started_at = datetime.now()
        results = []

        async for result in self.run_streaming(on_error=on_error):
            results.append(result)

        return TestRun(
            run_id=run_id,
            started_at=started_at,
            completed_at=datetime.now(),
            results=results,
        )

    async def run_streaming(
        self, on_error: OnErrorCallback | None = None
    ) -> AsyncIterator[TestResult]:
        """Run tests with streaming results."""
        if not self.graph:
            await self.load()
        async for result in run_tests_streaming(
            self.graph,
            self.test_cases,
            self.options,
            self.mock_mode,
            on_error=on_error,
        ):
            self.results.append(result)
            yield result

    @property
    def total_tests(self) -> int:
        """Total number of tests."""
        return len(self.test_cases)

    @property
    def completed_tests(self) -> int:
        """Number of completed tests."""
        return len(self.results)

    @property
    def passed_count(self) -> int:
        """Number of passed tests."""
        return sum(1 for r in self.results if r.status == "pass")

    @property
    def failed_count(self) -> int:
        """Number of failed tests."""
        return sum(1 for r in self.results if r.status == "fail")
