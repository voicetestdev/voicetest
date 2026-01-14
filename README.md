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
> config tests/fixtures/retell/sample_config.json
> tests tests/fixtures/retell/sample_tests.json
> set agent_model ollama_chat/qwen2.5:0.5b
> run
```

### CLI Commands

```bash
# List available importers
voicetest importers

# Run tests against an agent config
voicetest run --config agent.json --tests tests.json

# Export agent as Mermaid diagram
voicetest export --config agent.json --format mermaid

# Launch full TUI
voicetest tui --config agent.json --tests tests.json
```

## Test Case Format

```json
[
  {
    "id": "test-1",
    "name": "Customer billing inquiry",
    "user_prompt": "## Identity\nYour name is Jane.\n\n## Goal\nGet help with a charge on your bill.\n\n## Personality\nPolite but confused.",
    "metrics": ["Agent greeted the customer", "Agent addressed the billing concern"],
    "required_nodes": ["greeting", "billing"],
    "max_turns": 10
  }
]
```

## Features

- **Multi-source import**: Retell JSON, custom Python functions (Vapi in M2)
- **Unified IR**: AgentGraph representation for any voice agent
- **Configurable LLMs**: Separate models for agent, simulator, and judge
- **DSPy-based evaluation**: LLM judges with reasoning
- **Flow validation**: Required/forbidden node constraints
- **CLI + TUI + Shell**: Multiple interface options

## LLM Configuration

Configure different models for each role:

```python
from voicetest.models.test_case import RunOptions

options = RunOptions(
    agent_model="openai/gpt-4o-mini",      # Agent responses
    simulator_model="openai/gpt-4o-mini",  # User simulation
    judge_model="openai/gpt-4o-mini",      # Metric evaluation
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

## Project Structure

```
voicetest/
├── voicetest/           # Package
│   ├── api.py           # Core API
│   ├── cli.py           # CLI
│   ├── models/          # Pydantic models
│   ├── importers/       # Source importers (retell, custom)
│   ├── exporters/       # Graph export (mermaid, livekit)
│   ├── engine/          # Execution engine
│   ├── simulator/       # User simulation
│   ├── judges/          # Evaluation judges
│   └── tui/             # TUI and shell
├── tests/
│   ├── unit/            # Unit tests (164 tests)
│   └── integration/     # Integration tests (Ollama)
└── docs/
    ├── M1_SPEC.md       # M1 specification
    └── M2_SPEC.md       # M2 specification
```

## License

MIT
