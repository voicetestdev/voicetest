"""REST API for voicetest.

Thin wrapper over the core API (voicetest.api). All business logic
lives in api.py - this module just handles HTTP concerns.

Run with: voicetest serve
Or: uvicorn voicetest.rest:app --reload
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from voicetest import api
from voicetest.models.agent import AgentGraph
from voicetest.models.results import Message, MetricResult, TestResult, TestRun
from voicetest.models.test_case import RunOptions, TestCase
from voicetest.settings import Settings, load_settings, save_settings


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


@router.post("/runs/single", response_model=TestResult)
async def run_test(request: RunTestRequest) -> TestResult:
    """Run a single test case."""
    return await api.run_test(
        request.graph,
        request.test_case,
        options=request.options,
    )


@router.post("/runs", response_model=TestRun)
async def run_tests(request: RunTestsRequest) -> TestRun:
    """Run multiple test cases."""
    return await api.run_tests(
        request.graph,
        request.test_cases,
        options=request.options,
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


@router.put("/settings", response_model=Settings)
async def update_settings(settings: Settings) -> Settings:
    """Update settings in .voicetest.toml."""
    save_settings(settings)
    return settings


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
