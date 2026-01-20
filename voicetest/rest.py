"""REST API for voicetest.

Thin wrapper over the core API (voicetest.api). All business logic
lives in api.py - this module just handles HTTP concerns.

Run with: voicetest serve
Or: uvicorn voicetest.rest:app --reload
"""

import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from voicetest import api
from voicetest.container import get_container
from voicetest.models.agent import AgentGraph, GlobalMetric, MetricsConfig
from voicetest.models.results import Message, MetricResult, TestResult, TestRun
from voicetest.models.test_case import RunOptions, TestCase
from voicetest.settings import Settings, load_settings, save_settings
from voicetest.storage.db import get_connection, init_schema
from voicetest.storage.repositories import (
    AgentRepository,
    RunRepository,
    TestCaseRepository,
)

# Active runs: run_id -> {"cancel": Event, "websockets": set[WebSocket], "message_queue": list}
_active_runs: dict[str, dict[str, Any]] = {}

_initialized = False


def init_storage() -> None:
    """Initialize storage and register linked agents."""
    global _initialized

    conn = get_connection()
    init_schema(conn)
    _initialized = True

    linked_agents = os.environ.get("VOICETEST_LINKED_AGENTS", "")
    if linked_agents:
        for agent_path in linked_agents.split(","):
            if agent_path.strip():
                _register_linked_agent(Path(agent_path.strip()))


def _register_linked_agent(path: Path) -> None:
    """Register a linked agent from filesystem if not already registered."""
    repo = get_agent_repo()
    existing = repo.list_all()
    for agent in existing:
        if agent.get("source_path") == str(path):
            return

    name = path.stem
    repo.create(
        name=name,
        source_type="linked",
        source_path=str(path),
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
    allow_origins=["*"],
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


class ExportRequest(BaseModel):
    """Request to export an agent graph."""

    graph: AgentGraph
    format: str


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
    """Request to create an agent from config."""

    name: str
    config: dict[str, Any]
    source: str | None = None


class UpdateAgentRequest(BaseModel):
    """Request to update an agent."""

    name: str | None = None


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


class ExportTestsRequest(BaseModel):
    """Request to export test cases."""

    format: str = "retell"
    test_ids: list[str] | None = None  # None means all tests


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


@router.post("/agents/export")
async def export_agent(request: ExportRequest) -> dict[str, str]:
    """Export an agent graph to a format."""
    try:
        content = await api.export_agent(request.graph, format=request.format)
        return {"content": content, "format": request.format}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


def _build_run_options(settings: Settings, request_options: RunOptions | None) -> RunOptions:
    """Build RunOptions from settings, with request options for run params only.

    Models always come from settings. Run parameters (max_turns, timeout, verbose, flow_judge)
    come from request if provided, otherwise from settings.
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


@router.get("/agents/{agent_id}/graph", response_model=AgentGraph)
async def get_agent_graph(agent_id: str) -> AgentGraph:
    """Get the AgentGraph for an agent."""
    repo = get_agent_repo()
    agent = repo.get(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    try:
        return repo.load_graph(agent)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None


@router.post("/agents")
async def create_agent(request: CreateAgentRequest) -> dict:
    """Create an agent from config."""
    try:
        graph = await api.import_agent(request.config, source=request.source)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    repo = get_agent_repo()
    return repo.create(
        name=request.name,
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

    return repo.update(agent_id, name=request.name)


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
    """List all test cases for an agent."""
    return get_test_case_repo().list_for_agent(agent_id)


@router.post("/agents/{agent_id}/tests/export")
async def export_tests_for_agent(agent_id: str, request: ExportTestsRequest) -> list[dict]:
    """Export test cases for an agent to a specified format."""
    from voicetest.exporters.test_cases import export_tests

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
    """Create a test case for an agent."""
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
    return get_test_case_repo().create(agent_id, test_case)


@router.put("/tests/{test_id}")
async def update_test_case(test_id: str, request: CreateTestCaseRequest) -> dict:
    """Update a test case."""
    repo = get_test_case_repo()
    test = repo.get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test case not found")

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
    return repo.update(test_id, test_case)


@router.delete("/tests/{test_id}")
async def delete_test_case(test_id: str) -> dict:
    """Delete a test case."""
    repo = get_test_case_repo()
    test = repo.get(test_id)
    if not test:
        raise HTTPException(status_code=404, detail="Test case not found")

    repo.delete(test_id)
    return {"status": "deleted", "id": test_id}


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
        graph = agent_repo.load_graph(agent)
    except (FileNotFoundError, ValueError):
        return

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

            async def make_on_turn(rid: str):
                async def on_turn(transcript: list) -> None:
                    # Check for cancellation
                    if _is_run_cancelled(run_id, rid):
                        raise asyncio.CancelledError("Test cancelled by user")
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

            try:
                result = await api.run_test(
                    graph, test_case, options=options, on_turn=await make_on_turn(result_id)
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
                from voicetest.models.results import TestResult

                cancelled_result = TestResult(
                    test_name=test_case.name,
                    status="error",
                    transcript=[],
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
                from voicetest.models.results import TestResult

                error_result = TestResult(
                    test_name=test_case.name,
                    status="error",
                    transcript=[],
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
    from starlette.websockets import WebSocketDisconnect, WebSocketState

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
    if request.test_ids:
        test_records = [
            test_case_repo.get(tid) for tid in request.test_ids if test_case_repo.get(tid)
        ]
    else:
        test_records = test_case_repo.list_for_agent(agent_id)

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

    background_tasks.add_task(_execute_run, run["id"], agent_id, test_records, result_ids, options)

    return {
        "id": run["id"],
        "agent_id": agent_id,
        "started_at": run["started_at"],
        "test_count": len(test_records),
    }


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
        file_path = WEB_DIST / path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(WEB_DIST / "index.html")
