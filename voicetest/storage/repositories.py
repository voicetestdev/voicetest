"""Repository classes for CRUD operations on each entity."""

from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy.orm import Session

from voicetest.models.agent import AgentGraph, MetricsConfig
from voicetest.models.results import TestResult
from voicetest.models.test_case import TestCase
from voicetest.storage.linked_file import read_json, write_json
from voicetest.storage.models import Agent, Call, Result, Run
from voicetest.storage.models import TestCase as TestCaseModel


logger = logging.getLogger(__name__)


def _serialize_datetime(dt: datetime | None) -> str | None:
    """Convert datetime to ISO string."""
    return dt.isoformat() if dt else None


class AgentRepository:
    """CRUD operations for agents."""

    def __init__(self, session: Session):
        self.session = session

    def list_all(self, user_id: str | None = None) -> list[dict]:
        """List all agents, optionally filtered by user_id."""
        query = self.session.query(Agent)
        if user_id is not None:
            query = query.filter(Agent.user_id == user_id)
        agents = query.order_by(Agent.created_at.desc()).all()
        return [self._to_dict(a) for a in agents]

    def get(self, agent_id: str, user_id: str | None = None) -> dict | None:
        """Get agent by ID, optionally checking ownership."""
        agent = self.session.get(Agent, agent_id)
        if not agent:
            return None
        if user_id is not None and agent.user_id != user_id:
            return None
        return self._to_dict(agent)

    def create(
        self,
        name: str,
        source_type: str,
        source_path: str | None = None,
        tests_paths: list[str] | None = None,
        graph_json: str | None = None,
        metrics_config: MetricsConfig | None = None,
        user_id: str | None = None,
    ) -> dict:
        """Create a new agent."""
        agent_id = str(uuid4())
        now = datetime.now(UTC)

        agent = Agent(
            id=agent_id,
            user_id=user_id,
            name=name,
            source_type=source_type,
            source_path=source_path,
            tests_paths=tests_paths,
            graph_json=graph_json,
            metrics_config=None,
            created_at=now,
            updated_at=now,
        )
        self.session.add(agent)
        self.session.commit()

        if metrics_config:
            return self.update_metrics_config(agent_id, metrics_config)

        return self.get(agent_id)

    def update(
        self,
        agent_id: str,
        name: str | None = None,
        source_path: str | None = None,
        tests_paths: list[str] | None = None,
        graph_json: str | None = None,
    ) -> dict | None:
        """Update an agent."""
        agent = self.session.get(Agent, agent_id)
        if not agent:
            return None

        if name is not None:
            agent.name = name
        if source_path is not None:
            agent.source_path = source_path
        if tests_paths is not None:
            agent.tests_paths = tests_paths
        if graph_json is not None:
            agent.graph_json = graph_json

        agent.updated_at = datetime.now(UTC)
        self.session.commit()

        return self.get(agent_id)

    def update_metrics_config(
        self,
        agent_id: str,
        metrics_config: MetricsConfig,
    ) -> dict | None:
        """Update an agent's metrics configuration."""
        agent = self.session.get(Agent, agent_id)
        if not agent:
            return None

        agent.metrics_config = None
        agent.updated_at = datetime.now(UTC)
        self.session.commit()

        return self._get_with_metrics_json(agent_id, metrics_config)

    def _get_with_metrics_json(self, agent_id: str, metrics_config: MetricsConfig) -> dict:
        """Get agent dict with metrics_config as JSON string for API compatibility."""
        agent = self.session.get(Agent, agent_id)
        result = self._to_dict(agent)
        result["metrics_config"] = metrics_config.model_dump_json()
        agent.metrics_config = json.loads(metrics_config.model_dump_json())
        self.session.commit()
        return result

    def get_metrics_config(self, agent_id: str) -> MetricsConfig:
        """Get an agent's metrics configuration.

        Returns the stored configuration or a default if none exists.
        """
        agent = self.session.get(Agent, agent_id)
        if not agent:
            return MetricsConfig()

        if agent.metrics_config:
            return MetricsConfig.model_validate(agent.metrics_config)

        return MetricsConfig()

    def delete(self, agent_id: str) -> None:
        """Delete an agent."""
        agent = self.session.get(Agent, agent_id)
        if agent:
            self.session.delete(agent)
            self.session.commit()

    def load_graph(self, agent: dict) -> AgentGraph | Path:
        """Load the AgentGraph for an agent.

        For linked agents (source_path set), returns Path for caller to import.
        For imported agents (graph_json set), parses the stored JSON.

        Returns:
            AgentGraph if graph_json is stored, or Path for linked files.
        """
        if agent.get("graph_json"):
            return AgentGraph.model_validate_json(agent["graph_json"])

        if agent.get("source_path"):
            path = Path(agent["source_path"])
            if not path.exists():
                raise FileNotFoundError(f"Agent file not found: {path}")
            return path

        raise ValueError(f"Agent {agent['id']} has neither source_path nor graph_json")

    def _to_dict(self, agent: Agent) -> dict:
        """Convert Agent model to dictionary for API responses."""
        metrics_json = None
        if agent.metrics_config:
            metrics_json = json.dumps(agent.metrics_config)

        return {
            "id": agent.id,
            "user_id": agent.user_id,
            "name": agent.name,
            "source_type": agent.source_type,
            "source_path": agent.source_path,
            "tests_paths": agent.tests_paths,
            "graph_json": agent.graph_json,
            "metrics_config": metrics_json,
            "created_at": _serialize_datetime(agent.created_at),
            "updated_at": _serialize_datetime(agent.updated_at),
        }


class TestCaseRepository:
    """CRUD operations for test cases."""

    def __init__(self, session: Session):
        self.session = session

    def list_for_agent(self, agent_id: str) -> list[dict]:
        """List all test cases for an agent."""
        test_cases = (
            self.session.query(TestCaseModel)
            .filter(TestCaseModel.agent_id == agent_id)
            .order_by(TestCaseModel.created_at)
            .all()
        )
        return [self._to_dict(tc) for tc in test_cases]

    def get(self, test_id: str) -> dict | None:
        """Get test case by ID."""
        tc = self.session.get(TestCaseModel, test_id)
        return self._to_dict(tc) if tc else None

    def create(self, agent_id: str, test_case: TestCase) -> dict:
        """Create a new test case."""
        test_id = str(uuid4())
        now = datetime.now(UTC)

        tc = TestCaseModel(
            id=test_id,
            agent_id=agent_id,
            name=test_case.name,
            user_prompt=test_case.user_prompt,
            metrics=test_case.metrics,
            dynamic_variables=test_case.dynamic_variables,
            tool_mocks=test_case.tool_mocks,
            type=test_case.type,
            llm_model=test_case.llm_model,
            includes=test_case.includes,
            excludes=test_case.excludes,
            patterns=test_case.patterns,
            created_at=now,
            updated_at=now,
        )
        self.session.add(tc)
        self.session.commit()

        return self.get(test_id)

    def update(self, test_id: str, test_case: TestCase) -> dict | None:
        """Update a test case."""
        tc = self.session.get(TestCaseModel, test_id)
        if not tc:
            return None

        tc.name = test_case.name
        tc.user_prompt = test_case.user_prompt
        tc.metrics = test_case.metrics
        tc.dynamic_variables = test_case.dynamic_variables
        tc.tool_mocks = test_case.tool_mocks
        tc.type = test_case.type
        tc.llm_model = test_case.llm_model
        tc.includes = test_case.includes
        tc.excludes = test_case.excludes
        tc.patterns = test_case.patterns
        tc.updated_at = datetime.now(UTC)

        self.session.commit()

        return self.get(test_id)

    def delete(self, test_id: str) -> None:
        """Delete a test case."""
        tc = self.session.get(TestCaseModel, test_id)
        if tc:
            self.session.delete(tc)
            self.session.commit()

    def to_model(self, record: dict) -> TestCase:
        """Convert a database record to a TestCase model."""
        return TestCase(
            name=record["name"],
            user_prompt=record["user_prompt"],
            metrics=record["metrics"] if record["metrics"] else [],
            dynamic_variables=record["dynamic_variables"] if record["dynamic_variables"] else {},
            tool_mocks=record["tool_mocks"] if record["tool_mocks"] else [],
            type=record["type"] or "llm",
            llm_model=record["llm_model"],
            includes=record["includes"] if record.get("includes") else [],
            excludes=record["excludes"] if record.get("excludes") else [],
            patterns=record["patterns"] if record.get("patterns") else [],
        )

    def list_for_agent_with_linked(
        self, agent_id: str, tests_paths: list[str] | None
    ) -> list[dict]:
        """List all test cases for an agent, merging DB and file-based tests.

        File-based tests get deterministic IDs via uuid5(NAMESPACE_URL, "{path}:{name}")
        and include source_path and source_index fields.
        """
        db_tests = self.list_for_agent(agent_id)

        if not tests_paths:
            return db_tests

        linked_tests = []
        for path in tests_paths:
            try:
                entries = read_json(path)
            except (FileNotFoundError, json.JSONDecodeError):
                logger.warning("Skipping unreadable tests file: %s", path)
                continue

            if not isinstance(entries, list):
                logger.warning("Tests file is not a JSON array: %s", path)
                continue

            for index, entry in enumerate(entries):
                test_id = str(uuid5(NAMESPACE_URL, f"{path}:{entry.get('name', index)}"))
                linked_tests.append(
                    self._linked_entry_to_dict(entry, test_id, agent_id, path, index)
                )

        return db_tests + linked_tests

    def update_linked(
        self,
        test_id: str,
        test_case: TestCase,
        source_path: str,
        source_index: int,
    ) -> dict:
        """Update a test case in a linked JSON file by index."""
        entries = read_json(source_path)
        entries[source_index] = self._test_case_to_file_entry(test_case)
        write_json(source_path, entries)

        return self._linked_entry_to_dict(
            entries[source_index], test_id, "", source_path, source_index
        )

    def delete_linked(
        self,
        test_id: str,
        source_path: str,
        source_index: int,
    ) -> None:
        """Delete a test case from a linked JSON file by index."""
        entries = read_json(source_path)
        entries.pop(source_index)
        write_json(source_path, entries)

    def create_in_file(
        self,
        source_path: str,
        agent_id: str,
        test_case: TestCase,
    ) -> dict:
        """Append a test case to a linked JSON file."""
        try:
            entries = read_json(source_path)
        except FileNotFoundError:
            entries = []

        entry = self._test_case_to_file_entry(test_case)
        entries.append(entry)
        write_json(source_path, entries)

        source_index = len(entries) - 1
        test_id = str(uuid5(NAMESPACE_URL, f"{source_path}:{test_case.name}"))
        return self._linked_entry_to_dict(entry, test_id, agent_id, source_path, source_index)

    def _test_case_to_file_entry(self, test_case: TestCase) -> dict:
        """Convert a TestCase model to a file-storable dict."""
        entry = {
            "name": test_case.name,
            "user_prompt": test_case.user_prompt,
            "type": test_case.type,
        }
        if test_case.metrics:
            entry["metrics"] = test_case.metrics
        if test_case.dynamic_variables:
            entry["dynamic_variables"] = test_case.dynamic_variables
        if test_case.tool_mocks:
            entry["tool_mocks"] = test_case.tool_mocks
        if test_case.llm_model:
            entry["llm_model"] = test_case.llm_model
        if test_case.includes:
            entry["includes"] = test_case.includes
        if test_case.excludes:
            entry["excludes"] = test_case.excludes
        if test_case.patterns:
            entry["patterns"] = test_case.patterns
        return entry

    def _linked_entry_to_dict(
        self,
        entry: dict,
        test_id: str,
        agent_id: str,
        source_path: str,
        source_index: int,
    ) -> dict:
        """Convert a file-based test entry to the standard API dict format."""
        return {
            "id": test_id,
            "agent_id": agent_id,
            "name": entry.get("name", ""),
            "user_prompt": entry.get("user_prompt", ""),
            "metrics": entry.get("metrics"),
            "dynamic_variables": entry.get("dynamic_variables"),
            "tool_mocks": entry.get("tool_mocks"),
            "type": entry.get("type", "llm"),
            "llm_model": entry.get("llm_model"),
            "includes": entry.get("includes"),
            "excludes": entry.get("excludes"),
            "patterns": entry.get("patterns"),
            "created_at": None,
            "updated_at": None,
            "source_path": source_path,
            "source_index": source_index,
        }

    def _to_dict(self, tc: TestCaseModel) -> dict:
        """Convert TestCase model to dictionary for API responses."""
        return {
            "id": tc.id,
            "agent_id": tc.agent_id,
            "name": tc.name,
            "user_prompt": tc.user_prompt,
            "metrics": tc.metrics,
            "dynamic_variables": tc.dynamic_variables,
            "tool_mocks": tc.tool_mocks,
            "type": tc.type,
            "llm_model": tc.llm_model,
            "includes": tc.includes,
            "excludes": tc.excludes,
            "patterns": tc.patterns,
            "created_at": _serialize_datetime(tc.created_at),
            "updated_at": _serialize_datetime(tc.updated_at),
        }


class RunRepository:
    """CRUD operations for runs and results."""

    def __init__(self, session: Session):
        self.session = session

    def _serialize_result_data(self, result: TestResult) -> dict:
        """Serialize TestResult data for storage."""
        return {
            "transcript": [m.model_dump() for m in result.transcript],
            "metrics": (
                [m.model_dump() for m in result.metric_results] if result.metric_results else None
            ),
            "tools": (
                [t.model_dump() for t in result.tools_called] if result.tools_called else None
            ),
            "models": result.models_used.model_dump() if result.models_used else None,
        }

    def list_all(self, limit: int = 50, user_id: str | None = None) -> list[dict]:
        """List all runs, optionally filtered by user_id."""
        query = self.session.query(Run)
        if user_id is not None:
            query = query.filter(Run.user_id == user_id)
        runs = query.order_by(Run.started_at.desc()).limit(limit).all()
        return [self._run_to_dict(r) for r in runs]

    def list_for_agent(
        self, agent_id: str, limit: int = 50, user_id: str | None = None
    ) -> list[dict]:
        """List runs for a specific agent, optionally filtered by user_id."""
        query = self.session.query(Run).filter(Run.agent_id == agent_id)
        if user_id is not None:
            query = query.filter(Run.user_id == user_id)
        runs = query.order_by(Run.started_at.desc()).limit(limit).all()
        return [self._run_to_dict(r) for r in runs]

    def get_with_results(self, run_id: str, user_id: str | None = None) -> dict | None:
        """Get a run with all its results, optionally checking ownership."""
        run = self.session.get(Run, run_id)
        if not run:
            return None
        if user_id is not None and run.user_id != user_id:
            return None

        result = self._run_to_dict(run)
        result["results"] = [self._result_to_dict(r) for r in run.results]
        return result

    def create(self, agent_id: str, user_id: str | None = None) -> dict:
        """Create a new run."""
        run_id = str(uuid4())
        now = datetime.now(UTC)

        run = Run(
            id=run_id,
            user_id=user_id,
            agent_id=agent_id,
            started_at=now,
            completed_at=None,
        )
        self.session.add(run)
        self.session.commit()

        return {
            "id": run_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "started_at": now,
            "completed_at": None,
        }

    def add_result(self, run_id: str, test_case_id: str, result: TestResult) -> None:
        """Add a result to a run."""
        result_id = str(uuid4())
        now = datetime.now(UTC)
        data = self._serialize_result_data(result)

        db_result = Result(
            id=result_id,
            run_id=run_id,
            test_case_id=test_case_id,
            test_name=result.test_name,
            status=result.status,
            duration_ms=result.duration_ms,
            turn_count=result.turn_count,
            end_reason=result.end_reason,
            error_message=result.error_message,
            transcript_json=data["transcript"],
            metrics_json=data["metrics"],
            nodes_visited=result.nodes_visited,
            tools_called=data["tools"],
            models_used=data["models"],
            created_at=now,
        )
        self.session.add(db_result)
        self.session.commit()

    def create_pending_result(self, run_id: str, test_case_id: str, test_name: str) -> str:
        """Create a pending result for an in-progress test."""
        result_id = str(uuid4())
        now = datetime.now(UTC)

        db_result = Result(
            id=result_id,
            run_id=run_id,
            test_case_id=test_case_id,
            test_name=test_name,
            status="running",
            transcript_json=[],
            created_at=now,
        )
        self.session.add(db_result)
        self.session.commit()
        return result_id

    def update_transcript(self, result_id: str, transcript: list) -> None:
        """Update the transcript for an in-progress result."""
        result = self.session.get(Result, result_id)
        if result:
            result.transcript_json = [m.model_dump() for m in transcript]
            self.session.commit()

    def mark_result_error(self, result_id: str, error_message: str) -> None:
        """Mark a result as error with a message."""
        result = self.session.get(Result, result_id)
        if result:
            result.status = "error"
            result.error_message = error_message
            self.session.commit()

    def mark_result_cancelled(self, result_id: str) -> None:
        """Mark a result as cancelled before it started."""
        result = self.session.get(Result, result_id)
        if result:
            result.status = "cancelled"
            result.error_message = "Cancelled before starting"
            self.session.commit()

    def complete_result(self, result_id: str, result: TestResult) -> None:
        """Update a pending result with final data."""
        db_result = self.session.get(Result, result_id)
        if not db_result:
            return

        data = self._serialize_result_data(result)

        db_result.status = result.status
        db_result.duration_ms = result.duration_ms
        db_result.turn_count = result.turn_count
        db_result.end_reason = result.end_reason
        db_result.error_message = result.error_message
        db_result.transcript_json = data["transcript"]
        db_result.metrics_json = data["metrics"]
        db_result.nodes_visited = result.nodes_visited
        db_result.tools_called = data["tools"]
        db_result.models_used = data["models"]

        self.session.commit()

    def complete(self, run_id: str) -> None:
        """Mark a run as completed."""
        run = self.session.get(Run, run_id)
        if run:
            run.completed_at = datetime.now(UTC)
            self.session.commit()

    def delete(self, run_id: str) -> None:
        """Delete a run and all its results."""
        run = self.session.get(Run, run_id)
        if run:
            self.session.query(Result).filter(Result.run_id == run_id).delete(
                synchronize_session=False
            )
            self.session.commit()
            self.session.query(Run).filter(Run.id == run_id).delete(synchronize_session=False)
            self.session.commit()

    def _run_to_dict(self, run: Run) -> dict:
        """Convert Run model to dictionary."""
        return {
            "id": run.id,
            "user_id": run.user_id,
            "agent_id": run.agent_id,
            "started_at": _serialize_datetime(run.started_at),
            "completed_at": _serialize_datetime(run.completed_at),
        }

    def _result_to_dict(self, result: Result) -> dict:
        """Convert Result model to dictionary."""
        return {
            "id": result.id,
            "run_id": result.run_id,
            "test_case_id": result.test_case_id,
            "test_name": result.test_name,
            "status": result.status,
            "duration_ms": result.duration_ms,
            "turn_count": result.turn_count,
            "end_reason": result.end_reason,
            "error_message": result.error_message,
            "transcript_json": result.transcript_json,
            "metrics_json": result.metrics_json,
            "nodes_visited": result.nodes_visited,
            "tools_called": result.tools_called,
            "models_used": result.models_used,
            "created_at": _serialize_datetime(result.created_at),
        }


class CallRepository:
    """CRUD operations for live calls."""

    def __init__(self, session: Session):
        self.session = session

    def get(self, call_id: str) -> dict | None:
        """Get call by ID."""
        call = self.session.get(Call, call_id)
        return self._to_dict(call) if call else None

    def list_for_agent(self, agent_id: str, limit: int = 50) -> list[dict]:
        """List calls for a specific agent."""
        calls = (
            self.session.query(Call)
            .filter(Call.agent_id == agent_id)
            .order_by(Call.started_at.desc())
            .limit(limit)
            .all()
        )
        return [self._to_dict(c) for c in calls]

    def create(self, agent_id: str, room_name: str) -> dict:
        """Create a new call."""
        call_id = str(uuid4())
        now = datetime.now(UTC)

        call = Call(
            id=call_id,
            agent_id=agent_id,
            room_name=room_name,
            status="pending",
            transcript_json=[],
            started_at=now,
            ended_at=None,
        )
        self.session.add(call)
        self.session.commit()

        return self.get(call_id)

    def update_status(self, call_id: str, status: str) -> dict | None:
        """Update call status."""
        call = self.session.get(Call, call_id)
        if not call:
            return None

        call.status = status
        self.session.commit()
        return self.get(call_id)

    def update_transcript(self, call_id: str, transcript: list) -> None:
        """Update the transcript for a call."""
        call = self.session.get(Call, call_id)
        if call:
            call.transcript_json = transcript
            self.session.commit()

    def end_call(self, call_id: str) -> dict | None:
        """Mark a call as ended."""
        call = self.session.get(Call, call_id)
        if not call:
            return None

        call.status = "ended"
        call.ended_at = datetime.now(UTC)
        self.session.commit()
        return self.get(call_id)

    def delete(self, call_id: str) -> None:
        """Delete a call."""
        call = self.session.get(Call, call_id)
        if call:
            self.session.delete(call)
            self.session.commit()

    def _to_dict(self, call: Call) -> dict:
        """Convert Call model to dictionary."""
        return {
            "id": call.id,
            "agent_id": call.agent_id,
            "room_name": call.room_name,
            "status": call.status,
            "transcript_json": call.transcript_json,
            "started_at": _serialize_datetime(call.started_at),
            "ended_at": _serialize_datetime(call.ended_at),
        }
