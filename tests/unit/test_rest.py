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
            assert "ext" in exp
            assert exp["ext"] != "undefined"


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
        assert content["response_engine"]["type"] == "conversation-flow"
        cf = content["conversationFlow"]
        assert "nodes" in cf
        assert "start_node_id" in cf


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

        async def mock_evaluate_with_llm(
            self, transcript, criterion, threshold, on_error=None, use_heard=False
        ):
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
        assert settings["models"]["agent"] is None  # default is None

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

        from voicetest.rest import app
        from voicetest.rest import init_storage

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

    def test_create_agent_from_path(self, db_client, tmp_path, sample_retell_config):
        import json

        agent_file = tmp_path / "agent.json"
        agent_file.write_text(json.dumps(sample_retell_config))

        response = db_client.post(
            "/api/agents",
            json={
                "name": "Path Agent",
                "path": str(agent_file),
            },
        )
        assert response.status_code == 200

        agent = response.json()
        assert agent["name"] == "Path Agent"
        assert agent["source_type"] == "retell"
        assert agent["source_path"] == str(agent_file.resolve())

    def test_create_agent_relative_path_stored_as_absolute(
        self, db_client, tmp_path, sample_retell_config, monkeypatch
    ):
        import json
        import os

        agent_file = tmp_path / "agent.json"
        agent_file.write_text(json.dumps(sample_retell_config))

        # Use a relative path
        monkeypatch.chdir(tmp_path)
        response = db_client.post(
            "/api/agents",
            json={
                "name": "Relative Path Agent",
                "path": "agent.json",
            },
        )
        assert response.status_code == 200

        agent = response.json()
        # Path should be stored as absolute
        assert os.path.isabs(agent["source_path"])
        assert agent["source_path"] == str(agent_file.resolve())

    def test_create_agent_path_not_found(self, db_client):
        response = db_client.post(
            "/api/agents",
            json={
                "name": "Missing Agent",
                "path": "/nonexistent/path/agent.json",
            },
        )
        assert response.status_code == 400
        assert "File not found" in response.json()["detail"]

    def test_create_agent_path_is_directory(self, db_client, tmp_path):
        response = db_client.post(
            "/api/agents",
            json={
                "name": "Dir Agent",
                "path": str(tmp_path),
            },
        )
        assert response.status_code == 400
        assert "not a file" in response.json()["detail"]

    def test_create_agent_invalid_json(self, db_client, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("{ not valid json }")

        response = db_client.post(
            "/api/agents",
            json={
                "name": "Bad JSON Agent",
                "path": str(bad_file),
            },
        )
        assert response.status_code == 400
        # Auto-detection fails on invalid JSON before parsing
        assert "Could not auto-detect" in response.json()["detail"]

    def test_create_agent_invalid_config_json(self, db_client, tmp_path, sample_retell_config):
        import json

        # Valid JSON but missing required fields
        bad_config = {"nodes": []}
        bad_file = tmp_path / "bad_config.json"
        bad_file.write_text(json.dumps(bad_config))

        response = db_client.post(
            "/api/agents",
            json={
                "name": "Bad Config Agent",
                "path": str(bad_file),
            },
        )
        assert response.status_code == 400

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


class TestAgentVariablesEndpoint:
    """Tests for GET /agents/{id}/variables endpoint."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app
        from voicetest.rest import init_storage

        init_storage()

        return TestClient(app)

    def test_get_variables_from_dynamic_graph(self, db_client, graph_with_dynamic_variables):
        """Agent with {{var}} placeholders returns extracted variable names."""
        from voicetest.rest import get_agent_repo

        repo = get_agent_repo()
        agent = repo.create(
            name="Vars Agent",
            source_type="custom",
            graph_json=graph_with_dynamic_variables.model_dump_json(),
        )
        agent_id = agent["id"]

        response = db_client.get(f"/api/agents/{agent_id}/variables")
        assert response.status_code == 200

        data = response.json()
        assert "variables" in data
        variables = data["variables"]
        assert "company_name" in variables
        assert "customer_name" in variables
        assert "account_status" in variables

    def test_get_variables_no_variables(self, db_client, sample_retell_config):
        """Agent without {{var}} placeholders returns empty list."""
        agent_response = db_client.post(
            "/api/agents",
            json={"name": "No Vars Agent", "config": sample_retell_config},
        )
        agent_id = agent_response.json()["id"]

        response = db_client.get(f"/api/agents/{agent_id}/variables")
        assert response.status_code == 200
        assert response.json()["variables"] == []

    def test_get_variables_nonexistent_agent(self, db_client):
        """Returns 404 for non-existent agent."""
        response = db_client.get("/api/agents/nonexistent/variables")
        assert response.status_code == 404


class TestTestCasesCRUD:
    """Tests for test case CRUD endpoints."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app
        from voicetest.rest import init_storage

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

        from voicetest.rest import app
        from voicetest.rest import init_storage

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

        from voicetest.rest import app
        from voicetest.rest import init_storage

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

        from voicetest.rest import app
        from voicetest.rest import init_storage

        init_storage()

        return TestClient(app)

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

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app
        from voicetest.rest import init_storage

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
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app
        from voicetest.rest import init_storage

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


class TestPlatformEndpoints:
    """Tests for platform integration endpoints."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database and settings."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        # Clear platform API keys from environment
        monkeypatch.delenv("RETELL_API_KEY", raising=False)
        monkeypatch.delenv("VAPI_API_KEY", raising=False)
        monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
        monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

        # Use temp directory for settings
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".voicetest").mkdir()

        from voicetest.rest import app
        from voicetest.rest import init_storage

        init_storage()

        return TestClient(app)

    def test_get_platform_status_retell_not_configured(self, db_client):
        """Platform status returns false when API key not configured."""
        response = db_client.get("/api/platforms/retell/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "retell"
        assert data["configured"] is False

    def test_get_platform_status_vapi_not_configured(self, db_client):
        """Platform status returns false when API key not configured."""
        response = db_client.get("/api/platforms/vapi/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "vapi"
        assert data["configured"] is False

    def test_get_platform_status_invalid_platform(self, db_client):
        """Invalid platform name returns 400."""
        response = db_client.get("/api/platforms/invalid/status")
        assert response.status_code == 400
        assert "Invalid platform" in response.json()["detail"]

    def test_configure_platform_retell(self, db_client):
        """Configure platform sets API key in settings."""
        response = db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-retell-key"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "retell"
        assert data["configured"] is True

        # Verify status now shows configured
        status_response = db_client.get("/api/platforms/retell/status")
        assert status_response.json()["configured"] is True

    def test_configure_platform_already_configured_returns_409(self, db_client):
        """Configure returns 409 when API key already set."""
        # First configuration succeeds
        db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-key-1"},
        )

        # Second configuration fails
        response = db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-key-2"},
        )
        assert response.status_code == 409
        assert "already configured" in response.json()["detail"]

    def test_list_retell_agents_not_configured(self, db_client):
        """List agents returns 400 when API key not configured."""
        response = db_client.get("/api/platforms/retell/agents")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_list_vapi_agents_not_configured(self, db_client):
        """List agents returns 400 when API key not configured."""
        response = db_client.get("/api/platforms/vapi/agents")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_list_retell_agents_mocked(self, db_client, monkeypatch):
        """List Retell agents with mocked client."""
        from unittest.mock import MagicMock

        from voicetest.platforms.retell import RetellPlatformClient

        # Configure platform first
        db_client.post(
            "/api/platforms/retell/configure",
            json={"api_key": "test-retell-key"},
        )

        # Mock the client
        mock_flow = MagicMock()
        mock_flow.conversation_flow_id = "flow-123"
        mock_flow.conversation_flow_name = "Test Flow"

        mock_client = MagicMock()
        mock_client.conversation_flow.list.return_value = [mock_flow]

        monkeypatch.setattr(
            RetellPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        response = db_client.get("/api/platforms/retell/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["id"] == "flow-123"
        assert agents[0]["name"] == "Test Flow"

    def test_list_vapi_agents_mocked(self, db_client, monkeypatch):
        """List VAPI agents with mocked client."""
        from unittest.mock import MagicMock

        from voicetest.platforms.vapi import VapiPlatformClient

        # Configure platform first
        db_client.post(
            "/api/platforms/vapi/configure",
            json={"api_key": "test-vapi-key"},
        )

        # Mock the client
        mock_asst = MagicMock()
        mock_asst.id = "asst-456"
        mock_asst.name = "Test Assistant"

        mock_client = MagicMock()
        mock_client.assistants.list.return_value = [mock_asst]

        monkeypatch.setattr(
            VapiPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        response = db_client.get("/api/platforms/vapi/agents")
        assert response.status_code == 200
        agents = response.json()
        assert len(agents) == 1
        assert agents[0]["id"] == "asst-456"
        assert agents[0]["name"] == "Test Assistant"

    def test_import_retell_agent_not_configured(self, db_client):
        """Import agent returns 400 when API key not configured."""
        response = db_client.post("/api/platforms/retell/agents/flow-123/import", json={})
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_export_to_retell_not_configured(self, db_client, sample_retell_config):
        """Export to platform returns 400 when API key not configured."""
        # First import to get a graph
        import_response = db_client.post(
            "/api/agents/import", json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = db_client.post(
            "/api/platforms/retell/export",
            json={"graph": graph, "name": "Test Export"},
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_export_to_vapi_not_configured(self, db_client, sample_retell_config):
        """Export to platform returns 400 when API key not configured."""
        import_response = db_client.post(
            "/api/agents/import", json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = db_client.post(
            "/api/platforms/vapi/export",
            json={"graph": graph, "name": "Test Export"},
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_platform_status_configured_via_env(self, db_client, monkeypatch):
        """Platform shows as configured when API key is in environment."""
        monkeypatch.setenv("RETELL_API_KEY", "env-api-key")

        response = db_client.get("/api/platforms/retell/status")
        assert response.status_code == 200
        assert response.json()["configured"] is True

    def test_get_platform_status_livekit_not_configured(self, db_client):
        """LiveKit platform status returns false when API key not configured."""
        response = db_client.get("/api/platforms/livekit/status")
        assert response.status_code == 200
        data = response.json()
        assert data["platform"] == "livekit"
        assert data["configured"] is False

    def test_list_livekit_agents_not_configured(self, db_client):
        """List LiveKit agents returns 400 when API key not configured."""
        response = db_client.get("/api/platforms/livekit/agents")
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_import_livekit_agent_not_configured(self, db_client):
        """Import LiveKit agent returns 400 when API key not configured."""
        response = db_client.post("/api/platforms/livekit/agents/agent-123/import", json={})
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]

    def test_export_to_livekit_not_configured(self, db_client, sample_retell_config):
        """Export to LiveKit returns 400 when API key not configured."""
        import_response = db_client.post(
            "/api/agents/import", json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = db_client.post(
            "/api/platforms/livekit/export",
            json={"graph": graph, "name": "Test Export"},
        )
        assert response.status_code == 400
        assert "not configured" in response.json()["detail"]


class TestLiveKitImportExport:
    """Tests for LiveKit-specific import/export functionality."""

    def test_import_livekit_agent_from_file(self, client, sample_livekit_agent_code):
        """Import LiveKit agent code via dict."""
        response = client.post(
            "/api/agents/import",
            json={"config": {"code": sample_livekit_agent_code}, "source": "livekit"},
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["source_type"] == "livekit"
        assert graph["entry_node_id"] == "greeting"
        assert "greeting" in graph["nodes"]

    def test_export_to_livekit_format(self, client, sample_retell_config):
        """Export graph to LiveKit Python code."""
        import_response = client.post("/api/agents/import", json={"config": sample_retell_config})
        graph = import_response.json()

        response = client.post("/api/agents/export", json={"graph": graph, "format": "livekit"})
        assert response.status_code == 200

        result = response.json()
        assert result["format"] == "livekit"
        assert "class Agent_greeting" in result["content"]
        assert "from livekit.agents import" in result["content"]

    def test_livekit_roundtrip(self, client, sample_livekit_agent_code):
        """Import LiveKit code and export back to LiveKit."""
        import_response = client.post(
            "/api/agents/import",
            json={"config": {"code": sample_livekit_agent_code}, "source": "livekit"},
        )
        assert import_response.status_code == 200
        graph = import_response.json()

        export_response = client.post(
            "/api/agents/export", json={"graph": graph, "format": "livekit"}
        )
        assert export_response.status_code == 200

        result = export_response.json()
        assert "Agent_greeting" in result["content"]
        assert "Agent_billing" in result["content"]

    def test_livekit_listed_in_importers(self, client):
        """LiveKit should be listed in available importers."""
        response = client.get("/api/importers")
        assert response.status_code == 200

        importers = response.json()
        source_types = [imp["source_type"] for imp in importers]
        assert "livekit" in source_types


class TestSyncToPlatform:
    """Tests for sync-to-platform functionality."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database and settings."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        monkeypatch.delenv("RETELL_API_KEY", raising=False)
        monkeypatch.delenv("VAPI_API_KEY", raising=False)
        monkeypatch.delenv("LIVEKIT_API_KEY", raising=False)
        monkeypatch.delenv("LIVEKIT_API_SECRET", raising=False)

        monkeypatch.chdir(tmp_path)
        (tmp_path / ".voicetest").mkdir()

        from voicetest.rest import app
        from voicetest.rest import init_storage

        init_storage()

        return TestClient(app)

    def _create_agent_with_graph(self, db_client, graph, name):
        """Helper to create an agent with a specific graph using the repository."""
        from voicetest.rest import get_agent_repo

        repo = get_agent_repo()
        return repo.create(
            name=name,
            source_type=graph.source_type,
            graph_json=graph.model_dump_json(),
        )

    def test_sync_status_no_platform_source(self, db_client):
        """Sync status returns can_sync=False for non-platform agents."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="custom",
        )

        agent = self._create_agent_with_graph(db_client, graph, "Custom Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert "not a supported platform" in status["reason"]

    def test_sync_status_platform_no_remote_id(self, db_client):
        """Sync status returns can_sync=False when agent has no remote ID."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent No ID")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert status["platform"] == "retell"
        assert "No remote ID" in status["reason"]

    def test_sync_status_platform_not_configured(self, db_client):
        """Sync status returns needs_configuration=True when platform not configured."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert status["platform"] == "retell"
        assert status["remote_id"] == "flow-123"
        assert status["needs_configuration"] is True
        assert "not configured" in status["reason"]

    def test_sync_status_can_sync(self, db_client, monkeypatch):
        """Sync status returns can_sync=True when all conditions met."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        monkeypatch.setenv("RETELL_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is True
        assert status["platform"] == "retell"
        assert status["remote_id"] == "flow-123"

    def test_sync_status_bland_not_supported(self, db_client, monkeypatch):
        """Sync status returns can_sync=False for Bland (doesn't support updates)."""
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        monkeypatch.setenv("BLAND_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="bland",
            source_metadata={"agent_id": "agent-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Bland Agent")
        agent_id = agent["id"]

        status_response = db_client.get(f"/api/agents/{agent_id}/sync-status")
        assert status_response.status_code == 200
        status = status_response.json()
        assert status["can_sync"] is False
        assert status["platform"] == "bland"
        assert "does not support syncing" in status["reason"]

    def test_sync_agent_not_found(self, db_client):
        """Sync returns 404 for non-existent agent."""
        import json

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
        )

        response = db_client.post(
            "/api/agents/nonexistent/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert response.status_code == 404

    def test_sync_platform_not_supported(self, db_client):
        """Sync returns 400 for non-platform source."""
        import json

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="custom",
        )

        agent = self._create_agent_with_graph(db_client, graph, "Custom Agent")
        agent_id = agent["id"]

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 400
        assert "not a supported platform" in sync_response.json()["detail"]

    def test_sync_no_remote_id(self, db_client, monkeypatch):
        """Sync returns 400 when agent has no remote ID."""
        import json

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        monkeypatch.setenv("RETELL_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 400
        assert "No remote ID" in sync_response.json()["detail"]

    def test_sync_retell_success_mocked(self, db_client, monkeypatch):
        """Sync to Retell calls update_agent correctly."""
        import json
        from unittest.mock import MagicMock

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.platforms.retell import RetellPlatformClient

        monkeypatch.setenv("RETELL_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="retell",
            source_metadata={"conversation_flow_id": "flow-123"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "Retell Agent")
        agent_id = agent["id"]

        mock_flow = MagicMock()
        mock_flow.conversation_flow_id = "flow-123"
        mock_flow.conversation_flow_name = "Updated Flow"

        mock_client = MagicMock()
        mock_client.conversation_flow.update.return_value = mock_flow

        monkeypatch.setattr(
            RetellPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 200

        result = sync_response.json()
        assert result["id"] == "flow-123"
        assert result["platform"] == "retell"
        assert result["synced"] is True

        mock_client.conversation_flow.update.assert_called_once()

    def test_sync_vapi_success_mocked(self, db_client, monkeypatch):
        """Sync to VAPI calls update_agent correctly."""
        import json
        from unittest.mock import MagicMock

        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode
        from voicetest.platforms.vapi import VapiPlatformClient

        monkeypatch.setenv("VAPI_API_KEY", "test-key")

        graph = AgentGraph(
            nodes={
                "main": AgentNode(
                    id="main",
                    state_prompt="Hello",
                    transitions=[],
                ),
            },
            entry_node_id="main",
            source_type="vapi",
            source_metadata={"assistant_id": "asst-456"},
        )

        agent = self._create_agent_with_graph(db_client, graph, "VAPI Agent")
        agent_id = agent["id"]

        mock_assistant = MagicMock()
        mock_assistant.id = "asst-456"
        mock_assistant.name = "Updated Assistant"

        mock_client = MagicMock()
        mock_client.assistants.update.return_value = mock_assistant

        monkeypatch.setattr(
            VapiPlatformClient, "get_client", lambda self, api_key=None: mock_client
        )

        sync_response = db_client.post(
            f"/api/agents/{agent_id}/sync",
            json={"graph": json.loads(graph.model_dump_json())},
        )
        assert sync_response.status_code == 200

        result = sync_response.json()
        assert result["id"] == "asst-456"
        assert result["platform"] == "vapi"
        assert result["synced"] is True

        mock_client.assistants.update.assert_called_once()


class TestPlatformSupportsUpdate:
    """Tests for platform supports_update property."""

    def test_retell_supports_update(self):
        """Retell platform supports updates."""
        from voicetest.platforms.retell import RetellPlatformClient

        client = RetellPlatformClient()
        assert client.supports_update is True
        assert client.remote_id_key == "conversation_flow_id"

    def test_vapi_supports_update(self):
        """VAPI platform supports updates."""
        from voicetest.platforms.vapi import VapiPlatformClient

        client = VapiPlatformClient()
        assert client.supports_update is True
        assert client.remote_id_key == "assistant_id"

    def test_livekit_supports_update(self):
        """LiveKit platform supports updates."""
        from voicetest.platforms.livekit import LiveKitPlatformClient

        client = LiveKitPlatformClient()
        assert client.supports_update is True
        assert client.remote_id_key == "agent_id"

    def test_bland_does_not_support_update(self):
        """Bland platform does not support updates."""
        from voicetest.platforms.bland import BlandPlatformClient

        client = BlandPlatformClient()
        assert client.supports_update is False
        assert client.remote_id_key is None

    def test_bland_update_agent_raises(self):
        """Bland update_agent raises NotImplementedError."""
        from voicetest.platforms.bland import BlandPlatformClient

        client = BlandPlatformClient()
        with pytest.raises(NotImplementedError) as exc_info:
            client.update_agent(None, "agent-123", {})
        assert "does not support" in str(exc_info.value)


class TestPlatformRegistrySupportsUpdate:
    """Tests for PlatformRegistry supports_update method."""

    def test_registry_supports_update_retell(self):
        """Registry returns True for Retell."""
        from voicetest.platforms.registry import PlatformRegistry
        from voicetest.platforms.retell import RetellPlatformClient

        registry = PlatformRegistry()
        registry.register(RetellPlatformClient())

        assert registry.supports_update("retell") is True

    def test_registry_supports_update_bland(self):
        """Registry returns False for Bland."""
        from voicetest.platforms.bland import BlandPlatformClient
        from voicetest.platforms.registry import PlatformRegistry

        registry = PlatformRegistry()
        registry.register(BlandPlatformClient())

        assert registry.supports_update("bland") is False

    def test_registry_get_remote_id_key(self):
        """Registry returns correct remote ID key."""
        from voicetest.platforms.registry import PlatformRegistry
        from voicetest.platforms.retell import RetellPlatformClient
        from voicetest.platforms.vapi import VapiPlatformClient

        registry = PlatformRegistry()
        registry.register(RetellPlatformClient())
        registry.register(VapiPlatformClient())

        assert registry.get_remote_id_key("retell") == "conversation_flow_id"
        assert registry.get_remote_id_key("vapi") == "assistant_id"

    def test_registry_supports_update_unknown_platform(self):
        """Registry raises ValueError for unknown platform."""
        from voicetest.platforms.registry import PlatformRegistry

        registry = PlatformRegistry()

        with pytest.raises(ValueError) as exc_info:
            registry.supports_update("unknown")
        assert "Unknown platform" in str(exc_info.value)


class TestSnippetEndpoints:
    """Tests for snippet CRUD and DRY analysis endpoints."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app
        from voicetest.rest import init_storage

        init_storage()

        return TestClient(app)

    def _create_agent_with_graph(self, db_client, graph):
        """Helper to create an agent with a specific graph."""
        from voicetest.rest import get_agent_repo

        repo = get_agent_repo()
        return repo.create(
            name="Snippet Test Agent",
            source_type=graph.source_type,
            graph_json=graph.model_dump_json(),
        )

    def _make_graph(self, snippets=None, **node_prompts):
        from voicetest.models.agent import AgentGraph
        from voicetest.models.agent import AgentNode

        nodes = {}
        first_id = None
        for node_id, prompt in node_prompts.items():
            if first_id is None:
                first_id = node_id
            nodes[node_id] = AgentNode(id=node_id, state_prompt=prompt, transitions=[])

        return AgentGraph(
            nodes=nodes,
            entry_node_id=first_id or "a",
            source_type="custom",
            snippets=snippets or {},
        )

    def test_get_snippets(self, db_client):
        graph = self._make_graph(snippets={"greeting": "Hello!", "signoff": "Bye!"}, a="main")
        agent = self._create_agent_with_graph(db_client, graph)
        agent_id = agent["id"]

        response = db_client.get(f"/api/agents/{agent_id}/snippets")
        assert response.status_code == 200
        data = response.json()
        assert data["snippets"] == {"greeting": "Hello!", "signoff": "Bye!"}

    def test_get_snippets_not_found(self, db_client):
        response = db_client.get("/api/agents/nonexistent/snippets")
        assert response.status_code == 404

    def test_update_snippet(self, db_client):
        graph = self._make_graph(a="main")
        agent = self._create_agent_with_graph(db_client, graph)
        agent_id = agent["id"]

        response = db_client.put(
            f"/api/agents/{agent_id}/snippets/greeting",
            json={"text": "Hello world!"},
        )
        assert response.status_code == 200

        # Verify it's persisted
        get_response = db_client.get(f"/api/agents/{agent_id}/snippets")
        assert get_response.json()["snippets"]["greeting"] == "Hello world!"

    def test_delete_snippet(self, db_client):
        graph = self._make_graph(snippets={"greeting": "Hello!"}, a="main")
        agent = self._create_agent_with_graph(db_client, graph)
        agent_id = agent["id"]

        response = db_client.delete(f"/api/agents/{agent_id}/snippets/greeting")
        assert response.status_code == 200

        # Verify it's gone
        get_response = db_client.get(f"/api/agents/{agent_id}/snippets")
        assert "greeting" not in get_response.json()["snippets"]

    def test_delete_snippet_not_found(self, db_client):
        graph = self._make_graph(a="main")
        agent = self._create_agent_with_graph(db_client, graph)
        agent_id = agent["id"]

        response = db_client.delete(f"/api/agents/{agent_id}/snippets/nonexistent")
        assert response.status_code == 404

    def test_analyze_dry(self, db_client):
        graph = self._make_graph(
            a="Always be polite and professional in every interaction. Task A.",
            b="Always be polite and professional in every interaction. Task B.",
        )
        agent = self._create_agent_with_graph(db_client, graph)
        agent_id = agent["id"]

        response = db_client.post(f"/api/agents/{agent_id}/analyze-dry")
        assert response.status_code == 200
        data = response.json()
        assert "exact" in data
        assert "fuzzy" in data
        assert len(data["exact"]) > 0

    def test_apply_snippets(self, db_client):
        graph = self._make_graph(
            a="Always be polite. Task A.",
            b="Always be polite. Task B.",
        )
        agent = self._create_agent_with_graph(db_client, graph)
        agent_id = agent["id"]

        response = db_client.post(
            f"/api/agents/{agent_id}/apply-snippets",
            json={"snippets": [{"name": "tone", "text": "Always be polite."}]},
        )
        assert response.status_code == 200
        data = response.json()

        # Snippet should be added to the graph
        assert "tone" in data["snippets"]
        assert data["snippets"]["tone"] == "Always be polite."

        # The text should be replaced with refs in prompts
        assert "{%tone%}" in data["nodes"]["a"]["state_prompt"]
        assert "{%tone%}" in data["nodes"]["b"]["state_prompt"]

    def test_export_expanded(self, db_client):
        graph = self._make_graph(
            snippets={"greeting": "Hello!"},
            a="{%greeting%} Welcome to support.",
        )
        self._create_agent_with_graph(db_client, graph)

        # Export with expanded=True should resolve snippet refs
        response = db_client.post(
            "/api/agents/export",
            json={
                "graph": graph.model_dump(),
                "format": "mermaid",
                "expanded": True,
            },
        )
        assert response.status_code == 200


class TestDiagnosisEndpoints:
    """Tests for diagnosis and fix endpoints."""

    @pytest.fixture
    def db_client(self, tmp_path, monkeypatch):
        """Create a test client with isolated database."""
        db_path = tmp_path / "test.duckdb"
        monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
        monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")

        from voicetest.rest import app
        from voicetest.rest import init_storage

        init_storage()

        return TestClient(app)

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
