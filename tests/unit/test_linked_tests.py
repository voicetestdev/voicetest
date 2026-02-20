"""Tests for linking/unlinking test files to agents via REST API."""

import json

from fastapi.testclient import TestClient
import pytest

from voicetest.rest import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
def agent(client):
    """Create a test agent and return its record."""
    from voicetest.rest import get_agent_repo

    repo = get_agent_repo()
    return repo.create(
        name="Test Agent",
        source_type="custom",
        graph_json=json.dumps(
            {
                "nodes": {
                    "main": {
                        "id": "main",
                        "state_prompt": "Hello",
                        "transitions": [],
                        "metadata": {},
                    }
                },
                "entry_node_id": "main",
                "source_type": "custom",
                "source_metadata": {},
            }
        ),
    )


@pytest.fixture
def test_file(tmp_path):
    """Create a temp JSON file with test cases."""
    tests = [
        {"name": "Greeting", "user_prompt": "Say hello", "type": "llm"},
        {"name": "Farewell", "user_prompt": "Say goodbye", "type": "llm"},
    ]
    path = tmp_path / "tests.json"
    path.write_text(json.dumps(tests))
    return path


@pytest.fixture
def second_test_file(tmp_path):
    """Create a second temp JSON file with different test cases."""
    tests = [
        {"name": "Billing", "user_prompt": "Check my bill", "type": "llm"},
    ]
    path = tmp_path / "tests2.json"
    path.write_text(json.dumps(tests))
    return path


class TestLinkTestFile:
    """Tests for POST /agents/{agent_id}/tests-paths."""

    def test_link_test_file(self, client, agent, test_file):
        response = client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(test_file)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == str(test_file)
        assert data["test_count"] == 2
        assert str(test_file) in data["tests_paths"]

    def test_link_file_not_found(self, client, agent):
        response = client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": "/nonexistent/tests.json"},
        )
        assert response.status_code == 400

    def test_link_file_invalid_json(self, client, agent, tmp_path):
        bad_file = tmp_path / "bad.json"
        bad_file.write_text("not json at all {{{")
        response = client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(bad_file)},
        )
        assert response.status_code == 400

    def test_link_file_not_array(self, client, agent, tmp_path):
        obj_file = tmp_path / "object.json"
        obj_file.write_text(json.dumps({"name": "not an array"}))
        response = client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(obj_file)},
        )
        assert response.status_code == 400

    def test_link_file_already_linked(self, client, agent, test_file):
        # Link once
        client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(test_file)},
        )
        # Link again
        response = client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(test_file)},
        )
        assert response.status_code == 409

    def test_link_agent_not_found(self, client, test_file):
        response = client.post(
            "/api/agents/nonexistent/tests-paths",
            json={"path": str(test_file)},
        )
        assert response.status_code == 404


class TestUnlinkTestFile:
    """Tests for DELETE /agents/{agent_id}/tests-paths."""

    def test_unlink_test_file(self, client, agent, test_file):
        # Link first
        client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(test_file)},
        )
        # Unlink
        response = client.delete(
            f"/api/agents/{agent['id']}/tests-paths",
            params={"path": str(test_file)},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["path"] == str(test_file)
        assert str(test_file) not in data["tests_paths"]

    def test_unlink_file_not_linked(self, client, agent):
        response = client.delete(
            f"/api/agents/{agent['id']}/tests-paths",
            params={"path": "/some/file.json"},
        )
        assert response.status_code == 404

    def test_unlink_agent_not_found(self, client):
        response = client.delete(
            "/api/agents/nonexistent/tests-paths",
            params={"path": "/some/file.json"},
        )
        assert response.status_code == 404


class TestLinkedTestsIntegration:
    """Integration tests for linked tests appearing in test lists."""

    def test_linked_tests_appear_in_list(self, client, agent, test_file):
        # Link file
        client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(test_file)},
        )
        # Fetch tests
        response = client.get(f"/api/agents/{agent['id']}/tests")
        assert response.status_code == 200
        tests = response.json()
        names = [t["name"] for t in tests]
        assert "Greeting" in names
        assert "Farewell" in names

    def test_link_multiple_files(self, client, agent, test_file, second_test_file):
        client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(test_file)},
        )
        client.post(
            f"/api/agents/{agent['id']}/tests-paths",
            json={"path": str(second_test_file)},
        )
        response = client.get(f"/api/agents/{agent['id']}/tests")
        assert response.status_code == 200
        tests = response.json()
        names = [t["name"] for t in tests]
        assert "Greeting" in names
        assert "Farewell" in names
        assert "Billing" in names
