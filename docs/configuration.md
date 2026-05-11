---
description: LLM models, run options, settings.toml — every knob voicetest exposes.
---

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

For guidance on which model to use for each role, see the [Models guide](models.md).

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

| Section    | Keys                                                   | Notes                                                              |
| ---------- | ------------------------------------------------------ | ------------------------------------------------------------------ |
| `[models]` | `agent`, `simulator`, `judge`                          | LiteLLM strings; required for any non-local model                  |
| `[run]`    | `max_turns`, `audio_eval`, `streaming`, etc.           | Defaults for new runs; per-run overrides win                       |
| `[audio]`  | `tts_url`, `stt_url`                                   | Set when audio eval is enabled                                     |
| `[cache]`  | `cache_backend`, `s3_bucket`, `s3_prefix`, `s3_region` | See [Features: LLM response cache](features.md#llm-response-cache) |

`voicetest settings` prints the active configuration; `voicetest settings --set <key>=<value>` updates it.

## Environment variables

| Variable                                 | Purpose                                                             |
| ---------------------------------------- | ------------------------------------------------------------------- |
| `GROQ_API_KEY`                           | Default LLM provider for the demo agent and quickstart              |
| `OPENAI_API_KEY`                         | OpenAI models                                                       |
| `ANTHROPIC_API_KEY`                      | Anthropic Claude models                                             |
| `VERTEXAI_LOCATION`                      | Override the Vertex AI region (default `us-central1`)               |
| `VOICETEST_DB_PATH`                      | Override DuckDB storage location (default `.voicetest/data.duckdb`) |
| `RETELL_API_KEY`                         | Retell platform integration                                         |
| `VAPI_API_KEY`                           | VAPI platform integration                                           |
| `BLAND_API_KEY`                          | Bland platform integration                                          |
| `TELNYX_API_KEY`                         | Telnyx platform integration                                         |
| `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` | LiveKit platform integration                                        |

## Using Claude Code as your LLM backend

If you have [Claude Code](https://claude.ai/claude-code) installed, you can route LLM calls through your existing Claude subscription instead of configuring a separate API key. See [Claude Code Integration](claude-code.md).
