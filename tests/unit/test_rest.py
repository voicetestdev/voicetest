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
        assert "class Agent_greeting" in result["content"]

    def test_livekit_roundtrip_preserves_structure(self, client, sample_livekit_agent_code):
        """Import then export LiveKit agent preserves node structure."""
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


class TestUpdateMetadataEndpoint:
    """Tests for PUT /agents/{id}/metadata endpoint."""

    def test_update_metadata_merges_updates(self, db_client, sample_retell_config):
        from voicetest.rest import get_agent_repo

        repo = get_agent_repo()

        from voicetest.importers.retell import RetellImporter

        importer = RetellImporter()
        graph = importer.import_agent(sample_retell_config)
        agent = repo.create(
            name="Meta Agent",
            source_type="retell",
            graph_json=graph.model_dump_json(),
        )
        agent_id = agent["id"]

        response = db_client.put(
            f"/api/agents/{agent_id}/metadata",
            json={"updates": {"custom_field": "custom_value", "version": 99}},
        )
        assert response.status_code == 200

        result = response.json()
        assert result["source_metadata"]["custom_field"] == "custom_value"
        assert result["source_metadata"]["version"] == 99
        # Original metadata should still be present
        assert "conversation_flow_id" in result["source_metadata"]

    def test_update_metadata_returns_404_for_missing_agent(self, db_client):
        response = db_client.put(
            "/api/agents/nonexistent/metadata",
            json={"updates": {"key": "value"}},
        )
        assert response.status_code == 404
