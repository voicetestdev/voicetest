"""REST API for voicetest.

Transport adapter over the service layer. All business logic lives in
voicetest.services — this module handles HTTP/WebSocket concerns.

Run with: voicetest serve
Or: uvicorn voicetest.rest:app --reload
"""

import asyncio
from datetime import UTC
from datetime import datetime
import json
import logging
import os
from pathlib import Path
import tempfile
from typing import Any

from fastapi import APIRouter
from fastapi import BackgroundTasks
from fastapi import FastAPI
from fastapi import Header
from fastapi import HTTPException
from fastapi import Request
from fastapi import Response
from fastapi import UploadFile
from fastapi import WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from voicetest.calls import get_call_manager
from voicetest.chat import get_chat_manager
from voicetest.container import get_container
from voicetest.container import get_session
from voicetest.demo import get_demo_agent
from voicetest.demo import get_demo_tests
from voicetest.executor import RunJob
from voicetest.executor import get_executor_factory
from voicetest.models.agent import AgentGraph
from voicetest.models.agent import GlobalMetric
from voicetest.models.agent import MetricsConfig
from voicetest.models.diagnosis import Diagnosis as DiagnosisModel
from voicetest.models.diagnosis import PromptChange as PromptChangeModel
from voicetest.models.results import Message
from voicetest.models.results import MetricResult
from voicetest.models.results import TestResult
from voicetest.models.results import TestRun
from voicetest.models.test_case import RunOptions
from voicetest.models.test_case import TestCase
from voicetest.pathutil import resolve_within
from voicetest.retry import RetryError
from voicetest.services import get_agent_service
from voicetest.services import get_diagnosis_service
from voicetest.services import get_discovery_service
from voicetest.services import get_evaluation_service
from voicetest.services import get_platform_service
from voicetest.services import get_run_service
from voicetest.services import get_settings_service
from voicetest.services import get_snippet_service
from voicetest.services import get_test_case_service
from voicetest.services import get_test_execution_service
from voicetest.settings import Settings
from voicetest.settings import load_settings
from voicetest.settings import resolve_model
from voicetest.storage.models import Result as ResultModel
from voicetest.storage.models import Run as RunModel
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import CallRepository
from voicetest.storage.repositories import TestCaseRepository


# Configure logging from env var set by CLI (carries across uvicorn --reload workers).
# Can't use basicConfig here — uvicorn already configured the root logger, making it a no-op.
_log_level = os.environ.get("VOICETEST_LOG_LEVEL", "WARNING").upper()
_vt_logger = logging.getLogger("voicetest")
_vt_logger.setLevel(getattr(logging, _log_level, logging.WARNING))
if not _vt_logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
    _vt_logger.addHandler(_handler)
_vt_logger.info("voicetest logging configured at %s", _log_level)


# Active runs: run_id -> {"cancel": Event, "websockets": set[WebSocket], "message_queue": list}
_active_runs: dict[str, dict[str, Any]] = {}

_initialized = False


def init_storage() -> None:
    """Initialize storage and register linked agents."""
    global _initialized

    get_session()
    _initialized = True

    linked_agents = os.environ.get("VOICETEST_LINKED_AGENTS", "")
    linked_tests_raw = os.environ.get("VOICETEST_LINKED_TESTS", "")

    # Parse linked tests: "agent_path=test1,test2;agent_path2=test3"
    tests_by_agent: dict[str, list[str]] = {}
    if linked_tests_raw:
        for pair in linked_tests_raw.split(";"):
            pair = pair.strip()
            if "=" not in pair:
                continue
            agent_path, test_paths_str = pair.split("=", 1)
            agent_path = agent_path.strip()
            test_paths = [p.strip() for p in test_paths_str.split(",") if p.strip()]
            if agent_path and test_paths:
                tests_by_agent[agent_path] = test_paths

    if linked_agents:
        for agent_path in linked_agents.split(","):
            agent_path = agent_path.strip()
            if agent_path:
                tests_paths = tests_by_agent.get(agent_path)
                _register_linked_agent(Path(agent_path), tests_paths=tests_paths)


def _register_linked_agent(path: Path, tests_paths: list[str] | None = None) -> None:
    """Register a linked agent from filesystem if not already registered."""
    repo = get_agent_repo()
    existing = repo.list_all()
    for agent in existing:
        if agent.get("source_path") == str(path):
            # Update tests_paths if they changed
            if tests_paths and agent.get("tests_paths") != tests_paths:
                repo.update(agent["id"], tests_paths=tests_paths)
            return

    name = path.stem
    repo.create(
        name=name,
        source_type="linked",
        source_path=str(path),
        tests_paths=tests_paths,
    )


def _get_repo[T](repo_type: type[T]) -> T:
    """Resolve a repository from the DI container, initializing storage if needed."""
    if not _initialized:
        init_storage()
    return get_container().resolve(repo_type)


def get_agent_repo() -> AgentRepository:
    """Get the agent repository from the DI container."""
    return _get_repo(AgentRepository)


def get_test_case_repo() -> TestCaseRepository:
    """Get the test case repository from the DI container."""
    return _get_repo(TestCaseRepository)


def get_call_repo() -> CallRepository:
    """Get the call repository from the DI container."""
    return _get_repo(CallRepository)


def _find_web_dist() -> Path | None:
    """Find the web dist folder relative to the package root."""
    dist = Path(__file__).parent.parent / "web" / "dist"
    return dist if dist.exists() else None


WEB_DIST = _find_web_dist()

app = FastAPI(
    title="voicetest",
    description="Voice agent test harness API",
    version="0.1.0",
)

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # nosemgrep: python.fastapi.security.wildcard-cors.wildcard-cors
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/api")


# Request/Response models


class ImportRequest(BaseModel):
    """Request to import an agent config."""

    config: dict[str, Any]
    source: str | None = None


class RemoteAgentInfo(BaseModel):
    """Information about a remote agent on a platform."""

    id: str
    name: str


class PlatformStatusResponse(BaseModel):
    """Response from platform status check."""

    configured: bool
    platform: str


class PlatformInfo(BaseModel):
    """Information about a platform."""

    name: str
    configured: bool
    env_key: str
    required_env_keys: list[str]


class ConfigurePlatformRequest(BaseModel):
    """Request to configure platform credentials."""

    api_key: str
    api_secret: str | None = None


class ExportToPlatformRequest(BaseModel):
    """Request to export an agent to a platform."""

    graph: AgentGraph
    name: str | None = None


class ExportToPlatformResponse(BaseModel):
    """Response from exporting an agent to a platform."""

    id: str
    name: str
    platform: str


class SyncStatusResponse(BaseModel):
    """Response from sync status check."""

    can_sync: bool
    reason: str | None = None
    platform: str | None = None
    remote_id: str | None = None
    needs_configuration: bool = False


class SyncToPlatformRequest(BaseModel):
    """Request to sync an agent to its source platform."""

    graph: AgentGraph


class SyncToPlatformResponse(BaseModel):
    """Response from syncing an agent to a platform."""

    id: str
    name: str
    platform: str
    synced: bool


class ExportRequest(BaseModel):
    """Request to export an agent graph."""

    graph: AgentGraph
    format: str
    expanded: bool = False


class RunTestRequest(BaseModel):
    """Request to run a single test."""

    graph: AgentGraph
    test_case: TestCase
    options: RunOptions | None = None


class RunTestsRequest(BaseModel):
    """Request to run multiple tests."""

    graph: AgentGraph
    test_cases: list[TestCase]
    options: RunOptions | None = None


class EvaluateRequest(BaseModel):
    """Request to evaluate a transcript."""

    transcript: list[Message]
    metrics: list[str]


class CreateAgentRequest(BaseModel):
    """Request to create an agent from config or file path."""

    name: str
    config: dict[str, Any] | None = None
    path: str | None = None
    source: str | None = None


class UpdateAgentRequest(BaseModel):
    """Request to update an agent."""

    name: str | None = None
    default_model: str | None = None
    graph_json: str | None = None


class UpdateSnippetRequest(BaseModel):
    """Request to create or update a single snippet."""

    text: str


class ApplySnippetsRequest(BaseModel):
    """Request to apply snippets: add them to graph and replace occurrences in prompts."""

    snippets: list[dict[str, str]]


class UpdatePromptRequest(BaseModel):
    """Request to update a prompt (general, node, or transition).

    - node_id=None: updates source_metadata.general_prompt
    - node_id set, transition_target_id=None: updates node's state_prompt
    - node_id set, transition_target_id set: updates transition condition value
    """

    node_id: str | None = None
    prompt_text: str
    transition_target_id: str | None = None


class UpdateMetadataRequest(BaseModel):
    """Request to merge updates into an agent's source_metadata."""

    updates: dict[str, Any]


class UpdateMetricsConfigRequest(BaseModel):
    """Request to update an agent's metrics configuration."""

    threshold: float = 0.7
    global_metrics: list[GlobalMetric] = []


class CreateTestCaseRequest(BaseModel):
    """Request to create a test case."""

    name: str
    user_prompt: str
    metrics: list[str] = []
    dynamic_variables: dict[str, Any] = {}
    tool_mocks: list[Any] = []
    type: str = "simulation"
    llm_model: str | None = None
    includes: list[str] = []
    excludes: list[str] = []
    patterns: list[str] = []


class StartRunRequest(BaseModel):
    """Request to start a test run."""

    test_ids: list[str] | None = None
    options: RunOptions | None = None


class LinkTestFileRequest(BaseModel):
    """Request to link a test file to an agent."""

    path: str


class ExportTestsRequest(BaseModel):
    """Request to export test cases."""

    format: str = "retell"
    test_ids: list[str] | None = None  # None means all tests


class StartCallResponse(BaseModel):
    """Response from starting a call."""

    call_id: str
    room_name: str
    livekit_url: str
    token: str


class CallStatusResponse(BaseModel):
    """Response with call status."""

    id: str
    agent_id: str
    room_name: str
    status: str
    transcript: list[dict]
    started_at: str
    ended_at: str | None = None


class StartChatResponse(BaseModel):
    """Response from starting a text chat."""

    chat_id: str


class StartChatRequest(BaseModel):
    """Request to start a text chat session."""

    dynamic_variables: dict[str, Any] = {}


class StartCallRequest(BaseModel):
    """Request to start a live voice call."""

    dynamic_variables: dict[str, Any] = {}


class ImporterInfo(BaseModel):
    """Importer information for API response."""

    source_type: str
    description: str
    file_patterns: list[str]


# Endpoints


@router.get("/health")
async def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "ok"}


class ExportFormatInfo(BaseModel):
    """Export format information for API response."""

    id: str
    name: str
    description: str
    ext: str


@router.get("/importers", response_model=list[ImporterInfo])
async def list_importers() -> list[ImporterInfo]:
    """List available importers."""
    importers = get_discovery_service().list_importers()
    return [
        ImporterInfo(
            source_type=imp.source_type,
            description=imp.description,
            file_patterns=imp.file_patterns,
        )
        for imp in importers
    ]


@router.get("/exporters", response_model=list[ExportFormatInfo])
async def list_exporters() -> list[ExportFormatInfo]:
    """List available export formats."""
    formats = get_discovery_service().list_export_formats()
    return [ExportFormatInfo(**f) for f in formats]


@router.post("/agents/import", response_model=AgentGraph)
async def import_agent(request: ImportRequest) -> AgentGraph:
    """Import an agent from config."""
    try:
        return await get_agent_service().import_agent(request.config, source=request.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/import-file", response_model=AgentGraph)
async def import_agent_file(file: UploadFile, source: str | None = None) -> AgentGraph:
    """Import an agent from an uploaded file (XLSForm, JSON, etc.)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    suffix = Path(file.filename).suffix
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            return await get_agent_service().import_agent(tmp_path, source=source)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/export")
async def export_agent(request: ExportRequest) -> dict[str, str]:
    """Export an agent graph to a format."""
    try:
        content = await get_agent_service().export_agent(
            request.graph, format=request.format, expanded=request.expanded
        )
        return {"content": content, "format": request.format}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


def _build_run_options(settings: Settings, request_options: RunOptions | None) -> RunOptions:
    """Build RunOptions from settings, with request options for run params only.

    Models come from settings (can be None if not configured).
    Run parameters (max_turns, timeout, verbose, flow_judge, streaming) come from
    request if provided, otherwise from settings.
    """
    return RunOptions(
        agent_model=settings.models.agent,
        simulator_model=settings.models.simulator,
        judge_model=settings.models.judge,
        max_turns=request_options.max_turns if request_options else settings.run.max_turns,
        timeout_seconds=request_options.timeout_seconds if request_options else 60.0,
        verbose=(request_options.verbose if request_options else False) or settings.run.verbose,
        flow_judge=(
            (request_options.flow_judge if request_options else False) or settings.run.flow_judge
        ),
        streaming=settings.run.streaming,
        test_model_precedence=settings.run.test_model_precedence,
        split_transitions=(
            (request_options.split_transitions if request_options else False)
            or settings.run.split_transitions
        ),
        audio_eval=(
            (request_options.audio_eval if request_options else False) or settings.run.audio_eval
        ),
    )


@router.post("/runs/single", response_model=TestResult)
async def run_test(request: RunTestRequest) -> TestResult:
    """Run a single test case."""
    settings = load_settings()
    settings.apply_env()
    options = _build_run_options(settings, request.options)
    return await get_test_execution_service().run_test(
        request.graph,
        request.test_case,
        options=options,
    )


@router.post("/runs", response_model=TestRun)
async def run_tests(request: RunTestsRequest) -> TestRun:
    """Run multiple test cases."""
    settings = load_settings()
    settings.apply_env()
    options = _build_run_options(settings, request.options)
    return await get_test_execution_service().run_tests(
        request.graph,
        request.test_cases,
        options=options,
    )


@router.post("/evaluate", response_model=list[MetricResult])
async def evaluate_transcript(request: EvaluateRequest) -> list[MetricResult]:
    """Evaluate a transcript against metrics."""
    return await get_evaluation_service().evaluate_transcript(
        request.transcript,
        request.metrics,
    )


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    """Get current settings from .voicetest.toml."""
    return get_settings_service().get_settings()


@router.get("/settings/defaults", response_model=Settings)
async def get_default_settings() -> Settings:
    """Get default settings (not from file)."""
    return get_settings_service().get_defaults()


@router.put("/settings", response_model=Settings)
async def update_settings(settings: Settings) -> Settings:
    """Update settings in .voicetest.toml."""
    return get_settings_service().update_settings(settings)


@router.get("/agents")
async def list_agents() -> list[dict]:
    """List all agents."""
    return get_agent_service().list_agents()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """Get agent by ID."""
    return _require_agent(agent_id)


@router.get("/agents/{agent_id}/graph", response_model=None)
async def get_agent_graph(
    agent_id: str,
    response: Response,
    if_none_match: str | None = Header(default=None),
) -> AgentGraph | Response:
    """Get the AgentGraph for an agent.

    For linked agents (source_path), uses file mtime for ETag-based caching.
    Returns 304 Not Modified if the file hasn't changed.
    """
    svc = get_agent_service()
    try:
        graph, etag, not_modified = svc.get_graph_with_etag(agent_id, if_none_match)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None

    if not_modified:
        return Response(status_code=304)

    if etag:
        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, must-revalidate"

    return graph


@router.get("/agents/{agent_id}/variables")
async def get_agent_variables(agent_id: str) -> dict:
    """Extract dynamic variable names from agent prompts.

    Scans general_prompt and all node state_prompt values for {{var}} placeholders.
    Returns unique variable names in first-appearance order.
    """
    svc = get_agent_service()
    try:
        variables = svc.get_variables(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"variables": variables}


def _require_agent(agent_id: str) -> dict:
    """Get agent or raise 404."""
    agent = get_agent_service().get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _load_agent_graph(agent_id: str) -> tuple[dict, AgentGraph]:
    """Load agent record and its graph. Raises HTTPException on failure."""
    try:
        return get_agent_service().load_graph(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/agents/{agent_id}/snippets")
async def get_snippets(agent_id: str) -> dict:
    """Get all snippets defined for an agent."""
    svc = get_snippet_service()
    try:
        return {"snippets": svc.get_snippets(agent_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/snippets")
async def update_all_snippets(agent_id: str, body: dict) -> dict:
    """Replace all snippets for an agent."""
    svc = get_snippet_service()
    try:
        return {"snippets": svc.update_all_snippets(agent_id, body.get("snippets", {}))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/snippets/{name}")
async def update_snippet(agent_id: str, name: str, request: UpdateSnippetRequest) -> dict:
    """Create or update a single snippet."""
    svc = get_snippet_service()
    try:
        return {"snippets": svc.update_snippet(agent_id, name, request.text)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/agents/{agent_id}/snippets/{name}")
async def delete_snippet(agent_id: str, name: str) -> dict:
    """Delete a single snippet."""
    svc = get_snippet_service()
    try:
        return {"snippets": svc.delete_snippet(agent_id, name)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents/{agent_id}/analyze-dry")
async def analyze_dry(agent_id: str) -> dict:
    """Run auto-DRY analysis on an agent's prompts."""
    svc = get_snippet_service()
    try:
        return svc.analyze_dry(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents/{agent_id}/apply-snippets", response_model=AgentGraph)
async def apply_snippets(agent_id: str, request: ApplySnippetsRequest) -> AgentGraph:
    """Apply snippets: add them to graph and replace occurrences in prompts with {%name%} refs."""
    svc = get_snippet_service()
    try:
        return svc.apply_snippets(agent_id, request.snippets)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents")
async def create_agent(request: CreateAgentRequest) -> dict:
    """Create an agent from config dict or file path."""
    svc = get_agent_service()
    try:
        return svc.create_agent(
            name=request.name,
            config=request.config,
            path=request.path,
            source=request.source,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"File not found: {request.path}") from None
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from None
    except PermissionError:
        raise HTTPException(status_code=400, detail=f"Permission denied: {request.path}") from None


@router.post("/agents/upload")
async def create_agent_from_file(
    file: UploadFile,
    name: str | None = None,
    source: str | None = None,
) -> dict:
    """Create an agent from an uploaded file (XLSForm, JSON, etc.)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    agent_name = name or Path(file.filename).stem
    suffix = Path(file.filename).suffix
    agent_svc = get_agent_service()

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            graph = await agent_svc.import_agent(tmp_path, source=source)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    repo = get_agent_repo()
    return repo.create(
        name=agent_name,
        source_type=graph.source_type,
        graph_json=graph.model_dump_json(),
    )


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, request: UpdateAgentRequest) -> dict:
    """Update an agent."""
    try:
        return get_agent_service().update_agent(
            agent_id,
            name=request.name,
            default_model=request.default_model,
            graph_json=request.graph_json,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/prompts", response_model=AgentGraph)
async def update_prompt(agent_id: str, request: UpdatePromptRequest) -> AgentGraph:
    """Update a general or node-specific prompt.

    When node_id is None, updates source_metadata.general_prompt.
    When node_id is set, updates that node's state_prompt.
    For linked-file agents, writes back to the source file on disk.
    """
    try:
        return get_agent_service().update_prompt(
            agent_id,
            prompt_text=request.prompt_text,
            node_id=request.node_id,
            transition_target_id=request.transition_target_id,
        )
    except ValueError as e:
        detail = str(e)
        status = 400 if "Cannot write" in detail else 404
        raise HTTPException(status_code=status, detail=detail) from None


@router.put("/agents/{agent_id}/metadata", response_model=AgentGraph)
async def update_metadata(agent_id: str, request: UpdateMetadataRequest) -> AgentGraph:
    """Merge updates into an agent's source_metadata."""
    try:
        return get_agent_service().update_metadata(agent_id, request.updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    """Delete an agent."""
    get_agent_service().delete_agent(agent_id)
    return {"status": "deleted", "id": agent_id}


@router.get("/agents/{agent_id}/metrics-config")
async def get_metrics_config(agent_id: str) -> dict:
    """Get an agent's metrics configuration."""
    _require_agent(agent_id)
    config = get_agent_service().get_metrics_config(agent_id)
    return config.model_dump()


@router.put("/agents/{agent_id}/metrics-config")
async def update_metrics_config(agent_id: str, request: UpdateMetricsConfigRequest) -> dict:
    """Update an agent's metrics configuration."""
    _require_agent(agent_id)
    config = MetricsConfig(
        threshold=request.threshold,
        global_metrics=request.global_metrics,
    )
    get_agent_service().update_metrics_config(agent_id, config)
    return config.model_dump()


@router.get("/agents/{agent_id}/tests")
async def list_tests_for_agent(agent_id: str) -> list[dict]:
    """List all test cases for an agent, including file-based linked tests."""
    return get_test_case_service().list_tests(agent_id)


@router.post("/agents/{agent_id}/tests-paths")
async def link_test_file(agent_id: str, request: LinkTestFileRequest) -> dict:
    """Link a JSON test file to an agent.

    The file must exist, contain valid JSON, and be a JSON array.
    Tests from the file will appear alongside DB tests via list_for_agent_with_linked.
    """
    try:
        return get_test_case_service().link_test_file(agent_id, request.path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        detail = str(e)
        status = 409 if "already linked" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from None


@router.delete("/agents/{agent_id}/tests-paths")
async def unlink_test_file(agent_id: str, path: str) -> dict:
    """Unlink a test file from an agent.

    Removes the path from tests_paths. The file itself is not deleted.
    """
    try:
        return get_test_case_service().unlink_test_file(agent_id, path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents/{agent_id}/tests/export")
async def export_tests_for_agent(agent_id: str, request: ExportTestsRequest) -> list[dict]:
    """Export test cases for an agent to a specified format."""
    try:
        return get_test_case_service().export_tests(agent_id, request.test_ids, request.format)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/{agent_id}/tests")
async def create_test_case(agent_id: str, request: CreateTestCaseRequest) -> dict:
    """Create a test case for an agent.

    If the agent has linked test files, the test is appended to the first file.
    Otherwise it is stored in the database.
    """
    test_case = TestCase(
        name=request.name,
        user_prompt=request.user_prompt,
        metrics=request.metrics,
        dynamic_variables=request.dynamic_variables,
        tool_mocks=request.tool_mocks,
        type=request.type,
        llm_model=request.llm_model,
        includes=request.includes,
        excludes=request.excludes,
        patterns=request.patterns,
    )

    return get_test_case_service().create_test(agent_id, test_case)


@router.put("/tests/{test_id}")
async def update_test_case(test_id: str, request: CreateTestCaseRequest) -> dict:
    """Update a test case (DB or linked file)."""
    test_case = TestCase(
        name=request.name,
        user_prompt=request.user_prompt,
        metrics=request.metrics,
        dynamic_variables=request.dynamic_variables,
        tool_mocks=request.tool_mocks,
        type=request.type,
        llm_model=request.llm_model,
        includes=request.includes,
        excludes=request.excludes,
        patterns=request.patterns,
    )

    try:
        return get_test_case_service().update_test(test_id, test_case)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/tests/{test_id}")
async def delete_test_case(test_id: str) -> dict:
    """Delete a test case (DB or linked file)."""
    try:
        get_test_case_service().delete_test(test_id)
        return {"status": "deleted", "id": test_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


class LoadDemoResponse(BaseModel):
    """Response from loading demo data."""

    agent_id: str
    agent_name: str
    test_count: int
    created: bool


@router.post("/demo", response_model=LoadDemoResponse)
async def load_demo() -> LoadDemoResponse:
    """Load demo agent and tests into the database.

    If the demo agent already exists, returns its info without creating duplicates.
    """
    demo_agent_config = get_demo_agent()
    demo_tests = get_demo_tests()

    graph = await get_agent_service().import_agent(demo_agent_config)

    agent_repo = get_agent_repo()
    test_repo = get_test_case_repo()

    existing = agent_repo.list_all()
    demo_agent = next((a for a in existing if a.get("name") == "Demo Healthcare Agent"), None)

    if demo_agent:
        test_count = len(test_repo.list_for_agent(demo_agent["id"]))
        return LoadDemoResponse(
            agent_id=demo_agent["id"],
            agent_name=demo_agent["name"],
            test_count=test_count,
            created=False,
        )

    agent = agent_repo.create(
        name="Demo Healthcare Agent",
        source_type=graph.source_type,
        graph_json=graph.model_dump_json(),
    )

    for test_data in demo_tests:
        test_case = TestCase(**test_data)
        test_repo.create(agent["id"], test_case)

    return LoadDemoResponse(
        agent_id=agent["id"],
        agent_name=agent["name"],
        test_count=len(demo_tests),
        created=True,
    )


@router.get("/gallery")
async def list_gallery() -> list[dict]:
    """List available test gallery fixtures."""
    gallery_dir = Path(__file__).parent / "fixtures" / "test_gallery"
    if not gallery_dir.exists():
        return []

    fixtures = []
    for file in gallery_dir.glob("*.json"):
        try:
            data = json.loads(file.read_text())
            fixtures.append(
                {
                    "id": file.stem,
                    "name": data.get("name", file.stem),
                    "description": data.get("description", ""),
                    "tests": data.get("tests", []),
                }
            )
        except (json.JSONDecodeError, KeyError):
            continue

    return fixtures


@router.get("/agents/{agent_id}/runs")
async def list_runs_for_agent(agent_id: str, limit: int = 50) -> list[dict]:
    """List all runs for an agent."""
    return get_run_service().list_runs(agent_id, limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Get a run with all results."""
    run_svc = get_run_service()
    run = run_svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Detect orphaned run: not completed but not actively running
    if run["completed_at"] is None and run_id not in _active_runs:
        run_svc.complete(run_id)
        run["completed_at"] = datetime.now(UTC).isoformat()

    # Fix inconsistent state: run complete but results still "running"
    if run["completed_at"] is not None:
        for result in run["results"]:
            if result["status"] == "running":
                run_svc.mark_result_error(result["id"], "Run orphaned - backend stopped")
                result["status"] = "error"
                result["error_message"] = "Run orphaned - backend stopped"

    return run


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict:
    """Delete a run and all its results."""
    run = get_run_service().get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Don't allow deleting active runs
    if run_id in _active_runs:
        raise HTTPException(status_code=400, detail="Cannot delete an active run")

    get_run_service().delete_run(run_id)
    return {"status": "deleted", "id": run_id}


@router.post("/results/{result_id}/audio-eval")
async def audio_eval_result(result_id: str) -> dict:
    """Run audio evaluation on an existing test result.

    Performs TTS->STT round-trip on assistant messages and re-evaluates
    metrics using the "heard" text.
    """
    run_svc = get_run_service()
    tc_svc = get_test_case_service()

    session = get_session()
    db_result = session.get(ResultModel, result_id)
    if not db_result:
        raise HTTPException(status_code=404, detail="Result not found")

    result_dict = run_svc._runs._result_to_dict(db_result)
    transcript_data = result_dict.get("transcript_json") or []
    if not transcript_data:
        raise HTTPException(status_code=400, detail="Result has no transcript")

    transcript = [Message(**m) for m in transcript_data]

    # Find the test case to get metrics/rules
    test_case_id = result_dict.get("test_case_id")
    test_record = tc_svc.get_test(test_case_id) if test_case_id else None
    if not test_record:
        test_record = tc_svc.find_linked_test(test_case_id) if test_case_id else None
    if not test_record:
        raise HTTPException(status_code=400, detail="Test case not found for result")

    test_case = tc_svc.to_model(test_record)

    # Load metrics config for global metrics
    run = session.get(RunModel, db_result.run_id)
    metrics_config = get_agent_service().get_metrics_config(run.agent_id) if run else None

    settings = load_settings()
    settings.apply_env()
    judge_model = resolve_model(settings.models.judge)

    transformed, audio_metrics = await get_evaluation_service().audio_eval_result(
        transcript,
        test_case,
        metrics_config=metrics_config,
        judge_model=judge_model,
        settings=settings,
    )

    # Update stored result with audio eval data
    run_svc.update_audio_eval(result_id, transformed, audio_metrics)

    # Return updated result
    session.refresh(db_result)
    return run_svc._runs._result_to_dict(db_result)


def _load_result_context(result_id: str) -> tuple[dict, "TestCase", AgentGraph, str]:
    """Load result, test case, agent graph, and judge model for diagnosis endpoints.

    Returns:
        Tuple of (result_dict, test_case, agent_graph, judge_model).

    Raises:
        HTTPException on missing data.
    """
    run_svc = get_run_service()
    tc_svc = get_test_case_service()

    session = get_session()
    db_result = session.get(ResultModel, result_id)
    if not db_result:
        raise HTTPException(status_code=404, detail="Result not found")

    result_dict = run_svc._runs._result_to_dict(db_result)

    # Find test case
    test_case_id = result_dict.get("test_case_id")
    test_record = tc_svc.get_test(test_case_id) if test_case_id else None
    if not test_record:
        test_record = tc_svc.find_linked_test(test_case_id) if test_case_id else None
    if not test_record:
        raise HTTPException(status_code=400, detail="Test case not found for result")

    test_case = tc_svc.to_model(test_record)

    # Load agent graph
    run = session.get(RunModel, db_result.run_id)
    if not run:
        raise HTTPException(status_code=400, detail="Run not found for result")

    _agent, graph = _load_agent_graph(run.agent_id)

    # Resolve judge model
    settings = load_settings()
    settings.apply_env()
    judge_model = resolve_model(settings.models.judge)

    return result_dict, test_case, graph, judge_model


@router.post("/results/{result_id}/diagnose")
async def diagnose_result(result_id: str, request: Request) -> dict:
    """Diagnose why a test result failed and suggest a fix.

    Analyzes the graph structure, transcript, and failed metrics to identify
    the root cause and propose concrete prompt/transition changes.

    Optional body: {"model": "provider/model-name"} to override the judge model.
    """
    result_dict, test_case, graph, judge_model = _load_result_context(result_id)

    try:
        body = await request.json()
    except Exception:
        body = {}
    model_override = body.get("model")
    if model_override:
        judge_model = model_override

    transcript_data = result_dict.get("transcript_json") or []
    transcript = [Message(**m) for m in transcript_data]

    metrics_data = result_dict.get("metrics_json") or []
    metric_results = [MetricResult(**m) for m in metrics_data]
    nodes_visited = result_dict.get("nodes_visited") or []

    diagnosis_result = await get_diagnosis_service().diagnose_failure(
        graph=graph,
        transcript=transcript,
        nodes_visited=nodes_visited,
        failed_metrics=metric_results,
        test_scenario=test_case.user_prompt,
        judge_model=judge_model,
    )

    return diagnosis_result.model_dump()


@router.post("/results/{result_id}/apply-fix")
async def apply_fix(result_id: str, body: dict) -> dict:
    """Apply proposed changes to a copy of the graph and rerun the test.

    Non-destructive: does not persist changes.
    """
    result_dict, test_case, graph, judge_model = _load_result_context(result_id)

    changes = [PromptChangeModel.model_validate(c) for c in body.get("changes", [])]
    iteration = body.get("iteration", 1)

    metrics_data = result_dict.get("metrics_json") or []
    original_metrics = [MetricResult(**m) for m in metrics_data]

    # Load metrics config for global metrics
    session = get_session()
    db_result = session.get(ResultModel, result_id)
    run = session.get(RunModel, db_result.run_id)
    metrics_config = get_agent_service().get_metrics_config(run.agent_id) if run else None

    options = RunOptions(judge_model=judge_model)

    attempt_result = await get_diagnosis_service().apply_and_rerun(
        graph=graph,
        test_case=test_case,
        changes=changes,
        original_metrics=original_metrics,
        iteration=iteration,
        options=options,
        metrics_config=metrics_config,
    )

    return attempt_result.model_dump()


@router.post("/results/{result_id}/revise-fix")
async def revise_fix_endpoint(result_id: str, body: dict) -> dict:
    """Revise a previous fix attempt based on new metric results.

    Given the original diagnosis and previous changes, produce a revised fix.

    Optional body field: "model" to override the judge model.
    """
    result_dict, test_case, graph, judge_model = _load_result_context(result_id)

    model_override = body.get("model")
    if model_override:
        judge_model = model_override

    diagnosis = DiagnosisModel.model_validate(body["diagnosis"])
    prev_changes = [PromptChangeModel.model_validate(c) for c in body["previous_changes"]]
    new_metrics = [MetricResult.model_validate(m) for m in body["new_metric_results"]]

    fix = await get_diagnosis_service().revise_fix(
        graph=graph,
        diagnosis=diagnosis,
        prev_changes=prev_changes,
        new_metrics=new_metrics,
        judge_model=judge_model,
    )

    return fix.model_dump()


@router.post("/agents/{agent_id}/save-fix")
async def save_fix(agent_id: str, body: dict) -> dict:
    """Persist proposed changes to the agent graph.

    Applies changes and saves the modified graph.
    """
    agent, graph = _load_agent_graph(agent_id)
    changes = [PromptChangeModel.model_validate(c) for c in body.get("changes", [])]

    modified_graph = get_diagnosis_service().apply_fix_to_graph(graph, changes)
    get_agent_service().save_graph(agent_id, agent, modified_graph)

    return modified_graph.model_dump()


async def _broadcast_run_update(run_id: str, data: dict) -> None:
    """Broadcast update to all WebSocket clients watching this run."""
    if run_id not in _active_runs:
        return
    message = json.dumps(data)
    websockets = _active_runs[run_id]["websockets"]
    if not websockets:
        # Queue message for replay when WebSocket connects
        _active_runs[run_id]["message_queue"].append(message)
        return
    dead_sockets = []
    for ws in websockets:
        try:
            await ws.send_text(message)
        except Exception:
            dead_sockets.append(ws)
    for ws in dead_sockets:
        _active_runs[run_id]["websockets"].discard(ws)


def _is_run_cancelled(run_id: str, result_id: str | None = None) -> bool:
    """Check if run or specific test is cancelled."""
    if run_id not in _active_runs:
        return False
    cancelled = _active_runs[run_id].get("cancelled_tests", set())
    if result_id and result_id in cancelled:
        return True
    return _active_runs[run_id]["cancel"].is_set()


async def _execute_run(
    run_id: str,
    agent_id: str,
    test_records: list[dict],
    result_ids: dict[str, str],
    options: RunOptions,
) -> None:
    """Execute tests for a run in the background."""
    # _active_runs[run_id] is set up in start_run() before this task starts

    agent_svc = get_agent_service()
    tc_svc = get_test_case_service()
    run_svc = get_run_service()

    try:
        _agent, graph = agent_svc.load_graph(agent_id)
    except (FileNotFoundError, ValueError):
        return

    # Load metrics config for global metrics
    metrics_config = agent_svc.get_metrics_config(agent_id)

    try:
        for test_record in test_records:
            # Get pre-created result ID
            result_id = result_ids[test_record["id"]]

            # Check if this specific test was cancelled before it started
            if run_id in _active_runs and result_id in _active_runs[run_id]["cancelled_tests"]:
                run_svc.mark_result_cancelled(result_id)
                await _broadcast_run_update(
                    run_id,
                    {"type": "test_cancelled", "result_id": result_id},
                )
                continue

            # Check if entire run is cancelled
            if _is_run_cancelled(run_id):
                # Mark ALL remaining tests (including current) as cancelled
                remaining_idx = test_records.index(test_record)
                for remaining_record in test_records[remaining_idx:]:
                    remaining_result_id = result_ids[remaining_record["id"]]
                    run_svc.mark_result_cancelled(remaining_result_id)
                    await _broadcast_run_update(
                        run_id,
                        {"type": "test_cancelled", "result_id": remaining_result_id},
                    )
                break

            test_case = tc_svc.to_model(test_record)

            # Broadcast that test is now actively running
            await _broadcast_run_update(
                run_id,
                {
                    "type": "test_started",
                    "result_id": result_id,
                    "test_case_id": test_record["id"],
                    "test_name": test_case.name,
                },
            )

            async def make_on_turn(rid: str, transcript_ref: list[Message]):
                async def on_turn(transcript: list) -> None:
                    nonlocal transcript_ref
                    # Check for cancellation
                    if _is_run_cancelled(run_id, rid):
                        raise asyncio.CancelledError("Test cancelled by user")
                    # Track transcript for error recovery
                    transcript_ref.clear()
                    transcript_ref.extend(transcript)
                    run_svc.update_transcript(rid, transcript)
                    await _broadcast_run_update(
                        run_id,
                        {
                            "type": "transcript_update",
                            "result_id": rid,
                            "transcript": [m.model_dump() for m in transcript],
                        },
                    )

                return on_turn

            def make_on_token(rid: str):
                async def on_token(token: str, source: str) -> None:
                    await _broadcast_run_update(
                        run_id,
                        {
                            "type": "token_update",
                            "result_id": rid,
                            "token": token,
                            "source": source,
                        },
                    )

                return on_token

            def make_on_error(rid: str):
                async def on_error(error: RetryError) -> None:
                    await _broadcast_run_update(
                        run_id,
                        {
                            "type": "retry_error",
                            "result_id": rid,
                            "error_type": error.error_type,
                            "message": error.message,
                            "attempt": error.attempt,
                            "max_attempts": error.max_attempts,
                            "retry_after": error.retry_after,
                        },
                    )

                return on_error

            # Track transcript for error cases
            last_transcript: list[Message] = []

            try:
                result = await get_test_execution_service().run_test(
                    graph,
                    test_case,
                    options=options,
                    metrics_config=metrics_config,
                    on_turn=await make_on_turn(result_id, last_transcript),
                    on_token=make_on_token(result_id) if options.streaming else None,
                    on_error=make_on_error(result_id),
                )
                run_svc.complete_result(result_id, result)
                await _broadcast_run_update(
                    run_id,
                    {
                        "type": "test_completed",
                        "result_id": result_id,
                        "status": result.status,
                    },
                )
            except asyncio.CancelledError:
                cancelled_result = TestResult(
                    test_name=test_case.name,
                    status="error",
                    transcript=last_transcript,
                    error_message="Cancelled by user",
                )
                run_svc.complete_result(result_id, cancelled_result)
                await _broadcast_run_update(
                    run_id,
                    {
                        "type": "test_cancelled",
                        "result_id": result_id,
                    },
                )
            except Exception as e:
                error_result = TestResult(
                    test_name=test_case.name,
                    status="error",
                    transcript=last_transcript,
                    error_message=str(e),
                )
                run_svc.complete_result(result_id, error_result)
                await _broadcast_run_update(
                    run_id,
                    {
                        "type": "test_error",
                        "result_id": result_id,
                        "error": str(e),
                    },
                )

        run_svc.complete(run_id)
        await _broadcast_run_update(run_id, {"type": "run_completed"})
    finally:
        # Clean up after a delay to allow final messages
        await asyncio.sleep(1)
        _active_runs.pop(run_id, None)


@router.websocket("/runs/{run_id}/ws")
async def run_websocket(websocket: WebSocket, run_id: str):
    """WebSocket for streaming run updates and receiving cancel commands."""
    try:
        await websocket.accept()
    except Exception as e:
        print(f"[WS] Failed to accept connection for run {run_id}: {e}")
        return

    # Send current state BEFORE registering for broadcasts to avoid race condition
    # where test_started arrives before state and then state overwrites it
    try:
        run = get_run_service().get_run(run_id)
        if not run:
            # Run not found - send error and close
            await websocket.send_json({"type": "error", "message": "Run not found"})
            await websocket.close(code=1008)  # Policy violation
            return
        msg = json.dumps({"type": "state", "run": run})
        await websocket.send_text(msg)

        # If run is already complete (not in _active_runs), send run_completed and close
        if run.get("completed_at") and run_id not in _active_runs:
            await websocket.send_json({"type": "run_completed"})
            await websocket.close(code=1000)  # Normal closure
            return

    except WebSocketDisconnect:
        print(f"[WS] Client disconnected during state send for run {run_id}")
        return
    except Exception as e:
        print(f"[WS] Error sending state for run {run_id}: {type(e).__name__}: {e}")
        try:
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.close(code=1011)  # Unexpected condition
        except Exception:
            pass
        return

    # Now register this WebSocket and get any queued messages
    queued_messages = []
    if run_id in _active_runs:
        _active_runs[run_id]["websockets"].add(websocket)
        queued_messages = _active_runs[run_id]["message_queue"]
        _active_runs[run_id]["message_queue"] = []

    try:
        # Replay any messages that were queued before connection
        for msg in queued_messages:
            await websocket.send_text(msg)

        # Listen for commands
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "cancel_test" and run_id in _active_runs:
                result_id = data.get("result_id")
                if result_id:
                    _active_runs[run_id]["cancelled_tests"].add(result_id)
            elif data.get("type") == "cancel_run" and run_id in _active_runs:
                _active_runs[run_id]["cancel"].set()
    except WebSocketDisconnect:
        # Normal disconnect - client closed connection
        pass
    except Exception as e:
        print(f"[WS] Exception in websocket handler for run {run_id}: {type(e).__name__}: {e}")
    finally:
        if run_id in _active_runs:
            _active_runs[run_id]["websockets"].discard(websocket)


class BackgroundTaskExecutor:
    """Default executor using FastAPI BackgroundTasks."""

    def __init__(self, background_tasks: BackgroundTasks):
        self.background_tasks = background_tasks

    def submit(self, job: RunJob) -> None:
        """Submit job to run in background."""
        self.background_tasks.add_task(
            _execute_run,
            job.run_id,
            job.agent_id,
            job.test_records,
            job.result_ids,
            job.options,
        )


@router.post("/agents/{agent_id}/runs")
async def start_run(
    agent_id: str,
    request: StartRunRequest,
    background_tasks: BackgroundTasks,
) -> dict:
    """Start a new test run. Tests execute in background, poll GET /runs/{id} for results."""
    _require_agent(agent_id)

    tc_svc = get_test_case_service()
    all_tests = tc_svc.list_tests(agent_id)

    if request.test_ids:
        tests_by_id = {t["id"]: t for t in all_tests}
        test_records = [tests_by_id[tid] for tid in request.test_ids if tid in tests_by_id]
    else:
        test_records = all_tests

    if not test_records:
        raise HTTPException(status_code=400, detail="No test cases to run")

    run_svc = get_run_service()
    run = run_svc.create_run(agent_id)

    # Create all pending results upfront so they appear immediately in UI
    # Map test_case_id -> result_id for the background task to use
    result_ids: dict[str, str] = {}
    for test_record in test_records:
        result_id = run_svc.create_pending_result(run["id"], test_record["id"], test_record["name"])
        result_ids[test_record["id"]] = result_id

    settings = load_settings()
    settings.apply_env()
    options = _build_run_options(settings, request.options)

    # Set up active run tracking BEFORE background task starts
    # so WebSocket connections can register immediately
    _active_runs[run["id"]] = {
        "cancel": asyncio.Event(),
        "websockets": set(),
        "cancelled_tests": set(),
        "message_queue": [],
    }

    # Create job and submit to executor
    job = RunJob(
        run_id=run["id"],
        agent_id=agent_id,
        test_records=test_records,
        result_ids=result_ids,
        options=options,
    )

    # Use custom executor if configured, otherwise default to BackgroundTasks
    executor_factory = get_executor_factory()
    if executor_factory:
        executor = executor_factory()
        executor.submit(job)
    else:
        executor = BackgroundTaskExecutor(background_tasks)
        executor.submit(job)

    return {
        "id": run["id"],
        "agent_id": agent_id,
        "started_at": run["started_at"],
        "test_count": len(test_records),
    }


# Live call endpoints


class LiveKitStatusResponse(BaseModel):
    """Response from LiveKit health check."""

    available: bool
    error: str | None = None


@router.get("/livekit/status", response_model=LiveKitStatusResponse)
async def get_livekit_status() -> LiveKitStatusResponse:
    """Check if LiveKit server is reachable."""
    call_manager = get_call_manager()

    try:
        # Try to create and immediately delete a test room
        test_room = f"health-check-{int(datetime.now(UTC).timestamp())}"
        await call_manager.create_room(test_room)
        return LiveKitStatusResponse(available=True)
    except Exception as e:
        error_msg = str(e)
        # Clean up the error message for display
        if "Connect call failed" in error_msg or "Cannot connect to host" in error_msg:
            error_msg = "LiveKit server not reachable"
        return LiveKitStatusResponse(available=False, error=error_msg)


@router.post("/agents/{agent_id}/calls/start", response_model=StartCallResponse)
async def start_call(agent_id: str, request: StartCallRequest | None = None) -> StartCallResponse:
    """Start a live voice call with an agent.

    Creates a LiveKit room and spawns an agent worker subprocess.
    Returns connection info including a token for the browser to join.
    """
    try:
        _agent, graph = get_agent_service().load_graph(agent_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot load agent graph: {e}") from None

    call_repo = get_call_repo()
    call_manager = get_call_manager()

    settings = load_settings()
    settings.apply_env()
    agent_model = settings.models.agent

    dynamic_variables = request.dynamic_variables if request else {}

    try:
        call_info = await call_manager.start_call(
            agent_id,
            graph,
            call_repo,
            agent_model=agent_model,
            dynamic_variables=dynamic_variables or None,
        )
        return StartCallResponse(**call_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start call: {e}") from None


@router.get("/calls/{call_id}", response_model=CallStatusResponse)
async def get_call(call_id: str) -> CallStatusResponse:
    """Get call status and transcript."""
    call_repo = get_call_repo()
    call = call_repo.get(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call_manager = get_call_manager()
    active_call = call_manager.get_active_call(call_id)

    transcript = call.get("transcript_json", [])
    if active_call:
        transcript = active_call.transcript

    return CallStatusResponse(
        id=call["id"],
        agent_id=call["agent_id"],
        room_name=call["room_name"],
        status=call["status"],
        transcript=transcript,
        started_at=call["started_at"],
        ended_at=call.get("ended_at"),
    )


@router.post("/calls/{call_id}/end")
async def end_call(call_id: str) -> dict:
    """End a live call and save the transcript as a run."""
    call_repo = get_call_repo()
    call = call_repo.get(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call_manager = get_call_manager()

    try:
        await call_manager.end_call(call_id, call_repo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end call: {e}") from None

    # Re-fetch call to get final transcript and timestamps
    call = call_repo.get(call_id)
    run_id = await _save_call_as_run(call)

    return {"status": "ended", "call_id": call_id, "run_id": run_id}


async def _save_call_as_run(call: dict) -> str | None:
    """Convert a completed call into a Run with a single Result.

    Evaluates global metrics against the transcript if the agent has any configured.
    Returns the run_id, or None if the call has no transcript.
    """
    transcript_data = call.get("transcript_json") or []
    if not transcript_data:
        return None

    agent_id = call["agent_id"]
    call_id = call["id"]

    # Convert raw transcript dicts to Message objects
    transcript = [Message(**m) for m in transcript_data]

    # Compute duration from call timestamps
    duration_ms = None
    if call.get("started_at") and call.get("ended_at"):
        started = datetime.fromisoformat(call["started_at"])
        ended = datetime.fromisoformat(call["ended_at"])
        duration_ms = int((ended - started).total_seconds() * 1000)

    turn_count = len(transcript) // 2

    # Evaluate global metrics if agent has them configured
    metrics_config = get_agent_service().get_metrics_config(agent_id)
    metric_results: list[MetricResult] = []

    if metrics_config and metrics_config.global_metrics:
        settings = load_settings()
        settings.apply_env()
        judge_model = resolve_model(settings.models.judge)
        try:
            metric_results = await get_test_execution_service().evaluate_global_metrics(
                transcript, metrics_config, judge_model=judge_model
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "Failed to evaluate global metrics for call %s", call_id
            )

    metrics_passed = all(r.passed for r in metric_results)
    status = "pass" if metrics_passed else "fail"

    test_result = TestResult(
        test_name="Live Call",
        status=status,
        transcript=transcript,
        metric_results=metric_results,
        turn_count=turn_count,
        duration_ms=duration_ms,
        end_reason="user_ended",
    )

    run_svc = get_run_service()
    run = run_svc.create_run(agent_id)
    run_svc.add_result_from_call(run["id"], call_id, test_result)
    run_svc.complete(run["id"])

    return run["id"]


@router.websocket("/calls/{call_id}/ws")
async def call_websocket(websocket: WebSocket, call_id: str):
    """WebSocket for streaming call updates (transcript, status)."""
    try:
        await websocket.accept()
    except Exception:
        return

    call_repo = get_call_repo()
    call = call_repo.get(call_id)
    if not call:
        await websocket.send_json({"type": "error", "message": "Call not found"})
        await websocket.close(code=1008)
        return

    call_manager = get_call_manager()

    try:
        state_msg = {
            "type": "state",
            "call": {
                "id": call["id"],
                "status": call["status"],
                "transcript": call.get("transcript_json", []),
            },
        }
        await websocket.send_json(state_msg)

        queued_messages = call_manager.register_websocket(call_id, websocket)

        for msg in queued_messages:
            await websocket.send_text(msg)

        while True:
            data = await websocket.receive_json()
            if data.get("type") == "end_call":
                await call_manager.end_call(call_id, call_repo)
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        _vt_logger.exception("Error in call websocket for %s", call_id)
    finally:
        call_manager.unregister_websocket(call_id, websocket)


# Text chat endpoints


@router.post("/agents/{agent_id}/chats/start", response_model=StartChatResponse)
async def start_chat(agent_id: str, request: StartChatRequest | None = None) -> StartChatResponse:
    """Start a text chat session with an agent.

    Creates a ConversationEngine in-process (no LiveKit or subprocess needed).
    Returns a chat_id for WebSocket connection.
    """
    try:
        _agent, graph = get_agent_service().load_graph(agent_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot load agent graph: {e}") from None

    call_repo = get_call_repo()
    chat_manager = get_chat_manager()

    settings = load_settings()
    settings.apply_env()
    agent_model = settings.models.agent

    dynamic_variables = request.dynamic_variables if request else {}

    try:
        chat_info = await chat_manager.start_chat(
            agent_id,
            graph,
            call_repo,
            agent_model=agent_model,
            dynamic_variables=dynamic_variables or None,
        )
        return StartChatResponse(**chat_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start chat: {e}") from None


@router.post("/chats/{chat_id}/end")
async def end_chat_session(chat_id: str) -> dict:
    """End a text chat session and save the transcript as a run."""
    call_repo = get_call_repo()
    call = call_repo.get(chat_id)
    if not call:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat_manager = get_chat_manager()

    try:
        await chat_manager.end_chat(chat_id, call_repo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end chat: {e}") from None

    # Re-fetch call to get final transcript and timestamps
    call = call_repo.get(chat_id)
    run_id = await _save_call_as_run(call)

    return {"status": "ended", "chat_id": chat_id, "run_id": run_id}


@router.websocket("/chats/{chat_id}/ws")
async def chat_websocket(websocket: WebSocket, chat_id: str):
    """WebSocket for text chat: send messages, receive streaming responses."""
    try:
        await websocket.accept()
    except Exception:
        return

    call_repo = get_call_repo()
    call = call_repo.get(chat_id)
    if not call:
        await websocket.send_json({"type": "error", "message": "Chat not found"})
        await websocket.close(code=1008)
        return

    chat_manager = get_chat_manager()

    try:
        # Send initial state
        active_chat = chat_manager.get_active_chat(chat_id)
        transcript = active_chat.transcript if active_chat else (call.get("transcript_json") or [])
        state_msg = {
            "type": "state",
            "chat": {
                "id": call["id"],
                "status": call["status"],
                "transcript": transcript,
            },
        }
        await websocket.send_json(state_msg)

        # Register for broadcasts and replay queued messages
        queued_messages = chat_manager.register_websocket(chat_id, websocket)
        for msg in queued_messages:
            await websocket.send_text(msg)

        # Listen for messages from client
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "message":
                content = data.get("content", "").strip()
                if content:
                    await chat_manager.process_message(chat_id, content, call_repo)
            elif data.get("type") == "end_chat":
                await chat_manager.end_chat(chat_id, call_repo)
                break
    except WebSocketDisconnect:
        pass
    except Exception:
        _vt_logger.exception("Error in chat websocket for %s", chat_id)
    finally:
        chat_manager.unregister_websocket(chat_id, websocket)


# Platform integration endpoints


@router.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms() -> list[PlatformInfo]:
    """List all available platforms and their configuration status."""
    platforms = get_platform_service().list_platforms()
    return [PlatformInfo(**p) for p in platforms]


@router.get("/platforms/{platform}/status", response_model=PlatformStatusResponse)
async def get_platform_status(platform: str) -> PlatformStatusResponse:
    """Check if a platform API key is configured."""
    try:
        result = get_platform_service().get_status(platform)
        return PlatformStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/platforms/{platform}/configure", response_model=PlatformStatusResponse)
async def configure_platform(
    platform: str, request: ConfigurePlatformRequest
) -> PlatformStatusResponse:
    """Configure platform credentials. Returns 409 if already configured."""
    try:
        result = get_platform_service().configure(platform, request.api_key, request.api_secret)
        return PlatformStatusResponse(**result)
    except ValueError as e:
        detail = str(e)
        status = 409 if "already configured" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from None


@router.get("/platforms/{platform}/agents", response_model=list[RemoteAgentInfo])
async def list_platform_agents(platform: str) -> list[RemoteAgentInfo]:
    """List agents from any supported platform."""
    try:
        agents = get_platform_service().list_remote_agents(platform)
        return [RemoteAgentInfo(**a) for a in agents]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list {platform} agents: {e}"
        ) from None


@router.post("/platforms/{platform}/agents/{agent_id}/import", response_model=AgentGraph)
async def import_platform_agent(platform: str, agent_id: str) -> AgentGraph:
    """Import an agent from any supported platform by ID."""
    try:
        return get_platform_service().import_from_platform(platform, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to import {platform} agent: {e}"
        ) from None


@router.post("/platforms/{platform}/export", response_model=ExportToPlatformResponse)
async def export_to_platform(
    platform: str, request: ExportToPlatformRequest
) -> ExportToPlatformResponse:
    """Export an agent graph to any supported platform."""
    try:
        result = get_platform_service().export_to_platform(platform, request.graph, request.name)
        return ExportToPlatformResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export to {platform}: {e}"
        ) from None


@router.get("/agents/{agent_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(agent_id: str) -> SyncStatusResponse:
    """Check if an agent can be synced to its source platform."""
    _require_agent(agent_id)
    result = get_platform_service().get_sync_status(agent_id)
    return SyncStatusResponse(**result)


@router.post("/agents/{agent_id}/sync", response_model=SyncToPlatformResponse)
async def sync_to_platform(agent_id: str, request: SyncToPlatformRequest) -> SyncToPlatformResponse:
    """Sync an agent to its source platform."""
    _require_agent(agent_id)
    try:
        result = get_platform_service().sync_to_platform(agent_id, request.graph)
        return SyncToPlatformResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync: {e}") from None


def create_app() -> FastAPI:
    """Create the FastAPI app (for programmatic use)."""
    return app


# Include API router
app.include_router(router)

# SPA static file serving (must be after API routes)
if WEB_DIST is not None:
    app.mount("/assets", StaticFiles(directory=WEB_DIST / "assets"), name="static")

    @app.get("/{path:path}")
    async def serve_spa(path: str) -> FileResponse:
        """Serve the SPA for all non-API routes."""
        if WEB_DIST is None:
            raise HTTPException(status_code=404, detail="Web UI not found")
        if path:
            file_path = resolve_within(path, base=WEB_DIST)
            if file_path.is_file():
                return FileResponse(file_path)
        return FileResponse(WEB_DIST / "index.html")
