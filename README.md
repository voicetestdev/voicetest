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

![Web UI Demo (light)](docs/demos/web-demo-light.gif)

## Quick Start

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
voicetest run --agent agent.json --tests tests.json --all

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

## Core Concepts

### Agent Graphs

An agent is represented as an **AgentGraph**: a directed graph of nodes connected by transitions. Each node has a prompt, a type, and outgoing edges that control conversation flow. The graph has a single `entry_node_id` where every conversation starts.

### Node Types

| Type             | LLM Call         | Speech | Routing                                                                    |
| ---------------- | ---------------- | ------ | -------------------------------------------------------------------------- |
| **Conversation** | Yes              | Yes    | LLM picks a transition via prompt match, or falls back to an `always` edge |
| **Logic**        | No               | No     | Evaluates equations top-to-bottom; first match wins                        |
| **Extract**      | Yes (extraction) | No     | LLM extracts variables from the conversation, then equations route         |

**Conversation nodes** are the standard building block — they generate a spoken response and use LLM judgment (or an `always` edge) to choose the next node.

**Logic nodes** (also called branch nodes) have no prompt and produce no speech. All their transitions use `equation` or `always` conditions, evaluated deterministically without an LLM call.

**Extract nodes** combine LLM extraction with deterministic routing. They define `variables_to_extract` (each with a name, description, type, and optional choices). The engine calls the LLM once to extract all variables from the conversation history, stores them as dynamic variables, then evaluates equation transitions using the extracted values.

### Dynamic Variables

Prompts can reference dynamic variables using `{{variable_name}}` syntax. Variables come from two sources:

- **Test case `dynamic_variables`**: Set before the conversation starts (e.g., `{{caller_name}}`, `{{account_id}}`)
- **Extract node output**: Populated during the conversation when an extract node fires

Expansion order: snippet references `{%name%}` are resolved first, then `{{variable}}` placeholders are substituted into the result. Unknown variables are left as-is.

### Equations

Equation conditions on transitions support these operators:

| Operator          | Example                    | Notes                                             |
| ----------------- | -------------------------- | ------------------------------------------------- |
| `==`              | `status == "active"`       | String equality                                   |
| `!=`              | `tier != "free"`           | String inequality                                 |
| `>` `>=` `<` `<=` | `age >= 18`                | Numeric coercion; non-numeric values return false |
| `contains`        | `notes contains "urgent"`  | Substring match                                   |
| `not_contains`    | `reply not_contains "err"` | Substring absence                                 |
| `exists`          | `email exists`             | Variable is set                                   |
| `not_exist`       | `phone not_exist`          | Variable is absent                                |

Multiple clauses combine with `logical_operator`: `"and"` (default, all must match) or `"or"` (any must match).

### Test Cases

Test cases define simulated conversations to run against an agent:

```json
[
  {
    "name": "Customer billing inquiry",
    "user_prompt": "## Identity\nYour name is Jane.\n\n## Goal\nGet help with a charge on your bill.",
    "metrics": ["Agent greeted the customer and addressed the billing concern"],
    "dynamic_variables": {"caller_name": "Jane", "account_id": "12345"},
    "tool_mocks": [],
    "type": "simulation"
  }
]
```

- **`type: "simulation"`** — The engine simulates both agent and user, running a full multi-turn conversation
- **`metrics`** — LLM judges evaluate each metric against the transcript and produce a 0–1 score
- **`dynamic_variables`** — Key-value pairs injected into `{{var}}` placeholders before the conversation starts

## CLI Reference

### Testing

```bash
# Run tests against an agent definition
voicetest run --agent agent.json --tests tests.json --all

# Chat with an agent interactively
voicetest chat -a agent.json --model openai/gpt-4o --var name=Jane --var account=12345

# Evaluate a transcript against metrics (no simulation)
voicetest evaluate -t transcript.json -m "Agent was polite" -m "Agent resolved the issue"

# Diagnose test failures and suggest fixes
voicetest diagnose -a agent.json -t tests.json
voicetest diagnose -a agent.json -t tests.json --auto-fix --save fixed_agent.json

# Decompose an agent into sub-agents
voicetest decompose -a agent.json -o output/ [--num-agents N] [--model ID]
```

### Agent Management

| Command                                                                    | Description                            |
| -------------------------------------------------------------------------- | -------------------------------------- |
| `voicetest agent list`                                                     | List agents in the database            |
| `voicetest agent create -a agent.json --name "My Agent"`                   | Create an agent from a definition file |
| `voicetest agent get <agent-id>`                                           | Get agent details                      |
| `voicetest agent update <agent-id> --name "Renamed" --model openai/gpt-4o` | Update agent properties                |
| `voicetest agent delete <agent-id>`                                        | Delete an agent                        |
| `voicetest agent graph <agent-id>`                                         | Display agent graph structure          |

### Test Case Management

| Command                                         | Description                  |
| ----------------------------------------------- | ---------------------------- |
| `voicetest test list <agent-id>`                | List test cases for an agent |
| `voicetest test create <agent-id> -f test.json` | Create a test case from JSON |
| `voicetest test link <agent-id> tests.json`     | Link external test file      |
| `voicetest test unlink <agent-id> tests.json`   | Unlink external test file    |
| `voicetest test export <agent-id>`              | Export test cases            |

### Run History

| Command                          | Description                   |
| -------------------------------- | ----------------------------- |
| `voicetest runs list <agent-id>` | List past test runs           |
| `voicetest runs get <run-id>`    | View run details with results |
| `voicetest runs delete <run-id>` | Delete a run                  |

### Snippets

```bash
# Analyze agent prompts for repeated text
voicetest snippet analyze --agent agent.json

# List defined snippets
voicetest snippet list --agent agent.json

# Create or update a snippet
voicetest snippet set --agent agent.json greeting "Hello, how can I help?"

# Apply snippets to prompts
voicetest snippet apply --agent agent.json --snippets '[{"name": "greeting", "text": "Hello!"}]'
```

### Export

```bash
voicetest export --agent agent.json --format mermaid         # Diagram
voicetest export --agent agent.json --format livekit         # Python code
voicetest export --agent agent.json --format retell-llm      # Retell LLM JSON
voicetest export --agent agent.json --format retell-cf       # Retell Conversation Flow JSON
voicetest export --agent agent.json --format vapi-assistant  # VAPI Assistant JSON
voicetest export --agent agent.json --format vapi-squad      # VAPI Squad JSON
voicetest export --agent agent.json --format bland           # Bland AI JSON
voicetest export --agent agent.json --format telnyx          # Telnyx AI JSON
voicetest export --agent agent.json --format voicetest       # Voicetest JSON (.vt.json)
```

### Settings and Platforms

```bash
# Show current settings
voicetest settings

# Set a configuration value
voicetest settings --set models.agent=openai/gpt-4o

# List available platforms with configuration status
voicetest platforms

# Configure platform credentials
voicetest platform configure retell --api-key sk-xxx

# List agents on a remote platform
voicetest platform list-agents retell

# Import an agent from a platform
voicetest platform import retell <agent-id> -o imported.json

# Push a local agent to a platform
voicetest platform push retell -a agent.json
```

### JSON Output

All commands support `--json` for machine-parseable output (progress goes to stderr):

```bash
voicetest --json agent list
voicetest --json run -a agent.json -t tests.json --all
voicetest --json snippet analyze --agent agent.json
```

## Web UI

Start the server and open http://localhost:8000 in your browser:

```bash
voicetest serve
```

The web UI provides:

- Agent import and graph visualization
- Export agents to multiple formats (Mermaid, LiveKit, Retell, VAPI, Bland, Telnyx)
- Platform integration: import, push, and sync agents with Retell, VAPI, LiveKit, Telnyx
- Test case management with persistence
- Global metrics configuration (compliance checks that run on all tests)
- Test execution with real-time streaming transcripts
- Cancel in-progress tests
- Run history with detailed results and transcript inspection
- Audio evaluation with word-level diff of original vs. heard text
- Settings configuration (models, max turns, streaming, audio eval)

Data is persisted to `.voicetest/data.duckdb` (configurable via `VOICETEST_DB_PATH`).

The REST API is available at http://localhost:8000/api. Full API documentation is at [voicetest.dev/api](https://voicetest.dev/api/).

## Live Voice Calls

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

## Features

### Format Conversion

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

### Platform Integration

voicetest can connect directly to voice platforms to import and push agent configurations.

| Platform | Import | Push | Sync | API Key Env Var                          |
| -------- | ------ | ---- | ---- | ---------------------------------------- |
| Retell   | ✓      | ✓    | ✓    | `RETELL_API_KEY`                         |
| VAPI     | ✓      | ✓    | ✓    | `VAPI_API_KEY`                           |
| Bland    | ✓      | ✓    |      | `BLAND_API_KEY`                          |
| Telnyx   | ✓      | ✓    | ✓    | `TELNYX_API_KEY`                         |
| LiveKit  | ✓      | ✓    | ✓    | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |

In the Web UI, go to the "Platforms" tab to configure credentials, browse remote agents, import, push, and sync.

### Prompt Snippets

Agent prompts often repeat text across nodes — sign-off phrases, compliance disclaimers, tone instructions, etc. **Snippets** are named, reusable text blocks defined at the agent level and referenced in prompts via `{%snippet_name%}`.

| Snippet Name | Text                                                             |
| ------------ | ---------------------------------------------------------------- |
| `sign_off`   | "Thank you for calling. Is there anything else I can help with?" |
| `hipaa_warn` | "I need to verify your identity before sharing medical info."    |

Use `{%name%}` (with percent signs) in any node prompt or general prompt:

```
Welcome the caller and introduce yourself.

{%hipaa_warn%}

When the conversation ends:
{%sign_off%}
```

Snippets are expanded **before** dynamic variables (`{{var}}`), so you can combine both:

```
Hello {{caller_name}}, {%greeting%}
```

Click **Analyze DRY** to scan all prompts for repeated or near-identical text. Exact matches can be auto-extracted into snippets; fuzzy matches (above 80%) are flagged for review.

![DRY Analysis Demo (light)](docs/demos/dry-demo-light.gif)

When exporting, choose **Raw (.vt.json)** to preserve `{%snippet%}` references, or **Expanded** to resolve them to plain text for platform deployment.

### Global Metrics

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

### Diagnosis & Auto-Fix

When a test fails, voicetest can diagnose the root cause and suggest concrete prompt changes to fix it.

1. **Diagnose** — Click "Diagnose" on a failed result. The LLM analyzes the graph, transcript, and failed metrics to identify fault locations and root cause.
1. **Review & Edit** — Proposed changes are shown as editable textareas. Modify the suggested text before applying.
1. **Apply & Test** — Click "Apply & Test" to apply changes to a copy of the graph and rerun the test. A score comparison table shows original vs. new scores with deltas.
1. **Iterate** — If not all metrics pass, click "Try Again" to revise the fix based on the latest results.
1. **Save** — Click "Save Changes" to persist the fix to the agent graph.

**Auto-Fix Mode** runs an automated diagnose-apply-revise loop. Configure stop condition ("On improvement" or "When all pass") and max iterations (1–10, default 3).

### Audio Evaluation

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

Enable `audio_eval` in settings or toggle "Audio evaluation" in the Web UI. On-demand: click "Run audio eval" on any completed result.

Audio evaluation requires the TTS and STT services from `voicetest up`:

| Service   | URL                   | Description        |
| --------- | --------------------- | ------------------ |
| `whisper` | http://localhost:8001 | Faster Whisper STT |
| `kokoro`  | http://localhost:8002 | Kokoro TTS         |

### Agent Decomposition

Split a large agent into smaller, focused sub-agents:

```bash
voicetest decompose -a agent.json -o output/ [--num-agents N] [--model ID]
```

Three-phase LLM pipeline: **analyze** the graph → **refine** the decomposition plan → **build** sub-agent JSON files. Produces one `.json` file per sub-agent plus a `manifest.json` with handoff rules and sub-agent registry.

Options:

- `--num-agents N` — Target number of sub-agents (default: let the LLM decide)
- `--model ID` — LLM model override (defaults to judge model from settings)

### LLM Response Cache

DSPy LLM responses are cached to avoid redundant API calls. Default backend is local disk.

For shared caching across CI runners or team members, use the S3 backend:

```toml
# .voicetest/settings.toml
[cache]
cache_backend = "s3"
s3_bucket = "my-bucket"
s3_prefix = "dspy-cache/"
s3_region = "us-east-1"
```

Disable caching for a run with `no_cache = true` in run options or `--no-cache` on the CLI.

## Configuration

### LLM Models

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

### Run Options

| Option                  | Default   | Description                                 |
| ----------------------- | --------- | ------------------------------------------- |
| `max_turns`             | `20`      | Maximum conversation turns                  |
| `timeout_seconds`       | `60.0`    | Per-test timeout                            |
| `no_cache`              | `false`   | Bypass LLM response cache                   |
| `split_transitions`     | `false`   | Separate LLM call for transition selection  |
| `audio_eval`            | `false`   | TTS→STT round-trip evaluation               |
| `flow_judge`            | `false`   | Validate conversation flow                  |
| `streaming`             | `false`   | Stream tokens as LLM generates              |
| `test_model_precedence` | `false`   | Test-level model overrides global model     |
| `pattern_engine`        | `fnmatch` | Pattern matching engine: `fnmatch` or `re2` |

### Settings File

Settings are stored in `.voicetest/settings.toml`:

```toml
[models]
agent = "groq/llama-3.1-8b-instant"
simulator = "groq/llama-3.1-8b-instant"
judge = "groq/llama-3.1-8b-instant"

[run]
max_turns = 20
audio_eval = false
streaming = false

[audio]
tts_url = "http://localhost:8002/v1"
stt_url = "http://localhost:8001/v1"

[cache]
cache_backend = "disk"
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

- `claudecode/sonnet` — Claude Sonnet
- `claudecode/opus` — Claude Opus
- `claudecode/haiku` — Claude Haiku

This invokes the `claude` CLI via subprocess, using your existing Claude Code authentication.

### Claude Code Plugin

voicetest ships with a Claude Code plugin for agent-assisted voice testing. Slash commands
and auto-activating skills help Claude Code discover importers/exporters, run tests, export
agents, and convert between formats.

**For repo contributors** (automatic):

Skills and commands load automatically from `.claude/` (symlinked to `claude-plugin/`).

**Install as a marketplace plugin:**

```
/plugin marketplace add voicetestdev/voicetest
/plugin install voicetest@voicetest-plugins
```

**For pip-installed users:**

```bash
cd your-project
voicetest init-claude
```

**Available slash commands:**

- `/voicetest-run` — Run tests against an agent
- `/voicetest-export` — Export agent to a different format
- `/voicetest-convert` — Convert between platform formats
- `/voicetest-info` — List importers, exporters, platforms, and settings

**Plugin path** (for manual plugin loading):

```bash
claude --plugin-dir $(voicetest claude-plugin-path)
```

## CI/CD Integration

Run voice agent tests in CI to catch regressions before they reach production. Key benefits:

- **Bring your own LLM keys** — Use OpenRouter, OpenAI, etc. directly instead of paying per-minute through Retell/VAPI's built-in LLM interfaces
- **Test on prompt changes** — Automatically validate agent behavior when prompts or configs change
- **Track quality over time** — Ensure consistent agent performance across releases

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

## Architecture

### Conversation Engine

The `ConversationEngine.advance()` method traverses the agent graph from the current node until it produces speech or settles:

1. Call `_process_node()` on the current node
1. If the node produced a response (conversation node), return it
1. If the node is silent (logic or extract node) and transitioned, follow the edge and repeat
1. Maximum 20 hops per `advance()` call to prevent infinite loops

Silent nodes auto-fire: logic nodes evaluate equations deterministically, extract nodes call the LLM once for variable extraction then evaluate equations. Tool messages record transitions and extractions in the transcript.

### DI Container (Punq)

The project uses Punq for dependency injection. Key singletons:

- `Engine`, `sessionmaker`, `Session` — SQLAlchemy database layer (DuckDB-backed)
- `ImporterRegistry`, `ExporterRegistry`, `PlatformRegistry` — Registries

Repositories are transient but share the singleton session:

- `AgentRepository`, `TestCaseRepository`, `RunRepository`, `CallRepository`

Get instances via `voicetest.container`:

```python
from voicetest.container import get_session, get_importer_registry
```

**When to use DI:**

- Use `get_*` helpers for app code (REST handlers, CLI commands)
- Use `container.resolve(Type)` when you need the container directly
- For tests, use `reset_container()` to get fresh state
- Don't instantiate repositories directly; let Punq inject the session

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

- `graphs/simple_graph.json` — Basic agent graph for testing
- `retell/` — Retell format samples (including extract variable configs)
- `vapi/` — VAPI format samples
- `livekit/` — LiveKit format samples

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

Svelte 5 reactivity guidelines are documented in `web/README.md`.

## Project Structure

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

## Contact

Questions, feedback, or partnerships: [hello@voicetest.dev](mailto:hello@voicetest.dev)

## License

Apache 2.0
