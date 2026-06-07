"""Tests for WebSocket, run management, orphan detection, and diagnosis endpoints."""

import asyncio
import json
import threading
import time
from unittest.mock import AsyncMock
from unittest.mock import patch

import pytest

from voicetest.exceptions import QuotaExhaustedError
from voicetest.models.diagnosis import Diagnosis
from voicetest.models.diagnosis import DiagnosisResult
from voicetest.models.diagnosis import FaultLocation
from voicetest.models.diagnosis import FixAttemptResult
from voicetest.models.diagnosis import FixSuggestion
from voicetest.models.diagnosis import PromptChange
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import TestResult
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.services.run_runner import RunJob
from voicetest.services.run_runner import RunRunner
from voicetest.services.runs import RunService
from voicetest.services.testing.cases import TestCaseService
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository
from voicetest.web.coordinator import RunCoordinator


def _get_run_repo(db_client):
    return db_client.app.state.container.resolve(RunRepository)


def _get_test_case_repo(db_client):
    return db_client.app.state.container.resolve(TestCaseRepository)


def _get_coordinator(db_client) -> RunCoordinator:
    return db_client.app.state.container.resolve(RunCoordinator)


class TestRunWebSocket:
    """Tests for run WebSocket endpoint and message formats."""

    @pytest.fixture
    def agent_with_test(self, db_client, sample_retell_config):
        """Create an agent with a test case."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "WS Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        test_response = db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={
                "name": "WebSocket Test",
                "user_prompt": "Say hello",
                "metrics": [],
            },
        )
        test_id = test_response.json()["id"]

        return {"agent_id": agent_id, "test_id": test_id}

    def test_execute_run_sends_test_case_id_in_test_started(
        self, db_client, agent_with_test, monkeypatch
    ):
        """Verify _execute_run includes test_case_id when broadcasting test_started."""

        agent_id = agent_with_test["agent_id"]
        test_id = agent_with_test["test_id"]

        broadcast_calls = []
        coordinator = _get_coordinator(db_client)
        original_broadcast = coordinator.broadcast

        async def spy_broadcast(run_id, data):
            broadcast_calls.append(data)
            await original_broadcast(run_id, data)

        monkeypatch.setattr(coordinator, "broadcast", spy_broadcast)

        with patch(
            "voicetest.services.testing.execution.TestExecutionService.run_test"
        ) as mock_run_test:
            mock_run_test.return_value = TestResult(
                test_id="test",
                test_name="WebSocket Test",
                status="pass",
                transcript=[],
            )

            response = db_client.post(
                f"/api/agents/{agent_id}/runs",
                json={"test_ids": [test_id]},
            )
            assert response.status_code == 200

            time.sleep(0.5)

        test_started_msgs = [c for c in broadcast_calls if c.get("type") == "test_started"]
        assert len(test_started_msgs) >= 1, "Should have at least one test_started message"

        for msg in test_started_msgs:
            assert "test_case_id" in msg, "test_started must include test_case_id"
            assert msg["test_case_id"] == test_id, "test_case_id should match the test ID"


class TestTimeoutEnforcement:
    """Tests for turn_timeout_seconds enforcement on test execution."""

    @pytest.fixture
    def agent_with_test(self, db_client, sample_retell_config):
        """Create an agent with a test case."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Timeout Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        test_response = db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={
                "name": "Timeout Test",
                "user_prompt": "Say hello",
                "metrics": [],
            },
        )
        test_id = test_response.json()["id"]

        return {"agent_id": agent_id, "test_id": test_id}

    def test_turn_timeout_reports_completed_with_turn_timeout_reason(
        self, db_client, agent_with_test, monkeypatch
    ):
        """When a turn exceeds turn_timeout_seconds, run completes with end_reason=turn_timeout."""

        agent_id = agent_with_test["agent_id"]
        test_id = agent_with_test["test_id"]

        broadcast_calls = []
        coordinator = _get_coordinator(db_client)
        original_broadcast = coordinator.broadcast

        async def spy_broadcast(run_id, data):
            broadcast_calls.append(data)
            await original_broadcast(run_id, data)

        monkeypatch.setattr(coordinator, "broadcast", spy_broadcast)

        call_count = 0

        async def slow_llm(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                await asyncio.sleep(300)

            class MockResult:
                response = "Hello!"
                objectives_complete = False
                transition_to = "none"

            return MockResult()

        with patch("voicetest.engine.conversation.call_llm", side_effect=slow_llm):
            response = db_client.post(
                f"/api/agents/{agent_id}/runs",
                json={
                    "test_ids": [test_id],
                    "options": {"turn_timeout_seconds": 0.2},
                },
            )
            assert response.status_code == 200

            time.sleep(2.0)

        completed_msgs = [c for c in broadcast_calls if c.get("type") == "test_completed"]
        assert len(completed_msgs) >= 1, (
            f"Should have a test_completed message. Got: {broadcast_calls}"
        )


class TestTranscriptUpdate:
    """Tests for transcript streaming functionality."""

    def test_transcript_update_message_format(self):
        """Verify transcript_update message has correct structure."""

        transcript = [
            Message(role="assistant", content="Hello!"),
            Message(role="user", content="Hi there"),
        ]

        message = {
            "type": "transcript_update",
            "result_id": "result-123",
            "transcript": [m.model_dump() for m in transcript],
        }

        assert message["type"] == "transcript_update"
        assert "result_id" in message
        assert "transcript" in message
        assert len(message["transcript"]) == 2
        assert message["transcript"][0]["role"] == "assistant"
        assert message["transcript"][0]["content"] == "Hello!"


class TestOrphanedRunDetection:
    """Tests for orphaned run cleanup."""

    @pytest.fixture
    def orphaned_run(self, db_client, sample_retell_config):
        """Create an orphaned run (not registered with coordinator, not completed)."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Orphan Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        # Create run directly in DB (simulating a crashed run)
        run_repo = _get_run_repo(db_client)
        run = run_repo.create(agent_id)
        run_id = run["id"]

        result_id = run_repo.create_pending_result(run_id, "test-case-1", "Test Case 1")

        # Ensure coordinator has no entry (simulating backend restart)
        _get_coordinator(db_client).end(run_id)

        return {"run_id": run_id, "result_id": result_id, "agent_id": agent_id}

    def test_get_orphaned_run_marks_as_complete(self, db_client, orphaned_run):
        """GET /runs/{id} should mark orphaned runs as complete."""
        run_id = orphaned_run["run_id"]

        response = db_client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200

        run = response.json()
        assert run["completed_at"] is not None, "Orphaned run should be marked complete"

    def test_get_orphaned_run_marks_running_results_as_error(self, db_client, orphaned_run):
        """GET /runs/{id} should mark 'running' results as 'error'."""
        run_id = orphaned_run["run_id"]

        response = db_client.get(f"/api/runs/{run_id}")
        assert response.status_code == 200

        run = response.json()
        running_results = [r for r in run["results"] if r["status"] == "running"]
        assert len(running_results) == 0, "No results should still be 'running'"

        error_results = [r for r in run["results"] if r["status"] == "error"]
        assert len(error_results) >= 1, "Running results should be marked as error"
        assert "orphaned" in error_results[0]["error_message"].lower()

    def test_active_run_not_marked_orphaned(self, db_client, sample_retell_config):
        """GET /runs/{id} should NOT mark active runs as orphaned."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Active Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        run_repo = _get_run_repo(db_client)
        run = run_repo.create(agent_id)
        run_id = run["id"]

        # Mark the run active via the coordinator (simulating active run)
        coordinator = _get_coordinator(db_client)
        coordinator.start(run_id)

        try:
            response = db_client.get(f"/api/runs/{run_id}")
            assert response.status_code == 200

            run_data = response.json()
            assert run_data["completed_at"] is None, "Active run should NOT be marked complete"
        finally:
            coordinator.end(run_id)


class TestRunDeletion:
    """Tests for run deletion endpoint."""

    def test_delete_run(self, db_client, sample_retell_config):
        """DELETE /runs/{id} should delete the run and its results."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        run_repo = _get_run_repo(db_client)
        run = run_repo.create(agent_id)
        run_id = run["id"]
        run_repo.create_pending_result(run_id, "test-case-1", "Test Case 1")
        run_repo.complete(run_id)

        response = db_client.delete(f"/api/runs/{run_id}")
        assert response.status_code == 200
        assert response.json() == {"status": "deleted", "id": run_id}

        get_response = db_client.get(f"/api/runs/{run_id}")
        assert get_response.status_code == 404

    def test_delete_run_not_found(self, db_client):
        """DELETE /runs/{id} should return 404 for non-existent run."""
        response = db_client.delete("/api/runs/nonexistent-run-id")
        assert response.status_code == 404

    def test_delete_active_run_fails(self, db_client, sample_retell_config):
        """DELETE /runs/{id} should not allow deleting an active run."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        run_repo = _get_run_repo(db_client)
        run = run_repo.create(agent_id)
        run_id = run["id"]

        coordinator = _get_coordinator(db_client)
        coordinator.start(run_id)

        try:
            response = db_client.delete(f"/api/runs/{run_id}")
            assert response.status_code == 400
            assert "active" in response.json()["detail"].lower()
        finally:
            coordinator.end(run_id)


class TestWebSocketStateMessage:
    """Tests for WebSocket state message with pending results."""

    @pytest.fixture
    def agent_with_tests(self, db_client, sample_retell_config):
        """Create an agent with multiple test cases."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "WS State Test Agent", "config": sample_retell_config},
        )
        assert agent_response.status_code == 200, f"Failed to create agent: {agent_response.json()}"
        agent_id = agent_response.json()["id"]

        test_ids = []
        for i in range(3):
            test_response = db_client.post(
                f"/api/agents/{agent_id}/tests",
                json={
                    "name": f"Test {i + 1}",
                    "user_prompt": f"Test prompt {i + 1}",
                    "metrics": [],
                },
            )
            assert test_response.status_code == 200, (
                f"Failed to create test: {test_response.json()}"
            )
            test_ids.append(test_response.json()["id"])

        return {"agent_id": agent_id, "test_ids": test_ids}

    def test_websocket_connection_receives_state_message(self, db_client, agent_with_tests):
        """WebSocket connection should receive a valid state message with run data."""
        agent_id = agent_with_tests["agent_id"]
        test_ids = agent_with_tests["test_ids"]

        run_response = db_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": test_ids},
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["id"]

        # If the WebSocket handler fails (e.g., serialization error), this will raise
        with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
            data = websocket.receive_json()

            # Verify message structure
            assert data["type"] == "state", f"Expected 'state' message, got {data.get('type')}"
            assert "run" in data, "State message should contain 'run'"

            run_data = data["run"]
            assert run_data["id"] == run_id
            assert "results" in run_data, "Run should have 'results' field"
            assert "started_at" in run_data, "Run should have 'started_at' field"
            assert run_data["agent_id"] == agent_id

            results = run_data["results"]
            assert len(results) == len(test_ids), (
                f"Expected {len(test_ids)} results, got {len(results)}"
            )

            for result in results:
                assert "id" in result
                assert "test_case_id" in result
                assert "test_name" in result
                assert "status" in result
                assert result["run_id"] == run_id

    def test_websocket_state_message_json_serializable(self, db_client, agent_with_tests):
        """State message must be JSON serializable (no datetime objects etc).

        Regression test for: TypeError: Object of type datetime is not JSON serializable
        """

        agent_id = agent_with_tests["agent_id"]
        test_ids = agent_with_tests["test_ids"]

        run_response = db_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": test_ids},
        )
        run_id = run_response.json()["id"]

        with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
            data = websocket.receive_json()

            # Round-trip serialize to confirm no non-JSON values (e.g. datetime objects)
            reserialized = json.dumps(data)
            assert len(reserialized) > 0

            run_data = data["run"]
            assert isinstance(run_data["started_at"], str), "started_at should be ISO string"
            if run_data.get("completed_at"):
                assert isinstance(run_data["completed_at"], str), (
                    "completed_at should be ISO string"
                )

            for result in run_data["results"]:
                assert isinstance(result["created_at"], str), "created_at should be ISO string"

    def test_websocket_nonexistent_run_sends_error(self, db_client):
        """WebSocket connection to non-existent run should receive error and close."""
        fake_run_id = "00000000-0000-0000-0000-000000000000"

        with db_client.websocket_connect(f"/api/runs/{fake_run_id}/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "error"
            assert "not found" in data["message"].lower()

    def test_websocket_completed_run_sends_state_and_closes(self, db_client, agent_with_tests):
        """WebSocket connection to completed run should receive state and run_completed."""

        agent_id = agent_with_tests["agent_id"]
        test_ids = agent_with_tests["test_ids"]

        run_response = db_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": test_ids},
        )
        run_id = run_response.json()["id"]

        # Wait for the coordinator to drop the run (signaling completion)
        coordinator = _get_coordinator(db_client)
        max_wait = 10
        while coordinator.is_active(run_id) and max_wait > 0:
            time.sleep(0.5)
            max_wait -= 1

        run = db_client.get(f"/api/runs/{run_id}").json()
        assert run["completed_at"] is not None, "Run should be complete"

        with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "state"
            assert data["run"]["completed_at"] is not None

            data = websocket.receive_json()
            assert data["type"] == "run_completed"


class TestDiagnosisEndpoints:
    """Tests for diagnosis and fix endpoints."""

    @pytest.fixture
    def failed_result(self, db_client, sample_retell_config):
        """Create an agent, test case, run, and failed result for testing."""

        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Diag Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        test_case_repo = _get_test_case_repo(db_client)
        tc = TestCase(
            name="Billing test",
            user_prompt="Ask about a refund",
            metrics=["Agent resolves billing issue"],
        )
        tc_record = test_case_repo.create(agent_id, tc)
        tc_id = tc_record["id"]

        run_repo = _get_run_repo(db_client)
        run = run_repo.create(agent_id)
        run_id = run["id"]
        result_id = run_repo.create_pending_result(run_id, tc_id, "Billing test")

        # Complete with failed result
        test_result = TestResult(
            test_id="Billing test",
            test_name="Billing test",
            status="fail",
            transcript=[
                {"role": "assistant", "content": "Hello!", "metadata": {"node_id": "greeting"}},
                {"role": "user", "content": "I want a refund"},
                {
                    "role": "assistant",
                    "content": "Cannot help.",
                    "metadata": {"node_id": "greeting"},
                },
            ],
            metric_results=[
                MetricResult(
                    metric="Agent resolves billing issue",
                    score=0.3,
                    passed=False,
                    reasoning="Agent refused to help",
                    threshold=0.7,
                )
            ],
            nodes_visited=["greeting"],
        )
        run_repo.complete_result(result_id, test_result)
        run_repo.complete(run_id)

        return {
            "agent_id": agent_id,
            "run_id": run_id,
            "result_id": result_id,
            "test_case_id": tc_id,
        }

    def test_diagnose_returns_200(self, db_client, failed_result):
        mock_result = DiagnosisResult(
            diagnosis=Diagnosis(
                fault_locations=[
                    FaultLocation(
                        location_type="node_prompt",
                        node_id="greeting",
                        relevant_text="Greet the user",
                        explanation="Too brief",
                    )
                ],
                root_cause="Missing billing guidance",
                transcript_evidence="ASSISTANT: Cannot help.",
            ),
            fix=FixSuggestion(
                changes=[
                    PromptChange(
                        location_type="node_prompt",
                        node_id="greeting",
                        original_text="Greet the user",
                        proposed_text="Greet and help with billing",
                        rationale="Add billing help",
                    )
                ],
                summary="Added billing guidance",
                confidence=0.85,
            ),
        )

        with patch(
            "voicetest.services.diagnosis.DiagnosisService.diagnose_failure",
            new_callable=AsyncMock,
        ) as mock_diag:
            mock_diag.return_value = mock_result
            response = db_client.post(f"/api/results/{failed_result['result_id']}/diagnose")

        assert response.status_code == 200
        data = response.json()
        assert "diagnosis" in data
        assert "fix" in data
        assert data["diagnosis"]["root_cause"] == "Missing billing guidance"

    def test_diagnose_returns_404_for_missing_result(self, db_client):
        response = db_client.post("/api/results/nonexistent/diagnose")
        assert response.status_code == 404

    def test_apply_fix_returns_200(self, db_client, failed_result):
        mock_attempt = FixAttemptResult(
            iteration=1,
            changes_applied=[],
            test_passed=False,
            metric_results=[{"metric": "test", "score": 0.5, "passed": False}],
            improved=True,
            original_scores={"test": 0.3},
            new_scores={"test": 0.5},
        )

        with patch(
            "voicetest.services.diagnosis.DiagnosisService.apply_and_rerun",
            new_callable=AsyncMock,
        ) as mock_apply:
            mock_apply.return_value = mock_attempt
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/apply-fix",
                json={
                    "changes": [
                        {
                            "location_type": "node_prompt",
                            "node_id": "greeting",
                            "original_text": "old",
                            "proposed_text": "new",
                            "rationale": "fix",
                        }
                    ],
                    "iteration": 1,
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["improved"] is True

    def test_revise_fix_returns_200(self, db_client, failed_result):
        mock_fix = FixSuggestion(
            changes=[
                PromptChange(
                    location_type="node_prompt",
                    node_id="greeting",
                    original_text="old",
                    proposed_text="better",
                    rationale="improved fix",
                )
            ],
            summary="Revised fix",
            confidence=0.9,
        )

        with patch(
            "voicetest.services.diagnosis.DiagnosisService.revise_fix",
            new_callable=AsyncMock,
        ) as mock_revise:
            mock_revise.return_value = mock_fix
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/revise-fix",
                json={
                    "diagnosis": {
                        "fault_locations": [],
                        "root_cause": "test",
                        "transcript_evidence": "test",
                    },
                    "previous_changes": [
                        {
                            "location_type": "node_prompt",
                            "node_id": "greeting",
                            "original_text": "old",
                            "proposed_text": "new",
                            "rationale": "first try",
                        }
                    ],
                    "new_metric_results": [
                        {
                            "metric": "test",
                            "score": 0.5,
                            "passed": False,
                            "reasoning": "partial",
                        }
                    ],
                },
            )

        assert response.status_code == 200
        data = response.json()
        assert data["confidence"] == 0.9

    def test_save_fix_returns_200(self, db_client, failed_result):
        response = db_client.post(
            f"/api/agents/{failed_result['agent_id']}/save-fix",
            json={
                "changes": [
                    {
                        "location_type": "node_prompt",
                        "node_id": "greeting",
                        "original_text": "old",
                        "proposed_text": "new prompt text",
                        "rationale": "fix",
                    }
                ]
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data

    def test_diagnose_with_model_override(self, db_client, failed_result):
        mock_result = DiagnosisResult(
            diagnosis=Diagnosis(
                fault_locations=[],
                root_cause="test",
                transcript_evidence="test",
            ),
            fix=FixSuggestion(
                changes=[],
                summary="test",
                confidence=0.5,
            ),
        )

        with patch(
            "voicetest.services.diagnosis.DiagnosisService.diagnose_failure",
            new_callable=AsyncMock,
        ) as mock_diag:
            mock_diag.return_value = mock_result
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/diagnose",
                json={"model": "openai/gpt-4o"},
            )

        assert response.status_code == 200
        call_kwargs = mock_diag.call_args.kwargs
        assert call_kwargs["judge_model"] == "openai/gpt-4o"

    def test_diagnose_without_model_uses_default(self, db_client, failed_result):
        mock_result = DiagnosisResult(
            diagnosis=Diagnosis(
                fault_locations=[],
                root_cause="test",
                transcript_evidence="test",
            ),
            fix=FixSuggestion(
                changes=[],
                summary="test",
                confidence=0.5,
            ),
        )

        with patch(
            "voicetest.services.diagnosis.DiagnosisService.diagnose_failure",
            new_callable=AsyncMock,
        ) as mock_diag:
            mock_diag.return_value = mock_result
            # No body / empty body
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/diagnose",
            )

        assert response.status_code == 200
        call_kwargs = mock_diag.call_args.kwargs
        assert call_kwargs["judge_model"] != "openai/gpt-4o"

    def test_revise_fix_with_model_override(self, db_client, failed_result):
        mock_fix = FixSuggestion(
            changes=[],
            summary="Revised",
            confidence=0.9,
        )

        with patch(
            "voicetest.services.diagnosis.DiagnosisService.revise_fix",
            new_callable=AsyncMock,
        ) as mock_revise:
            mock_revise.return_value = mock_fix
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/revise-fix",
                json={
                    "diagnosis": {
                        "fault_locations": [],
                        "root_cause": "test",
                        "transcript_evidence": "test",
                    },
                    "previous_changes": [],
                    "new_metric_results": [],
                    "model": "anthropic/claude-3-sonnet",
                },
            )

        assert response.status_code == 200
        call_kwargs = mock_revise.call_args.kwargs
        assert call_kwargs["judge_model"] == "anthropic/claude-3-sonnet"

    def test_save_fix_returns_404_for_missing_agent(self, db_client):
        response = db_client.post(
            "/api/agents/nonexistent/save-fix",
            json={"changes": []},
        )
        assert response.status_code == 404


class TestRunRunnerLifecycle:
    """End-to-end coverage of voicetest.services.run_runner.RunRunner.

    These tests POST to /api/agents/{id}/runs, then spy on coordinator.broadcast
    to assert the full broadcast sequence (state lives at the WS layer; we
    verify orchestration here).
    """

    @pytest.fixture
    def two_tests_agent(self, db_client, sample_retell_config):
        """Agent + 2 test cases; returns {agent_id, test_ids[]}."""
        agent_resp = db_client.post(
            "/api/agents",
            json={"name": "Lifecycle Agent", "config": sample_retell_config},
        )
        agent_id = agent_resp.json()["id"]
        test_ids = []
        for i in range(2):
            tr = db_client.post(
                f"/api/agents/{agent_id}/tests",
                json={"name": f"Test {i + 1}", "user_prompt": f"Prompt {i + 1}", "metrics": []},
            )
            test_ids.append(tr.json()["id"])
        return {"agent_id": agent_id, "test_ids": test_ids}

    @staticmethod
    def _spy_broadcasts(coordinator, monkeypatch) -> tuple[list, threading.Event]:
        """Replace coordinator.broadcast with a spy + an event that fires on run_completed.

        Returns `(calls, completed)`. Callers can `completed.wait(timeout=N)` to
        synchronize on the end of the run instead of polling — `threading.Event`
        works cross-loop, which matters because the spy runs on the FastAPI
        BackgroundTask's loop while tests wait from the sync thread.
        """
        calls: list = []
        completed = threading.Event()
        original = coordinator.broadcast

        async def spy(run_id, data):
            calls.append(data)
            await original(run_id, data)
            if data.get("type") == "run_completed":
                completed.set()

        monkeypatch.setattr(coordinator, "broadcast", spy)
        return calls, completed

    def test_full_lifecycle_broadcasts_state_running_completed(
        self, db_client, two_tests_agent, monkeypatch
    ):
        """A run with N tests broadcasts test_started + test_completed, then run_completed."""

        broadcasts, completed = self._spy_broadcasts(_get_coordinator(db_client), monkeypatch)

        async def fake_run_test(*args, **kwargs):
            return TestResult(test_id="t", test_name="Patched", status="pass", transcript=[])

        with patch(
            "voicetest.services.testing.execution.TestExecutionService.run_test",
            side_effect=fake_run_test,
        ):
            resp = db_client.post(
                f"/api/agents/{two_tests_agent['agent_id']}/runs",
                json={"test_ids": two_tests_agent["test_ids"]},
            )
            assert resp.status_code == 200
            assert completed.wait(timeout=5), f"run never completed; broadcasts: {broadcasts}"

        types = [c.get("type") for c in broadcasts]
        assert types.count("test_started") == 2
        assert types.count("test_completed") == 2
        assert types[-1] == "run_completed"
        # Each test_started precedes its test_completed (both pairs).
        started_idxs = [i for i, t in enumerate(types) if t == "test_started"]
        completed_idxs = [i for i, t in enumerate(types) if t == "test_completed"]
        for s, c in zip(started_idxs, completed_idxs, strict=True):
            assert s < c

    # The cancel-path tests below invoke RunRunner.execute() directly through the
    # container. Running through POST + TestClient is unreliable for cancellation
    # timing because TestClient awaits the BackgroundTask before returning, leaving
    # no window for the test thread to inject a cancel between iterations.

    @staticmethod
    def _prepare_job(db_client, agent_id: str, test_ids: list[str]):
        """Mirror start_run: create the Run, pending results, and a RunJob."""

        container = db_client.app.state.container
        run_svc = container.resolve(RunService)
        tc_svc = container.resolve(TestCaseService)

        all_tests = tc_svc.list_tests(agent_id)
        tests_by_id = {t["id"]: t for t in all_tests}
        test_records = [tests_by_id[tid] for tid in test_ids]

        run = run_svc.create_run(agent_id)
        result_ids: dict[str, str] = {}
        for tr in test_records:
            result_ids[tr["id"]] = run_svc.create_pending_result(run["id"], tr["id"], tr["name"])

        job = RunJob(
            run_id=run["id"],
            agent_id=agent_id,
            test_records=test_records,
            result_ids=result_ids,
            options=RunOptions(),
        )
        return job, result_ids

    def test_runrunner_skips_cancelled_test(self, db_client, two_tests_agent, monkeypatch):
        """A test cancelled before the loop reaches it → test_cancelled; run_test is skipped."""

        coordinator = _get_coordinator(db_client)
        broadcasts, _completed = self._spy_broadcasts(coordinator, monkeypatch)

        job, result_ids = self._prepare_job(
            db_client, two_tests_agent["agent_id"], two_tests_agent["test_ids"]
        )
        second_test_id = two_tests_agent["test_ids"][1]
        coordinator.start(job.run_id)
        coordinator.cancel_test(job.run_id, result_ids[second_test_id])

        async def fake_run_test(*args, **kwargs):
            return TestResult(test_id="t", test_name="Patched", status="pass", transcript=[])

        with patch(
            "voicetest.services.testing.execution.TestExecutionService.run_test",
            side_effect=fake_run_test,
        ) as mock_run_test:
            runner = db_client.app.state.container.resolve(RunRunner)
            asyncio.run(runner.execute(job))

        types = [c.get("type") for c in broadcasts]
        assert types.count("test_completed") == 1
        assert types.count("test_cancelled") == 1
        assert types[-1] == "run_completed"
        assert mock_run_test.call_count == 1

    def test_runrunner_cancel_run_aborts_remaining(self, db_client, two_tests_agent, monkeypatch):
        """coordinator.cancel_run() before execute() → all tests cancelled."""

        coordinator = _get_coordinator(db_client)
        broadcasts, _completed = self._spy_broadcasts(coordinator, monkeypatch)

        job, _ = self._prepare_job(
            db_client, two_tests_agent["agent_id"], two_tests_agent["test_ids"]
        )
        coordinator.start(job.run_id)
        coordinator.cancel_run(job.run_id)

        with patch(
            "voicetest.services.testing.execution.TestExecutionService.run_test"
        ) as mock_run_test:
            runner = db_client.app.state.container.resolve(RunRunner)
            asyncio.run(runner.execute(job))

        types = [c.get("type") for c in broadcasts]
        assert types.count("test_cancelled") == 2
        assert types[-1] == "run_completed"
        assert mock_run_test.call_count == 0

    def test_run_websocket_forwards_cancel_run_to_coordinator(
        self, db_client, sample_retell_config
    ):
        """/runs/{id}/ws forwards a `cancel_run` message to RunCoordinator.cancel_run.

        Sets up the run via the repo + coordinator manually so the WS endpoint
        has something to attach to, avoiding TestClient + BackgroundTask races.
        """

        agent_resp = db_client.post(
            "/api/agents",
            json={"name": "WS Cancel Agent", "config": sample_retell_config},
        )
        agent_id = agent_resp.json()["id"]
        run_repo = db_client.app.state.container.resolve(RunRepository)
        run = run_repo.create(agent_id)
        run_id = run["id"]

        coordinator = _get_coordinator(db_client)
        coordinator.start(run_id)  # keep the WS endpoint past the "already complete" early-exit

        try:
            with (
                patch.object(coordinator, "cancel_run") as cancel_run_spy,
                db_client.websocket_connect(f"/api/runs/{run_id}/ws") as ws,
            ):
                ws.receive_json()  # state
                ws.send_json({"type": "cancel_run"})

                time.sleep(0.2)

            cancel_run_spy.assert_called_with(run_id)
        finally:
            coordinator.end(run_id)

    def test_run_websocket_broadcasts_cancel_requested_on_cancel_run(
        self, db_client, sample_retell_config, monkeypatch
    ):
        """A `cancel_run` message acks back with a run-scoped `cancel_requested`."""

        agent_resp = db_client.post(
            "/api/agents",
            json={"name": "WS Ack Run Agent", "config": sample_retell_config},
        )
        agent_id = agent_resp.json()["id"]
        run_repo = db_client.app.state.container.resolve(RunRepository)
        run_id = run_repo.create(agent_id)["id"]

        coordinator = _get_coordinator(db_client)
        coordinator.start(run_id)
        broadcasts, _completed = self._spy_broadcasts(coordinator, monkeypatch)

        try:
            with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as ws:
                ws.receive_json()  # state
                ws.send_json({"type": "cancel_run"})
                time.sleep(0.2)

            acks = [c for c in broadcasts if c.get("type") == "cancel_requested"]
            assert len(acks) == 1
            assert acks[0].get("result_id") is None
        finally:
            coordinator.end(run_id)

    def test_run_websocket_broadcasts_cancel_requested_on_cancel_test(
        self, db_client, sample_retell_config, monkeypatch
    ):
        """A `cancel_test` message acks back with the test's `result_id`."""

        agent_resp = db_client.post(
            "/api/agents",
            json={"name": "WS Ack Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_resp.json()["id"]
        run_repo = db_client.app.state.container.resolve(RunRepository)
        run_id = run_repo.create(agent_id)["id"]

        coordinator = _get_coordinator(db_client)
        coordinator.start(run_id)
        broadcasts, _completed = self._spy_broadcasts(coordinator, monkeypatch)

        try:
            with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as ws:
                ws.receive_json()  # state
                ws.send_json({"type": "cancel_test", "result_id": "res-123"})
                time.sleep(0.2)

            acks = [c for c in broadcasts if c.get("type") == "cancel_requested"]
            assert len(acks) == 1
            assert acks[0]["result_id"] == "res-123"
        finally:
            coordinator.end(run_id)

    def test_quota_exhausted_aborts_remaining_tests(self, db_client, two_tests_agent, monkeypatch):
        """When run_test raises QuotaExhaustedError, remaining tests are marked cancelled."""

        broadcasts, completed = self._spy_broadcasts(_get_coordinator(db_client), monkeypatch)
        agent_id = two_tests_agent["agent_id"]

        async def raises_quota(*args, **kwargs):
            raise QuotaExhaustedError("quota gone", reset_message="try later")

        with patch(
            "voicetest.services.testing.execution.TestExecutionService.run_test",
            side_effect=raises_quota,
        ):
            resp = db_client.post(
                f"/api/agents/{agent_id}/runs",
                json={"test_ids": two_tests_agent["test_ids"]},
            )
            assert resp.status_code == 200
            assert completed.wait(timeout=5), f"run never completed; broadcasts: {broadcasts}"

        types = [c.get("type") for c in broadcasts]
        assert "quota_exhausted" in types
        # First test errored via quota_exhausted, second test never started but was cancelled.
        assert types.count("test_cancelled") == 1
        assert "test_started" in types  # first test did start before raising
        quota_msg = next(c for c in broadcasts if c.get("type") == "quota_exhausted")
        assert quota_msg["reset_message"] == "try later"

    def test_runrunner_unexpected_exception_broadcasts_test_error(
        self, db_client, two_tests_agent, monkeypatch
    ):
        """A non-Quota / non-Cancelled exception from run_test is surfaced as `test_error`
        and the run continues to the next test."""
        broadcasts, _completed = self._spy_broadcasts(_get_coordinator(db_client), monkeypatch)

        job, result_ids = self._prepare_job(
            db_client, two_tests_agent["agent_id"], two_tests_agent["test_ids"]
        )
        first_test_id = two_tests_agent["test_ids"][0]
        first_result_id = result_ids[first_test_id]
        _get_coordinator(db_client).start(job.run_id)

        async def raises_unexpected(*args, **kwargs):
            raise RuntimeError("boom")

        with patch(
            "voicetest.services.testing.execution.TestExecutionService.run_test",
            side_effect=raises_unexpected,
        ):
            runner = db_client.app.state.container.resolve(RunRunner)
            asyncio.run(runner.execute(job))

        errors = [c for c in broadcasts if c.get("type") == "test_error"]
        assert len(errors) == 2, f"expected one test_error per test; got broadcasts: {broadcasts}"
        assert errors[0]["result_id"] == first_result_id
        assert errors[0]["error"] == "boom"
        # Run still finishes cleanly — unexpected errors don't abort the run.
        assert [c for c in broadcasts if c.get("type") == "run_completed"]
