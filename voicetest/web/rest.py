"""REST API for voicetest.

Transport adapter over the service layer. All business logic lives in
voicetest.services — this module handles HTTP/WebSocket concerns.

Run with: voicetest serve
Or: uvicorn voicetest.web.rest:app --reload
"""

from collections.abc import AsyncIterator
import contextlib
from datetime import UTC
from datetime import datetime
from importlib.metadata import version as pkg_version
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
from sqlalchemy import bindparam
from sqlalchemy import text
from sqlalchemy.orm import Session
from starlette.websockets import WebSocketDisconnect
from starlette.websockets import WebSocketState

from voicetest.container import create_container
from voicetest.demo import get_demo_agent
from voicetest.demo import get_demo_tests
from voicetest.importers.transcripts.retell import parse_retell_file
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
from voicetest.services.agents import AgentService
from voicetest.services.decompose import DecomposeService
from voicetest.services.diagnosis import DiagnosisService
from voicetest.services.discovery import DiscoveryService
from voicetest.services.evaluation import EvaluationService
from voicetest.services.platforms import PlatformService
from voicetest.services.run_runner import RunJob
from voicetest.services.run_runner import RunRunner
from voicetest.services.runs import RunService
from voicetest.services.settings import SettingsService
from voicetest.services.snippets import SnippetService
from voicetest.services.testing.cases import TestCaseService
from voicetest.services.testing.execution import TestExecutionService
from voicetest.services.testing.execution import resolve_run_options
from voicetest.settings import Settings
from voicetest.storage.models import Result as ResultModel
from voicetest.storage.models import Run as RunModel
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import CallRepository
from voicetest.storage.repositories import TestCaseRepository
from voicetest.util.cache import setup_cache_from_settings
from voicetest.util.pathutil import resolve_within
from voicetest.web.calls import CallManager
from voicetest.web.chat import ChatManager
from voicetest.web.coordinator import RunCoordinator


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


def _resolve[T](http_request: Request, cls: type[T]) -> T:
    """Resolve a service/repo/manager from the request-scoped container.

    `app.state.container` is set by the lifespan handler. Endpoints use this helper
    instead of holding services in module globals so per-request scoping (notably
    Postgres Session) works.
    """
    return http_request.app.state.container.resolve(cls)


def _db_session(http_request: Request) -> Session:
    """Resolve the DB session and recover from a failed-transaction state.

    DuckDB uses a singleton session; if its transaction failed, roll back so
    the next query starts clean.
    """
    session = _resolve(http_request, Session)
    if not session.is_active:
        session.rollback()
    return session


_logger = logging.getLogger("voicetest.web.rest")

_ORPHAN_ERROR_MESSAGE = "Run orphaned - backend stopped"

# Pre-compiled SQL for orphan cleanup. Two bulk UPDATEs replace N+1
# round-trips and use guard clauses so a redundant cleanup (e.g. after a
# server restart where the in-memory guard was lost) is a no-op rather
# than overwriting an already-finalized run/result.
_UPDATE_RUN_COMPLETED = text(
    "UPDATE runs SET completed_at = :ts WHERE id = :rid AND completed_at IS NULL"
)
_UPDATE_RESULTS_ORPHANED = text(
    "UPDATE results "
    "SET status = 'error', error_message = :msg "
    "WHERE id IN :rids AND status = 'running'"
).bindparams(bindparam("rids", expanding=True))


def init_storage(container) -> None:
    """Initialize storage (touches Session to create engine) and register linked agents."""
    container.resolve(Session)

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
        agent_repo = container.resolve(AgentRepository)
        for agent_path in linked_agents.split(","):
            agent_path = agent_path.strip()
            if agent_path:
                tests_paths = tests_by_agent.get(agent_path)
                _register_linked_agent(agent_repo, Path(agent_path), tests_paths=tests_paths)


def _register_linked_agent(
    repo: AgentRepository,
    path: Path,
    tests_paths: list[str] | None = None,
) -> None:
    """Register a linked agent from filesystem if not already registered."""
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


def _find_web_dist() -> Path | None:
    """Find the web dist folder relative to the package root."""
    dist = Path(__file__).parent.parent / "web" / "dist"
    return dist if dist.exists() else None


WEB_DIST = _find_web_dist()


@contextlib.asynccontextmanager
async def _lifespan(app: FastAPI):
    """Build the DI container and wire startup work on first request.

    Tests that need to override services pre-populate ``app.state.container``
    before the lifespan runs; in that case we respect their container and
    just run the dependent startup steps against it.
    """
    if not hasattr(app.state, "container"):
        app.state.container = create_container()
    init_storage(app.state.container)
    settings = app.state.container.resolve(SettingsService).get_settings()
    setup_cache_from_settings(settings.cache)
    yield


app = FastAPI(
    title="voicetest",
    description="Voice agent test harness API",
    version=pkg_version("voicetest"),
    lifespan=_lifespan,
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


class GoBackConditionRequest(BaseModel):
    """A go-back condition in a global node setting update."""

    id: str
    condition: str


class UpdateGlobalNodeSettingRequest(BaseModel):
    """Request to set a node's global_node_setting."""

    condition: str
    go_back_conditions: list[GoBackConditionRequest] = []


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
async def list_importers(http_request: Request) -> list[ImporterInfo]:
    """List available importers."""
    importers = _resolve(http_request, DiscoveryService).list_importers()
    return [
        ImporterInfo(
            source_type=imp.source_type,
            description=imp.description,
            file_patterns=imp.file_patterns,
        )
        for imp in importers
    ]


@router.get("/exporters", response_model=list[ExportFormatInfo])
async def list_exporters(http_request: Request) -> list[ExportFormatInfo]:
    """List available export formats."""
    formats = _resolve(http_request, DiscoveryService).list_export_formats()
    return [ExportFormatInfo(**f) for f in formats]


@router.post("/agents/import", response_model=AgentGraph)
async def import_agent(request: ImportRequest, http_request: Request) -> AgentGraph:
    """Import an agent from config."""
    try:
        return await _resolve(http_request, AgentService).import_agent(
            request.config, source=request.source
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/import-file", response_model=AgentGraph)
async def import_agent_file(
    file: UploadFile,
    http_request: Request,
    source: str | None = None,
) -> AgentGraph:
    """Import an agent from an uploaded file (XLSForm, JSON, etc.)."""
    try:
        async with _saved_upload(file) as tmp_path:
            return await _resolve(http_request, AgentService).import_agent(tmp_path, source=source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/export")
async def export_agent(request: ExportRequest, http_request: Request) -> dict[str, str]:
    """Export an agent graph to a format."""
    try:
        content = await _resolve(http_request, AgentService).export_agent(
            request.graph, format=request.format, expanded=request.expanded
        )
        return {"content": content, "format": request.format}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/runs/single", response_model=TestResult)
async def run_test(request: RunTestRequest, http_request: Request) -> TestResult:
    """Run a single test case."""
    return await _resolve(http_request, TestExecutionService).run_test(
        request.graph,
        request.test_case,
        options=request.options,
    )


@router.post("/runs", response_model=TestRun)
async def run_tests(request: RunTestsRequest, http_request: Request) -> TestRun:
    """Run multiple test cases."""
    return await _resolve(http_request, TestExecutionService).run_tests(
        request.graph,
        request.test_cases,
        options=request.options,
    )


@router.post("/evaluate", response_model=list[MetricResult])
async def evaluate_transcript(
    request: EvaluateRequest, http_request: Request
) -> list[MetricResult]:
    """Evaluate a transcript against metrics."""
    return await _resolve(http_request, EvaluationService).evaluate_transcript(
        request.transcript,
        request.metrics,
    )


@router.get("/settings", response_model=Settings)
async def get_settings(http_request: Request) -> Settings:
    """Get current settings from .voicetest.toml."""
    return _resolve(http_request, SettingsService).get_settings()


@router.get("/settings/defaults", response_model=Settings)
async def get_default_settings(http_request: Request) -> Settings:
    """Get default settings (not from file)."""
    return _resolve(http_request, SettingsService).get_defaults()


@router.put("/settings", response_model=Settings)
async def update_settings(settings: Settings, http_request: Request) -> Settings:
    """Update settings in .voicetest.toml."""
    return _resolve(http_request, SettingsService).update_settings(settings)


@router.get("/agents")
async def list_agents(http_request: Request) -> list[dict]:
    """List all agents."""
    return _resolve(http_request, AgentService).list_agents()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str, http_request: Request) -> dict:
    """Get agent by ID."""
    return _require_agent(http_request, agent_id)


@router.get("/agents/{agent_id}/graph", response_model=None)
async def get_agent_graph(
    agent_id: str,
    response: Response,
    http_request: Request,
    if_none_match: str | None = Header(default=None),
) -> AgentGraph | Response:
    """Get the AgentGraph for an agent.

    For linked agents (source_path), uses file mtime for ETag-based caching.
    Returns 304 Not Modified if the file hasn't changed.
    """
    svc = _resolve(http_request, AgentService)
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
async def get_agent_variables(agent_id: str, http_request: Request) -> dict:
    """Extract dynamic variable names from agent prompts.

    Scans general_prompt and all node state_prompt values for {{var}} placeholders.
    Returns unique variable names in first-appearance order.
    """
    svc = _resolve(http_request, AgentService)
    try:
        variables = svc.get_variables(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return {"variables": variables}


def _require_agent(http_request: Request, agent_id: str) -> dict:
    """Get agent or raise 404."""
    agent = _resolve(http_request, AgentService).get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


@contextlib.asynccontextmanager
async def _saved_upload(file: UploadFile) -> AsyncIterator[Path]:
    """Save an UploadFile to a temp path; remove it on exit.

    Yields the Path. Raises HTTPException(400) if no filename was provided.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    suffix = Path(file.filename).suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = Path(tmp.name)
    try:
        yield tmp_path
    finally:
        tmp_path.unlink(missing_ok=True)


def _load_agent_graph(http_request: Request, agent_id: str) -> tuple[dict, AgentGraph]:
    """Load agent record and its graph. Raises HTTPException on failure."""
    try:
        return _resolve(http_request, AgentService).load_graph(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/agents/{agent_id}/snippets")
async def get_snippets(agent_id: str, http_request: Request) -> dict:
    """Get all snippets defined for an agent."""
    svc = _resolve(http_request, SnippetService)
    try:
        return {"snippets": svc.get_snippets(agent_id)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/snippets")
async def update_all_snippets(agent_id: str, body: dict, http_request: Request) -> dict:
    """Replace all snippets for an agent."""
    svc = _resolve(http_request, SnippetService)
    try:
        return {"snippets": svc.update_all_snippets(agent_id, body.get("snippets", {}))}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/snippets/{name}")
async def update_snippet(
    agent_id: str, name: str, request: UpdateSnippetRequest, http_request: Request
) -> dict:
    """Create or update a single snippet."""
    svc = _resolve(http_request, SnippetService)
    try:
        return {"snippets": svc.update_snippet(agent_id, name, request.text)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/agents/{agent_id}/snippets/{name}")
async def delete_snippet(agent_id: str, name: str, http_request: Request) -> dict:
    """Delete a single snippet."""
    svc = _resolve(http_request, SnippetService)
    try:
        return {"snippets": svc.delete_snippet(agent_id, name)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents/{agent_id}/analyze-dry")
async def analyze_dry(agent_id: str, http_request: Request) -> dict:
    """Run auto-DRY analysis on an agent's prompts."""
    svc = _resolve(http_request, SnippetService)
    try:
        return svc.analyze_dry(agent_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents/{agent_id}/apply-snippets", response_model=AgentGraph)
async def apply_snippets(
    agent_id: str, request: ApplySnippetsRequest, http_request: Request
) -> AgentGraph:
    """Apply snippets: add them to graph and replace occurrences in prompts with {%name%} refs."""
    svc = _resolve(http_request, SnippetService)
    try:
        return svc.apply_snippets(agent_id, request.snippets)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


_SUPPORTED_TRANSCRIPT_FORMATS = {"retell"}


@router.post("/agents/{agent_id}/import-call")
async def import_call(
    agent_id: str,
    file: UploadFile,
    http_request: Request,
    format: str = "retell",
) -> dict:
    """Import call transcripts as a new Run with imported Results.

    The uploaded file's content is parsed by a platform-specific adapter
    (currently Retell only). Each conversation in the file becomes one Result
    inside the created Run, with status="imported" and no test_case_id linkage.
    """
    _require_agent(http_request, agent_id)

    if format not in _SUPPORTED_TRANSCRIPT_FORMATS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported format: {format!r}. "
                f"Supported: {sorted(_SUPPORTED_TRANSCRIPT_FORMATS)}"
            ),
        )

    try:
        async with _saved_upload(file) as tmp_path:
            results = parse_retell_file(tmp_path)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    if not results:
        raise HTTPException(status_code=400, detail="No conversations found in file")

    return _resolve(http_request, RunService).import_calls(agent_id, results)


@router.post("/agents")
async def create_agent(request: CreateAgentRequest, http_request: Request) -> dict:
    """Create an agent from config dict or file path."""
    svc = _resolve(http_request, AgentService)
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
    http_request: Request,
    name: str | None = None,
    source: str | None = None,
) -> dict:
    """Create an agent from an uploaded file (XLSForm, JSON, etc.)."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    agent_name = name or Path(file.filename).stem
    agent_svc = _resolve(http_request, AgentService)

    try:
        async with _saved_upload(file) as tmp_path:
            graph = await agent_svc.import_agent(tmp_path, source=source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    repo = _resolve(http_request, AgentRepository)
    return repo.create(
        name=agent_name,
        source_type=graph.source_type,
        graph_json=graph.model_dump_json(),
    )


@router.put("/agents/{agent_id}")
async def update_agent(agent_id: str, request: UpdateAgentRequest, http_request: Request) -> dict:
    """Update an agent."""
    try:
        return _resolve(http_request, AgentService).update_agent(
            agent_id,
            name=request.name,
            default_model=request.default_model,
            graph_json=request.graph_json,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/prompts", response_model=AgentGraph)
async def update_prompt(
    agent_id: str, request: UpdatePromptRequest, http_request: Request
) -> AgentGraph:
    """Update a general or node-specific prompt.

    When node_id is None, updates source_metadata.general_prompt.
    When node_id is set, updates that node's state_prompt.
    For linked-file agents, writes back to the source file on disk.
    """
    try:
        return _resolve(http_request, AgentService).update_prompt(
            agent_id,
            prompt_text=request.prompt_text,
            node_id=request.node_id,
            transition_target_id=request.transition_target_id,
        )
    except ValueError as e:
        detail = str(e)
        status = 400 if "Cannot write" in detail else 404
        raise HTTPException(status_code=status, detail=detail) from None


@router.put("/agents/{agent_id}/nodes/{node_id}/global-setting", response_model=AgentGraph)
async def update_global_node_setting(
    agent_id: str,
    node_id: str,
    request: UpdateGlobalNodeSettingRequest,
    http_request: Request,
) -> AgentGraph:
    """Set a node's global_node_setting (entry condition + go-back conditions)."""
    setting = {
        "condition": request.condition,
        "go_back_conditions": [
            {"id": gb.id, "condition": gb.condition} for gb in request.go_back_conditions
        ],
    }
    try:
        return _resolve(http_request, AgentService).update_global_node_setting(
            agent_id, node_id, setting
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/agents/{agent_id}/nodes/{node_id}/global-setting", response_model=AgentGraph)
async def delete_global_node_setting(
    agent_id: str, node_id: str, http_request: Request
) -> AgentGraph:
    """Remove a node's global_node_setting."""
    try:
        return _resolve(http_request, AgentService).update_global_node_setting(
            agent_id, node_id, None
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.put("/agents/{agent_id}/metadata", response_model=AgentGraph)
async def update_metadata(
    agent_id: str, request: UpdateMetadataRequest, http_request: Request
) -> AgentGraph:
    """Merge updates into an agent's source_metadata."""
    try:
        return _resolve(http_request, AgentService).update_metadata(agent_id, request.updates)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str, http_request: Request) -> dict:
    """Delete an agent."""
    _resolve(http_request, AgentService).delete_agent(agent_id)
    return {"status": "deleted", "id": agent_id}


@router.get("/agents/{agent_id}/metrics-config")
async def get_metrics_config(agent_id: str, http_request: Request) -> dict:
    """Get an agent's metrics configuration."""
    _require_agent(http_request, agent_id)
    config = _resolve(http_request, AgentService).get_metrics_config(agent_id)
    return config.model_dump()


@router.put("/agents/{agent_id}/metrics-config")
async def update_metrics_config(
    agent_id: str, request: UpdateMetricsConfigRequest, http_request: Request
) -> dict:
    """Update an agent's metrics configuration."""
    _require_agent(http_request, agent_id)
    config = MetricsConfig(
        threshold=request.threshold,
        global_metrics=request.global_metrics,
    )
    _resolve(http_request, AgentService).update_metrics_config(agent_id, config)
    return config.model_dump()


@router.get("/agents/{agent_id}/tests")
async def list_tests_for_agent(agent_id: str, http_request: Request) -> list[dict]:
    """List all test cases for an agent, including file-based linked tests."""
    return _resolve(http_request, TestCaseService).list_tests(agent_id)


@router.post("/agents/{agent_id}/tests-paths")
async def link_test_file(
    agent_id: str, request: LinkTestFileRequest, http_request: Request
) -> dict:
    """Link a JSON test file to an agent.

    The file must exist, contain valid JSON, and be a JSON array.
    Tests from the file will appear alongside DB tests via list_for_agent_with_linked.
    """
    try:
        return _resolve(http_request, TestCaseService).link_test_file(agent_id, request.path)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        detail = str(e)
        status = 409 if "already linked" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from None


@router.delete("/agents/{agent_id}/tests-paths")
async def unlink_test_file(agent_id: str, path: str, http_request: Request) -> dict:
    """Unlink a test file from an agent.

    Removes the path from tests_paths. The file itself is not deleted.
    """
    try:
        return _resolve(http_request, TestCaseService).unlink_test_file(agent_id, path)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents/{agent_id}/tests/export")
async def export_tests_for_agent(
    agent_id: str, request: ExportTestsRequest, http_request: Request
) -> list[dict]:
    """Export test cases for an agent to a specified format."""
    try:
        return _resolve(http_request, TestCaseService).export_tests(
            agent_id, request.test_ids, request.format
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/{agent_id}/tests")
async def create_test_case(
    agent_id: str, request: CreateTestCaseRequest, http_request: Request
) -> dict:
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

    return _resolve(http_request, TestCaseService).create_test(agent_id, test_case)


@router.put("/tests/{test_id}")
async def update_test_case(
    test_id: str, request: CreateTestCaseRequest, http_request: Request
) -> dict:
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
        return _resolve(http_request, TestCaseService).update_test(test_id, test_case)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.delete("/tests/{test_id}")
async def delete_test_case(test_id: str, http_request: Request) -> dict:
    """Delete a test case (DB or linked file)."""
    try:
        _resolve(http_request, TestCaseService).delete_test(test_id)
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
async def load_demo(http_request: Request) -> LoadDemoResponse:
    """Load demo agent and tests into the database.

    If the demo agent already exists, returns its info without creating duplicates.
    """
    demo_agent_config = get_demo_agent()
    demo_tests = get_demo_tests()

    graph = await _resolve(http_request, AgentService).import_agent(demo_agent_config)

    agent_repo = _resolve(http_request, AgentRepository)
    test_repo = _resolve(http_request, TestCaseRepository)

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
async def list_runs_for_agent(agent_id: str, http_request: Request, limit: int = 50) -> list[dict]:
    """List all runs for an agent."""
    return _resolve(http_request, RunService).list_runs(agent_id, limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str, http_request: Request) -> dict:
    """Get a run with all results."""
    run_svc = _resolve(http_request, RunService)
    run = run_svc.get_run(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Detect orphaned run: not completed but not actively running.
    # Correct the response dict immediately so the client sees accurate state,
    # and persist the cleanup inline using 2 bulk UPDATEs on the singleton
    # session (already holds the pool's only connection — spawning a separate
    # session would deadlock waiting for that slot). The cleanup slot is
    # single-flighted per run_id; concurrent clicks see owns=False and skip
    # straight to the response while the writes happen exactly once.
    coordinator = _resolve(http_request, RunCoordinator)
    if run["completed_at"] is None and not coordinator.is_active(run_id):
        run["completed_at"] = datetime.now(UTC).isoformat()

        orphaned_result_ids: list[str] = []
        for result in run["results"]:
            if result["status"] == "running":
                orphaned_result_ids.append(result["id"])
                result["status"] = "error"
                result["error_message"] = _ORPHAN_ERROR_MESSAGE

        with coordinator.claim_orphan_cleanup(run_id) as owns:
            if owns:
                _cleanup_orphaned_run(http_request, run_id, orphaned_result_ids)

    return run


def _cleanup_orphaned_run(http_request: Request, run_id: str, result_ids: list[str]) -> None:
    """Persist orphan-cleanup state to DB using the singleton session.

    Issues 2 bulk UPDATEs (run + results) with guard clauses so they're
    no-ops if the rows were already finalized by an earlier cleanup. DB
    errors are logged and swallowed: the in-memory response dict is
    already correctly patched, so the client gets the right view even if
    persistence fails — and the next GET will re-attempt the cleanup.
    """
    _logger.info("orphan-cleanup start run=%s n_results=%d", run_id, len(result_ids))
    try:
        session = _db_session(http_request)
        session.execute(
            _UPDATE_RUN_COMPLETED,
            {"ts": datetime.now(UTC), "rid": run_id},
        )
        if result_ids:
            session.execute(
                _UPDATE_RESULTS_ORPHANED,
                {"rids": result_ids, "msg": _ORPHAN_ERROR_MESSAGE},
            )
        session.commit()
        _logger.info("orphan-cleanup committed run=%s", run_id)
    except Exception:
        _logger.exception("orphan-cleanup failed run=%s", run_id)


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str, http_request: Request) -> dict:
    """Delete a run and all its results."""
    run_svc = _resolve(http_request, RunService)
    if not run_svc.get_run(run_id):
        raise HTTPException(status_code=404, detail="Run not found")

    if _resolve(http_request, RunCoordinator).is_active(run_id):
        raise HTTPException(status_code=400, detail="Cannot delete an active run")

    run_svc.delete_run(run_id)
    return {"status": "deleted", "id": run_id}


@router.post("/runs/{source_run_id}/replay")
async def replay_run(source_run_id: str, http_request: Request) -> dict:
    """Replay a source Run against the agent's current graph.

    Loads the source Run, drives a fresh conversation per source Result using
    the source's recorded user turns as a script, and persists the live
    conversations as a new Run.
    """
    run_svc = _resolve(http_request, RunService)
    source = run_svc.get_run(source_run_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source run not found")

    _agent, graph = _load_agent_graph(http_request, source["agent_id"])

    try:
        return await run_svc.replay_run(source_run_id, graph)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/results/{result_id}/audio-eval")
async def audio_eval_result(result_id: str, http_request: Request) -> dict:
    """Run audio evaluation on an existing test result.

    Performs TTS->STT round-trip on assistant messages and re-evaluates
    metrics using the "heard" text.
    """
    run_svc = _resolve(http_request, RunService)
    tc_svc = _resolve(http_request, TestCaseService)

    session = _db_session(http_request)
    db_result = session.get(ResultModel, result_id)
    if not db_result:
        raise HTTPException(status_code=404, detail="Result not found")

    result_dict = run_svc.result_to_dict(db_result)
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
    metrics_config = (
        _resolve(http_request, AgentService).get_metrics_config(run.agent_id) if run else None
    )

    transformed, audio_metrics = await _resolve(http_request, EvaluationService).audio_eval_result(
        transcript,
        test_case,
        metrics_config=metrics_config,
    )

    # Update stored result with audio eval data
    run_svc.update_audio_eval(result_id, transformed, audio_metrics)

    # Return updated result
    session.refresh(db_result)
    return run_svc.result_to_dict(db_result)


def _load_result_context(
    http_request: Request, result_id: str
) -> tuple[dict, "TestCase", AgentGraph]:
    """Load result, test case, and agent graph for diagnosis endpoints.

    Returns:
        Tuple of (result_dict, test_case, agent_graph).

    Raises:
        HTTPException on missing data.
    """
    run_svc = _resolve(http_request, RunService)
    tc_svc = _resolve(http_request, TestCaseService)

    session = _db_session(http_request)
    db_result = session.get(ResultModel, result_id)
    if not db_result:
        raise HTTPException(status_code=404, detail="Result not found")

    result_dict = run_svc.result_to_dict(db_result)

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

    _agent, graph = _load_agent_graph(http_request, run.agent_id)

    return result_dict, test_case, graph


@router.post("/results/{result_id}/diagnose")
async def diagnose_result(result_id: str, http_request: Request) -> dict:
    """Diagnose why a test result failed and suggest a fix.

    Analyzes the graph structure, transcript, and failed metrics to identify
    the root cause and propose concrete prompt/transition changes.

    Optional body: {"model": "provider/model-name"} to override the judge model.
    """
    result_dict, test_case, graph = _load_result_context(http_request, result_id)

    try:
        body = await http_request.json()
    except Exception:
        body = {}

    transcript_data = result_dict.get("transcript_json") or []
    transcript = [Message(**m) for m in transcript_data]

    metrics_data = result_dict.get("metrics_json") or []
    metric_results = [MetricResult(**m) for m in metrics_data]
    nodes_visited = result_dict.get("nodes_visited") or []

    diagnosis_result = await _resolve(http_request, DiagnosisService).diagnose_failure(
        graph=graph,
        transcript=transcript,
        nodes_visited=nodes_visited,
        failed_metrics=metric_results,
        test_scenario=test_case.user_prompt,
        judge_model=body.get("model"),
    )

    return diagnosis_result.model_dump()


@router.post("/results/{result_id}/apply-fix")
async def apply_fix(result_id: str, body: dict, http_request: Request) -> dict:
    """Apply proposed changes to a copy of the graph and rerun the test.

    Non-destructive: does not persist changes.
    """
    result_dict, test_case, graph = _load_result_context(http_request, result_id)

    changes = [PromptChangeModel.model_validate(c) for c in body.get("changes", [])]
    iteration = body.get("iteration", 1)

    metrics_data = result_dict.get("metrics_json") or []
    original_metrics = [MetricResult(**m) for m in metrics_data]

    # Load metrics config for global metrics
    session = _db_session(http_request)
    db_result = session.get(ResultModel, result_id)
    run = session.get(RunModel, db_result.run_id)
    metrics_config = (
        _resolve(http_request, AgentService).get_metrics_config(run.agent_id) if run else None
    )

    attempt_result = await _resolve(http_request, DiagnosisService).apply_and_rerun(
        graph=graph,
        test_case=test_case,
        changes=changes,
        original_metrics=original_metrics,
        iteration=iteration,
        metrics_config=metrics_config,
    )

    return attempt_result.model_dump()


@router.post("/results/{result_id}/revise-fix")
async def revise_fix_endpoint(result_id: str, body: dict, http_request: Request) -> dict:
    """Revise a previous fix attempt based on new metric results.

    Given the original diagnosis and previous changes, produce a revised fix.

    Optional body field: "model" to override the judge model.
    """
    result_dict, test_case, graph = _load_result_context(http_request, result_id)

    diagnosis = DiagnosisModel.model_validate(body["diagnosis"])
    prev_changes = [PromptChangeModel.model_validate(c) for c in body["previous_changes"]]
    new_metrics = [MetricResult.model_validate(m) for m in body["new_metric_results"]]

    fix = await _resolve(http_request, DiagnosisService).revise_fix(
        graph=graph,
        diagnosis=diagnosis,
        prev_changes=prev_changes,
        new_metrics=new_metrics,
        judge_model=body.get("model"),
    )

    return fix.model_dump()


@router.post("/agents/{agent_id}/save-fix")
async def save_fix(agent_id: str, body: dict, http_request: Request) -> dict:
    """Persist proposed changes to the agent graph.

    Applies changes and saves the modified graph.
    """
    agent, graph = _load_agent_graph(http_request, agent_id)
    changes = [PromptChangeModel.model_validate(c) for c in body.get("changes", [])]

    modified_graph = _resolve(http_request, DiagnosisService).apply_fix_to_graph(graph, changes)
    _resolve(http_request, AgentService).save_graph(agent_id, agent, modified_graph)

    return modified_graph.model_dump()


@router.post("/agents/{agent_id}/decompose")
async def decompose_agent(agent_id: str, http_request: Request) -> dict:
    """Decompose an agent into sub-agents with orchestrator manifest.

    Optional body: {"model": "provider/model-name", "num_agents": 0}
    """
    _agent, graph = _load_agent_graph(http_request, agent_id)

    try:
        body = await http_request.json()
    except Exception:
        body = {}

    result = await _resolve(http_request, DecomposeService).decompose(
        graph=graph,
        model=body.get("model"),
        num_agents=body.get("num_agents", 0),
    )

    return result.model_dump()


@router.websocket("/runs/{run_id}/ws")
async def run_websocket(websocket: WebSocket, run_id: str):
    """WebSocket for streaming run updates and receiving cancel commands."""
    container = websocket.app.state.container
    coordinator = container.resolve(RunCoordinator)

    try:
        await websocket.accept()
    except Exception as e:
        print(f"[WS] Failed to accept connection for run {run_id}: {e}")
        return

    # Send current state BEFORE registering for broadcasts to avoid race condition
    # where test_started arrives before state and then state overwrites it
    try:
        run = container.resolve(RunService).get_run(run_id)
        if not run:
            # Run not found - send error and close
            await websocket.send_json({"type": "error", "message": "Run not found"})
            await websocket.close(code=1008)  # Policy violation
            return
        msg = json.dumps({"type": "state", "run": run})
        await websocket.send_text(msg)

        # If run is already complete, send run_completed and close
        if run.get("completed_at") and not coordinator.is_active(run_id):
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

    # attach() replays any queued messages before subscribing to broadcasts,
    # under a per-run lock that blocks new broadcasts from interleaving.
    await coordinator.attach(run_id, websocket)

    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "cancel_test":
                result_id = data.get("result_id")
                if result_id:
                    coordinator.cancel_test(run_id, result_id)
            elif data.get("type") == "cancel_run":
                coordinator.cancel_run(run_id)
    except WebSocketDisconnect:
        # Normal disconnect - client closed connection
        pass
    except Exception as e:
        print(f"[WS] Exception in websocket handler for run {run_id}: {type(e).__name__}: {e}")
    finally:
        coordinator.detach(run_id, websocket)


@router.post("/agents/{agent_id}/runs")
async def start_run(
    agent_id: str,
    request: StartRunRequest,
    background_tasks: BackgroundTasks,
    http_request: Request,
) -> dict:
    """Start a new test run. Tests execute in background, poll GET /runs/{id} for results."""
    _require_agent(http_request, agent_id)

    tc_svc = _resolve(http_request, TestCaseService)
    all_tests = tc_svc.list_tests(agent_id)

    if request.test_ids:
        tests_by_id = {t["id"]: t for t in all_tests}
        test_records = [tests_by_id[tid] for tid in request.test_ids if tid in tests_by_id]
    else:
        test_records = all_tests

    if not test_records:
        raise HTTPException(status_code=400, detail="No test cases to run")

    run_svc = _resolve(http_request, RunService)
    run = run_svc.create_run(agent_id)

    # Create all pending results upfront so they appear immediately in UI
    # Map test_case_id -> result_id for the background task to use
    result_ids: dict[str, str] = {}
    for test_record in test_records:
        result_id = run_svc.create_pending_result(run["id"], test_record["id"], test_record["name"])
        result_ids[test_record["id"]] = result_id

    options = resolve_run_options(request.options, _resolve(http_request, SettingsService))

    # Register the run with the coordinator BEFORE the background task starts
    # so WebSocket connections can register immediately.
    _resolve(http_request, RunCoordinator).start(run["id"])

    # Create job and submit to executor
    job = RunJob(
        run_id=run["id"],
        agent_id=agent_id,
        test_records=test_records,
        result_ids=result_ids,
        options=options,
    )

    background_tasks.add_task(_resolve(http_request, RunRunner).execute, job)

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
async def get_livekit_status(http_request: Request) -> LiveKitStatusResponse:
    """Check if LiveKit server is reachable."""
    call_manager = _resolve(http_request, CallManager)

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
async def start_call(
    agent_id: str,
    http_request: Request,
    request: StartCallRequest | None = None,
) -> StartCallResponse:
    """Start a live voice call with an agent.

    Creates a LiveKit room and spawns an agent worker subprocess.
    Returns connection info including a token for the browser to join.
    """
    try:
        _agent, graph = _resolve(http_request, AgentService).load_graph(agent_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot load agent graph: {e}") from None

    call_repo = _resolve(http_request, CallRepository)
    call_manager = _resolve(http_request, CallManager)

    dynamic_variables = request.dynamic_variables if request else {}

    try:
        call_info = await call_manager.start_call(
            agent_id,
            graph,
            call_repo,
            dynamic_variables=dynamic_variables or None,
        )
        return StartCallResponse(**call_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start call: {e}") from None


@router.get("/calls/{call_id}", response_model=CallStatusResponse)
async def get_call(call_id: str, http_request: Request) -> CallStatusResponse:
    """Get call status and transcript."""
    call_repo = _resolve(http_request, CallRepository)
    call = call_repo.get(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call_manager = _resolve(http_request, CallManager)
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
async def end_call(call_id: str, http_request: Request) -> dict:
    """End a live call and save the transcript as a run."""
    call_repo = _resolve(http_request, CallRepository)
    call = call_repo.get(call_id)
    if not call:
        raise HTTPException(status_code=404, detail="Call not found")

    call_manager = _resolve(http_request, CallManager)

    try:
        await call_manager.end_call(call_id, call_repo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end call: {e}") from None

    # Re-fetch call to get final transcript and timestamps
    call = call_repo.get(call_id)
    run_id = await _resolve(http_request, RunService).save_call_as_run(call)

    return {"status": "ended", "call_id": call_id, "run_id": run_id}


@router.websocket("/calls/{call_id}/ws")
async def call_websocket(websocket: WebSocket, call_id: str):
    """WebSocket for streaming call updates (transcript, status)."""
    try:
        await websocket.accept()
    except Exception:
        return

    container = websocket.app.state.container
    call_repo = container.resolve(CallRepository)
    call = call_repo.get(call_id)
    if not call:
        await websocket.send_json({"type": "error", "message": "Call not found"})
        await websocket.close(code=1008)
        return

    call_manager = container.resolve(CallManager)

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

        await call_manager.attach_websocket(call_id, websocket)

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
        call_manager.detach_websocket(call_id, websocket)


# Text chat endpoints


@router.post("/agents/{agent_id}/chats/start", response_model=StartChatResponse)
async def start_chat(
    agent_id: str,
    http_request: Request,
    request: StartChatRequest | None = None,
) -> StartChatResponse:
    """Start a text chat session with an agent.

    Creates a ConversationEngine in-process (no LiveKit or subprocess needed).
    Returns a chat_id for WebSocket connection.
    """
    try:
        _agent, graph = _resolve(http_request, AgentService).load_graph(agent_id)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot load agent graph: {e}") from None

    call_repo = _resolve(http_request, CallRepository)
    chat_manager = _resolve(http_request, ChatManager)

    dynamic_variables = request.dynamic_variables if request else {}

    try:
        chat_info = await chat_manager.start_chat(
            agent_id,
            graph,
            call_repo,
            dynamic_variables=dynamic_variables or None,
        )
        return StartChatResponse(**chat_info)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start chat: {e}") from None


@router.post("/chats/{chat_id}/end")
async def end_chat_session(chat_id: str, http_request: Request) -> dict:
    """End a text chat session and save the transcript as a run."""
    call_repo = _resolve(http_request, CallRepository)
    call = call_repo.get(chat_id)
    if not call:
        raise HTTPException(status_code=404, detail="Chat not found")

    chat_manager = _resolve(http_request, ChatManager)

    try:
        await chat_manager.end_chat(chat_id, call_repo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to end chat: {e}") from None

    # Re-fetch call to get final transcript and timestamps
    call = call_repo.get(chat_id)
    run_id = await _resolve(http_request, RunService).save_call_as_run(call)

    return {"status": "ended", "chat_id": chat_id, "run_id": run_id}


@router.websocket("/chats/{chat_id}/ws")
async def chat_websocket(websocket: WebSocket, chat_id: str):
    """WebSocket for text chat: send messages, receive streaming responses."""
    try:
        await websocket.accept()
    except Exception:
        return

    container = websocket.app.state.container
    call_repo = container.resolve(CallRepository)
    call = call_repo.get(chat_id)
    if not call:
        await websocket.send_json({"type": "error", "message": "Chat not found"})
        await websocket.close(code=1008)
        return

    chat_manager = container.resolve(ChatManager)

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

        # Subscribe to broadcasts (replays any queued backlog atomically)
        await chat_manager.attach_websocket(chat_id, websocket)

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
        chat_manager.detach_websocket(chat_id, websocket)


# Platform integration endpoints


@router.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms(http_request: Request) -> list[PlatformInfo]:
    """List all available platforms and their configuration status."""
    platforms = _resolve(http_request, PlatformService).list_platforms()
    return [PlatformInfo(**p) for p in platforms]


@router.get("/platforms/{platform}/status", response_model=PlatformStatusResponse)
async def get_platform_status(platform: str, http_request: Request) -> PlatformStatusResponse:
    """Check if a platform API key is configured."""
    try:
        result = _resolve(http_request, PlatformService).get_status(platform)
        return PlatformStatusResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/platforms/{platform}/configure", response_model=PlatformStatusResponse)
async def configure_platform(
    platform: str, request: ConfigurePlatformRequest, http_request: Request
) -> PlatformStatusResponse:
    """Configure platform credentials. Returns 409 if already configured."""
    try:
        result = _resolve(http_request, PlatformService).configure(
            platform, request.api_key, request.api_secret
        )
        return PlatformStatusResponse(**result)
    except ValueError as e:
        detail = str(e)
        status = 409 if "already configured" in detail.lower() else 400
        raise HTTPException(status_code=status, detail=detail) from None


@router.get("/platforms/{platform}/agents", response_model=list[RemoteAgentInfo])
async def list_platform_agents(platform: str, http_request: Request) -> list[RemoteAgentInfo]:
    """List agents from any supported platform."""
    try:
        agents = _resolve(http_request, PlatformService).list_remote_agents(platform)
        return [RemoteAgentInfo(**a) for a in agents]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list {platform} agents: {e}"
        ) from None


@router.post("/platforms/{platform}/agents/{agent_id}/import", response_model=AgentGraph)
async def import_platform_agent(platform: str, agent_id: str, http_request: Request) -> AgentGraph:
    """Import an agent from any supported platform by ID."""
    try:
        return _resolve(http_request, PlatformService).import_from_platform(platform, agent_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to import {platform} agent: {e}"
        ) from None


@router.post("/platforms/{platform}/export", response_model=ExportToPlatformResponse)
async def export_to_platform(
    platform: str, request: ExportToPlatformRequest, http_request: Request
) -> ExportToPlatformResponse:
    """Export an agent graph to any supported platform."""
    try:
        result = _resolve(http_request, PlatformService).export_to_platform(
            platform, request.graph, request.name
        )
        return ExportToPlatformResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export to {platform}: {e}"
        ) from None


@router.get("/agents/{agent_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(agent_id: str, http_request: Request) -> SyncStatusResponse:
    """Check if an agent can be synced to its source platform."""
    _require_agent(http_request, agent_id)
    result = _resolve(http_request, PlatformService).get_sync_status(agent_id)
    return SyncStatusResponse(**result)


@router.post("/agents/{agent_id}/sync", response_model=SyncToPlatformResponse)
async def sync_to_platform(
    agent_id: str, request: SyncToPlatformRequest, http_request: Request
) -> SyncToPlatformResponse:
    """Sync an agent to its source platform."""
    _require_agent(http_request, agent_id)
    try:
        result = _resolve(http_request, PlatformService).sync_to_platform(agent_id, request.graph)
        return SyncToPlatformResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to sync: {e}") from None


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
