[![PyPI](https://img.shields.io/pypi/v/voicetest)](https://pypi.org/project/voicetest/) [![Release](https://img.shields.io/github/v/release/voicetestdev/voicetest)](https://github.com/voicetestdev/voicetest/releases) [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![Tests](https://github.com/voicetestdev/voicetest/actions/workflows/test.yml/badge.svg)](https://github.com/voicetestdev/voicetest/actions/workflows/test.yml)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
  <img alt="voicetest" src="assets/logo-light.svg" width="300">
</picture>

A generic test harness for voice agent workflows. Test agents from Retell, VAPI, LiveKit, Bland, and custom sources using a unified execution and evaluation model.

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

# Launch full TUI
voicetest tui --agent agent.json --tests tests.json

# Start REST API server with Web UI
voicetest serve
```

### Web UI

Start the server and open http://localhost:8000 in your browser:

```bash
voicetest serve
```

The web UI provides:

- Agent import and graph visualization
- Export agents to multiple formats (Mermaid, LiveKit, Retell, VAPI, Bland)
- Platform integration: import agents from, push agents to, and sync changes back to Retell, VAPI, LiveKit
- Test case management with persistence
- Export tests to platform formats (Retell)
- Global metrics configuration (compliance checks that run on all tests)
- Test execution with real-time streaming transcripts
- Cancel in-progress tests
- Run history with detailed results
- Transcript and metric inspection with scores
- Settings configuration (models, max turns, streaming)

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
VAPI ──────────┼───▶ AgentGraph ──┼───▶ VAPI
               │                  │
Bland ─────────┤                  ├───▶ Bland
               │                  │
LiveKit ───────┤                  ├───▶ LiveKit
               │                  │
XLSForm ───────┤                  └───▶ Mermaid
               │
Custom ────────┘
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

- **Multi-source import**: Retell CF, Retell LLM, VAPI, Bland, LiveKit, XLSForm, custom Python functions
- **Format conversion**: Convert between Retell, VAPI, Bland, LiveKit, and other formats
- **Unified IR**: AgentGraph representation for any voice agent
- **Multi-format export**: Mermaid diagrams, LiveKit Python, Retell LLM, Retell CF, VAPI, Bland
- **Platform integration**: Import, push, and sync agents with Retell, VAPI, Bland, LiveKit via API
- **Configurable LLMs**: Separate models for agent, simulator, and judge
- **DSPy-based evaluation**: LLM judges with reasoning and 0-1 scores
- **Global metrics**: Define compliance checks that run on all tests for an agent
- **Multiple interfaces**: CLI, TUI, interactive shell, Web UI, REST API
- **Persistence**: DuckDB storage for agents, tests, and run history
- **Real-time streaming**: WebSocket-based transcript streaming during test execution
- **Token streaming**: Optional token-level streaming as LLM generates responses (experimental)
- **Cancellation**: Cancel in-progress tests to stop token usage

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

## Platform Integration

voicetest can connect directly to voice platforms to import and push agent configurations.

### Supported Platforms

| Platform | Import | Push | Sync | API Key Env Var                          |
| -------- | ------ | ---- | ---- | ---------------------------------------- |
| Retell   | ✓      | ✓    | ✓    | `RETELL_API_KEY`                         |
| VAPI     | ✓      | ✓    | ✓    | `VAPI_API_KEY`                           |
| Bland    | ✓      | ✓    |      | `BLAND_API_KEY`                          |
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

## Development

### Docker Development (Recommended)

The easiest way to get a full development environment running is with Docker Compose:

```bash
# Clone and start all services
git clone https://github.com/voicetestdev/voicetest
cd voicetest
docker compose -f docker-compose.dev.yml up
```

This starts five services:

| Service    | URL                   | Description                              |
| ---------- | --------------------- | ---------------------------------------- |
| `livekit`  | ws://localhost:7880   | LiveKit server for real-time voice calls |
| `whisper`  | http://localhost:8001 | Faster Whisper STT server                |
| `kokoro`   | http://localhost:8002 | Kokoro TTS server                        |
| `backend`  | http://localhost:8000 | FastAPI backend with hot reload          |
| `frontend` | http://localhost:5173 | Vite dev server with hot reload          |

Open http://localhost:5173 to access the web UI. Changes to Python or TypeScript files trigger automatic reloads.

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
│   ├── models/          # Pydantic models
│   ├── importers/       # Source importers (retell, vapi, bland, livekit, xlsform, custom)
│   ├── exporters/       # Format exporters (mermaid, livekit, retell, vapi, bland, test_cases)
│   ├── platforms/       # Platform SDK clients (retell, vapi, bland, livekit)
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
