"""Background test-run orchestrator.

Owns the per-test loop that drives `TestExecutionService` and broadcasts
lifecycle events through `RunCoordinator`. Lives behind the container so
`rest.py` only has to schedule `RunRunner.execute(job)` on a background
task.
"""

import asyncio
from dataclasses import dataclass

from voicetest.core.exceptions import QuotaExhaustedError
from voicetest.models.results import Message
from voicetest.models.results import TestResult
from voicetest.models.test_case import RunOptions
from voicetest.services.agents import AgentService
from voicetest.services.runs import RunService
from voicetest.services.testing.cases import TestCaseService
from voicetest.services.testing.execution import TestExecutionService
from voicetest.util.retry import RetryError
from voicetest.web.coordinator import RunCoordinator


@dataclass
class RunJob:
    """Job data for executing a test run."""

    run_id: str
    agent_id: str
    test_records: list[dict]
    result_ids: dict[str, str]
    options: RunOptions


class RunRunner:
    """Drives a `RunJob` through `TestExecutionService` and broadcasts progress."""

    def __init__(
        self,
        agent_service: AgentService,
        test_case_service: TestCaseService,
        run_service: RunService,
        test_execution_service: TestExecutionService,
        coordinator: RunCoordinator,
    ):
        self._agents = agent_service
        self._tests = test_case_service
        self._runs = run_service
        self._exec = test_execution_service
        self._coordinator = coordinator

    async def execute(self, job: RunJob) -> None:
        """Execute the tests in `job`. Caller has already called `coordinator.start(run_id)`."""
        try:
            _agent, graph = self._agents.load_graph(job.agent_id)
        except (FileNotFoundError, ValueError):
            return

        metrics_config = self._agents.get_metrics_config(job.agent_id)

        try:
            for idx, test_record in enumerate(job.test_records):
                result_id = job.result_ids[test_record["id"]]

                if self._coordinator.is_test_cancelled(job.run_id, result_id):
                    self._runs.mark_result_cancelled(result_id)
                    await self._coordinator.broadcast(
                        job.run_id,
                        {"type": "test_cancelled", "result_id": result_id},
                    )
                    continue

                if self._coordinator.is_cancelled(job.run_id):
                    await self._cancel_remaining(job, idx)
                    break

                test_case = self._tests.to_model(test_record)

                await self._coordinator.broadcast(
                    job.run_id,
                    {
                        "type": "test_started",
                        "result_id": result_id,
                        "test_case_id": test_record["id"],
                        "test_name": test_case.name,
                    },
                )

                last_transcript: list[Message] = []
                try:
                    result = await self._exec.run_test(
                        graph,
                        test_case,
                        options=job.options,
                        metrics_config=metrics_config,
                        on_turn=self._make_on_turn(job.run_id, result_id, last_transcript),
                        on_token=self._make_on_token(job.run_id, result_id)
                        if job.options.streaming
                        else None,
                        on_error=self._make_on_error(job.run_id, result_id),
                    )
                    self._runs.complete_result(result_id, result)
                    await self._coordinator.broadcast(
                        job.run_id,
                        {
                            "type": "test_completed",
                            "result_id": result_id,
                            "status": result.status,
                        },
                    )
                except asyncio.CancelledError:
                    cancelled_result = TestResult(
                        test_name=test_case.name,
                        status="error",
                        transcript=last_transcript,
                        error_message="Cancelled by user",
                    )
                    self._runs.complete_result(result_id, cancelled_result)
                    await self._coordinator.broadcast(
                        job.run_id,
                        {"type": "test_cancelled", "result_id": result_id},
                    )
                except QuotaExhaustedError as e:
                    error_result = TestResult(
                        test_name=test_case.name,
                        status="error",
                        transcript=last_transcript,
                        error_message=str(e),
                    )
                    self._runs.complete_result(result_id, error_result)
                    await self._coordinator.broadcast(
                        job.run_id,
                        {
                            "type": "quota_exhausted",
                            "result_id": result_id,
                            "message": str(e),
                            "reset_message": e.reset_message,
                        },
                    )
                    # Quota won't reset for hours — abort rather than burn through retry backoff.
                    await self._cancel_remaining(job, idx + 1)
                    break
                except Exception as e:
                    error_result = TestResult(
                        test_name=test_case.name,
                        status="error",
                        transcript=last_transcript,
                        error_message=str(e),
                    )
                    self._runs.complete_result(result_id, error_result)
                    await self._coordinator.broadcast(
                        job.run_id,
                        {
                            "type": "test_error",
                            "result_id": result_id,
                            "error": str(e),
                        },
                    )

            self._runs.complete(job.run_id)
            await self._coordinator.broadcast(job.run_id, {"type": "run_completed"})
        finally:
            # Delay so final WS messages flush before subscribers detach.
            await asyncio.sleep(1)
            self._coordinator.end(job.run_id)

    async def _cancel_remaining(self, job: RunJob, start_idx: int) -> None:
        for remaining_record in job.test_records[start_idx:]:
            remaining_result_id = job.result_ids[remaining_record["id"]]
            self._runs.mark_result_cancelled(remaining_result_id)
            await self._coordinator.broadcast(
                job.run_id,
                {"type": "test_cancelled", "result_id": remaining_result_id},
            )

    def _make_on_turn(self, run_id: str, result_id: str, transcript_ref: list[Message]):
        async def on_turn(transcript: list) -> None:
            if self._coordinator.is_cancelled(run_id, result_id):
                raise asyncio.CancelledError("Test cancelled by user")
            transcript_ref.clear()
            transcript_ref.extend(transcript)
            self._runs.update_transcript(result_id, transcript)
            await self._coordinator.broadcast(
                run_id,
                {
                    "type": "transcript_update",
                    "result_id": result_id,
                    "transcript": [m.model_dump() for m in transcript],
                },
            )

        return on_turn

    def _make_on_token(self, run_id: str, result_id: str):
        async def on_token(token: str, source: str) -> None:
            await self._coordinator.broadcast(
                run_id,
                {
                    "type": "token_update",
                    "result_id": result_id,
                    "token": token,
                    "source": source,
                },
            )

        return on_token

    def _make_on_error(self, run_id: str, result_id: str):
        async def on_error(error: RetryError) -> None:
            await self._coordinator.broadcast(
                run_id,
                {
                    "type": "retry_error",
                    "result_id": result_id,
                    "error_type": error.error_type,
                    "message": error.message,
                    "attempt": error.attempt,
                    "max_attempts": error.max_attempts,
                    "retry_after": error.retry_after,
                },
            )

        return on_error
