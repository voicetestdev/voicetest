"""REST API for voicetest.

Thin wrapper over the core API (voicetest.api). All business logic
lives in api.py - this module just handles HTTP concerns.

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

from voicetest import api
from voicetest.calls import get_call_manager
from voicetest.chat import get_chat_manager
from voicetest.container import get_container
from voicetest.container import get_exporter_registry
from voicetest.container import get_importer_registry
from voicetest.container import get_session
from voicetest.demo import get_demo_agent
from voicetest.demo import get_demo_tests
from voicetest.executor import RunJob
from voicetest.executor import get_executor_factory
from voicetest.exporters.test_cases import export_tests
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
from voicetest.pathutil import resolve_file
from voicetest.pathutil import resolve_path
from voicetest.pathutil import resolve_within
from voicetest.platforms.registry import PlatformRegistry
from voicetest.retry import RetryError
from voicetest.settings import Settings
from voicetest.settings import load_settings
from voicetest.settings import resolve_model
from voicetest.settings import save_settings
from voicetest.snippets import suggest_snippets
from voicetest.storage.linked_file import check_file
from voicetest.storage.linked_file import compute_etag
from voicetest.storage.linked_file import write_json
from voicetest.storage.models import Result as ResultModel
from voicetest.storage.models import Run as RunModel
from voicetest.storage.repositories import AgentRepository
from voicetest.storage.repositories import CallRepository
from voicetest.storage.repositories import RunRepository
from voicetest.storage.repositories import TestCaseRepository
from voicetest.templating import expand_graph_snippets
from voicetest.templating import extract_variables


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


def get_agent_repo() -> AgentRepository:
    """Get the agent repository from the DI container."""
    if not _initialized:
        init_storage()
    return get_container().resolve(AgentRepository)


def get_test_case_repo() -> TestCaseRepository:
    """Get the test case repository from the DI container."""
    if not _initialized:
        init_storage()
    return get_container().resolve(TestCaseRepository)


def get_run_repo() -> RunRepository:
    """Get the run repository from the DI container."""
    if not _initialized:
        init_storage()
    return get_container().resolve(RunRepository)


def get_call_repo() -> CallRepository:
    """Get the call repository from the DI container."""
    if not _initialized:
        init_storage()
    return get_container().resolve(CallRepository)


def _find_linked_test(test_id: str) -> dict | None:
    """Search all agents' linked test files for a test with the given ID.

    Returns the matching test dict (with source_path/source_index) or None.
    """
    agent_repo = get_agent_repo()
    test_repo = get_test_case_repo()

    for agent in agent_repo.list_all():
        tests_paths = agent.get("tests_paths")
        if not tests_paths:
            continue
        linked = test_repo.list_for_agent_with_linked(agent["id"], tests_paths)
        for t in linked:
            if t["id"] == test_id and t.get("source_path"):
                return t

    return None


def _find_web_dist() -> Path | None:
    """Find the web dist folder, checking both dev and installed locations."""
    # Development: relative to package root
    dev_path = Path(__file__).parent.parent / "web" / "dist"
    if dev_path.exists():
        return dev_path

    # Installed: in site-packages alongside voicetest
    installed_path = Path(__file__).parent.parent / "web" / "dist"
    if installed_path.exists():
        return installed_path

    return None


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
    importers = api.list_importers()
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
    formats = api.list_export_formats()
    return [ExportFormatInfo(**f) for f in formats]


@router.post("/agents/import", response_model=AgentGraph)
async def import_agent(request: ImportRequest) -> AgentGraph:
    """Import an agent from config."""
    try:
        return await api.import_agent(request.config, source=request.source)
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
            return await api.import_agent(tmp_path, source=source)
        finally:
            Path(tmp_path).unlink(missing_ok=True)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@router.post("/agents/export")
async def export_agent(request: ExportRequest) -> dict[str, str]:
    """Export an agent graph to a format."""
    try:
        graph = request.graph
        if request.expanded and graph.snippets:
            graph = expand_graph_snippets(graph)
        content = await api.export_agent(graph, format=request.format)
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
    return await api.run_test(
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
    return await api.run_tests(
        request.graph,
        request.test_cases,
        options=options,
    )


@router.post("/evaluate", response_model=list[MetricResult])
async def evaluate_transcript(request: EvaluateRequest) -> list[MetricResult]:
    """Evaluate a transcript against metrics."""
    return await api.evaluate_transcript(
        request.transcript,
        request.metrics,
    )


@router.get("/settings", response_model=Settings)
async def get_settings() -> Settings:
    """Get current settings from .voicetest.toml."""
    return load_settings()


@router.get("/settings/defaults", response_model=Settings)
async def get_default_settings() -> Settings:
    """Get default settings (not from file)."""
    return Settings()


@router.put("/settings", response_model=Settings)
async def update_settings(settings: Settings) -> Settings:
    """Update settings in .voicetest.toml."""
    save_settings(settings)
    return settings


@router.get("/agents")
async def list_agents() -> list[dict]:
    """List all agents."""
    return get_agent_repo().list_all()


@router.get("/agents/{agent_id}")
async def get_agent(agent_id: str) -> dict:
    """Get agent by ID."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


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
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # For linked agents, use file mtime for caching
    source_path = agent.get("source_path")
    if source_path:
        try:
            _mtime, etag = check_file(source_path, agent_id)
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Agent file not found: {source_path}"
            ) from None

        if if_none_match and if_none_match == etag:
            return Response(status_code=304)

        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, must-revalidate"

        return get_importer_registry().import_agent(resolve_path(source_path))

    # For non-linked agents, use updated_at for caching
    try:
        result = repo.load_graph(agent)
        if isinstance(result, Path):
            return get_importer_registry().import_agent(result)

        updated_at = agent.get("updated_at", "")
        etag = compute_etag(agent_id, updated_at)

        if if_none_match and if_none_match == etag:
            return Response(status_code=304)

        response.headers["ETag"] = etag
        response.headers["Cache-Control"] = "private, must-revalidate"

        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.get("/agents/{agent_id}/variables")
async def get_agent_variables(agent_id: str) -> dict:
    """Extract dynamic variable names from agent prompts.

    Scans general_prompt and all node state_prompt values for {{var}} placeholders.
    Returns unique variable names in first-appearance order.
    """
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = repo.load_graph(agent)
        graph = get_importer_registry().import_agent(result) if isinstance(result, Path) else result
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot load agent graph: {e}") from None

    # Collect all text that might contain {{var}} placeholders
    texts = []
    general_prompt = graph.source_metadata.get("general_prompt", "")
    if general_prompt:
        texts.append(general_prompt)
    for node in graph.nodes.values():
        if node.state_prompt:
            texts.append(node.state_prompt)

    combined = "\n".join(texts)
    variables = extract_variables(combined)

    return {"variables": variables}


def _load_agent_graph(agent_id: str) -> tuple[dict, AgentGraph]:
    """Load agent record and its graph. Raises HTTPException on failure."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = repo.load_graph(agent)
        graph = get_importer_registry().import_agent(result) if isinstance(result, Path) else result
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=400, detail=f"Cannot load agent graph: {e}") from None

    return agent, graph


def _save_agent_graph(agent_id: str, agent: dict, graph: AgentGraph) -> None:
    """Persist an updated graph back to DB or linked file."""
    source_path = agent.get("source_path")
    if source_path:
        try:
            _write_graph_to_linked_file(graph, source_path, agent)
        except OSError as e:
            raise HTTPException(
                status_code=400, detail=f"Cannot write to linked file: {e}"
            ) from None
    else:
        get_agent_repo().update(agent_id, graph_json=graph.model_dump_json())


@router.get("/agents/{agent_id}/snippets")
async def get_snippets(agent_id: str) -> dict:
    """Get all snippets defined for an agent."""
    _agent, graph = _load_agent_graph(agent_id)
    return {"snippets": graph.snippets}


@router.put("/agents/{agent_id}/snippets")
async def update_all_snippets(agent_id: str, body: dict) -> dict:
    """Replace all snippets for an agent."""
    agent, graph = _load_agent_graph(agent_id)
    graph.snippets = body.get("snippets", {})
    _save_agent_graph(agent_id, agent, graph)
    return {"snippets": graph.snippets}


@router.put("/agents/{agent_id}/snippets/{name}")
async def update_snippet(agent_id: str, name: str, request: UpdateSnippetRequest) -> dict:
    """Create or update a single snippet."""
    agent, graph = _load_agent_graph(agent_id)
    graph.snippets[name] = request.text
    _save_agent_graph(agent_id, agent, graph)
    return {"snippets": graph.snippets}


@router.delete("/agents/{agent_id}/snippets/{name}")
async def delete_snippet(agent_id: str, name: str) -> dict:
    """Delete a single snippet."""
    agent, graph = _load_agent_graph(agent_id)
    if name not in graph.snippets:
        raise HTTPException(status_code=404, detail=f"Snippet not found: {name}")
    del graph.snippets[name]
    _save_agent_graph(agent_id, agent, graph)
    return {"snippets": graph.snippets}


@router.post("/agents/{agent_id}/analyze-dry")
async def analyze_dry(agent_id: str) -> dict:
    """Run auto-DRY analysis on an agent's prompts."""
    _agent, graph = _load_agent_graph(agent_id)
    result = suggest_snippets(graph)
    return {
        "exact": [{"text": m.text, "locations": m.locations} for m in result.exact],
        "fuzzy": [
            {"texts": m.texts, "locations": m.locations, "similarity": m.similarity}
            for m in result.fuzzy
        ],
    }


@router.post("/agents/{agent_id}/apply-snippets", response_model=AgentGraph)
async def apply_snippets(agent_id: str, request: ApplySnippetsRequest) -> AgentGraph:
    """Apply snippets: add them to graph and replace occurrences in prompts with {%name%} refs."""
    agent, graph = _load_agent_graph(agent_id)

    for snippet in request.snippets:
        name = snippet["name"]
        text = snippet["text"]
        graph.snippets[name] = text

        ref = "{%" + name + "%}"

        # Replace in general_prompt
        general_prompt = graph.source_metadata.get("general_prompt", "")
        if text in general_prompt:
            graph.source_metadata["general_prompt"] = general_prompt.replace(text, ref)

        # Replace in node state_prompts
        for node in graph.nodes.values():
            if text in node.state_prompt:
                node.state_prompt = node.state_prompt.replace(text, ref)

    _save_agent_graph(agent_id, agent, graph)
    return graph


@router.post("/agents")
async def create_agent(request: CreateAgentRequest) -> dict:
    """Create an agent from config dict or file path."""
    if not request.config and not request.path:
        raise HTTPException(status_code=400, detail="Either config or path is required")

    # Validate and resolve path before attempting import
    absolute_path: str | None = None
    if request.path:
        path = resolve_file(request.path)
        try:
            path.read_text()
        except PermissionError:
            raise HTTPException(
                status_code=400, detail=f"Permission denied: {request.path}"
            ) from None
        absolute_path = str(path)

    try:
        source = absolute_path if absolute_path else request.config
        graph = await api.import_agent(source, source=request.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except FileNotFoundError:
        raise HTTPException(status_code=400, detail=f"File not found: {request.path}") from None
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from None
    except PermissionError:
        raise HTTPException(status_code=400, detail=f"Permission denied: {request.path}") from None

    repo = get_agent_repo()
    return repo.create(
        name=request.name,
        source_type=graph.source_type,
        source_path=absolute_path,
        graph_json=graph.model_dump_json(),
    )


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

    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        try:
            graph = await api.import_agent(tmp_path, source=source)
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
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    graph_json = request.graph_json
    if graph_json is None and request.default_model is not None and agent.get("graph_json"):
        # Update default_model in existing stored graph
        graph_data = json.loads(agent["graph_json"])
        graph_data["default_model"] = request.default_model if request.default_model else None
        graph_json = json.dumps(graph_data)

    return repo.update(agent_id, name=request.name, graph_json=graph_json)


@router.put("/agents/{agent_id}/prompts", response_model=AgentGraph)
async def update_prompt(agent_id: str, request: UpdatePromptRequest) -> AgentGraph:
    """Update a general or node-specific prompt.

    When node_id is None, updates source_metadata.general_prompt.
    When node_id is set, updates that node's state_prompt.
    For linked-file agents, writes back to the source file on disk.
    """
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Load the current graph
    source_path = agent.get("source_path")
    if source_path:
        try:
            graph = get_importer_registry().import_agent(resolve_path(source_path))
        except FileNotFoundError:
            raise HTTPException(
                status_code=404, detail=f"Agent file not found: {source_path}"
            ) from None
    else:
        try:
            result = repo.load_graph(agent)
            if isinstance(result, Path):
                graph = get_importer_registry().import_agent(result)
            else:
                graph = result
        except (FileNotFoundError, ValueError) as e:
            raise HTTPException(status_code=404, detail=str(e)) from None

    # Apply the prompt update
    if request.node_id is None:
        graph.source_metadata["general_prompt"] = request.prompt_text
    elif request.transition_target_id is not None:
        node = graph.get_node(request.node_id)
        if not node:
            raise HTTPException(
                status_code=404,
                detail=f"Node not found: {request.node_id}",
            )
        transition = next(
            (t for t in node.transitions if t.target_node_id == request.transition_target_id),
            None,
        )
        if not transition:
            raise HTTPException(
                status_code=404,
                detail=f"Transition not found: {request.node_id} -> {request.transition_target_id}",
            )
        transition.condition.value = request.prompt_text
    else:
        node = graph.get_node(request.node_id)
        if not node:
            raise HTTPException(
                status_code=404,
                detail=f"Node not found: {request.node_id}",
            )
        node.state_prompt = request.prompt_text

    # Persist the change
    if source_path:
        try:
            _write_graph_to_linked_file(graph, source_path, agent)
        except OSError as e:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot write to linked file: {e}",
            ) from None
    else:
        repo.update(agent_id, graph_json=graph.model_dump_json())

    return graph


def _write_graph_to_linked_file(graph: AgentGraph, source_path: str, agent: dict) -> None:
    """Export a graph back to a linked file on disk."""
    source_type = agent.get("source_type", "")

    # Try format-based exporter (e.g. retell-llm)
    exporter_registry = get_exporter_registry()
    exporter = exporter_registry.get(source_type)
    if exporter:
        exported = json.loads(exporter.export(graph))
        write_json(source_path, exported)
        return

    # Try platform-based exporter
    platform_registry = _get_platform_registry()
    if platform_registry.has_platform(source_type):
        platform_exporter = platform_registry.get_exporter(source_type)
        if platform_exporter:
            exported = platform_exporter(graph)
            write_json(source_path, exported)
            return

    raise HTTPException(
        status_code=400,
        detail=f"No exporter available for source type: {source_type}",
    )


@router.delete("/agents/{agent_id}")
async def delete_agent(agent_id: str) -> dict:
    """Delete an agent."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    repo.delete(agent_id)
    return {"status": "deleted", "id": agent_id}


@router.get("/agents/{agent_id}/metrics-config")
async def get_metrics_config(agent_id: str) -> dict:
    """Get an agent's metrics configuration."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    config = repo.get_metrics_config(agent_id)
    return config.model_dump()


@router.put("/agents/{agent_id}/metrics-config")
async def update_metrics_config(agent_id: str, request: UpdateMetricsConfigRequest) -> dict:
    """Update an agent's metrics configuration."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    config = MetricsConfig(
        threshold=request.threshold,
        global_metrics=request.global_metrics,
    )
    repo.update_metrics_config(agent_id, config)
    return config.model_dump()


@router.get("/agents/{agent_id}/tests")
async def list_tests_for_agent(agent_id: str) -> list[dict]:
    """List all test cases for an agent, including file-based linked tests."""
    agent = get_agent_repo().get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    tests_paths = agent.get("tests_paths")
    return get_test_case_repo().list_for_agent_with_linked(agent_id, tests_paths)


@router.post("/agents/{agent_id}/tests-paths")
async def link_test_file(agent_id: str, request: LinkTestFileRequest) -> dict:
    """Link a JSON test file to an agent.

    The file must exist, contain valid JSON, and be a JSON array.
    Tests from the file will appear alongside DB tests via list_for_agent_with_linked.
    """
    agent_repo = get_agent_repo()
    agent = agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    path = resolve_file(request.path)
    resolved = str(path)

    # Validate JSON content is an array
    try:
        content = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {e}") from None

    if not isinstance(content, list):
        raise HTTPException(status_code=400, detail="File must contain a JSON array")

    # Check for duplicates
    current_paths = agent.get("tests_paths") or []
    if resolved in current_paths:
        raise HTTPException(status_code=409, detail="File already linked")

    updated_paths = current_paths + [resolved]
    agent_repo.update(agent_id, tests_paths=updated_paths)

    return {
        "path": resolved,
        "test_count": len(content),
        "tests_paths": updated_paths,
    }


@router.delete("/agents/{agent_id}/tests-paths")
async def unlink_test_file(agent_id: str, path: str) -> dict:
    """Unlink a test file from an agent.

    Removes the path from tests_paths. The file itself is not deleted.
    """
    agent_repo = get_agent_repo()
    agent = agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    resolved = str(resolve_path(path))
    current_paths = agent.get("tests_paths") or []

    if resolved not in current_paths:
        raise HTTPException(status_code=404, detail="File not linked to this agent")

    updated_paths = [p for p in current_paths if p != resolved]
    agent_repo.update(agent_id, tests_paths=updated_paths)

    return {
        "path": resolved,
        "tests_paths": updated_paths,
    }


@router.post("/agents/{agent_id}/tests/export")
async def export_tests_for_agent(agent_id: str, request: ExportTestsRequest) -> list[dict]:
    """Export test cases for an agent to a specified format."""
    repo = get_test_case_repo()

    if request.test_ids:
        records = [repo.get(tid) for tid in request.test_ids if repo.get(tid)]
    else:
        records = repo.list_for_agent(agent_id)

    if not records:
        return []

    test_cases = [repo.to_model(r) for r in records]

    try:
        return export_tests(test_cases, request.format)
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

    repo = get_test_case_repo()
    agent = get_agent_repo().get(agent_id)
    tests_paths = agent.get("tests_paths") if agent else None

    if tests_paths:
        return repo.create_in_file(tests_paths[0], agent_id, test_case)

    return repo.create(agent_id, test_case)


@router.put("/tests/{test_id}")
async def update_test_case(test_id: str, request: CreateTestCaseRequest) -> dict:
    """Update a test case (DB or linked file)."""
    repo = get_test_case_repo()
    test = repo.get(test_id)

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

    if test:
        return repo.update(test_id, test_case)

    # Check linked files for this test ID
    linked = _find_linked_test(test_id)
    if linked:
        return repo.update_linked(test_id, test_case, linked["source_path"], linked["source_index"])

    raise HTTPException(status_code=404, detail="Test case not found")


@router.delete("/tests/{test_id}")
async def delete_test_case(test_id: str) -> dict:
    """Delete a test case (DB or linked file)."""
    repo = get_test_case_repo()
    test = repo.get(test_id)

    if test:
        repo.delete(test_id)
        return {"status": "deleted", "id": test_id}

    linked = _find_linked_test(test_id)
    if linked:
        repo.delete_linked(test_id, linked["source_path"], linked["source_index"])
        return {"status": "deleted", "id": test_id}

    raise HTTPException(status_code=404, detail="Test case not found")


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

    graph = await api.import_agent(demo_agent_config)

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
    return get_run_repo().list_for_agent(agent_id, limit)


@router.get("/runs/{run_id}")
async def get_run(run_id: str) -> dict:
    """Get a run with all results."""
    run_repo = get_run_repo()
    run = run_repo.get_with_results(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Detect orphaned run: not completed but not actively running
    if run["completed_at"] is None and run_id not in _active_runs:
        run_repo.complete(run_id)
        run["completed_at"] = datetime.now(UTC).isoformat()

    # Fix inconsistent state: run complete but results still "running"
    if run["completed_at"] is not None:
        for result in run["results"]:
            if result["status"] == "running":
                run_repo.mark_result_error(result["id"], "Run orphaned - backend stopped")
                result["status"] = "error"
                result["error_message"] = "Run orphaned - backend stopped"

    return run


@router.delete("/runs/{run_id}")
async def delete_run(run_id: str) -> dict:
    """Delete a run and all its results."""
    run_repo = get_run_repo()
    run = run_repo.get_with_results(run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")

    # Don't allow deleting active runs
    if run_id in _active_runs:
        raise HTTPException(status_code=400, detail="Cannot delete an active run")

    run_repo.delete(run_id)
    return {"status": "deleted", "id": run_id}


@router.post("/results/{result_id}/audio-eval")
async def audio_eval_result(result_id: str) -> dict:
    """Run audio evaluation on an existing test result.

    Performs TTS→STT round-trip on assistant messages and re-evaluates
    metrics using the "heard" text.
    """
    run_repo = get_run_repo()

    session = get_session()
    db_result = session.get(ResultModel, result_id)
    if not db_result:
        raise HTTPException(status_code=404, detail="Result not found")

    result_dict = run_repo._result_to_dict(db_result)
    transcript_data = result_dict.get("transcript_json") or []
    if not transcript_data:
        raise HTTPException(status_code=400, detail="Result has no transcript")

    transcript = [Message(**m) for m in transcript_data]

    # Find the test case to get metrics/rules
    test_case_id = result_dict.get("test_case_id")
    test_case_repo = get_test_case_repo()

    test_record = test_case_repo.get(test_case_id) if test_case_id else None
    if not test_record:
        test_record = _find_linked_test(test_case_id) if test_case_id else None
    if not test_record:
        raise HTTPException(status_code=400, detail="Test case not found for result")

    test_case = test_case_repo.to_model(test_record)

    # Load metrics config for global metrics
    run = session.get(RunModel, db_result.run_id)
    agent_repo = get_agent_repo()
    metrics_config = agent_repo.get_metrics_config(run.agent_id) if run else None

    settings = load_settings()
    settings.apply_env()
    judge_model = resolve_model(settings.models.judge)

    transformed, audio_metrics = await api.audio_eval_result(
        transcript,
        test_case,
        metrics_config=metrics_config,
        judge_model=judge_model,
        settings=settings,
    )

    # Update stored result with audio eval data
    run_repo.update_audio_eval(result_id, transformed, audio_metrics)

    # Return updated result
    session.refresh(db_result)
    return run_repo._result_to_dict(db_result)


def _load_result_context(result_id: str) -> tuple[dict, "TestCase", AgentGraph, str]:
    """Load result, test case, agent graph, and judge model for diagnosis endpoints.

    Returns:
        Tuple of (result_dict, test_case, agent_graph, judge_model).

    Raises:
        HTTPException on missing data.
    """
    run_repo = get_run_repo()
    session = get_session()
    db_result = session.get(ResultModel, result_id)
    if not db_result:
        raise HTTPException(status_code=404, detail="Result not found")

    result_dict = run_repo._result_to_dict(db_result)

    # Find test case
    test_case_id = result_dict.get("test_case_id")
    test_case_repo = get_test_case_repo()
    test_record = test_case_repo.get(test_case_id) if test_case_id else None
    if not test_record:
        test_record = _find_linked_test(test_case_id) if test_case_id else None
    if not test_record:
        raise HTTPException(status_code=400, detail="Test case not found for result")

    test_case = test_case_repo.to_model(test_record)

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

    diagnosis_result = await api.diagnose_failure(
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
    agent_repo = get_agent_repo()
    metrics_config = agent_repo.get_metrics_config(run.agent_id) if run else None

    options = RunOptions(judge_model=judge_model)

    attempt_result = await api.apply_and_rerun(
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

    fix = await api.revise_fix(
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

    modified_graph = api.apply_fix_to_graph(graph, changes)
    _save_agent_graph(agent_id, agent, modified_graph)

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

    agent_repo = get_agent_repo()
    test_case_repo = get_test_case_repo()
    run_repo = get_run_repo()

    agent = agent_repo.get(agent_id)
    if not agent:
        return

    try:
        result = agent_repo.load_graph(agent)
        graph = get_importer_registry().import_agent(result) if isinstance(result, Path) else result
    except (FileNotFoundError, ValueError):
        return

    # Load metrics config for global metrics
    metrics_config = agent_repo.get_metrics_config(agent_id)

    try:
        for test_record in test_records:
            # Get pre-created result ID
            result_id = result_ids[test_record["id"]]

            # Check if this specific test was cancelled before it started
            if run_id in _active_runs and result_id in _active_runs[run_id]["cancelled_tests"]:
                run_repo.mark_result_cancelled(result_id)
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
                    run_repo.mark_result_cancelled(remaining_result_id)
                    await _broadcast_run_update(
                        run_id,
                        {"type": "test_cancelled", "result_id": remaining_result_id},
                    )
                break

            test_case = test_case_repo.to_model(test_record)

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
                    run_repo.update_transcript(rid, transcript)
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
                result = await api.run_test(
                    graph,
                    test_case,
                    options=options,
                    metrics_config=metrics_config,
                    on_turn=await make_on_turn(result_id, last_transcript),
                    on_token=make_on_token(result_id) if options.streaming else None,
                    on_error=make_on_error(result_id),
                )
                run_repo.complete_result(result_id, result)
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
                run_repo.complete_result(result_id, cancelled_result)
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
                run_repo.complete_result(result_id, error_result)
                await _broadcast_run_update(
                    run_id,
                    {
                        "type": "test_error",
                        "result_id": result_id,
                        "error": str(e),
                    },
                )

        run_repo.complete(run_id)
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
        run = get_run_repo().get_with_results(run_id)
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
    agent_repo = get_agent_repo()
    agent = agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    test_case_repo = get_test_case_repo()
    tests_paths = agent.get("tests_paths")
    all_tests = test_case_repo.list_for_agent_with_linked(agent_id, tests_paths)

    if request.test_ids:
        tests_by_id = {t["id"]: t for t in all_tests}
        test_records = [tests_by_id[tid] for tid in request.test_ids if tid in tests_by_id]
    else:
        test_records = all_tests

    if not test_records:
        raise HTTPException(status_code=400, detail="No test cases to run")

    run_repo = get_run_repo()
    run = run_repo.create(agent_id)

    # Create all pending results upfront so they appear immediately in UI
    # Map test_case_id -> result_id for the background task to use
    result_ids: dict[str, str] = {}
    for test_record in test_records:
        result_id = run_repo.create_pending_result(
            run["id"], test_record["id"], test_record["name"]
        )
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
    agent_repo = get_agent_repo()
    agent = agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = agent_repo.load_graph(agent)
        graph = get_importer_registry().import_agent(result) if isinstance(result, Path) else result
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
    agent_repo = get_agent_repo()
    metrics_config = agent_repo.get_metrics_config(agent_id)
    metric_results: list[MetricResult] = []

    if metrics_config and metrics_config.global_metrics:
        settings = load_settings()
        settings.apply_env()
        judge_model = resolve_model(settings.models.judge)
        try:
            metric_results = await api.evaluate_global_metrics(
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

    run_repo = get_run_repo()
    run = run_repo.create(agent_id)
    run_repo.add_result_from_call(run["id"], call_id, test_result)
    run_repo.complete(run["id"])

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
    agent_repo = get_agent_repo()
    agent = agent_repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = agent_repo.load_graph(agent)
        graph = get_importer_registry().import_agent(result) if isinstance(result, Path) else result
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


def _get_platform_registry():
    """Get the platform registry from the DI container."""
    return get_container().resolve(PlatformRegistry)


def _validate_platform(platform: str) -> None:
    """Validate platform name using registry."""
    registry = _get_platform_registry()
    if not registry.has_platform(platform):
        raise HTTPException(status_code=400, detail=f"Invalid platform: {platform}")


def _is_platform_configured(platform: str) -> bool:
    """Check if a platform is configured using registry."""
    registry = _get_platform_registry()
    settings = load_settings()
    return registry.is_configured(platform, settings)


def _get_platform_api_key(platform: str) -> str | None:
    """Get API key for a platform using registry."""
    registry = _get_platform_registry()
    settings = load_settings()
    return registry.get_api_key(platform, settings)


def _get_configured_platform_client(platform: str) -> tuple[Any, Any]:
    """Get validated, configured platform client and SDK client.

    Args:
        platform: Platform identifier.

    Returns:
        Tuple of (PlatformClient, SDK client).

    Raises:
        HTTPException: If platform invalid or not configured.
    """
    _validate_platform(platform)
    if not _is_platform_configured(platform):
        raise HTTPException(status_code=400, detail=f"{platform} API key not configured")
    api_key = _get_platform_api_key(platform)
    registry = _get_platform_registry()
    platform_client = registry.get(platform)
    client = platform_client.get_client(api_key)
    return platform_client, client


@router.get("/platforms", response_model=list[PlatformInfo])
async def list_platforms() -> list[PlatformInfo]:
    """List all available platforms and their configuration status."""
    registry = _get_platform_registry()
    settings = load_settings()
    platforms = []
    for platform_name in registry.list_platforms():
        platforms.append(
            PlatformInfo(
                name=platform_name,
                configured=registry.is_configured(platform_name, settings),
                env_key=registry.get_env_key(platform_name),
                required_env_keys=registry.get_required_env_keys(platform_name),
            )
        )
    return platforms


@router.get("/platforms/{platform}/status", response_model=PlatformStatusResponse)
async def get_platform_status(platform: str) -> PlatformStatusResponse:
    """Check if a platform API key is configured."""
    _validate_platform(platform)
    return PlatformStatusResponse(
        configured=_is_platform_configured(platform),
        platform=platform,
    )


@router.post("/platforms/{platform}/configure", response_model=PlatformStatusResponse)
async def configure_platform(
    platform: str, request: ConfigurePlatformRequest
) -> PlatformStatusResponse:
    """Configure platform credentials. Returns 409 if already configured."""
    _validate_platform(platform)

    if _is_platform_configured(platform):
        raise HTTPException(
            status_code=409,
            detail=f"{platform} credentials are already configured. Use Settings to change them.",
        )

    registry = _get_platform_registry()
    required_keys = registry.get_required_env_keys(platform)
    settings = load_settings()

    # Set the primary API key
    env_key = registry.get_env_key(platform)
    settings.env[env_key] = request.api_key

    # Set the API secret if provided and required
    if request.api_secret and len(required_keys) > 1:
        # Find the secret key (usually ends with _SECRET)
        secret_keys = [k for k in required_keys if k.endswith("_SECRET")]
        if secret_keys:
            settings.env[secret_keys[0]] = request.api_secret

    save_settings(settings)
    settings.apply_env()

    return PlatformStatusResponse(configured=True, platform=platform)


@router.get("/platforms/{platform}/agents", response_model=list[RemoteAgentInfo])
async def list_platform_agents(platform: str) -> list[RemoteAgentInfo]:
    """List agents from any supported platform."""
    platform_client, client = _get_configured_platform_client(platform)

    try:
        agents = platform_client.list_agents(client)
        return [RemoteAgentInfo(**a) for a in agents]
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to list {platform} agents: {e}"
        ) from None


@router.post("/platforms/{platform}/agents/{agent_id}/import", response_model=AgentGraph)
async def import_platform_agent(platform: str, agent_id: str) -> AgentGraph:
    """Import an agent from any supported platform by ID."""
    platform_client, client = _get_configured_platform_client(platform)

    try:
        registry = _get_platform_registry()
        config = platform_client.get_agent(client, agent_id)
        importer = registry.get_importer(platform)
        if not importer:
            raise ValueError(f"No importer for platform: {platform}")
        return importer.import_agent(config)
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to import {platform} agent: {e}"
        ) from None


@router.post("/platforms/{platform}/export", response_model=ExportToPlatformResponse)
async def export_to_platform(
    platform: str, request: ExportToPlatformRequest
) -> ExportToPlatformResponse:
    """Export an agent graph to any supported platform."""
    platform_client, client = _get_configured_platform_client(platform)

    try:
        registry = _get_platform_registry()
        exporter = registry.get_exporter(platform)
        if not exporter:
            raise ValueError(f"No exporter for platform: {platform}")
        config = exporter(request.graph)

        result = platform_client.create_agent(client, config, request.name)
        return ExportToPlatformResponse(
            id=result["id"],
            name=result["name"],
            platform=platform,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to export to {platform}: {e}"
        ) from None


@router.get("/agents/{agent_id}/sync-status", response_model=SyncStatusResponse)
async def get_sync_status(agent_id: str) -> SyncStatusResponse:
    """Check if an agent can be synced to its source platform."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    try:
        result = repo.load_graph(agent)
        graph = get_importer_registry().import_agent(result) if isinstance(result, Path) else result
    except (FileNotFoundError, ValueError):
        return SyncStatusResponse(
            can_sync=False,
            reason="Agent graph not available",
        )

    source_metadata = graph.source_metadata or {}
    source_type = graph.source_type

    registry = _get_platform_registry()
    if not registry.has_platform(source_type):
        return SyncStatusResponse(
            can_sync=False,
            reason=f"Source '{source_type}' is not a supported platform",
        )

    if not registry.supports_update(source_type):
        return SyncStatusResponse(
            can_sync=False,
            reason=f"{source_type} does not support syncing",
            platform=source_type,
        )

    remote_id_key = registry.get_remote_id_key(source_type)
    if not remote_id_key:
        return SyncStatusResponse(
            can_sync=False,
            reason=f"{source_type} does not track remote IDs",
            platform=source_type,
        )

    remote_id = source_metadata.get(remote_id_key)
    if not remote_id:
        return SyncStatusResponse(
            can_sync=False,
            reason=f"No remote ID found (missing {remote_id_key} in source_metadata)",
            platform=source_type,
        )

    if not _is_platform_configured(source_type):
        return SyncStatusResponse(
            can_sync=False,
            reason=f"{source_type} API key not configured",
            platform=source_type,
            remote_id=remote_id,
            needs_configuration=True,
        )

    return SyncStatusResponse(
        can_sync=True,
        platform=source_type,
        remote_id=remote_id,
    )


@router.post("/agents/{agent_id}/sync", response_model=SyncToPlatformResponse)
async def sync_to_platform(agent_id: str, request: SyncToPlatformRequest) -> SyncToPlatformResponse:
    """Sync an agent to its source platform."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    graph = request.graph
    source_metadata = graph.source_metadata or {}
    source_type = graph.source_type

    registry = _get_platform_registry()
    if not registry.has_platform(source_type):
        raise HTTPException(
            status_code=400, detail=f"Source '{source_type}' is not a supported platform"
        )

    if not registry.supports_update(source_type):
        raise HTTPException(status_code=400, detail=f"{source_type} does not support syncing")

    remote_id_key = registry.get_remote_id_key(source_type)
    if not remote_id_key:
        raise HTTPException(status_code=400, detail=f"{source_type} does not track remote IDs")

    remote_id = source_metadata.get(remote_id_key)
    if not remote_id:
        raise HTTPException(
            status_code=400,
            detail=f"No remote ID found (missing {remote_id_key} in source_metadata)",
        )

    platform_client, client = _get_configured_platform_client(source_type)

    try:
        exporter = registry.get_exporter(source_type)
        if not exporter:
            raise ValueError(f"No exporter for platform: {source_type}")
        config = exporter(graph)

        result = platform_client.update_agent(client, remote_id, config)
        return SyncToPlatformResponse(
            id=result["id"],
            name=result["name"],
            platform=source_type,
            synced=True,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to sync to {source_type}: {e}"
        ) from None


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
