"""Tests for PUT /agents/{agent_id}/prompts endpoint."""

import json
from pathlib import Path
import shutil
import tempfile

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


def _create_stored_agent(client, graph_dict: dict, name: str = "Test Agent") -> str:
    """Create an agent in the DB and return its ID."""
    response = client.post(
        "/api/agents",
        json={"name": name, "config": graph_dict},
    )
    assert response.status_code == 200
    return response.json()["id"]


def _create_linked_agent(
    client, fixture_path: Path, name: str = "Linked Agent"
) -> tuple[str, Path]:
    """Copy a fixture to a temp file and create a linked agent pointing to it.

    Returns (agent_id, temp_file_path). Caller must clean up the temp file.
    """
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    shutil.copy2(fixture_path, tmp_path)

    response = client.post(
        "/api/agents",
        json={"name": name, "path": str(tmp_path)},
    )
    assert response.status_code == 200
    return response.json()["id"], tmp_path


class TestUpdateGeneralPrompt:
    """Tests for updating general_prompt via PUT /agents/{agent_id}/prompts."""

    def test_update_general_prompt_stored_agent(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        response = client.put(
            f"/api/agents/{agent_id}/prompts",
            json={"node_id": None, "prompt_text": "You are a friendly bot."},
        )
        assert response.status_code == 200

        graph = response.json()
        assert graph["source_metadata"]["general_prompt"] == "You are a friendly bot."

    def test_update_general_prompt_persists(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        client.put(
            f"/api/agents/{agent_id}/prompts",
            json={"node_id": None, "prompt_text": "Persisted prompt"},
        )

        # Reload graph and verify persistence
        response = client.get(f"/api/agents/{agent_id}/graph")
        assert response.status_code == 200
        graph = response.json()
        assert graph["source_metadata"]["general_prompt"] == "Persisted prompt"


class TestUpdateNodePrompt:
    """Tests for updating node state_prompt via PUT /agents/{agent_id}/prompts."""

    def test_update_node_prompt_stored_agent(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        # Get the graph to find a valid node ID
        graph_resp = client.get(f"/api/agents/{agent_id}/graph")
        graph = graph_resp.json()
        node_id = list(graph["nodes"].keys())[0]

        response = client.put(
            f"/api/agents/{agent_id}/prompts",
            json={"node_id": node_id, "prompt_text": "Updated node prompt."},
        )
        assert response.status_code == 200

        result_graph = response.json()
        assert result_graph["nodes"][node_id]["state_prompt"] == "Updated node prompt."

    def test_update_node_prompt_persists(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        graph_resp = client.get(f"/api/agents/{agent_id}/graph")
        graph = graph_resp.json()
        node_id = list(graph["nodes"].keys())[0]

        client.put(
            f"/api/agents/{agent_id}/prompts",
            json={"node_id": node_id, "prompt_text": "Persisted node prompt."},
        )

        response = client.get(f"/api/agents/{agent_id}/graph")
        assert response.status_code == 200
        result_graph = response.json()
        assert result_graph["nodes"][node_id]["state_prompt"] == "Persisted node prompt."


class TestUpdateTransitionCondition:
    """Tests for updating transition conditions via PUT /agents/{agent_id}/prompts."""

    def test_update_transition_condition(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        graph_resp = client.get(f"/api/agents/{agent_id}/graph")
        graph = graph_resp.json()

        # Find a node with transitions
        source_node_id = None
        target_node_id = None
        for nid, node in graph["nodes"].items():
            if node["transitions"]:
                source_node_id = nid
                target_node_id = node["transitions"][0]["target_node_id"]
                break
        assert source_node_id is not None, "No node with transitions found"

        response = client.put(
            f"/api/agents/{agent_id}/prompts",
            json={
                "node_id": source_node_id,
                "prompt_text": "Customer asks about refills",
                "transition_target_id": target_node_id,
            },
        )
        assert response.status_code == 200

        result = response.json()
        transitions = result["nodes"][source_node_id]["transitions"]
        matching = [t for t in transitions if t["target_node_id"] == target_node_id]
        assert len(matching) == 1
        assert matching[0]["condition"]["value"] == "Customer asks about refills"

    def test_update_transition_condition_persists(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        graph_resp = client.get(f"/api/agents/{agent_id}/graph")
        graph = graph_resp.json()

        source_node_id = None
        target_node_id = None
        for nid, node in graph["nodes"].items():
            if node["transitions"]:
                source_node_id = nid
                target_node_id = node["transitions"][0]["target_node_id"]
                break

        client.put(
            f"/api/agents/{agent_id}/prompts",
            json={
                "node_id": source_node_id,
                "prompt_text": "Persisted condition",
                "transition_target_id": target_node_id,
            },
        )

        response = client.get(f"/api/agents/{agent_id}/graph")
        result = response.json()
        transitions = result["nodes"][source_node_id]["transitions"]
        matching = [t for t in transitions if t["target_node_id"] == target_node_id]
        assert matching[0]["condition"]["value"] == "Persisted condition"

    def test_update_transition_target_not_found(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        graph_resp = client.get(f"/api/agents/{agent_id}/graph")
        graph = graph_resp.json()
        node_id = list(graph["nodes"].keys())[0]

        response = client.put(
            f"/api/agents/{agent_id}/prompts",
            json={
                "node_id": node_id,
                "prompt_text": "test",
                "transition_target_id": "nonexistent_target",
            },
        )
        assert response.status_code == 404


class TestUpdatePromptErrors:
    """Tests for error cases in prompt update."""

    def test_update_prompt_agent_not_found(self, client):
        response = client.put(
            "/api/agents/nonexistent-id/prompts",
            json={"node_id": None, "prompt_text": "test"},
        )
        assert response.status_code == 404

    def test_update_prompt_node_not_found(self, client, sample_retell_llm_config):
        agent_id = _create_stored_agent(client, sample_retell_llm_config)

        response = client.put(
            f"/api/agents/{agent_id}/prompts",
            json={"node_id": "nonexistent_node", "prompt_text": "test"},
        )
        assert response.status_code == 404


class TestLinkedFileWriteBack:
    """Tests for writing prompt changes back to linked files on disk."""

    def test_general_prompt_writes_to_file(self, client, sample_retell_llm_config_path):
        agent_id, tmp_path = _create_linked_agent(client, sample_retell_llm_config_path)
        try:
            response = client.put(
                f"/api/agents/{agent_id}/prompts",
                json={"node_id": None, "prompt_text": "Written to file prompt"},
            )
            assert response.status_code == 200

            # Read the file directly and verify the prompt was written
            raw = json.loads(tmp_path.read_text())
            assert raw["general_prompt"] == "Written to file prompt"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_node_prompt_writes_to_file(self, client, sample_retell_llm_config_path):
        agent_id, tmp_path = _create_linked_agent(client, sample_retell_llm_config_path)
        try:
            # Get a node ID from the graph
            graph_resp = client.get(f"/api/agents/{agent_id}/graph")
            graph = graph_resp.json()
            node_id = list(graph["nodes"].keys())[0]

            response = client.put(
                f"/api/agents/{agent_id}/prompts",
                json={"node_id": node_id, "prompt_text": "Written to file node prompt"},
            )
            assert response.status_code == 200

            # Read the file and find the state with matching name
            raw = json.loads(tmp_path.read_text())
            matching_states = [s for s in raw["states"] if s["name"] == node_id]
            assert len(matching_states) == 1
            assert matching_states[0]["state_prompt"] == "Written to file node prompt"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_transition_writes_to_file(self, client, sample_retell_llm_config_path):
        agent_id, tmp_path = _create_linked_agent(client, sample_retell_llm_config_path)
        try:
            graph_resp = client.get(f"/api/agents/{agent_id}/graph")
            graph = graph_resp.json()

            # Find a node with transitions
            source_node_id = None
            target_node_id = None
            for nid, node in graph["nodes"].items():
                if node["transitions"]:
                    source_node_id = nid
                    target_node_id = node["transitions"][0]["target_node_id"]
                    break

            response = client.put(
                f"/api/agents/{agent_id}/prompts",
                json={
                    "node_id": source_node_id,
                    "prompt_text": "Written to file transition",
                    "transition_target_id": target_node_id,
                },
            )
            assert response.status_code == 200

            # Read the file and check the edge description
            raw = json.loads(tmp_path.read_text())
            matching_states = [s for s in raw["states"] if s["name"] == source_node_id]
            assert len(matching_states) == 1
            matching_edges = [
                e
                for e in matching_states[0]["edges"]
                if e["destination_state_name"] == target_node_id
            ]
            assert len(matching_edges) == 1
            assert matching_edges[0]["description"] == "Written to file transition"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_file_round_trip_preserves_structure(self, client, sample_retell_llm_config_path):
        """Verify that writing back to a linked file preserves the overall JSON structure."""
        agent_id, tmp_path = _create_linked_agent(client, sample_retell_llm_config_path)
        try:
            original = json.loads(sample_retell_llm_config_path.read_text())

            # Make a small change
            client.put(
                f"/api/agents/{agent_id}/prompts",
                json={"node_id": None, "prompt_text": "Slightly changed"},
            )

            written = json.loads(tmp_path.read_text())

            # Core keys that survive the import→export round-trip should be present
            for key in ("llm_id", "model", "begin_message", "general_prompt", "states"):
                assert key in written, f"Missing key: {key}"

            # States count should be the same
            assert len(original["states"]) == len(written["states"])
            # Model, llm_id, begin_message should be unchanged
            assert written["model"] == original["model"]
            assert written["llm_id"] == original["llm_id"]
            assert written["begin_message"] == original["begin_message"]
            # The general_prompt should reflect our update
            assert written["general_prompt"] == "Slightly changed"
        finally:
            tmp_path.unlink(missing_ok=True)

    def test_read_only_file_returns_400(self, client, sample_retell_llm_config_path):
        """Verify that a read-only linked file produces a clear error."""
        agent_id, tmp_path = _create_linked_agent(client, sample_retell_llm_config_path)
        try:
            # Make the file read-only
            tmp_path.chmod(0o444)

            response = client.put(
                f"/api/agents/{agent_id}/prompts",
                json={"node_id": None, "prompt_text": "Should fail"},
            )
            assert response.status_code == 400
            assert "Cannot write" in response.json()["detail"]
        finally:
            # Restore write permission so cleanup works
            tmp_path.chmod(0o644)
            tmp_path.unlink(missing_ok=True)
