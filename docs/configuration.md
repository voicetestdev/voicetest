# Configuration

## LLM models

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

### Vertex AI

For Vertex AI models that aren't available in the default `us-central1` region, set the `VERTEXAI_LOCATION` environment variable:

```bash
export VERTEXAI_LOCATION=global  # needed for e.g. gemini-3.1-flash-lite-preview
```

See the [LiteLLM Vertex AI docs](https://docs.litellm.ai/docs/providers/vertex) for supported regions.

## Run options

| Option                  | Default   | Description                                  |
| ----------------------- | --------- | -------------------------------------------- |
| `max_turns`             | `50`      | Maximum conversation turns                   |
| `turn_timeout_seconds`  | `60.0`    | Per-turn timeout (user sim + agent response) |
| `no_cache`              | `false`   | Bypass LLM response cache                    |
| `audio_eval`            | `false`   | TTS/STT round-trip evaluation                |
| `flow_judge`            | `false`   | Validate conversation flow                   |
| `streaming`             | `false`   | Stream tokens as LLM generates               |
| `test_model_precedence` | `false`   | Test-level model overrides global model      |
| `pattern_engine`        | `fnmatch` | Pattern matching engine: `fnmatch` or `re2`  |

## Settings file

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

## Claude Code passthrough

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

### Subprocess timeout

Each call has a 600-second timeout on the `claude` CLI subprocess. If a request exceeds it, voicetest translates the failure into a retryable timeout error. Timeouts are capped at **2 attempts** (vs. the default 8 used for rate limits and connection errors) because each attempt costs the full timeout — bounding worst-case wallclock at roughly twice the timeout. If both attempts fail, the test surfaces as `status="error"` with a clear message rather than a raw `subprocess.TimeoutExpired` stacktrace.

If you consistently hit the timeout on legitimate long generations, raise the `timeout` argument when constructing the LM (Python API), or split the workload into smaller prompts.

## Claude Code plugin

voicetest ships with a Claude Code plugin for agent-assisted voice testing. Slash commands and auto-activating skills help Claude Code discover importers/exporters, run tests, export agents, and convert between formats.

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
