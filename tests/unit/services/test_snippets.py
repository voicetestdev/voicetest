"""Tests for voicetest.services.snippets module."""

import pytest

from voicetest.models.agent import AgentGraph
from voicetest.services import get_agent_service
from voicetest.services import get_snippet_service


@pytest.fixture
def agent_id(tmp_path, monkeypatch):
    """Create a temp agent with snippets-friendly prompts and return its ID."""
    db_path = tmp_path / "test.duckdb"
    monkeypatch.setenv("VOICETEST_DB_PATH", str(db_path))
    monkeypatch.setenv("VOICETEST_LINKED_AGENTS", "")
    monkeypatch.chdir(tmp_path)

    config = {
        "source_type": "custom",
        "entry_node_id": "main",
        "nodes": {
            "main": {
                "id": "main",
                "state_prompt": "Always be polite and professional.",
                "transitions": [],
            },
            "billing": {
                "id": "billing",
                "state_prompt": "Always be polite and professional. Handle billing.",
                "transitions": [],
            },
        },
        "source_metadata": {
            "general_prompt": "You are a customer service agent. Always be polite and professional."
        },
    }
    agent_svc = get_agent_service()
    created = agent_svc.create_agent(name="Snippet Agent", config=config)
    return created["id"]


class TestGetSnippets:
    def test_initially_empty(self, agent_id):
        svc = get_snippet_service()
        assert svc.get_snippets(agent_id) == {}


class TestUpdateAllSnippets:
    def test_replaces_all(self, agent_id):
        svc = get_snippet_service()
        result = svc.update_all_snippets(agent_id, {"greeting": "Hello!", "closing": "Bye!"})
        assert result == {"greeting": "Hello!", "closing": "Bye!"}

    def test_roundtrip(self, agent_id):
        svc = get_snippet_service()
        svc.update_all_snippets(agent_id, {"a": "alpha"})
        assert svc.get_snippets(agent_id) == {"a": "alpha"}


class TestUpdateSnippet:
    def test_add_single(self, agent_id):
        svc = get_snippet_service()
        result = svc.update_snippet(agent_id, "polite", "Always be polite and professional.")
        assert "polite" in result

    def test_overwrite_single(self, agent_id):
        svc = get_snippet_service()
        svc.update_snippet(agent_id, "polite", "Be polite.")
        result = svc.update_snippet(agent_id, "polite", "Be very polite.")
        assert result["polite"] == "Be very polite."


class TestDeleteSnippet:
    def test_delete_existing(self, agent_id):
        svc = get_snippet_service()
        svc.update_snippet(agent_id, "temp", "Temporary snippet.")
        result = svc.delete_snippet(agent_id, "temp")
        assert "temp" not in result

    def test_delete_nonexistent_raises(self, agent_id):
        svc = get_snippet_service()
        with pytest.raises(ValueError, match="Snippet not found"):
            svc.delete_snippet(agent_id, "nonexistent")


class TestApplySnippets:
    def test_replaces_occurrences_in_prompts(self, agent_id):
        svc = get_snippet_service()
        graph = svc.apply_snippets(
            agent_id,
            [{"name": "polite", "text": "Always be polite and professional."}],
        )
        assert isinstance(graph, AgentGraph)
        # The snippet text should be replaced by the reference
        assert "{%polite%}" in graph.nodes["main"].state_prompt
        assert "{%polite%}" in graph.nodes["billing"].state_prompt
        assert "{%polite%}" in graph.source_metadata.get("general_prompt", "")
