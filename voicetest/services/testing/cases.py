"""Test case CRUD, linked file management, and export."""

import json
from pathlib import Path

from voicetest.exporters.test_cases import export_tests
from voicetest.models.test_case import TestCase
from voicetest.pathutil import resolve_file
from voicetest.pathutil import resolve_path
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import TestCaseRepository


class TestCaseService:
    """Manages test case CRUD, file linking, and export."""

    def __init__(
        self,
        test_case_repo: TestCaseRepository,
        agent_repo: AgentRepository,
    ):
        self._repo = test_case_repo
        self._agent_repo = agent_repo

    def list_tests(self, agent_id: str) -> list[dict]:
        """List all test cases for an agent, including file-based linked tests."""
        agent = self._agent_repo.get(agent_id)
        tests_paths = agent.get("tests_paths") if agent else None
        return self._repo.list_for_agent_with_linked(agent_id, tests_paths)

    def create_test(self, agent_id: str, test_case: TestCase) -> dict:
        """Create a test case for an agent.

        If the agent has linked test files, the test is appended to the first file.
        Otherwise it is stored in the database.
        """
        agent = self._agent_repo.get(agent_id)
        tests_paths = agent.get("tests_paths") if agent else None

        if tests_paths:
            return self._repo.create_in_file(tests_paths[0], agent_id, test_case)

        return self._repo.create(agent_id, test_case)

    def update_test(self, test_id: str, test_case: TestCase) -> dict:
        """Update a test case (DB or linked file).

        Raises:
            ValueError: If test case not found.
        """
        test = self._repo.get(test_id)
        if test:
            return self._repo.update(test_id, test_case)

        linked = self._find_linked_test(test_id)
        if linked:
            return self._repo.update_linked(
                test_id, test_case, linked["source_path"], linked["source_index"]
            )

        raise ValueError(f"Test case not found: {test_id}")

    def delete_test(self, test_id: str) -> None:
        """Delete a test case (DB or linked file).

        Raises:
            ValueError: If test case not found.
        """
        test = self._repo.get(test_id)
        if test:
            self._repo.delete(test_id)
            return

        linked = self._find_linked_test(test_id)
        if linked:
            self._repo.delete_linked(test_id, linked["source_path"], linked["source_index"])
            return

        raise ValueError(f"Test case not found: {test_id}")

    def link_test_file(self, agent_id: str, path: str) -> dict:
        """Link a JSON test file to an agent.

        The file must exist, contain valid JSON, and be a JSON array.

        Returns:
            Dict with path, test_count, and tests_paths.

        Raises:
            ValueError: If file is invalid or already linked.
            FileNotFoundError: If file does not exist.
        """
        resolved = resolve_file(path)
        resolved_str = str(resolved)

        content = json.loads(resolved.read_text())
        if not isinstance(content, list):
            raise ValueError("File must contain a JSON array")

        agent = self._agent_repo.get(agent_id)
        if not agent:
            raise FileNotFoundError(f"Agent not found: {agent_id}")
        current_paths = agent.get("tests_paths") or []
        if resolved_str in current_paths:
            raise ValueError("File already linked")

        updated_paths = current_paths + [resolved_str]
        self._agent_repo.update(agent_id, tests_paths=updated_paths)

        return {
            "path": resolved_str,
            "test_count": len(content),
            "tests_paths": updated_paths,
        }

    def unlink_test_file(self, agent_id: str, path: str) -> dict:
        """Unlink a test file from an agent.

        Returns:
            Dict with path and tests_paths.

        Raises:
            ValueError: If file is not linked.
        """
        resolved = str(resolve_path(path))
        agent = self._agent_repo.get(agent_id)
        if not agent:
            raise FileNotFoundError(f"Agent not found: {agent_id}")
        current_paths = agent.get("tests_paths") or []

        if resolved not in current_paths:
            raise ValueError("File not linked to this agent")

        updated_paths = [p for p in current_paths if p != resolved]
        self._agent_repo.update(agent_id, tests_paths=updated_paths)

        return {"path": resolved, "tests_paths": updated_paths}

    def export_tests(self, agent_id: str, test_ids: list[str] | None, format: str) -> list[dict]:
        """Export test cases for an agent to a specified format."""
        if test_ids:
            records = [self._repo.get(tid) for tid in test_ids if self._repo.get(tid)]
        else:
            records = self._repo.list_for_agent(agent_id)

        if not records:
            return []

        test_cases = [self._repo.to_model(r) for r in records]
        return export_tests(test_cases, format)

    def get_test(self, test_id: str) -> dict | None:
        """Get a single test case by ID (DB only)."""
        return self._repo.get(test_id)

    def find_linked_test(self, test_id: str) -> dict | None:
        """Search all agents' linked test files for a test with the given ID."""
        return self._find_linked_test(test_id)

    def to_model(self, record: dict) -> TestCase:
        """Convert a test record dict to a TestCase model."""
        return self._repo.to_model(record)

    def load_test_cases(self, tests_path: Path) -> list[TestCase]:
        """Load test cases from a JSON file."""
        data = json.loads(tests_path.read_text())
        return [TestCase.model_validate(tc) for tc in data]

    def _find_linked_test(self, test_id: str) -> dict | None:
        """Search all agents' linked test files for a test with the given ID."""
        for agent in self._agent_repo.list_all():
            tests_paths = agent.get("tests_paths")
            if not tests_paths:
                continue
            linked = self._repo.list_for_agent_with_linked(agent["id"], tests_paths)
            for t in linked:
                if t["id"] == test_id and t.get("source_path"):
                    return t
        return None
