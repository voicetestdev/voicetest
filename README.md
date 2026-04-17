[![PyPI](https://img.shields.io/pypi/v/voicetest)](https://pypi.org/project/voicetest/) [![Release](https://img.shields.io/github/v/release/voicetestdev/voicetest)](https://github.com/voicetestdev/voicetest/releases) [![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0) [![Tests](https://github.com/voicetestdev/voicetest/actions/workflows/test.yml/badge.svg)](https://github.com/voicetestdev/voicetest/actions/workflows/test.yml)

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="assets/logo-dark.svg">
  <source media="(prefers-color-scheme: light)" srcset="assets/logo-light.svg">
  <img alt="voicetest" src="assets/logo-light.svg" width="300">
</picture>

Open-source test harness for voice agent workflows.

- **Simulate conversations** — LLM-powered users talk to your agent, LLM judges score the results
- **Test any platform** — Retell, VAPI, LiveKit, Bland, Telnyx, or custom agents
- **Convert between formats** — Import from one platform, export to another via a unified graph IR
- **Diagnose failures** — Auto-fix broken prompts with an LLM-powered repair loop
- **Run anywhere** — CLI, Web UI, REST API, CI/CD

## Installation

```bash
uv tool install voicetest
```

Or add to a project (`uv run voicetest` to run):

```bash
uv add voicetest
```

Or with pip:

```bash
pip install voicetest
```

## Quick start

Try voicetest with a sample healthcare receptionist agent and 8 test cases:

```bash
# Set up an API key (free, no credit card at https://console.groq.com)
export GROQ_API_KEY=gsk_...

# Load demo and start web UI
voicetest demo --serve
```

> **Tip:** If you have [Claude Code](https://claude.ai/claude-code) installed, skip API key setup and use `claudecode/sonnet` as your model. See [Claude Code Passthrough](https://voicetest.dev/docs/configuration/#claude-code-passthrough).

![Web UI Demo (light)](docs/demos/web-demo-light.gif)

## Web UI

```bash
voicetest serve
```

Agent import, graph visualization, test execution with real-time streaming transcripts, run history, diagnosis, and more at http://localhost:8000.

## Platform support

Import from any supported format, convert through the unified AgentGraph, and export to any other:

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

| Platform | Import | Push | Sync | API Key Env Var                          |
| -------- | ------ | ---- | ---- | ---------------------------------------- |
| Retell   | ✓      | ✓    | ✓    | `RETELL_API_KEY`                         |
| VAPI     | ✓      | ✓    | ✓    | `VAPI_API_KEY`                           |
| Bland    | ✓      | ✓    |      | `BLAND_API_KEY`                          |
| Telnyx   | ✓      | ✓    | ✓    | `TELNYX_API_KEY`                         |
| LiveKit  | ✓      | ✓    | ✓    | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |

## CI/CD

Run voice agent tests in GitHub Actions to catch regressions before production:

```yaml
name: Voice Agent Tests
on:
  push:
    paths: ["agents/**"]

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

## Configuration

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
```

Any [LiteLLM-compatible model](https://docs.litellm.ai/docs/providers) works — OpenAI, Anthropic, Google, Ollama, and more. See the [full configuration reference](https://voicetest.dev/docs/configuration/).

## Documentation

Full documentation is at [voicetest.dev/docs](https://voicetest.dev/docs/).

| Topic                                                          | Description                                                  |
| -------------------------------------------------------------- | ------------------------------------------------------------ |
| [Getting Started](https://voicetest.dev/docs/getting-started/) | Install, demo, first test walkthrough                        |
| [Core Concepts](https://voicetest.dev/docs/concepts/)          | Agent graphs, node types, test cases                         |
| [CLI Reference](https://voicetest.dev/docs/cli/)               | All commands and options                                     |
| [Features](https://voicetest.dev/docs/features/)               | Format conversion, diagnosis, audio eval, snippets, and more |
| [Configuration](https://voicetest.dev/docs/configuration/)     | Models, settings, Claude Code, platform credentials          |
| [Architecture](https://voicetest.dev/docs/architecture/)       | Engine internals, DI, storage                                |
| [Development](https://voicetest.dev/docs/development/)         | Contributing, Docker setup, code quality                     |

## Contact

Questions, feedback, or partnerships: [hello@voicetest.dev](mailto:hello@voicetest.dev)

## License

Apache 2.0
