"""Tests for agent CRUD, variables, test cases, gallery, and snippet endpoints."""

import pytest


class TestAgentsCRUD:
    """Tests for agent CRUD endpoints."""

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

    def test_list_gallery(self, db_client):
        response = db_client.get("/api/gallery")
        assert response.status_code == 200
        assert isinstance(response.json(), list)


class TestSnippetEndpoints:
    """Tests for snippet CRUD and DRY analysis endpoints."""

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
