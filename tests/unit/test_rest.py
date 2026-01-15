"""Tests for voicetest REST API."""

import pytest
from fastapi.testclient import TestClient

from voicetest.rest import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestHealthEndpoint:
    """Tests for health check endpoint."""

    def test_health_returns_ok(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}


class TestImportersEndpoint:
    """Tests for importers endpoint."""

    def test_list_importers(self, client):
        response = client.get("/importers")
        assert response.status_code == 200

        importers = response.json()
        assert isinstance(importers, list)
        assert len(importers) >= 2  # retell and custom

        source_types = [imp["source_type"] for imp in importers]
        assert "retell" in source_types
        assert "custom" in source_types

    def test_importer_has_required_fields(self, client):
        response = client.get("/importers")
        importers = response.json()

        for imp in importers:
            assert "source_type" in imp
            assert "description" in imp
            assert "file_patterns" in imp


class TestImportEndpoint:
    """Tests for agent import endpoint."""

    def test_import_retell_config(self, client, sample_retell_config):
        response = client.post(
            "/agents/import",
            json={"config": sample_retell_config}
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["source_type"] == "retell"
        assert graph["entry_node_id"] == "greeting"
        assert len(graph["nodes"]) == 4

    def test_import_with_explicit_source(self, client, sample_retell_config):
        response = client.post(
            "/agents/import",
            json={"config": sample_retell_config, "source": "retell"}
        )
        assert response.status_code == 200
        assert response.json()["source_type"] == "retell"

    def test_import_unknown_source_returns_400(self, client):
        response = client.post(
            "/agents/import",
            json={"config": {}, "source": "nonexistent"}
        )
        assert response.status_code == 400

    def test_import_undetectable_config_returns_400(self, client):
        response = client.post(
            "/agents/import",
            json={"config": {"random": "data"}}
        )
        assert response.status_code == 400


class TestExportEndpoint:
    """Tests for agent export endpoint."""

    def test_export_mermaid(self, client, sample_retell_config):
        # First import
        import_response = client.post(
            "/agents/import",
            json={"config": sample_retell_config}
        )
        graph = import_response.json()

        # Then export
        response = client.post(
            "/agents/export",
            json={"graph": graph, "format": "mermaid"}
        )
        assert response.status_code == 200

        result = response.json()
        assert result["format"] == "mermaid"
        assert "flowchart" in result["content"].lower()
        assert "greeting" in result["content"]

    def test_export_livekit(self, client, sample_retell_config):
        import_response = client.post(
            "/agents/import",
            json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = client.post(
            "/agents/export",
            json={"graph": graph, "format": "livekit"}
        )
        assert response.status_code == 200

        result = response.json()
        assert "class Agent_greeting" in result["content"]

    def test_export_unknown_format_returns_400(self, client, sample_retell_config):
        import_response = client.post(
            "/agents/import",
            json={"config": sample_retell_config}
        )
        graph = import_response.json()

        response = client.post(
            "/agents/export",
            json={"graph": graph, "format": "unknown"}
        )
        assert response.status_code == 400


class TestRunEndpoints:
    """Tests for test run endpoints."""

    def test_run_single_test(self, client, sample_retell_config):
        # Import agent
        import_response = client.post(
            "/agents/import",
            json={"config": sample_retell_config}
        )
        graph = import_response.json()

        # Create test case (Retell format)
        test_case = {
            "name": "API test",
            "user_prompt": "When asked, say Test. Say hello.",
            "metrics": ["Agent responded."],
        }

        # Run test (will use mock mode internally due to test environment)
        response = client.post(
            "/runs/single",
            json={"graph": graph, "test_case": test_case}
        )

        # Should succeed even if test itself fails (it returns a result)
        assert response.status_code == 200
        result = response.json()
        assert result["test_id"] == "API test"
        assert result["status"] in ("pass", "fail", "error")

    def test_run_multiple_tests(self, client, sample_retell_config):
        import_response = client.post(
            "/agents/import",
            json={"config": sample_retell_config}
        )
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
            }
        ]

        response = client.post(
            "/runs",
            json={"graph": graph, "test_cases": test_cases}
        )
        assert response.status_code == 200

        run = response.json()
        assert "run_id" in run
        assert len(run["results"]) == 2


class TestEvaluateEndpoint:
    """Tests for transcript evaluation endpoint."""

    def test_evaluate_transcript(self, client):
        from unittest.mock import patch

        from voicetest.models.results import MetricResult

        async def mock_evaluate_with_llm(self, transcript, criterion):
            return MetricResult(
                metric=criterion,
                passed=True,
                reasoning=f"Mock evaluation for: {criterion}",
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
                "/evaluate",
                json={
                    "transcript": transcript,
                    "metrics": ["Agent greeted user", "Agent offered help"]
                }
            )

        assert response.status_code == 200
        results = response.json()
        assert len(results) == 2
        assert results[0]["passed"] is True
        assert results[1]["passed"] is True


class TestSettingsEndpoint:
    """Tests for settings endpoints."""

    def test_get_settings(self, client, tmp_path, monkeypatch):
        # Use temp directory so we don't pollute the real settings
        monkeypatch.chdir(tmp_path)

        response = client.get("/settings")

        assert response.status_code == 200
        settings = response.json()
        assert "models" in settings
        assert "run" in settings
        assert settings["models"]["agent"] == "openai/gpt-4o-mini"

    def test_update_settings(self, client, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)

        new_settings = {
            "models": {
                "agent": "anthropic/claude-3-haiku",
                "simulator": "openai/gpt-4o-mini",
                "judge": "openai/gpt-4o-mini",
            },
            "run": {
                "max_turns": 10,
                "verbose": True,
            }
        }

        response = client.put("/settings", json=new_settings)

        assert response.status_code == 200
        result = response.json()
        assert result["models"]["agent"] == "anthropic/claude-3-haiku"
        assert result["run"]["max_turns"] == 10

        # Verify it persisted
        get_response = client.get("/settings")
        assert get_response.json()["models"]["agent"] == "anthropic/claude-3-haiku"
