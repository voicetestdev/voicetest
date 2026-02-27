"""Run service: persisted test run management."""

from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository


class RunService:
    """Manages persisted test runs (CRUD, result tracking)."""

    def __init__(
        self,
        run_repo: RunRepository,
        agent_repo: AgentRepository,
        test_case_repo: TestCaseRepository,
    ):
        self._runs = run_repo
        self._agents = agent_repo
        self._tests = test_case_repo

    def create_run(self, agent_id: str) -> dict:
        """Create a new run."""
        return self._runs.create(agent_id)

    def list_runs(self, agent_id: str, limit: int = 50) -> list[dict]:
        """List runs for an agent."""
        return self._runs.list_for_agent(agent_id, limit)

    def get_run(self, run_id: str) -> dict | None:
        """Get a run with all results."""
        return self._runs.get_with_results(run_id)

    def delete_run(self, run_id: str) -> None:
        """Delete a run and all its results."""
        self._runs.delete(run_id)

    def create_pending_result(self, run_id: str, test_case_id: str, test_name: str) -> str:
        """Create a pending result placeholder for a test."""
        return self._runs.create_pending_result(run_id, test_case_id, test_name)

    def complete_result(self, result_id: str, result) -> None:
        """Mark a result as complete with test data."""
        self._runs.complete_result(result_id, result)

    def mark_result_error(self, result_id: str, error: str) -> None:
        """Mark a result as errored."""
        self._runs.mark_result_error(result_id, error)

    def mark_result_cancelled(self, result_id: str) -> None:
        """Mark a result as cancelled."""
        self._runs.mark_result_cancelled(result_id)

    def complete(self, run_id: str) -> None:
        """Mark a run as completed."""
        self._runs.complete(run_id)

    def update_transcript(self, result_id: str, transcript) -> None:
        """Update a result's transcript."""
        self._runs.update_transcript(result_id, transcript)

    def update_audio_eval(self, result_id: str, transformed, audio_metrics) -> None:
        """Update a result with audio eval data."""
        self._runs.update_audio_eval(result_id, transformed, audio_metrics)

    def add_result_from_call(self, run_id: str, call_id: str, test_result) -> None:
        """Add a result to a run from a completed call."""
        self._runs.add_result_from_call(run_id, call_id, test_result)
