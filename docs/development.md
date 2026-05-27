---
description: Contributor guide — code quality, fixtures, Docker development, frontend, and voicetest's internals.
---

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

## Internals

These details are useful when contributing to voicetest or building on its Python API. Public users don't need to read this section.

### DI container (Punq)

The project uses [Punq](https://github.com/bobthemighty/punq) for dependency injection. Key singletons:

- `Engine`, `sessionmaker`, `Session` — SQLAlchemy database layer (DuckDB-backed)
- `ImporterRegistry`, `ExporterRegistry`, `PlatformRegistry` — registries

Repositories are transient but share the singleton session:

- `AgentRepository`, `TestCaseRepository`, `RunRepository`, `CallRepository`

Get instances via `voicetest.container`:

```python
from voicetest.container import get_session, get_importer_registry
```

**When to use DI:**

- Use `get_*` helpers for app code (REST handlers, CLI commands).
- Use `container.resolve(Type)` when you need the container directly.
- For tests, use `reset_container()` to get fresh state.
- Don't instantiate repositories directly; let Punq inject the session.

### DSPy signatures

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

### Retry and idempotency

`voicetest.util.retry.with_retry` wraps the LLM call path (`voicetest.llm.base.call_llm`) with exponential backoff. Retries fire on the exceptions listed in `RETRYABLE_EXCEPTIONS`: `litellm.RateLimitError`, `litellm.Timeout`, `litellm.APIConnectionError`, `openai.APITimeoutError`, and `AdapterParseError`.

LLM-provider classes are responsible for translating transient upstream failures into one of these exception types so the retry layer catches them — e.g. `voicetest.llm.claudecode.ClaudeCodeLM` maps 5xx → `APIConnectionError`, 429 → `RateLimitError`, 408/504/524 → `Timeout`. Non-transient errors (4xx other than the rate-limit/timeout codes, malformed responses, quota exhausted) stay as `RuntimeError` or `QuotaExhaustedError` so they fail fast instead of burning the retry budget.

**Idempotency contract.** The retry layer assumes the wrapped function is idempotent. Today every caller is an LLM completion, where duplicate generations on the upstream side are accepted: the worst case is an extra billed token chunk that never reaches us. If a future caller performs side effects (tool execution, DB write, external API mutation), that call MUST NOT be retried by `with_retry`. Wrap it in explicit error handling, or guard the side effect with an idempotency key on the receiving side. Extending `RETRYABLE_EXCEPTIONS` or adding new `with_retry` call sites without checking this contract will silently re-trigger side effects on transient failure.

### Function nodes (tool calls) — weak support

`NodeType.FUNCTION` represents a tool-call node in the agent graph (Retell CF's `"type": "function"` is the canonical example — a node whose runtime job is to invoke an external HTTP/webhook tool and branch on the result). Voicetest **does not execute the underlying tool**. The engine's behavior on a function node is deliberately limited:

- A `logger.warning(...)` records that the node was reached and that tool execution is unsupported, naming the node id and pointing to the tracking issue.
- The engine then follows the first `always`-type transition out of the node (Retell's `else_edge` shape, imported into the IR as an always-type `Transition`).
- If no fallback edge is present, the call stalls cleanly — empty response, no exception.
- Non-`always` transitions on the function node are **skipped**, even when their conditions reference variables that voicetest could in principle evaluate. This is intentional: in practice these conditions are almost always tool-result driven (e.g. `{{tool_result.status}} == "success"`); evaluating them against an absent `tool_result` would return false and route the conversation incorrectly. Taking the else edge unconditionally is the safer default until real tool execution lands.

The full tool-execution roadmap — mock-mode (consume `TestCase.tool_mocks`), live HTTP execution behind a flag, and result-driven branching — is tracked at [voicetestdev/voicetest#51](https://github.com/voicetestdev/voicetest/issues/51). When that work lands, `_evaluate_function_node` in `voicetest/engine/conversation.py` is the swap-in site.

### Retell terminal-tool conversion

When importing Retell LLM-format agents, terminal tools (`end_call`, `transfer_call`) are converted to proper CF node types during export rather than remaining as tools in the tools array:

- `end_call` tools become `type=end` nodes in the Conversation Flow.
- `transfer_call` tools become `type=transfer_call` nodes with `transfer_destination` and `transfer_option`.
- Tool metadata carries `transfer_destination` and `transfer_option` through the import/export pipeline.
- The agent envelope (voice_id, language, etc.) is preserved from LLM format through CF export so the result re-imports cleanly into the Retell UI.

## Project structure

```
voicetest/
├── voicetest/                    # Python package
│   ├── cli.py                    # CLI (40+ commands)
│   ├── container.py              # Dependency injection (Punq) — composition root
│   ├── config.py                 # Path resolution for .voicetest/ data dirs
│   ├── settings.py               # Pydantic Settings model + TOML loading
│   ├── exceptions.py             # Shared domain exceptions
│   ├── runner.py                 # Shared CLI/TUI run orchestration over AppServices
│   ├── web/                      # FastAPI + WebSocket + SPA serving
│   │   ├── rest.py               # REST endpoints + lifespan
│   │   ├── broadcast.py          # BroadcastBus + SessionRegistry (WS pub/sub)
│   │   ├── coordinator.py        # RunCoordinator: per-run cancel + orphan claim
│   │   ├── calls.py              # CallManager: live LiveKit voice calls
│   │   └── chat.py               # ChatManager: text chat sessions
│   ├── livecall/                 # Live-call agent runtime
│   │   ├── agent_worker.py       # `python -m voicetest.livecall.agent_worker` subprocess
│   │   └── livekit_adapter.py    # LiveKit llm.LLM adapter wrapping ConversationEngine
│   ├── engine/                   # Conversation engine
│   │   ├── conversation.py       # ConversationEngine: advance(), graph traversal
│   │   ├── equations.py          # Deterministic equation evaluation
│   │   ├── modules.py            # DSPy modules for state execution
│   │   └── session.py            # ConversationRunner for simulated tests
│   ├── services/                 # Service layer (agents, diagnosis, evaluation, runs, etc.)
│   │   └── run_runner.py         # Background test-run orchestrator (scheduled by REST)
│   ├── simulator/                # User simulation (LLM-driven + scripted replay)
│   ├── judges/                   # Evaluation judges (metric, rule, diagnosis)
│   ├── llm/                      # LLM client + retry infrastructure
│   ├── models/                   # Pydantic models (agent, test_case, results, decompose, etc.)
│   ├── importers/                # Source importers (retell, vapi, bland, telnyx, livekit, xlsform, custom)
│   ├── exporters/                # Format exporters (mermaid, livekit, retell, vapi, bland, telnyx, voicetest_ir)
│   ├── platforms/                # Platform SDK clients (retell, vapi, bland, telnyx, livekit)
│   ├── storage/                  # SQLAlchemy + DuckDB persistence layer
│   ├── tui/                      # TUI and shell
│   ├── util/                     # Pure helpers (audio, cache, formatting, retry, templating, etc.)
│   ├── compose/                  # Packaged resource: docker-compose.yml shipped in the wheel,
│   │                             # loaded via importlib.resources by `voicetest up`
│   └── demo/                     # Packaged resource: bundled demo agent + tests JSON,
│                                 # loaded via importlib.resources by `voicetest demo`
├── claude-plugin/                # Claude Code plugin (commands + skills)
├── web/                          # Frontend (Bun + Svelte + Vite)
│   └── dist/                     # Built assets (bundled in package)
├── tests/
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests (Ollama)
│   └── fixtures/                 # Sample agent/test JSON for tests
└── docs/
```

`compose/` and `demo/` live inside the Python package on purpose — they're loaded via `importlib.resources` so they ship with the wheel and work for pip-installed users. The root-level `docker-compose.dev.yml` is a separate dev-only file that *includes* `voicetest/compose/docker-compose.yml`.
