[![PyPI](https://img.shields.io/pypi/v/voicetest)](https://pypi.org/project/voicetest/) [![Release](https://img.shields.io/github/v/release/voicetestdev/voicetest)](https://github.com/voicetestdev/voicetest/releases) [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![Tests](https://github.com/voicetestdev/voicetest/actions/workflows/test.yml/badge.svg)](https://github.com/voicetestdev/voicetest/actions/workflows/test.yml)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
  <img alt="voicetest" src="assets/logo-light.svg" width="300">
</picture>

A generic test harness for voice agent workflows. Test agents from Retell, VAPI, LiveKit, Bland, Telnyx, and custom sources using a unified execution and evaluation model.

## Installation

```bash
uv tool install voicetest
```

Or add to a project (use `uv run voicetest` to run):

```bash
uv add voicetest
```

Or with pip:

```bash
pip install voicetest
```

## Quick Demo

Try voicetest with a sample healthcare receptionist agent and tests:

```bash
# Set up an API key (free, no credit card at https://console.groq.com)
export GROQ_API_KEY=gsk_...

# Load demo and start interactive shell
voicetest demo

# Or load demo and start web UI
voicetest demo --serve
```

> **Tip:** If you have [Claude Code](https://claude.ai/claude-code) installed, you can skip API key setup entirely and use `claudecode/sonnet` as your model. See [Claude Code Passthrough](#claude-code-passthrough) for details.

The demo includes a healthcare receptionist agent with 8 test cases covering appointment scheduling, identity verification, and more.

![CLI Demo](docs/demos/cli-demo.gif)

![Web UI Demo](docs/demos/web-demo.gif)

## Quick Start

### Interactive Shell

```bash
# Launch interactive shell (default)
uv run voicetest

# In the shell:
> agent tests/fixtures/retell/sample_config.json
> tests tests/fixtures/retell/sample_tests.json
> set agent_model ollama_chat/qwen2.5:0.5b
> run
```

### CLI Commands

```bash
# List available importers
voicetest importers

# Run tests against an agent definition
voicetest run --agent agent.json --tests tests.json

# Export agent to different formats
voicetest export --agent agent.json --format mermaid         # Diagram
voicetest export --agent agent.json --format livekit         # Python code
voicetest export --agent agent.json --format retell-llm      # Retell LLM JSON
voicetest export --agent agent.json --format retell-cf       # Retell Conversation Flow JSON
voicetest export --agent agent.json --format vapi-assistant  # VAPI Assistant JSON
voicetest export --agent agent.json --format vapi-squad      # VAPI Squad JSON
voicetest export --agent agent.json --format bland           # Bland AI JSON
voicetest export --agent agent.json --format telnyx          # Telnyx AI JSON
voicetest export --agent agent.json --format voicetest       # Voicetest JSON (.vt.json)

# Launch full TUI
voicetest tui --agent agent.json --tests tests.json

# Start REST API server with Web UI
voicetest serve

# Start infrastructure (LiveKit, Whisper, Kokoro) + backend for live calls
voicetest up

# Stop infrastructure services
voicetest down
```

### Live Voice Calls

For live voice calls, you need infrastructure services (LiveKit, Whisper STT, Kokoro TTS). The `up` command starts them via Docker and then launches the backend:

```bash
# Start infrastructure + backend server
voicetest up

# Or start infrastructure only (e.g., to run the backend separately)
voicetest up --detach

# Stop infrastructure when done
voicetest down
```

This requires Docker with the compose plugin. The infrastructure services are:

| Service   | URL                   | Description                              |
| --------- | --------------------- | ---------------------------------------- |
| `livekit` | ws://localhost:7880   | LiveKit server for real-time voice calls |
| `whisper` | http://localhost:8001 | Faster Whisper STT server                |
| `kokoro`  | http://localhost:8002 | Kokoro TTS server                        |

If you only need simulated tests (no live voice), `voicetest serve` is sufficient and does not require Docker.

### Web UI

Start the server and open http://localhost:8000 in your browser:

```bash
voicetest serve
```

The web UI provides:

- Agent import and graph visualization
- Export agents to multiple formats (Mermaid, LiveKit, Retell, VAPI, Bland, Telnyx)
- Platform integration: import agents from, push agents to, and sync changes back to Retell, VAPI, LiveKit, Telnyx
- Test case management with persistence
- Export tests to platform formats (Retell)
- Global metrics configuration (compliance checks that run on all tests)
- Test execution with real-time streaming transcripts
- Cancel in-progress tests
- Run history with detailed results
- Transcript and metric inspection with scores
- Audio evaluation with word-level diff of original vs. heard text
- Settings configuration (models, max turns, streaming, audio eval)

Data is persisted to `.voicetest/data.duckdb` (configurable via `VOICETEST_DB_PATH`).

### REST API

The REST API is available at http://localhost:8000/api when running `voicetest serve`. Full API documentation is at [voicetest.dev/api](https://voicetest.dev/api/).

```bash
# Health check
curl http://localhost:8000/api/health

# List agents
curl http://localhost:8000/api/agents

# Start a test run
curl -X POST http://localhost:8000/api/agents/{id}/runs \
  -H "Content-Type: application/json" \
  -d '{"test_ids": ["test-1", "test-2"]}'

# WebSocket for real-time updates
wscat -c ws://localhost:8000/api/runs/{id}/ws
```

## Format Conversion

voicetest can convert between agent formats via its unified AgentGraph representation:

```
Retell CF ─────┐                  ┌───▶ Retell LLM
               │                  │
Retell LLM ────┼                  ├───▶ Retell CF
               │                  │
VAPI ──────────┼                  ├───▶ VAPI
               │                  │
Bland ─────────┼───▶ AgentGraph ──┼───▶ Bland
               │                  │
Telnyx ────────┤                  ├───▶ Telnyx
               │                  │
LiveKit ───────┤                  ├───▶ LiveKit
               │                  │
XLSForm ───────┤                  ├───▶ Mermaid
               │                  │
Custom ────────┘                  └───▶ Voicetest JSON
```

Import from any supported format, then export to any other:

```bash
# Convert Retell Conversation Flow to Retell LLM format
voicetest export --agent retell-cf-agent.json --format retell-llm > retell-llm-agent.json

# Convert VAPI assistant to Retell LLM format
voicetest export --agent vapi-assistant.json --format retell-llm > retell-agent.json

# Convert Retell LLM to VAPI format
voicetest export --agent retell-llm-agent.json --format vapi-assistant > vapi-agent.json
```

## Test Case Format

Test cases follow the Retell export format:

```json
[
  {
    "name": "Customer billing inquiry",
    "user_prompt": "## Identity\nYour name is Jane.\n\n## Goal\nGet help with a charge on your bill.",
    "metrics": ["Agent greeted the customer and addressed the billing concern"],
    "dynamic_variables": {},
    "tool_mocks": [],
    "type": "simulation"
  }
]
```

## Features

- **Multi-source import**: Retell CF, Retell LLM, VAPI, Bland, Telnyx, LiveKit, XLSForm, custom Python functions
- **Format conversion**: Convert between Retell, VAPI, Bland, Telnyx, LiveKit, and other formats
- **Unified IR**: AgentGraph representation for any voice agent
- **Multi-format export**: Mermaid diagrams, LiveKit Python, Retell LLM, Retell CF, VAPI, Bland, Telnyx, Voicetest JSON (.vt.json)
- **Platform integration**: Import, push, and sync agents with Retell, VAPI, Bland, Telnyx, LiveKit via API
- **Configurable LLMs**: Separate models for agent, simulator, and judge
- **DSPy-based evaluation**: LLM judges with reasoning and 0-1 scores
- **Global metrics**: Define compliance checks that run on all tests for an agent
- **Multiple interfaces**: CLI, TUI, interactive shell, Web UI, REST API
- **Persistence**: DuckDB storage for agents, tests, and run history
- **Real-time streaming**: WebSocket-based transcript streaming during test execution
- **Token streaming**: Optional token-level streaming as LLM generates responses (experimental)
- **Cancellation**: Cancel in-progress tests to stop token usage
- **Prompt snippets**: Named reusable text blocks (`{%name%}`) with auto-DRY analysis
- **Audio evaluation**: TTS→STT round-trip to catch pronunciation issues (e.g., phone numbers spoken as words)

## Global Metrics

Global metrics are compliance-style checks that run on every test for an agent. Configure them in the "Metrics" tab in the Web UI.

Each agent has:

- **Pass threshold**: Default score (0-1) required for metrics to pass (default: 0.7)
- **Global metrics**: List of criteria evaluated on every test run

Each global metric has:

- **Name**: Display name (e.g., "HIPAA Compliance")
- **Criteria**: What the LLM judge evaluates (e.g., "Agent must verify patient identity before sharing medical information")
- **Threshold override**: Optional per-metric threshold (uses agent default if not set)
- **Enabled**: Toggle to skip without deleting

Example use cases:

- HIPAA compliance checks for healthcare agents
- PCI-DSS validation for payment processing
- Brand voice consistency across all conversations
- Safety guardrails and content policy adherence

## Prompt Snippets (DRY)

Agent prompts often repeat text across nodes — sign-off phrases, compliance disclaimers, tone instructions, etc. **Snippets** are named, reusable text blocks defined at the agent level and referenced in prompts via `{%snippet_name%}`.

### Defining Snippets

In the Web UI, open an agent and scroll to the **Snippets** section. Each snippet has a name and a text body:

| Snippet Name | Text                                                             |
| ------------ | ---------------------------------------------------------------- |
| `sign_off`   | "Thank you for calling. Is there anything else I can help with?" |
| `hipaa_warn` | "I need to verify your identity before sharing medical info."    |

### Referencing Snippets in Prompts

Use `{%name%}` (with percent signs) in any node prompt or general prompt:

```
Welcome the caller and introduce yourself.

{%hipaa_warn%}

When the conversation ends:
{%sign_off%}
```

Snippets are expanded (replaced with their text) **before** dynamic variables (`{{var}}`), so you can combine both:

```
Hello {{caller_name}}, {%greeting%}
```

### Auto-DRY Analysis

Click **Analyze DRY** to scan all prompts for repeated or near-identical text:

- **Exact matches**: Sentences that appear verbatim in 2+ nodes. Click "Apply" to extract into a snippet and replace all occurrences with `{%ref%}`.
- **Fuzzy matches**: Sentences that are similar (above 80% match). Review and decide whether to unify them.
- **Apply All**: Applies all exact-match suggestions at once.

### Export Modes

When an agent has snippets, the export modal offers two modes:

- **Raw (.vt.json)**: Preserves `{%snippet%}` references and the snippets dictionary. Use this for sharing with teammates or version control.
- **Expanded**: Resolves all snippet references to plain text. Use this for platform deployment (Retell, VAPI, LiveKit, etc.).

Platform-specific formats (Retell, VAPI, Bland, Telnyx, LiveKit) are always exported expanded.

### REST API

```bash
# Get snippets for an agent
curl http://localhost:8000/api/agents/{id}/snippets

# Update a single snippet
curl -X PUT http://localhost:8000/api/agents/{id}/snippets/sign_off \
  -H "Content-Type: application/json" \
  -d '{"text": "Thanks for calling!"}'

# Run DRY analysis
curl -X POST http://localhost:8000/api/agents/{id}/analyze-dry

# Apply suggested snippets
curl -X POST http://localhost:8000/api/agents/{id}/apply-snippets \
  -H "Content-Type: application/json" \
  -d '{"snippets": [{"name": "sign_off", "text": "Thanks for calling!"}]}'

# Export with snippets expanded
curl -X POST http://localhost:8000/api/agents/export \
  -H "Content-Type: application/json" \
  -d '{"graph": {...}, "format": "retell-llm", "expanded": true}'
```

## Post-Run Diagnosis & Auto-Fix

When a test fails, voicetest can diagnose the root cause and suggest concrete prompt changes to fix it.

### Manual Flow

1. **Diagnose** - Click "Diagnose" on a failed result. The LLM analyzes the graph, transcript, and failed metrics to identify fault locations and root cause.
1. **Review & Edit** - Proposed changes are shown as editable textareas. Modify the suggested text before applying.
1. **Apply & Test** - Click "Apply & Test" to apply changes to a copy of the graph and rerun the test. A score comparison table shows original vs. new scores with deltas.
1. **Iterate** - If not all metrics pass, click "Try Again" to revise the fix based on the latest results. The table shows delta from both original and previous iteration.
1. **Save** - Click "Save Changes" to persist the fix to the agent graph.

### Model Selection

Enter a model string (e.g., `openai/gpt-4o`, `anthropic/claude-3-sonnet`) in the model input to override the default judge model for diagnosis and fix revision. Leave blank to use the model from settings.

### Auto-Fix Mode

Click "Auto Fix" to run an automated diagnose-apply-revise loop:

- **Stop condition**: "On improvement" stops when scores improve; "When all pass" stops only when every metric passes.
- **Max iterations**: Limits the number of apply-revise cycles (1-10, default 3).
- **Progress**: A live table shows scores with deltas from both original and previous iteration.
- **Cancel**: Stop the loop at any time.

### REST API

```bash
# Diagnose a failed result (optional model override)
curl -X POST http://localhost:8000/api/results/{result_id}/diagnose \
  -H "Content-Type: application/json" \
  -d '{"model": "openai/gpt-4o"}'

# Apply fix and rerun test
curl -X POST http://localhost:8000/api/results/{result_id}/apply-fix \
  -H "Content-Type: application/json" \
  -d '{"changes": [...], "iteration": 1}'

# Revise a fix based on new metric results
curl -X POST http://localhost:8000/api/results/{result_id}/revise-fix \
  -H "Content-Type: application/json" \
  -d '{"diagnosis": {...}, "previous_changes": [...], "new_metric_results": [...], "model": "openai/gpt-4o"}'

# Save changes to agent graph
curl -X POST http://localhost:8000/api/agents/{agent_id}/save-fix \
  -H "Content-Type: application/json" \
  -d '{"changes": [...]}'
```

## Audio Evaluation

Text-only evaluation has a blind spot: when an agent produces "415-555-1234", an LLM judge sees correct digits and passes. But TTS might speak it as "four hundred fifteen, five hundred fifty-five..." — which a caller can't use. Audio evaluation catches these issues by round-tripping agent messages through TTS→STT and judging what would actually be *heard*.

```
Conversation runs normally (text-only)
    ↓
Judges evaluate raw text → metric_results
    ↓
Agent messages → TTS → audio → STT → "heard" text
    ↓
Judges evaluate heard text → audio_metric_results
```

Both sets of results are stored. The original message text is preserved alongside what was heard, with a word-level diff shown in the UI.

### Triggering Audio Evaluation

**Automatic (per-run setting):** Enable `audio_eval` in settings to run TTS→STT round-trip on every test automatically.

```toml
# .voicetest/settings.toml
[run]
audio_eval = true
```

Or toggle the "Audio evaluation" checkbox in the Settings page of the Web UI.

**On-demand (button):** After a test completes, click "Run audio eval" in the results view to run audio evaluation on that specific result.

**REST API:**

```bash
# Run audio eval on an existing result
curl -X POST http://localhost:8000/api/results/{result_id}/audio-eval
```

### Requirements

Audio evaluation requires the TTS and STT services from `voicetest up`:

| Service   | URL                   | Description        |
| --------- | --------------------- | ------------------ |
| `whisper` | http://localhost:8001 | Faster Whisper STT |
| `kokoro`  | http://localhost:8002 | Kokoro TTS         |

Service URLs are configurable in settings:

```toml
# .voicetest/settings.toml
[audio]
tts_url = "http://localhost:8002/v1"
stt_url = "http://localhost:8001/v1"
```

## Platform Integration

voicetest can connect directly to voice platforms to import and push agent configurations.

### Supported Platforms

| Platform | Import | Push | Sync | API Key Env Var                          |
| -------- | ------ | ---- | ---- | ---------------------------------------- |
| Retell   | ✓      | ✓    | ✓    | `RETELL_API_KEY`                         |
| VAPI     | ✓      | ✓    | ✓    | `VAPI_API_KEY`                           |
| Bland    | ✓      | ✓    |      | `BLAND_API_KEY`                          |
| Telnyx   | ✓      | ✓    | ✓    | `TELNYX_API_KEY`                         |
| LiveKit  | ✓      | ✓    | ✓    | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |

### Usage

In the Web UI, go to the "Platforms" tab to:

1. **Configure** - Enter API keys (stored in settings, not in env)
1. **Browse** - List agents on the remote platform
1. **Import** - Pull an agent config into voicetest for testing
1. **Push** - Deploy a local agent to the platform
1. **Sync** - Push local changes back to the source platform (for imported agents)

API keys can also be set via environment variables or in the Settings page.

## CI/CD Integration

Run voice agent tests in CI to catch regressions before they reach production. Key benefits:

- **Bring your own LLM keys** - Use OpenRouter, OpenAI, etc. directly instead of paying per-minute through Retell/VAPI's built-in LLM interfaces
- **Test on prompt changes** - Automatically validate agent behavior when prompts or configs change
- **Track quality over time** - Ensure consistent agent performance across releases

Example GitHub Actions workflow (see [docs/examples/ci-workflow.yml](docs/examples/ci-workflow.yml)):

```yaml
name: Voice Agent Tests
on:
  push:
    paths: ["agents/**"]  # Trigger on agent config or test changes

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install voicetest
      - run: voicetest run --agent agents/receptionist.json --tests agents/tests.json --all
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

## LLM Configuration

Configure different models for each role using [LiteLLM format](https://docs.litellm.ai/docs/providers):

```python
from voicetest.models.test_case import RunOptions

options = RunOptions(
    agent_model="openai/gpt-4o-mini",
    simulator_model="gemini/gemini-1.5-flash",
    judge_model="anthropic/claude-3-haiku-20240307",
    max_turns=20,
)
```

Or use Ollama for local execution:

```python
options = RunOptions(
    agent_model="ollama_chat/qwen2.5:0.5b",
    simulator_model="ollama_chat/qwen2.5:0.5b",
    judge_model="ollama_chat/qwen2.5:0.5b",
)
```

In the shell:

```
> set agent_model gemini/gemini-1.5-flash
> set simulator_model ollama_chat/qwen2.5:0.5b
```

### Claude Code Passthrough

If you have [Claude Code](https://claude.ai/claude-code) installed, you can use it as your LLM backend without configuring API keys:

```toml
# .voicetest/settings.toml
[models]
agent = "claudecode/sonnet"
simulator = "claudecode/haiku"
judge = "claudecode/sonnet"
```

Available model strings:

- `claudecode/sonnet` - Claude Sonnet
- `claudecode/opus` - Claude Opus
- `claudecode/haiku` - Claude Haiku

This invokes the `claude` CLI via subprocess, using your existing Claude Code authentication.

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

### Terminal Tool Conversion (Retell)

When importing Retell LLM format agents, terminal tools (`end_call`, `transfer_call`) are converted to proper CF node types during export rather than remaining as tools in the tools array:

- `end_call` tools become `type=end` nodes in the Conversation Flow
- `transfer_call` tools become `type=transfer_call` nodes with `transfer_destination` and `transfer_option`
- Tool metadata carries `transfer_destination` and `transfer_option` through the import/export pipeline
- The agent envelope (voice_id, language, etc.) is preserved from LLM format through CF export for Retell UI re-import

### Diagnosis & Auto-Fix

Post-run failure diagnosis and auto-fix flow:

- `voicetest/models/diagnosis.py` - Pydantic models (Diagnosis, FixSuggestion, PromptChange, etc.)
- `voicetest/judges/diagnosis.py` - DSPy signatures and DiagnosisJudge class
- `voicetest/api.py` - `diagnose_failure()`, `apply_and_rerun()`, `revise_fix()`, `apply_fix_to_graph()`
- `voicetest/rest.py` - REST endpoints: `/results/{id}/diagnose`, `/results/{id}/apply-fix`, `/results/{id}/revise-fix`, `/agents/{id}/save-fix`
- `web/src/components/RunsView.svelte` - UI: diagnose button, model input, edit-before-apply textareas, auto-fix loop with progress

Flow: diagnose (identify fault locations + root cause) -> suggest fix (prompt changes) -> user edits changes -> apply & rerun test -> compare scores -> iterate or save.

## Development

### Code Quality

All code must pass pre-commit checks before committing:

```bash
uv run pre-commit run --all-files
```

**Pre-commit Hooks:**

- **Python**: `ruff` (lint + auto-fix) and `ruff-format`
- **TypeScript/Svelte**: `svelte-check` and `tsc --noEmit`
- **Markdown**: `mdformat` with GFM support
- **General**: trailing-whitespace, end-of-file-fixer, check-yaml, check-json

**Python Style (pyproject.toml):**

- Line length: 100, target Python 3.12
- **Imports must be at top of file** (PLC0415 enforced)
- 2 blank lines after imports
- No relative parent imports (`from .. import` banned)
- No unused imports/variables

**TypeScript/Svelte Style:**

- Strict mode enabled
- No unused locals or parameters
- No fallthrough in switch statements

### Test Fixtures

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

### Docker Development (Recommended)

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

**Claude Code Authentication:** The dev image includes Claude Code CLI. To authenticate for `claudecode/*` model passthrough:

```bash
docker compose -f docker-compose.dev.yml exec backend claude login
```

Credentials persist in the `claude-auth` Docker volume across container restarts.

**Linked Agents:** The compose file mounts your home directory (`$HOME`) read-only so linked agents with absolute paths work inside the container. On macOS, you may need to grant Docker Desktop access to your home directory in Settings → Resources → File Sharing.

To stop all services:

```bash
docker compose -f docker-compose.dev.yml down
```

### Manual Development

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

### LiveKit CLI

LiveKit integration tests require the `lk` CLI tool for agent deployment and listing operations. Install it from https://docs.livekit.io/home/cli/cli-setup/

```bash
# macOS
brew install livekit-cli

# Linux
curl -sSL https://get.livekit.io/cli | bash
```

Tests that require the CLI will skip automatically if it's not installed.

### Frontend Development

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

**Svelte 5 Reactivity Guidelines:**

- Use `$derived($store)` to consume Svelte stores in components - the `$store` syntax alone may not trigger re-renders in browsers
- Do not use `Set` or `Map` with `$state` or `writable` stores - use arrays and `Record<K,V>` instead
- Always reassign objects/arrays instead of mutating them: `obj = { ...obj, [key]: value }` not `obj[key] = value`
- Use `onMount()` for one-time data fetching, not `$effect()` - effects are for reactive dependencies
- Violating these rules can cause the entire app's reactivity to silently break

```svelte
<script lang="ts">
  import { myStore } from "./stores";

  // WRONG - may not trigger re-renders in browser
  // {#if $myStore === "value"}

  // CORRECT - use $derived for reliable reactivity
  let value = $derived($myStore);
  // {#if value === "value"}
</script>
```

**When to Add Libraries:**

The frontend uses minimal dependencies by design. Consider adding a library when:

- Table features: Need filtering, pagination, virtual scrolling, or column resizing (→ `@tanstack/svelte-table`)
- Forms: Complex validation, multi-step wizards, or field arrays (→ `superforms` + `zod`)
- Charts: Need data visualization beyond simple metrics (→ `layerchart` or `pancake`)
- State: Cross-component state becomes unwieldy with stores (→ evaluate if architecture needs rethinking first)

## Project Structure

```
voicetest/
├── voicetest/           # Python package
│   ├── api.py           # Core API
│   ├── cli.py           # CLI
│   ├── rest.py          # REST API server + WebSocket + SPA serving
│   ├── container.py     # Dependency injection (Punq)
│   ├── compose/         # Bundled Docker Compose for infrastructure services
│   ├── models/          # Pydantic models
│   ├── importers/       # Source importers (retell, vapi, bland, telnyx, livekit, xlsform, custom)
│   ├── exporters/       # Format exporters (mermaid, livekit, retell, vapi, bland, telnyx, voicetest_ir)
│   ├── platforms/       # Platform SDK clients (retell, vapi, bland, telnyx, livekit)
│   ├── engine/          # Execution engine
│   ├── simulator/       # User simulation
│   ├── judges/          # Evaluation judges (metric, rule)
│   ├── storage/         # DuckDB persistence layer
│   └── tui/             # TUI and shell
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

## Contact

Questions, feedback, or partnerships: [hello@voicetest.dev](mailto:hello@voicetest.dev)

## License

Apache 2.0
