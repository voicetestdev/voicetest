"""Tests for the call-transcript import REST endpoint."""

import json


def _create_agent(client, sample_retell_config) -> str:
    """Create an agent and return its id."""
    response = client.post(
        "/api/agents",
        json={"name": "Import Test Agent", "config": sample_retell_config},
    )
    return response.json()["id"]


class TestImportCallEndpoint:
    def test_import_single_call(self, db_client, sample_retell_config, retell_call):
        agent_id = _create_agent(db_client, sample_retell_config)
        payload = json.dumps(retell_call("call_001"))

        response = db_client.post(
            f"/api/agents/{agent_id}/import-call",
            files={"file": ("call.json", payload, "application/json")},
        )

        assert response.status_code == 200
        run = response.json()
        assert run["agent_id"] == agent_id
        assert run["completed_at"] is not None  # imports are marked complete immediately
        assert len(run["results"]) == 1
        result = run["results"][0]
        assert result["status"] == "imported"
        assert result["test_name"] == "call_001"
        assert result["test_case_id"] is None
        assert result["call_id"] is None
        # Transcript is stored on the result
        assert len(result["transcript_json"]) == 2

    def test_import_array_of_calls(self, db_client, sample_retell_config, retell_call):
        agent_id = _create_agent(db_client, sample_retell_config)
        payload = json.dumps([retell_call("call_a"), retell_call("call_b")])

        response = db_client.post(
            f"/api/agents/{agent_id}/import-call",
            files={"file": ("calls.json", payload, "application/json")},
        )

        assert response.status_code == 200
        run = response.json()
        assert len(run["results"]) == 2
        assert {r["test_name"] for r in run["results"]} == {"call_a", "call_b"}

    def test_import_webhook_envelope(self, db_client, sample_retell_config, retell_call):
        """Retell webhook payloads wrap the call object — adapter should handle it."""
        agent_id = _create_agent(db_client, sample_retell_config)
        payload = json.dumps({"event": "call_ended", "call": retell_call("call_wh")})

        response = db_client.post(
            f"/api/agents/{agent_id}/import-call",
            files={"file": ("webhook.json", payload, "application/json")},
        )

        assert response.status_code == 200
        run = response.json()
        assert len(run["results"]) == 1
        assert run["results"][0]["test_name"] == "call_wh"

    def test_unknown_agent_returns_404(self, db_client, retell_call):
        payload = json.dumps(retell_call())
        response = db_client.post(
            "/api/agents/nonexistent/import-call",
            files={"file": ("call.json", payload, "application/json")},
        )

        assert response.status_code == 404
        assert "Agent not found" in response.json()["detail"]

    def test_unsupported_format_returns_400(self, db_client, sample_retell_config, retell_call):
        agent_id = _create_agent(db_client, sample_retell_config)
        payload = json.dumps(retell_call())

        response = db_client.post(
            f"/api/agents/{agent_id}/import-call?format=vapi",
            files={"file": ("call.json", payload, "application/json")},
        )

        assert response.status_code == 400
        assert "Unsupported format" in response.json()["detail"]

    def test_invalid_json_returns_400(self, db_client, sample_retell_config):
        agent_id = _create_agent(db_client, sample_retell_config)

        response = db_client.post(
            f"/api/agents/{agent_id}/import-call",
            files={"file": ("garbage.json", "not json", "application/json")},
        )

        assert response.status_code == 400
        assert "Not valid JSON" in response.json()["detail"]

    def test_payload_with_no_calls_returns_400(self, db_client, sample_retell_config):
        agent_id = _create_agent(db_client, sample_retell_config)
        payload = json.dumps({"unrelated": "payload"})

        response = db_client.post(
            f"/api/agents/{agent_id}/import-call",
            files={"file": ("empty.json", payload, "application/json")},
        )

        assert response.status_code == 400
        assert "No Retell call objects" in response.json()["detail"]


class TestReplayEndpoint:
    def test_replay_unknown_source_returns_404(self, db_client):
        response = db_client.post("/api/runs/nonexistent/replay")
        assert response.status_code == 404
        assert "Source run not found" in response.json()["detail"]

    def test_replay_source_with_no_results_returns_400(self, db_client, sample_retell_config):
        """An empty source run can't be replayed — service should reject."""
        from voicetest.services import get_run_service

        agent_id = _create_agent(db_client, sample_retell_config)
        # Create an empty run via the service (no results)
        empty_run = get_run_service().create_run(agent_id)

        response = db_client.post(f"/api/runs/{empty_run['id']}/replay")
        assert response.status_code == 400
        assert "no results to replay" in response.json()["detail"]

    def test_replay_drives_runner_against_current_graph(
        self, db_client, sample_retell_config, retell_call, stub_conversation_runner
    ):
        """End-to-end: import a call, replay it, verify a new Run is produced
        whose Results were driven by ConversationRunner against the agent's
        current graph. The stub_conversation_runner fixture replaces the real
        runner so we don't need LLMs."""
        agent_id = _create_agent(db_client, sample_retell_config)
        import_response = db_client.post(
            f"/api/agents/{agent_id}/import-call",
            files={"file": ("call.json", json.dumps(retell_call()), "application/json")},
        )
        source_run_id = import_response.json()["id"]

        # Replay it
        response = db_client.post(f"/api/runs/{source_run_id}/replay")

        assert response.status_code == 200, response.text
        replay = response.json()
        assert replay["agent_id"] == agent_id
        assert replay["completed_at"] is not None
        assert len(replay["results"]) == 1
        result = replay["results"][0]
        assert result["test_name"].startswith("Replay of ")
        assert result["status"] == "pass"
        # The replay's transcript came from the runner (user turns from source,
        # agent turns from the stub).
        assert len(result["transcript_json"]) > 0
        # The stub captured one simulator invocation
        assert len(stub_conversation_runner) == 1
