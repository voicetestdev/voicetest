# Voicetest Project Instructions

## Project Overview

A generic test harness for voice agent workflows. Test agents from Retell, VAPI, LiveKit, Bland, and custom sources using a unified execution and evaluation model.

## Code Quality Requirements

All code must pass pre-commit checks before committing:

```bash
uv run pre-commit run --all-files
```

### Pre-commit Hooks

- **Python**: `ruff` (lint + auto-fix) and `ruff-format`
- **TypeScript/Svelte**: `svelte-check` and `tsc --noEmit`
- **Markdown**: `mdformat` with GFM support
- **General**: trailing-whitespace, end-of-file-fixer, check-yaml, check-json

### Python Style (pyproject.toml)

- Line length: 100, target Python 3.12
- **Imports must be at top of file** (PLC0415 enforced)
- 2 blank lines after imports
- No relative parent imports (`from .. import` banned)
- No unused imports/variables

### TypeScript/Svelte Style

- Strict mode enabled
- No unused locals or parameters
- No fallthrough in switch statements

## Development Commands

### Backend (Python)

```bash
# Install dependencies
uv sync --all-extras

# Run unit tests
uv run pytest tests/unit -v

# Run integration tests (requires Ollama with qwen2.5:0.5b)
uv run pytest tests/integration -v

# Run specific test file
uv run pytest tests/unit/path/to/test.py -v

# Lint
uv run ruff check voicetest/ tests/

# Start dev server with reload
uv run voicetest serve --reload

# Run demo with web UI
uv run voicetest demo --serve
```

### Frontend (Bun/Svelte)

Uses **mise** for runtime version management. Always prefix bun commands with `mise exec --`:

```bash
cd web

# Install dependencies
mise exec -- bun install

# Run dev server (hot reload at http://localhost:5173)
mise exec -- bun run dev

# Run tests
mise exec -- bunx vitest run

# Type check
mise exec -- bunx tsc --noEmit

# Build for production
mise exec -- bun run build

# Run e2e tests (starts server automatically)
mise exec -- bunx playwright test --config=e2e/playwright.config.ts
```

## Architecture

### DI Container (Punq)

The project uses Punq for dependency injection. Key singletons:

- `duckdb.DuckDBPyConnection` - Database connection (singleton for data visibility)
- `ImporterRegistry`, `ExporterRegistry`, `PlatformRegistry` - Registries

Repositories are transient but share the singleton connection:

- `AgentRepository`, `TestCaseRepository`, `RunRepository`

Get instances via `voicetest.container`:

```python
from voicetest.container import get_db_connection, get_importer_registry
```

**When to use DI:**

- Use `get_*` helpers for app code (REST handlers, CLI commands)
- Use `container.resolve(Type)` when you need the container directly
- For tests, use `reset_container()` to get fresh state
- Don't instantiate repositories directly; let Punq inject the connection

### DSPy Signatures

When defining DSPy signatures, type the fields accurately:

```python
class MySignature(dspy.Signature):
    """Docstring becomes the prompt context."""

    input_text: str = dspy.InputField(desc="What this input contains")
    count: int = dspy.InputField(desc="Numeric input")

    result: str = dspy.OutputField(desc="What the LLM should produce")
    score: float = dspy.OutputField(desc="Numeric score from 0.0 to 1.0")
    items: list[str] = dspy.OutputField(desc="List of extracted items")
    valid: bool = dspy.OutputField(desc="True/False judgment")
```

The type annotations (`str`, `int`, `float`, `bool`, `list[str]`) guide the LLM's output format. The `desc` should clarify semantics, not just repeat the type.

### Storage

Data persists to `.voicetest/data.duckdb` (or `VOICETEST_DB_PATH` env var).

Tests are scoped to agents via `agent_id` foreign key in `test_cases` table.

### Svelte 5 Reactivity

Critical rules to prevent silent reactivity failures:

- Use `$derived($store)` to consume stores in components
- Never use `Set` or `Map` with `$state` or `writable` stores
- Always reassign objects/arrays instead of mutating
- Use `onMount()` for one-time data fetching, not `$effect()`

## Project Structure

```
voicetest/
├── voicetest/           # Python package
│   ├── container.py     # DI container (Punq)
│   ├── rest.py          # REST API + WebSocket + SPA
│   ├── storage/         # DuckDB persistence
│   │   ├── db.py        # Connection factory and schema
│   │   └── repositories.py
│   ├── importers/       # Source importers
│   ├── exporters/       # Format exporters
│   └── platforms/       # Platform SDK clients
├── web/                 # Frontend (Bun + Svelte + Vite)
│   ├── src/
│   │   ├── components/
│   │   └── lib/         # API client, stores, types
│   └── e2e/             # Playwright tests
└── tests/
    ├── unit/
    ├── integration/
    └── fixtures/        # Shared test fixtures
```

## Test Fixtures

Shared fixtures live in `tests/fixtures/`:

- `graphs/simple_graph.json` - Basic agent graph for testing
- `retell/` - Retell format samples
- `vapi/` - VAPI format samples
- `livekit/` - LiveKit format samples

Use fixtures via pytest:

```python
def test_something(sample_graph_dict, fixtures_dir):
    # sample_graph_dict is the parsed JSON
    # fixtures_dir is Path to tests/fixtures/
```
