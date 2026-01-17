# voicetest

A generic test harness for voice agent workflows. Test agents from Retell, Vapi, LiveKit, and custom sources using a unified execution and evaluation model.

## Installation

```bash
pip install voicetest
```

Or with uv:

```bash
uv add voicetest
```

## Quick Start

### Interactive Shell

```bash
# Launch interactive shell (default)
uv run voicetest

# In the shell:
> agent tests/fixtures/retell/sample_agent.json
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
voicetest export --agent agent.json --format mermaid      # Diagram
voicetest export --agent agent.json --format livekit      # Python code
voicetest export --agent agent.json --format retell-llm   # Retell LLM JSON
voicetest export --agent agent.json --format retell-cf    # Retell Conversation Flow JSON

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
- Export to multiple formats (Mermaid, LiveKit, Retell LLM, Retell CF)
- Test case management
- Test execution with live results
- Transcript and metric inspection
- Settings configuration

### REST API

The REST API is available at http://localhost:8000/api when running `voicetest serve`:

```bash
# Health check
curl http://localhost:8000/api/health

# List importers
curl http://localhost:8000/api/importers

# List export formats
curl http://localhost:8000/api/exporters

# Import agent
curl -X POST http://localhost:8000/api/agents/import \
  -H "Content-Type: application/json" \
  -d '{"config": {...}}'

# Export agent (formats: mermaid, livekit, retell-llm, retell-cf)
curl -X POST http://localhost:8000/api/agents/export \
  -H "Content-Type: application/json" \
  -d '{"graph": {...}, "format": "retell-llm"}'

# Run tests
curl -X POST http://localhost:8000/api/runs \
  -H "Content-Type: application/json" \
  -d '{"graph": {...}, "test_cases": [...]}'
```

## Format Conversion

voicetest can convert between agent formats via its unified AgentGraph representation:

```
Retell CF ─────┐                  ┌───▶ Retell LLM
               │                  │
Retell LLM ────┼───▶ AgentGraph ──┼───▶ Retell CF
               │                  │
Custom ────────┘                  ├───▶ Mermaid
                                  └───▶ LiveKit
```

Import from any supported format, then export to any other:

```bash
# Convert Retell Conversation Flow to Retell LLM format
voicetest export --agent retell-cf-agent.json --format retell-llm > retell-llm-agent.json

# Convert Retell LLM to Conversation Flow format
voicetest export --agent retell-llm-agent.json --format retell-cf > retell-cf-agent.json
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

- **Multi-source import**: Retell Conversation Flow, Retell LLM, custom Python functions
- **Format conversion**: Convert between Retell LLM and Conversation Flow formats
- **Unified IR**: AgentGraph representation for any voice agent
- **Multi-format export**: Mermaid diagrams, LiveKit Python code, Retell LLM, Retell CF
- **Configurable LLMs**: Separate models for agent, simulator, and judge
- **DSPy-based evaluation**: LLM judges with reasoning
- **Multiple interfaces**: CLI, TUI, interactive shell, Web UI, REST API

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

## Development

```bash
# Clone and install
git clone https://github.com/pld/voicetest
cd voicetest
uv sync --all-extras

# Run unit tests
uv run pytest tests/unit

# Run integration tests (requires Ollama with qwen2.5:0.5b)
uv run pytest tests/integration

# Lint
uv run ruff check voicetest/ tests/
```

### Frontend Development

The web UI is built with Bun + Svelte + Vite. Uses [mise](https://mise.jdx.dev/) for version management.

```bash
# Terminal 1 - Frontend dev server with hot reload
cd web
mise exec -- bun install
mise exec -- bun run dev   # http://localhost:5173

# Terminal 2 - Backend API
uv run voicetest serve --reload   # http://localhost:8000
```

The Vite dev server proxies `/api/*` to the FastAPI backend.

```bash
# Build for production
cd web && mise exec -- bun run build
```

## Project Structure

```
voicetest/
├── voicetest/           # Python package
│   ├── api.py           # Core API
│   ├── cli.py           # CLI
│   ├── rest.py          # REST API server + SPA serving
│   ├── models/          # Pydantic models
│   ├── importers/       # Source importers (retell, retell_llm, custom)
│   ├── exporters/       # Format exporters (mermaid, livekit, retell_llm, retell_cf)
│   ├── engine/          # Execution engine
│   ├── simulator/       # User simulation
│   ├── judges/          # Evaluation judges
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
    └── M2_SPEC.md       # Future roadmap
```

## License

MIT
