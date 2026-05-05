"""Run service: persisted test run management."""

from voicetest.models.results import TestResult
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
        """List runs for an agent with result summary counts."""
        return self._runs.list_for_agent_with_summary(agent_id, limit)

    def get_run(self, run_id: str) -> dict | None:
        """Get a run with all results, enriched with dynamic variables."""
        run = self._runs.get_with_results(run_id)
        if not run:
            return None

        # Enrich results with dynamic_variables from test cases (DB + file-based)
        tc_ids = {r.get("test_case_id") for r in run["results"] if r.get("test_case_id")}
        if tc_ids:
            agent_id = run["agent_id"]
            agent = self._agents.get(agent_id)
            tests_paths = agent.get("tests_paths") if agent else None
            all_tests = self._tests.list_for_agent_with_linked(agent_id, tests_paths)
            dv_map = {}
            for tc in all_tests:
                if tc["id"] in tc_ids and tc.get("dynamic_variables"):
                    dv_map[tc["id"]] = tc["dynamic_variables"]
            for r in run["results"]:
                dv = dv_map.get(r.get("test_case_id"))
                if dv:
                    r["dynamic_variables"] = dv

        return run

    def add_result(
        self,
        run_id: str,
        result,
        *,
        test_case_id: str | None = None,
        call_id: str | None = None,
    ) -> str:
        """Add a completed result to a run.

        Pass `test_case_id` for test runs, `call_id` for live calls, or neither
        for imported transcripts. Returns the new result id.
        """
        return self._runs.add_result(run_id, result, test_case_id=test_case_id, call_id=call_id)

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

    def add_result_from_call(self, run_id: str, call_id: str, test_result) -> str:
        """Back-compat alias — prefer add_result(run_id, result, call_id=...).

        Retained because external integrators may depend on this entry point.
        """
        return self.add_result(run_id, test_result, call_id=call_id)

    def import_calls(self, agent_id: str, results: list[TestResult]) -> dict:
        """Persist a batch of imported call transcripts as a single Run.

        Creates one Run with N Results — each Result holds one call's transcript
        with status="imported" and no test_case_id/call_id linkage. The Run is
        marked complete immediately since imports are historical, not running.

        Returns the created Run record.
        """
        run = self.create_run(agent_id)
        for result in results:
            self.add_result(run["id"], result)
        self.complete(run["id"])
        return self.get_run(run["id"])
