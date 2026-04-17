# Development

## Code quality

All code must pass pre-commit checks before committing:

```bash
uv run pre-commit run --all-files
```

**Pre-commit hooks:**

- **Python**: `ruff` (lint + auto-fix) and `ruff-format`
- **TypeScript/Svelte**: `svelte-check` and `tsc --noEmit`
- **Markdown**: `mdformat` with MkDocs support
- **General**: trailing-whitespace, end-of-file-fixer, check-yaml, check-json

**Python style (pyproject.toml):**

- Line length: 100, target Python 3.12
- **Imports must be at top of file** (PLC0415 enforced)
- 2 blank lines after imports
- No relative parent imports (`from .. import` banned)
- No unused imports/variables

**TypeScript/Svelte style:**

- Strict mode enabled
- No unused locals or parameters
- No fallthrough in switch statements

## Test fixtures

Shared fixtures live in `tests/fixtures/`:

- `graphs/simple_graph.json` — Basic agent graph for testing
- `retell/` — Retell format samples (including extract variables, global nodes)
- `vapi/` — VAPI format samples
- `livekit/` — LiveKit format samples

Use fixtures via pytest:

```python
def test_something(sample_graph_dict, fixtures_dir):
    # sample_graph_dict is the parsed JSON
    # fixtures_dir is Path to tests/fixtures/
```

## Docker development (recommended)

The easiest way to get a full development environment running is with Docker Compose:

```bash
# Clone and start all services
git clone https://github.com/voicetestdev/voicetest
cd voicetest
docker compose -f docker-compose.dev.yml up
```

The dev compose file includes the base infrastructure from `voicetest/compose/docker-compose.yml` (the same file bundled with the package for `voicetest up`) and adds backend + frontend services on top. This starts five services:

| Service    | URL                   | Description                              |
| ---------- | --------------------- | ---------------------------------------- |
| `livekit`  | ws://localhost:7880   | LiveKit server for real-time voice calls |
| `whisper`  | http://localhost:8001 | Faster Whisper STT server                |
| `kokoro`   | http://localhost:8002 | Kokoro TTS server                        |
| `backend`  | http://localhost:8000 | FastAPI backend with hot reload          |
| `frontend` | http://localhost:5173 | Vite dev server with hot reload          |

Open http://localhost:5173 to access the web UI. Changes to Python or TypeScript files trigger automatic reloads.

**Claude Code authentication:** The dev image includes Claude Code CLI. To authenticate for `claudecode/*` model passthrough:

```bash
docker compose -f docker-compose.dev.yml exec backend claude login
```

Credentials persist in the `claude-auth` Docker volume across container restarts.

**Linked agents:** The compose file mounts your home directory (`$HOME`) read-only so linked agents with absolute paths work inside the container. On macOS, you may need to grant Docker Desktop access to your home directory in Settings → Resources → File Sharing.

To stop all services:

```bash
docker compose -f docker-compose.dev.yml down
```

## Manual development

If you prefer running services manually (e.g., for debugging):

```bash
# Clone and install
git clone https://github.com/voicetestdev/voicetest
cd voicetest
uv sync

# Run unit tests
uv run pytest tests/unit

# Run integration tests (requires Ollama with qwen2.5:0.5b)
uv run pytest tests/integration

# Lint
uv run ruff check voicetest/ tests/
```

## LiveKit CLI

LiveKit integration tests require the `lk` CLI tool for agent deployment and listing operations. Install it from https://docs.livekit.io/home/cli/cli-setup/

```bash
# macOS
brew install livekit-cli

# Linux
curl -sSL https://get.livekit.io/cli | bash
```

Tests that require the CLI will skip automatically if it's not installed.

## Frontend development

The web UI is built with Bun + Svelte + Vite. The recommended approach is to use Docker Compose (see above), which handles all services automatically.

For manual frontend development, uses [mise](https://mise.jdx.dev/) for version management:

```bash
# Terminal 1 - Frontend dev server with hot reload
cd web
mise exec -- bun install
mise exec -- bun run dev   # http://localhost:5173

# Terminal 2 - Backend API
uv run voicetest serve --reload   # http://localhost:8000

# Terminal 3 - LiveKit server (for live voice calls)
docker run --rm -p 7880:7880 -p 7881:7881 -p 7882:7882/udp livekit/livekit-server --dev
```

The Vite dev server proxies `/api/*` to the FastAPI backend.

```bash
# Run frontend tests
cd web && npx vitest run

# Build for production
cd web && mise exec -- bun run build
```

Svelte 5 reactivity guidelines are documented in `web/README.md`.

## Project structure

```
voicetest/
├── voicetest/           # Python package
│   ├── cli.py           # CLI (40+ commands)
│   ├── rest.py          # REST API server + WebSocket + SPA serving
│   ├── container.py     # Dependency injection (Punq)
│   ├── cache.py         # LLM response cache (disk + S3 backends)
│   ├── templating.py    # Snippet and variable expansion
│   ├── services/        # Service layer (agents, diagnosis, evaluation, runs, snippets, etc.)
│   ├── compose/         # Bundled Docker Compose for infrastructure services
│   ├── models/          # Pydantic models (agent, test_case, results, decompose, etc.)
│   ├── importers/       # Source importers (retell, vapi, bland, telnyx, livekit, xlsform, custom)
│   ├── exporters/       # Format exporters (mermaid, livekit, retell, vapi, bland, telnyx, voicetest_ir)
│   ├── platforms/       # Platform SDK clients (retell, vapi, bland, telnyx, livekit)
│   ├── engine/          # Execution engine
│   │   ├── conversation.py    # ConversationEngine: advance(), graph traversal
│   │   ├── equations.py       # Deterministic equation evaluation
│   │   ├── modules.py         # DSPy modules for state execution
│   │   ├── session.py         # ConversationRunner for simulated tests
│   │   └── livekit_llm.py     # LiveKit real-time integration
│   ├── simulator/       # User simulation
│   ├── judges/          # Evaluation judges (metric, rule, diagnosis)
│   ├── storage/         # DuckDB persistence layer
│   └── tui/             # TUI and shell
├── claude-plugin/       # Claude Code plugin (commands + skills)
│   ├── commands/        # Slash commands (/voicetest-run, etc.)
│   └── skills/          # Auto-activating skill + references
├── web/                 # Frontend (Bun + Svelte + Vite)
│   ├── src/
│   │   ├── components/  # Svelte components
│   │   └── lib/         # API client, stores, types
│   └── dist/            # Built assets (bundled in package)
├── tests/
│   ├── unit/            # Unit tests
│   └── integration/     # Integration tests (Ollama)
└── docs/
```
