# voicetest docs

voicetest is an open-source test harness for voice agent workflows. Define agent graphs, simulate conversations with LLM-powered users, evaluate transcripts with LLM judges, and convert between platform formats (Retell, VAPI, LiveKit, Bland, Telnyx).

## Where to start

| If you want to...                                                                      | Go here                               |
| -------------------------------------------------------------------------------------- | ------------------------------------- |
| **Get up and running** — install, run the demo, first test in 5 minutes                | [Getting Started](getting-started.md) |
| **Test an agent** — CLI commands for running tests, managing agents, exporting results | [CLI Reference](cli.md)               |
| **Understand the model** — agent graphs, node types, transitions, dynamic variables    | [Core Concepts](concepts.md)          |
| **Configure models and settings** — LLM providers, run options, platform credentials   | [Configuration](configuration.md)     |

## Feature highlights

- **[Format conversion](features.md#format-conversion)** — Import from any supported platform, export to any other
- **[Platform integration](features.md#platform-integration)** — Import, push, and sync agents with Retell, VAPI, LiveKit, Bland, Telnyx
- **[Diagnosis and auto-fix](features.md#diagnosis-auto-fix)** — LLM-powered root cause analysis with automated prompt repair
- **[Audio evaluation](features.md#audio-evaluation)** — TTS/STT round-trip catches pronunciation and number-reading issues
- **[Global metrics](features.md#global-metrics)** — Compliance checks (HIPAA, PCI-DSS) that run on every test
- **[Agent decomposition](features.md#agent-decomposition)** — Split large agents into focused sub-agents
- **[CI/CD integration](getting-started.md#cicd)** — Run voice agent tests in GitHub Actions

## Interfaces

| Interface         | Command           | Description                                                        |
| ----------------- | ----------------- | ------------------------------------------------------------------ |
| Web UI            | `voicetest serve` | Visual test management, streaming transcripts, graph visualization |
| CLI               | `voicetest run`   | Fast iteration, scripting, CI/CD                                   |
| Interactive shell | `voicetest`       | REPL for exploratory testing                                       |
| REST API          | `voicetest serve` | Integrate with any toolchain at `localhost:8000/api`               |
