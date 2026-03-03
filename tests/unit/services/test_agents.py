"""Tests for voicetest.services.agents module."""

import json

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.models.agent import MetricsConfig
from voicetest.services import get_agent_service


@pytest.fixture
def svc(tmp_path, monkeypatch):
    """AgentService backed by an isolated temp database."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)
    return get_agent_service()


@pytest.fixture
def custom_config_path(tmp_path):
    """Write a minimal custom agent JSON file and return its path."""
    data = {
        "source_type": "custom",
        "entry_node_id": "main",
        "nodes": {
            "main": {
                "id": "main",
                "state_prompt": "You are a helpful assistant.",
                "transitions": [],
                "tools": [],
                "metadata": {},
            }
        },
        "source_metadata": {"general_prompt": "Be helpful."},
    }
    path = tmp_path / "agent.json"
    path.write_text(json.dumps(data))
    return path


class TestImportAgent:
    @pytest.mark.asyncio
    async def test_import_from_dict(self, svc):
        config = {
            "source_type": "custom",
            "entry_node_id": "main",
            "nodes": {
                "main": {
                    "id": "main",
                    "state_prompt": "Hello.",
                    "transitions": [],
                }
            },
            "source_metadata": {},
        }
        graph = await svc.import_agent(config, source="agentgraph")
        assert isinstance(graph, AgentGraph)
        assert "main" in graph.nodes

    @pytest.mark.asyncio
    async def test_import_from_path(self, svc, custom_config_path):
        graph = await svc.import_agent(custom_config_path)
        assert isinstance(graph, AgentGraph)
        assert graph.source_type == "custom"


class TestCreateAgent:
    def test_create_from_path(self, svc, custom_config_path):
        agent = svc.create_agent(name="Test Agent", path=str(custom_config_path))
        assert agent["name"] == "Test Agent"
        assert "id" in agent

    def test_create_from_config(self, svc):
        config = {
            "source_type": "custom",
            "entry_node_id": "main",
            "nodes": {
                "main": {
                    "id": "main",
                    "state_prompt": "Hello.",
                    "transitions": [],
                }
            },
            "source_metadata": {},
        }
        agent = svc.create_agent(name="Config Agent", config=config)
        assert agent["name"] == "Config Agent"

    def test_create_requires_config_or_path(self, svc):
        with pytest.raises(ValueError, match="Either config or path"):
            svc.create_agent(name="Empty")


class TestListAndGetAgent:
    def test_list_empty(self, svc):
        assert svc.list_agents() == []

    def test_list_after_create(self, svc, custom_config_path):
        svc.create_agent(name="Agent1", path=str(custom_config_path))
        agents = svc.list_agents()
        assert len(agents) == 1
        assert agents[0]["name"] == "Agent1"

    def test_get_agent(self, svc, custom_config_path):
        created = svc.create_agent(name="Agent1", path=str(custom_config_path))
        agent = svc.get_agent(created["id"])
        assert agent is not None
        assert agent["name"] == "Agent1"

    def test_get_nonexistent(self, svc):
        assert svc.get_agent("nonexistent") is None


class TestUpdateAgent:
    def test_update_name(self, svc, custom_config_path):
        created = svc.create_agent(name="Old Name", path=str(custom_config_path))
        updated = svc.update_agent(created["id"], name="New Name")
        assert updated["name"] == "New Name"

    def test_update_nonexistent_raises(self, svc):
        with pytest.raises(ValueError, match="Agent not found"):
            svc.update_agent("nonexistent", name="Nope")


class TestDeleteAgent:
    def test_delete(self, svc, custom_config_path):
        created = svc.create_agent(name="Doomed", path=str(custom_config_path))
        svc.delete_agent(created["id"])
        assert svc.get_agent(created["id"]) is None


class TestLoadAndSaveGraph:
    def test_load_graph(self, svc, custom_config_path):
        created = svc.create_agent(name="Graph Agent", path=str(custom_config_path))
        agent, graph = svc.load_graph(created["id"])
        assert isinstance(graph, AgentGraph)
        assert agent["id"] == created["id"]

    def test_load_graph_nonexistent(self, svc):
        with pytest.raises(ValueError, match="Agent not found"):
            svc.load_graph("nonexistent")

    def test_save_and_reload(self, svc):
        config = {
            "source_type": "custom",
            "entry_node_id": "main",
            "nodes": {
                "main": {
                    "id": "main",
                    "state_prompt": "Original prompt.",
                    "transitions": [],
                }
            },
            "source_metadata": {},
        }
        created = svc.create_agent(name="Save Agent", config=config)
        agent, graph = svc.load_graph(created["id"])
        graph.nodes["main"].state_prompt = "Updated prompt."
        svc.save_graph(created["id"], agent, graph)

        _, reloaded = svc.load_graph(created["id"])
        assert reloaded.nodes["main"].state_prompt == "Updated prompt."


class TestGetVariables:
    def test_no_variables(self, svc):
        config = {
            "source_type": "custom",
            "entry_node_id": "main",
            "nodes": {
                "main": {
                    "id": "main",
                    "state_prompt": "No variables here.",
                    "transitions": [],
                }
            },
            "source_metadata": {"general_prompt": "Plain prompt."},
        }
        created = svc.create_agent(name="NoVars", config=config)
        variables = svc.get_variables(created["id"])
        assert variables == []


class TestMetricsConfig:
    def test_get_default_metrics_config(self, svc):
        config = {
            "source_type": "custom",
            "entry_node_id": "main",
            "nodes": {
                "main": {
                    "id": "main",
                    "state_prompt": "Hello.",
                    "transitions": [],
                }
            },
            "source_metadata": {},
        }
        created = svc.create_agent(name="Metrics Agent", config=config)
        mc = svc.get_metrics_config(created["id"])
        assert isinstance(mc, MetricsConfig)

    def test_update_metrics_config(self, svc):
        config = {
            "source_type": "custom",
            "entry_node_id": "main",
            "nodes": {
                "main": {
                    "id": "main",
                    "state_prompt": "Hello.",
                    "transitions": [],
                }
            },
            "source_metadata": {},
        }
        created = svc.create_agent(name="Metrics Agent", config=config)
        mc = MetricsConfig(threshold=0.9)
        result = svc.update_metrics_config(created["id"], mc)
        assert result.threshold == 0.9
