# Getting Started

## Installation

=== "uv (recommended)"

````
```bash
uv tool install voicetest
```

Or add to a project:

```bash
uv add voicetest
```
````

=== "pip"

````
```bash
pip install voicetest
```
````

## Quick start with the demo

The fastest way to see voicetest in action — a healthcare receptionist agent with 8 test cases:

```bash
# Set up an API key (free, no credit card at https://console.groq.com)
export GROQ_API_KEY=gsk_...

# Load demo and start interactive shell
voicetest demo

# Or load demo and start web UI
voicetest demo --serve
```

!!! tip "No API key? Use Claude Code"
If you have [Claude Code](https://claude.ai/claude-code) installed, skip API key setup and use `claudecode/sonnet` as your model. See [Claude Code Passthrough](configuration.md#claude-code-passthrough).

The demo includes test cases covering appointment scheduling, identity verification, and more.

![CLI Demo](demos/cli-demo.gif)

## Interactive shell

```bash
# Launch interactive shell
voicetest

# In the shell:
> agent tests/fixtures/retell/sample_config.json
> tests tests/fixtures/retell/sample_tests.json
> set agent_model ollama_chat/qwen2.5:0.5b
> run
```

## Web UI

Start the server and open http://localhost:8000:

```bash
voicetest serve
```

![Web UI Demo (light)](demos/web-demo-light.gif)

The web UI provides agent import, graph visualization, test execution with real-time streaming transcripts, run history, and more. See [Features](features.md) for the full list.

## Running tests from the CLI

```bash
# Run all tests against an agent definition
voicetest run --agent agent.json --tests tests.json --all

# Chat with an agent interactively
voicetest chat -a agent.json --model openai/gpt-4o
```

See the [CLI Reference](cli.md) for all commands.

## Live voice calls

For live voice calls (not just simulated tests), you need infrastructure services. The `up` command starts LiveKit, Whisper STT, and Kokoro TTS via Docker:

```bash
# Start infrastructure + backend server
voicetest up

# Stop when done
voicetest down
```

If you only need simulated tests, `voicetest serve` is sufficient and does not require Docker.

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

## Next steps

- [Core Concepts](concepts.md) — Understand agent graphs, node types, and test cases
- [Configuration](configuration.md) — Set up LLM models, settings, and platform credentials
- [Features](features.md) — Format conversion, diagnosis, audio evaluation, and more
- [CLI Reference](cli.md) — All commands and options
