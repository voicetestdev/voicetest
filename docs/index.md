---
description: Open-source test harness for voice agents on Retell, VAPI, LiveKit, Bland, and Telnyx. Simulate conversations, judge with LLMs, catch regressions in CI.
---

# voicetest

Voice agents break in ways unit tests can't catch: a transition that fires too eagerly, a prompt that confuses the LLM under hedging, a phone number TTS reads as "four hundred fifteen, five hundred fifty-five." Manual testing doesn't scale — you click through a few conversations, ship the change, and find out from a customer three days later that something broke.

**Voicetest is the test harness that closes that loop.** It simulates real multi-turn conversations against your agent, judges the results with LLMs, and catches regressions before your users do.

Open source. Apache 2.0. Free forever.

![Web UI](demos/web-demo-light.gif)

## What you get

```bash
# Install once
uv tool install voicetest

# Run a regression suite against any agent (Retell, VAPI, LiveKit, Bland, Telnyx)
voicetest run --agent agent.json --tests tests.json --all
```

```
Test                          Pass  Score  Turns
─────────────────────────────────────────────────
Schedules an appointment       ✓    0.93   8
Handles cancellation           ✗    0.41   12
No PII leakage                 ✓    1.00   6
─────────────────────────────────────────────────
2/3 passed
```

When something fails, voicetest can [diagnose](recipes/diagnose-failing-test.md) and propose the fix. When you tweak a prompt, you can [snapshot the suite](recipes/regression-test-prompt-changes.md) before and after to see what moved. When you have production calls, you can [import them as a regression suite](recipes/import-call-history.md). When you're ready to ship, [GitHub Actions](recipes/ci-github-actions.md) blocks merges that regress.

## Where to start

| If you want to...                                                                 | Go here                               |
| --------------------------------------------------------------------------------- | ------------------------------------- |
| **Get your first test running in 5 minutes** — install, run the demo, see results | [Getting Started](getting-started.md) |
| **Solve a specific problem** — task-oriented walkthroughs                         | [Recipes](recipes/index.md)           |
| **Understand graphs, nodes, and judging**                                         | [Core Concepts](concepts.md)          |
| **Configure models, platforms, and credentials**                                  | [Configuration](configuration.md)     |
| **Browse every CLI command**                                                      | [CLI Reference](cli.md)               |

## What's distinctive

- **Test any platform.** Retell, VAPI, LiveKit, Bland, Telnyx, or custom — voicetest's [unified AgentGraph IR](architecture.md#the-agentgraph-ir) means one test suite runs against agents from any of them.
- **[Convert between platforms](features.md#format-conversion)** without manual rewrites — import a Retell Conversation Flow, export to VAPI; import VAPI, export to LiveKit.
- **[LLM-powered diagnosis](features.md#diagnosis-auto-fix)** identifies the root cause of a failed test and proposes a prompt fix, with a one-click "apply and re-run" loop.
- **[Replay production calls](features.md#transcript-import-replay)** against the agent's current graph to detect drift before users notice.
- **[Audio evaluation](features.md#audio-evaluation)** catches what text-only judges miss — TTS/STT round-trip checks for digit-reading and pronunciation issues.
- **[Run anywhere](recipes/ci-github-actions.md)** — CLI, Web UI, REST API, GitHub Actions, or as a Claude Code plugin.

## Platform support

| Platform | Import | Export | Push | Sync |
| -------- | :----: | :----: | :--: | :--: |
| Retell   |   ✓    |   ✓    |  ✓   |  ✓   |
| VAPI     |   ✓    |   ✓    |  ✓   |  ✓   |
| LiveKit  |   ✓    |   ✓    |  ✓   |  ✓   |
| Bland    |   ✓    |   ✓    |  ✓   |      |
| Telnyx   |   ✓    |   ✓    |  ✓   |  ✓   |

## Interfaces

| Interface         | Command           | Best for                                                                          |
| ----------------- | ----------------- | --------------------------------------------------------------------------------- |
| Web UI            | `voicetest serve` | Visual iteration, side-by-side run comparison, diagnosis                          |
| CLI               | `voicetest run`   | Scripting, CI/CD, fast iteration                                                  |
| Interactive shell | `voicetest`       | Exploratory testing                                                               |
| REST API          | `voicetest serve` | Integrate with any toolchain at `localhost:8000/api`                              |
| Claude Code       | `/voicetest-run`  | Have Claude drive your test suite — see [Claude Code Integration](claude-code.md) |
