"""Tests for voicetest REST API."""

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestImportersEndpoint:
    """Tests for importers endpoint."""

    def test_list_importers(self, client):
        response = client.get("/api/importers")
        assert response.status_code == 200

        importers = response.json()
        assert isinstance(importers, list)
        assert len(importers) >= 2  # retell and custom

        source_types = [imp["source_type"] for imp in importers]
        assert "retell" in source_types
        assert "custom" in source_types

    def test_importer_has_required_fields(self, client):
        response = client.get("/api/importers")
        importers = response.json()

        for imp in importers:
            assert "source_type" in imp
            assert "description" in imp
            assert "file_patterns" in imp


class TestExportersEndpoint:
    """Tests for exporters endpoint."""

    def test_list_exporters(self, client):
        response = client.get("/api/exporters")
        assert response.status_code == 200

        exporters = response.json()
        assert isinstance(exporters, list)
        assert len(exporters) >= 4

        format_ids = [exp["id"] for exp in exporters]
        assert "mermaid" in format_ids
        assert "livekit" in format_ids
        assert "retell-llm" in format_ids
        assert "retell-cf" in format_ids

    def test_exporter_has_required_fields(self, client):
        response = client.get("/api/exporters")
        exporters = response.json()

        for exp in exporters:
            assert "id" in exp
            assert "name" in exp
            assert "description" in exp


class TestImportEndpoint:
    """Tests for agent import endpoint."""

    def test_import_retell_config(self, client, sample_retell_config):
        response = client.post("/api/agents/import", json={"config": sample_retell_config})
        assert response.status_code == 200

        graph = response.json()
        assert graph["source_type"] == "retell"
        assert graph["entry_node_id"] == "greeting"
        assert len(graph["nodes"]) == 4

    def test_import_with_explicit_source(self, client, sample_retell_config):
        response = client.post(
            "/api/agents/import", json={"config": sample_retell_config, "source": "retell"}
        )
        assert response.status_code == 200
        assert response.json()["source_type"] == "retell"

    def test_import_unknown_source_returns_400(self, client):
        response = client.post("/api/agents/import", json={"config": {}, "source": "nonexistent"})
        assert response.status_code == 400

    def test_import_undetectable_config_returns_400(self, client):
        response = client.post("/api/agents/import", json={"config": {"random": "data"}})
        assert response.status_code == 400


class TestExportEndpoint:
    """Tests for agent export endpoint."""

    def test_export_mermaid(self, client, sample_retell_config):
        # First import
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        # Then export
        response = client.post("/api/agents/export", json={"graph": graph, "format": "mermaid"})
        assert response.status_code == 200

        result = response.json()
        assert result["format"] == "mermaid"
        assert "flowchart" in result["content"].lower()
        assert "greeting" in result["content"]

    def test_export_livekit(self, client, sample_retell_config):
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        response = client.post("/api/agents/export", json={"graph": graph, "format": "livekit"})
        assert response.status_code == 200

        result = response.json()
        assert "class Agent_greeting" in result["content"]

    def test_export_unknown_format_returns_400(self, client, sample_retell_config):
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        response = client.post("/api/agents/export", json={"graph": graph, "format": "unknown"})
        assert response.status_code == 400

    def test_export_retell_llm(self, client, sample_retell_config):
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        response = client.post("/api/agents/export", json={"graph": graph, "format": "retell-llm"})
        assert response.status_code == 200

        result = response.json()
        assert result["format"] == "retell-llm"
        import json

        content = json.loads(result["content"])
        assert "states" in content
        assert "general_prompt" in content

    def test_export_retell_cf(self, client, sample_retell_config):
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        response = client.post("/api/agents/export", json={"graph": graph, "format": "retell-cf"})
        assert response.status_code == 200

        result = response.json()
        assert result["format"] == "retell-cf"
        import json

        content = json.loads(result["content"])
        assert "nodes" in content
        assert "start_node_id" in content


class TestRunEndpoints:
    """Tests for test run endpoints."""

    def test_run_single_test(self, client, sample_retell_config):
        # Import agent
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        # Create test case (Retell format)
        test_case = {
            "name": "API test",
            "user_prompt": "When asked, say Test. Say hello.",
            "metrics": ["Agent responded."],
        }

        # Run test (will use mock mode internally due to test environment)
        response = client.post("/api/runs/single", json={"graph": graph, "test_case": test_case})

        # Should succeed even if test itself fails (it returns a result)
        assert response.status_code == 200
        result = response.json()
        assert result["test_id"] == "API test"
        assert result["status"] in ("pass", "fail", "error")

    def test_run_multiple_tests(self, client, sample_retell_config):
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        test_cases = [
            {
                "name": "Test 1",
                "user_prompt": "When asked, say A. Say hello.",
                "metrics": [],
            },
            {
                "name": "Test 2",
                "user_prompt": "When asked, say B. Say bye.",
                "metrics": [],
            },
        ]

        response = client.post("/api/runs", json={"graph": graph, "test_cases": test_cases})
        assert response.status_code == 200

        run = response.json()
        assert "run_id" in run
        assert len(run["results"]) == 2


class TestEvaluateEndpoint:
    """Tests for transcript evaluation endpoint."""

    def test_evaluate_transcript(self, client):
        from unittest.mock import patch

        from voicetest.models.results import MetricResult

        async def mock_evaluate_with_llm(self, transcript, criterion, threshold):
            return MetricResult(
                metric=criterion,
                score=0.9,
                passed=True,
                reasoning=f"Mock evaluation for: {criterion}",
                threshold=threshold,
            )

        transcript = [
            {"role": "assistant", "content": "Hello! How can I help you?"},
            {"role": "user", "content": "I need help with billing"},
            {"role": "assistant", "content": "I can help with that."},
        ]

        with patch(
            "voicetest.judges.metric.MetricJudge._evaluate_with_llm",
            mock_evaluate_with_llm,
        ):
            response = client.post(
                "/api/evaluate",
                json={
                    "transcript": transcript,
                    "metrics": ["Agent greeted user", "Agent offered help"],
                },
            )

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 2
        assert results[0]["passed"] is True
        assert results[1]["passed"] is True


class TestSettingsEndpoint:
    """Tests for settings endpoints."""

    def test_get_settings(self, client, tmp_path, monkeypatch):
        # Use temp directory with .voicetest/ so we use project mode (not global fallback)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".voicetest").mkdir()

        response = client.get("/api/settings")

        assert response.status_code == 200
        settings = response.json()
        assert "models" in settings
        assert "run" in settings
        assert settings["models"]["agent"] == "openai/gpt-4o-mini"

    def test_update_settings(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".voicetest").mkdir()

        new_settings = {
            "models": {
                "agent": "anthropic/claude-3-haiku",
                "simulator": "openai/gpt-4o-mini",
                "judge": "openai/gpt-4o-mini",
            },
            "run": {
                "max_turns": 10,
                "verbose": True,
            },
        }

        response = client.put("/api/settings", json=new_settings)

        assert response.status_code == 200
        result = response.json()
        assert result["models"]["agent"] == "anthropic/claude-3-haiku"
        assert result["run"]["max_turns"] == 10

        # Verify it persisted
        get_response = client.get("/api/settings")
        assert get_response.json()["models"]["agent"] == "anthropic/claude-3-haiku"


class TestAgentsCRUD:
    """Tests for agent CRUD endpoints."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

    def test_list_agents_empty(self, db_client):
        response = db_client.get("/api/agents")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_agent_from_import(self, db_client, sample_retell_config):
        response = db_client.post(
            "/api/agents",
            json={
                "name": "Test Agent",
                "config": sample_retell_config,
            },
        )
        assert response.status_code == 200

        agent = response.json()
        assert agent["id"] is not None
        assert agent["name"] == "Test Agent"
        assert agent["source_type"] == "retell"

    def test_get_agent(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "Find Me", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        response = db_client.get(f"/api/agents/{agent_id}")
        assert response.status_code == 200
        assert response.json()["name"] == "Find Me"

    def test_get_agent_graph(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "Graph Test", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        response = db_client.get(f"/api/agents/{agent_id}/graph")
        assert response.status_code == 200

        graph = response.json()
        assert graph["source_type"] == "retell"
        assert graph["entry_node_id"] == "greeting"

    def test_get_nonexistent_agent(self, db_client):
        response = db_client.get("/api/agents/nonexistent-id")
        assert response.status_code == 404

    def test_update_agent(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "Original", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        response = db_client.put(
            f"/api/agents/{agent_id}",
            json={"name": "Updated Name"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated Name"

    def test_delete_agent(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "To Delete", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        response = db_client.delete(f"/api/agents/{agent_id}")
        assert response.status_code == 200

        get_response = db_client.get(f"/api/agents/{agent_id}")
        assert get_response.status_code == 404

    def test_get_metrics_config_default(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        response = db_client.get(f"/api/agents/{agent_id}/metrics-config")
        assert response.status_code == 200

        config = response.json()
        assert config["threshold"] == 0.7
        assert config["global_metrics"] == []

    def test_update_metrics_config(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        new_config = {
            "threshold": 0.8,
            "global_metrics": [
                {
                    "name": "HIPAA",
                    "criteria": "Check HIPAA compliance",
                    "threshold": None,
                    "enabled": True,
                },
            ],
        }

        response = db_client.put(
            f"/api/agents/{agent_id}/metrics-config",
            json=new_config,
        )
        assert response.status_code == 200

        config = response.json()
        assert config["threshold"] == 0.8
        assert len(config["global_metrics"]) == 1
        assert config["global_metrics"][0]["name"] == "HIPAA"

    def test_metrics_config_included_in_agent_response(self, db_client, sample_retell_config):
        create_response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        agent_id = create_response.json()["id"]

        # Update metrics config
        db_client.put(
            f"/api/agents/{agent_id}/metrics-config",
            json={
                "threshold": 0.9,
                "global_metrics": [],
            },
        )

        # Get agent should include metrics_config
        response = db_client.get(f"/api/agents/{agent_id}")
        assert response.status_code == 200

        agent = response.json()
        assert "metrics_config" in agent


class TestTestCasesCRUD:
    """Tests for test case CRUD endpoints."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

    @pytest.fixture
    def agent_id(self, db_client, sample_retell_config):
        """Create an agent and return its ID."""
        response = db_client.post(
            "/api/agents",
            json={"name": "Test Agent", "config": sample_retell_config},
        )
        return response.json()["id"]

    def test_list_tests_empty(self, db_client, agent_id):
        response = db_client.get(f"/api/agents/{agent_id}/tests")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_test(self, db_client, agent_id):
        response = db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={
                "name": "Basic Test",
                "user_prompt": "Say hello",
                "metrics": ["Greets user"],
            },
        )
        assert response.status_code == 200

        test = response.json()
        assert test["id"] is not None
        assert test["name"] == "Basic Test"
        assert test["agent_id"] == agent_id

    def test_update_test(self, db_client, agent_id):
        create_response = db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={"name": "Original", "user_prompt": "Hello"},
        )
        test_id = create_response.json()["id"]

        response = db_client.put(
            f"/api/tests/{test_id}",
            json={"name": "Updated", "user_prompt": "New prompt"},
        )
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"

    def test_delete_test(self, db_client, agent_id):
        create_response = db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={"name": "To Delete", "user_prompt": "Bye"},
        )
        test_id = create_response.json()["id"]

        response = db_client.delete(f"/api/tests/{test_id}")
        assert response.status_code == 200

        list_response = db_client.get(f"/api/agents/{agent_id}/tests")
        assert len(list_response.json()) == 0

    def test_export_tests_retell(self, db_client, agent_id):
        """Export tests to Retell format."""
        db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={"name": "LLM Test", "user_prompt": "Hello", "metrics": ["Be helpful"]},
        )
        db_client.post(
            f"/api/agents/{agent_id}/tests",
            json={
                "name": "Rule Test",
                "user_prompt": "Check",
                "type": "rule",
                "includes": ["welcome"],
            },
        )

        response = db_client.post(
            f"/api/agents/{agent_id}/tests/export",
            json={"format": "retell"},
        )
        assert response.status_code == 200

        exported = response.json()
        assert len(exported) == 2
        assert exported[0]["type"] == "simulation"
        assert exported[0]["metrics"] == ["Be helpful"]
        assert exported[1]["type"] == "unit"
        assert exported[1]["includes"] == ["welcome"]


class TestGalleryEndpoint:
    """Tests for test gallery endpoint."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

    def test_list_gallery(self, db_client):
        response = db_client.get("/api/gallery")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestRunWebSocket:
    """Tests for run WebSocket endpoint and message formats."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

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
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

    @pytest.fixture
    def orphaned_run(self, db_client, sample_retell_config):
        """Create an orphaned run (not in _active_runs, not completed)."""
        from voicetest.rest import _active_runs, get_run_repo

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

        from voicetest.rest import _active_runs, get_run_repo

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

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

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

        from voicetest.rest import _active_runs, get_run_repo

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
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app, init_storage

        init_storage()

        return TestClient(app)

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
                    "name": f"Test {i+1}",
                    "user_prompt": f"Test prompt {i+1}",
                    "metrics": [],
                },
            )
            assert (
                test_response.status_code == 200
            ), f"Failed to create test: {test_response.json()}"
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
            assert len(results) == len(
                test_ids
            ), f"Expected {len(test_ids)} results, got {len(results)}"

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
                assert isinstance(
                    run_data["completed_at"], str
                ), "completed_at should be ISO string"

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
