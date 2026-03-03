"""Tests for voicetest.services.testing.cases module."""

import json

import pytest

from voicetest.models.test_case import TestCase
from voicetest.services import get_agent_service
from voicetest.services import get_test_case_service


@pytest.fixture
def setup(tmp_path, monkeypatch):
    """Create agent + test case service with isolated DB. Returns (agent_id, svc)."""
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
                "state_prompt": "Hello.",
                "transitions": [],
            }
        },
        "source_metadata": {},
    }
    agent_svc = get_agent_service()
    created = agent_svc.create_agent(name="Test Agent", config=config)
    svc = get_test_case_service()
    return created["id"], svc


class TestCreateAndGetTest:
    def test_create_returns_record(self, setup):
        agent_id, svc = setup
        tc = TestCase(name="greeting_test", user_prompt="Hello", metrics=["Was it polite?"])
        record = svc.create_test(agent_id, tc)
        assert "id" in record
        assert record["name"] == "greeting_test"

    def test_get_test(self, setup):
        agent_id, svc = setup
        tc = TestCase(name="greeting_test", user_prompt="Hello", metrics=["polite?"])
        created = svc.create_test(agent_id, tc)
        fetched = svc.get_test(created["id"])
        assert fetched is not None
        assert fetched["id"] == created["id"]

    def test_get_nonexistent(self, setup):
        _, svc = setup
        assert svc.get_test("nonexistent") is None


class TestListTests:
    def test_empty(self, setup):
        agent_id, svc = setup
        assert svc.list_tests(agent_id) == []

    def test_list_after_create(self, setup):
        agent_id, svc = setup
        tc = TestCase(name="test1", user_prompt="Help", metrics=["helpful?"])
        svc.create_test(agent_id, tc)
        tests = svc.list_tests(agent_id)
        assert len(tests) == 1


class TestUpdateTest:
    def test_update(self, setup):
        agent_id, svc = setup
        tc = TestCase(name="old_name", user_prompt="Help", metrics=["helpful?"])
        created = svc.create_test(agent_id, tc)
        updated_tc = TestCase(name="new_name", user_prompt="Help me", metrics=["helpful?"])
        updated = svc.update_test(created["id"], updated_tc)
        assert updated["name"] == "new_name"

    def test_update_nonexistent_raises(self, setup):
        _, svc = setup
        tc = TestCase(name="x", user_prompt="x", metrics=["x"])
        with pytest.raises(ValueError, match="Test case not found"):
            svc.update_test("nonexistent", tc)


class TestDeleteTest:
    def test_delete(self, setup):
        agent_id, svc = setup
        tc = TestCase(name="doomed", user_prompt="Bye", metrics=["polite?"])
        created = svc.create_test(agent_id, tc)
        svc.delete_test(created["id"])
        assert svc.get_test(created["id"]) is None

    def test_delete_nonexistent_raises(self, setup):
        _, svc = setup
        with pytest.raises(ValueError, match="Test case not found"):
            svc.delete_test("nonexistent")


class TestToModel:
    def test_converts_record(self, setup):
        agent_id, svc = setup
        tc = TestCase(name="conv_test", user_prompt="Hello", metrics=["polite?"])
        created = svc.create_test(agent_id, tc)
        record = svc.get_test(created["id"])
        model = svc.to_model(record)
        assert isinstance(model, TestCase)
        assert model.name == "conv_test"


class TestLoadTestCases:
    def test_load_from_file(self, setup, tmp_path):
        _, svc = setup
        tests_data = [
            {"name": "file_test", "user_prompt": "Hi", "metrics": ["greeting?"]},
        ]
        tests_path = tmp_path / "tests.json"
        tests_path.write_text(json.dumps(tests_data))
        cases = svc.load_test_cases(tests_path)
        assert len(cases) == 1
        assert isinstance(cases[0], TestCase)
        assert cases[0].name == "file_test"


class TestLinkTestFile:
    def test_link(self, setup, tmp_path):
        agent_id, svc = setup
        tests_data = [
            {"name": "linked_test", "user_prompt": "Hi", "metrics": ["greeting?"]},
        ]
        tests_path = tmp_path / "linked_tests.json"
        tests_path.write_text(json.dumps(tests_data))
        result = svc.link_test_file(agent_id, str(tests_path))
        assert result["test_count"] == 1
        assert str(tests_path) in result["tests_paths"]

    def test_link_non_array_raises(self, setup, tmp_path):
        agent_id, svc = setup
        bad_file = tmp_path / "bad.json"
        bad_file.write_text(json.dumps({"not": "an array"}))
        with pytest.raises(ValueError, match="JSON array"):
            svc.link_test_file(agent_id, str(bad_file))

    def test_link_duplicate_raises(self, setup, tmp_path):
        agent_id, svc = setup
        tests_path = tmp_path / "dup.json"
        tests_path.write_text(json.dumps([]))
        svc.link_test_file(agent_id, str(tests_path))
        with pytest.raises(ValueError, match="already linked"):
            svc.link_test_file(agent_id, str(tests_path))


class TestUnlinkTestFile:
    def test_unlink(self, setup, tmp_path):
        agent_id, svc = setup
        tests_path = tmp_path / "unlink_tests.json"
        tests_path.write_text(json.dumps([]))
        svc.link_test_file(agent_id, str(tests_path))
        result = svc.unlink_test_file(agent_id, str(tests_path))
        assert str(tests_path) not in result["tests_paths"]

    def test_unlink_not_linked_raises(self, setup, tmp_path):
        agent_id, svc = setup
        with pytest.raises(ValueError, match="not linked"):
            svc.unlink_test_file(agent_id, str(tmp_path / "nope.json"))
