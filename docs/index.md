# voicetest — Voice Agent Testing

Voice agents break in ways unit tests can't catch: wrong transitions, bad prompts, numbers that TTS mangles into nonsense. voicetest simulates real multi-turn conversations against your agent, then judges the results with LLMs — so you find the problems before your users do.

Open source. Apache 2.0. Free forever.

**For teams building voice agents on Retell, VAPI, LiveKit, Bland, or Telnyx.**

![Web UI](demos/web-demo-light.gif)

## Where to start

| If you want to...                                                                         | Go here                               |
| ----------------------------------------------------------------------------------------- | ------------------------------------- |
| **Get your first test running in 5 minutes** — install, run the demo, see results         | [Getting Started](getting-started.md) |
| **Test an agent you've already built** — CLI commands, managing agents, exporting results | [CLI Reference](cli.md)               |
| **Understand agent graphs and test cases** — nodes, transitions, dynamic variables        | [Core Concepts](concepts.md)          |
| **Configure LLM models and platforms** — providers, run options, credentials              | [Configuration](configuration.md)     |

## What you can do

- **[Import from Retell, export to VAPI](features.md#format-conversion)** — convert between any supported platform via a unified agent graph
- **[Push and sync with live platforms](features.md#platform-integration)** — import, push, and sync agent configs directly from the Web UI or CLI
- **[Diagnose failures and auto-fix prompts](features.md#diagnosis-auto-fix)** — LLM analyzes why a test failed and proposes prompt changes, with an automated repair loop
- **[Catch what LLM judges miss](features.md#audio-evaluation)** — TTS/STT round-trip evaluation catches pronunciation and number-reading issues
- **[Enforce compliance on every test](features.md#global-metrics)** — HIPAA, PCI-DSS, brand voice checks that run automatically
- **[Break large agents into sub-agents](features.md#agent-decomposition)** — LLM-powered decomposition with handoff rules
- **[Test in CI/CD](getting-started.md#cicd)** — run voice agent tests in GitHub Actions, block bad deploys

## Platform support

| Platform | Import | Export | Push | Sync |
| -------- | ------ | ------ | ---- | ---- |
| Retell   | ✓      | ✓      | ✓    | ✓    |
| VAPI     | ✓      | ✓      | ✓    | ✓    |
| LiveKit  | ✓      | ✓      | ✓    | ✓    |
| Bland    | ✓      | ✓      | ✓    |      |
| Telnyx   | ✓      | ✓      | ✓    | ✓    |

## Interfaces

| Interface         | Command           | Description                                                        |
| ----------------- | ----------------- | ------------------------------------------------------------------ |
| Web UI            | `voicetest serve` | Visual test management, streaming transcripts, graph visualization |
| CLI               | `voicetest run`   | Fast iteration, scripting, CI/CD                                   |
| Interactive shell | `voicetest`       | REPL for exploratory testing                                       |
| REST API          | `voicetest serve` | Integrate with any toolchain at `localhost:8000/api`               |
