"""Tests for WebSocket, run management, orphan detection, and diagnosis endpoints."""

import pytest


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

    def test_broadcast_test_started_includes_test_case_id(self):
        """Verify _broadcast_run_update sends test_case_id in test_started messages."""
        import asyncio

        from voicetest.rest import _active_runs

        run_id = "test-run-123"
        test_case_id = "test-case-456"
        result_id = "result-789"

        _active_runs[run_id] = {
            "cancel": asyncio.Event(),
            "websockets": set(),
            "cancelled_tests": set(),
        }

        message = {
            "type": "test_started",
            "result_id": result_id,
            "test_case_id": test_case_id,
            "test_name": "My Test",
        }

        assert "test_case_id" in message
        assert message["test_case_id"] == test_case_id

        del _active_runs[run_id]

    def test_execute_run_sends_test_case_id_in_test_started(
        self, db_client, agent_with_test, monkeypatch
    ):
        """Verify _execute_run includes test_case_id when broadcasting test_started."""
        from unittest.mock import patch

        agent_id = agent_with_test["agent_id"]
        test_id = agent_with_test["test_id"]

        broadcast_calls = []

        async def mock_broadcast(run_id, data):
            broadcast_calls.append(data)

        with (
            patch("voicetest.rest._broadcast_run_update", mock_broadcast),
            patch("voicetest.rest.api.run_test") as mock_run_test,
        ):
            from voicetest.models.results import TestResult

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

            import time

            time.sleep(0.5)

        test_started_msgs = [c for c in broadcast_calls if c.get("type") == "test_started"]
        assert len(test_started_msgs) >= 1, "Should have at least one test_started message"

        for msg in test_started_msgs:
            assert "test_case_id" in msg, "test_started must include test_case_id"
            assert msg["test_case_id"] == test_id, "test_case_id should match the test ID"


class TestTranscriptUpdate:
    """Tests for transcript streaming functionality."""

    def test_transcript_update_message_format(self):
        """Verify transcript_update message has correct structure."""
        from voicetest.models.results import Message

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
        """Create an orphaned run (not in _active_runs, not completed)."""
        from voicetest.rest import _active_runs
        from voicetest.rest import get_run_repo

        # Create agent
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Orphan Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        # Create run directly in DB (simulating a crashed run)
        run_repo = get_run_repo()
        run = run_repo.create(agent_id)
        run_id = run["id"]

        # Add a "running" result
        result_id = run_repo.create_pending_result(run_id, "test-case-1", "Test Case 1")

        # Ensure run is NOT in _active_runs (simulating backend restart)
        _active_runs.pop(run_id, None)

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
        import asyncio

        from voicetest.rest import _active_runs
        from voicetest.rest import get_run_repo

        # Create agent
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Active Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        # Create run
        run_repo = get_run_repo()
        run = run_repo.create(agent_id)
        run_id = run["id"]

        # Add run to _active_runs (simulating active run)
        _active_runs[run_id] = {
            "cancel": asyncio.Event(),
            "websockets": set(),
            "cancelled_tests": set(),
            "message_queue": [],
        }

        try:
            response = db_client.get(f"/api/runs/{run_id}")
            assert response.status_code == 200

            run_data = response.json()
            assert run_data["completed_at"] is None, "Active run should NOT be marked complete"
        finally:
            _active_runs.pop(run_id, None)


class TestRunDeletion:
    """Tests for run deletion endpoint."""

    def test_delete_run(self, db_client, sample_retell_config):
        """DELETE /runs/{id} should delete the run and its results."""
        from voicetest.rest import get_run_repo

        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        run_repo = get_run_repo()
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
        import asyncio

        from voicetest.rest import _active_runs
        from voicetest.rest import get_run_repo

        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        run_repo = get_run_repo()
        run = run_repo.create(agent_id)
        run_id = run["id"]

        _active_runs[run_id] = {
            "cancel": asyncio.Event(),
            "websockets": set(),
            "cancelled_tests": set(),
            "message_queue": [],
        }

        try:
            response = db_client.delete(f"/api/runs/{run_id}")
            assert response.status_code == 400
            assert "active" in response.json()["detail"].lower()
        finally:
            _active_runs.pop(run_id, None)


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
        """WebSocket connection should receive a valid state message with run data.

        This test verifies the WebSocket endpoint works correctly:
        1. Connection is accepted
        2. State message is sent immediately after connection
        3. State message contains valid run data with results
        """
        agent_id = agent_with_tests["agent_id"]
        test_ids = agent_with_tests["test_ids"]

        # Start a run via HTTP
        run_response = db_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": test_ids},
        )
        assert run_response.status_code == 200
        run_id = run_response.json()["id"]

        # Connect to WebSocket - this is the key test
        # If the WebSocket handler fails (e.g., serialization error), this will raise
        with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
            # Should receive state message immediately after connection
            data = websocket.receive_json()

            # Verify message structure
            assert data["type"] == "state", f"Expected 'state' message, got {data.get('type')}"
            assert "run" in data, "State message should contain 'run'"

            run_data = data["run"]
            assert run_data["id"] == run_id
            assert "results" in run_data, "Run should have 'results' field"
            assert "started_at" in run_data, "Run should have 'started_at' field"
            assert run_data["agent_id"] == agent_id

            # Results should exist (created by start_run)
            results = run_data["results"]
            assert len(results) == len(test_ids), (
                f"Expected {len(test_ids)} results, got {len(results)}"
            )

            # Verify each result has required fields (status may vary due to race)
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
        import json

        agent_id = agent_with_tests["agent_id"]
        test_ids = agent_with_tests["test_ids"]

        run_response = db_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": test_ids},
        )
        run_id = run_response.json()["id"]

        with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
            data = websocket.receive_json()

            # If we got here, JSON parsing worked on the client side
            # Also verify we can re-serialize it (round-trip test)
            reserialized = json.dumps(data)
            assert len(reserialized) > 0

            # Verify datetime fields are strings, not datetime objects
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
        import time

        from voicetest.rest import _active_runs

        agent_id = agent_with_tests["agent_id"]
        test_ids = agent_with_tests["test_ids"]

        # Start a run and wait for it to complete
        run_response = db_client.post(
            f"/api/agents/{agent_id}/runs",
            json={"test_ids": test_ids},
        )
        run_id = run_response.json()["id"]

        # Wait for run to complete and be removed from _active_runs
        max_wait = 10
        while run_id in _active_runs and max_wait > 0:
            time.sleep(0.5)
            max_wait -= 1

        # Verify run is complete
        run = db_client.get(f"/api/runs/{run_id}").json()
        assert run["completed_at"] is not None, "Run should be complete"

        # Connect WebSocket - should receive state showing completion
        with db_client.websocket_connect(f"/api/runs/{run_id}/ws") as websocket:
            data = websocket.receive_json()
            assert data["type"] == "state"
            assert data["run"]["completed_at"] is not None

            # Should also receive run_completed message
            data = websocket.receive_json()
            assert data["type"] == "run_completed"


class TestDiagnosisEndpoints:
    """Tests for diagnosis and fix endpoints."""

    @pytest.fixture
    def failed_result(self, db_client, sample_retell_config):
        """Create an agent, test case, run, and failed result for testing."""
        from voicetest.models.results import MetricResult
        from voicetest.models.results import TestResult
        from voicetest.models.test_case import TestCase
        from voicetest.rest import get_run_repo
        from voicetest.rest import get_test_case_repo

        # Create agent with graph
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "Diag Test Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        # Create test case
        test_case_repo = get_test_case_repo()
        tc = TestCase(
            name="Billing test",
            user_prompt="Ask about a refund",
            metrics=["Agent resolves billing issue"],
        )
        tc_record = test_case_repo.create(agent_id, tc)
        tc_id = tc_record["id"]

        # Create run + result
        run_repo = get_run_repo()
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
        from unittest.mock import AsyncMock
        from unittest.mock import patch

        from voicetest.models.diagnosis import Diagnosis
        from voicetest.models.diagnosis import DiagnosisResult
        from voicetest.models.diagnosis import FaultLocation
        from voicetest.models.diagnosis import FixSuggestion
        from voicetest.models.diagnosis import PromptChange

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

        with patch("voicetest.rest.api.diagnose_failure", new_callable=AsyncMock) as mock_diag:
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
        from unittest.mock import AsyncMock
        from unittest.mock import patch

        from voicetest.models.diagnosis import FixAttemptResult

        mock_attempt = FixAttemptResult(
            iteration=1,
            changes_applied=[],
            test_passed=False,
            metric_results=[{"metric": "test", "score": 0.5, "passed": False}],
            improved=True,
            original_scores={"test": 0.3},
            new_scores={"test": 0.5},
        )

        with patch("voicetest.rest.api.apply_and_rerun", new_callable=AsyncMock) as mock_apply:
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
        from unittest.mock import AsyncMock
        from unittest.mock import patch

        from voicetest.models.diagnosis import FixSuggestion
        from voicetest.models.diagnosis import PromptChange

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

        with patch("voicetest.rest.api.revise_fix", new_callable=AsyncMock) as mock_revise:
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
        from unittest.mock import AsyncMock
        from unittest.mock import patch

        from voicetest.models.diagnosis import Diagnosis
        from voicetest.models.diagnosis import DiagnosisResult
        from voicetest.models.diagnosis import FixSuggestion

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

        with patch("voicetest.rest.api.diagnose_failure", new_callable=AsyncMock) as mock_diag:
            mock_diag.return_value = mock_result
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/diagnose",
                json={"model": "openai/gpt-4o"},
            )

        assert response.status_code == 200
        # Verify the model override was passed through
        call_kwargs = mock_diag.call_args.kwargs
        assert call_kwargs["judge_model"] == "openai/gpt-4o"

    def test_diagnose_without_model_uses_default(self, db_client, failed_result):
        from unittest.mock import AsyncMock
        from unittest.mock import patch

        from voicetest.models.diagnosis import Diagnosis
        from voicetest.models.diagnosis import DiagnosisResult
        from voicetest.models.diagnosis import FixSuggestion

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

        with patch("voicetest.rest.api.diagnose_failure", new_callable=AsyncMock) as mock_diag:
            mock_diag.return_value = mock_result
            # No body / empty body
            response = db_client.post(
                f"/api/results/{failed_result['result_id']}/diagnose",
            )

        assert response.status_code == 200
        # Should use the default resolved judge model, not an override
        call_kwargs = mock_diag.call_args.kwargs
        assert call_kwargs["judge_model"] != "openai/gpt-4o"

    def test_revise_fix_with_model_override(self, db_client, failed_result):
        from unittest.mock import AsyncMock
        from unittest.mock import patch

        from voicetest.models.diagnosis import FixSuggestion

        mock_fix = FixSuggestion(
            changes=[],
            summary="Revised",
            confidence=0.9,
        )

        with patch("voicetest.rest.api.revise_fix", new_callable=AsyncMock) as mock_revise:
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
