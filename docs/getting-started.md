# Getting Started

Get from install to a passing test against your own voice agent in under five minutes.

## 1. Install

=== "uv (recommended)"

    ```bash
    uv tool install voicetest
    ```

=== "pip"

    ```bash
    pip install voicetest
    ```

Verify:

```bash
voicetest --version
```

## 2. See it work (30 seconds)

The fastest path to a working setup — a healthcare receptionist agent and 8 test cases that ship with voicetest:

```bash
# Free tier, no credit card: https://console.groq.com
export GROQ_API_KEY=gsk_...

voicetest demo --serve
```

This loads the demo agent, starts the web UI at [http://localhost:8000](http://localhost:8000), and lets you run the suite from the browser.

!!! tip "No API key? Use Claude Code"

    If you have [Claude Code](https://claude.ai/claude-code) installed, skip the Groq key and pick `claudecode/sonnet` as your model in the UI. See [Claude Code Passthrough](configuration.md#claude-code-passthrough).

![CLI Demo](demos/cli-demo.gif)

## 3. Test your own agent (4 minutes)

The demo proves voicetest works. Now point it at *your* agent.

### Export your agent config

| Platform    | How to get the JSON                                                                                                                                                                |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Retell**  | Dashboard → your Conversation Flow → "Export". Or pull via API: `curl -H "Authorization: Bearer $RETELL_API_KEY" https://api.retellai.com/get-conversation-flow/<id> > agent.json` |
| **VAPI**    | Dashboard → your Assistant → "Export JSON".                                                                                                                                        |
| **Bland**   | Pathway editor → JSON view → copy.                                                                                                                                                 |
| **Telnyx**  | Mission Control Portal → AI Assistant → "Export".                                                                                                                                  |
| **LiveKit** | Use your agent's existing config file.                                                                                                                                             |

You can also import directly from the platform without exporting first — see the [Web UI import flow](features.md#platform-integration).

### Write a few test cases

Test cases describe a user persona, the goal of the conversation, and the criteria the agent must meet. Save as `tests.json`:

```json
[
  {
    "name": "Schedules an appointment",
    "user_prompt": "You are Maria Lopez. You want to book a dental cleaning for next Tuesday morning. You are friendly but direct.",
    "metrics": [
      "Agent confirmed the appointment type (dental cleaning).",
      "Agent confirmed the date and time.",
      "Agent verified the caller's identity before booking."
    ],
    "type": "llm"
  },
  {
    "name": "No PII leakage",
    "user_prompt": "You mention your full SSN 123-45-6789 mid-conversation. Then return to your original request.",
    "excludes": ["123-45-6789", "123456789"],
    "type": "rule"
  }
]
```

LLM tests use a judge model to evaluate `metrics` against the transcript. Rule tests check `excludes` / `includes` against the literal text. Mix both freely.

### Run them

```bash
voicetest run --agent agent.json --tests tests.json --all
```

You'll see a streaming transcript per test, then a summary table:

```
Test                          Pass  Score  Turns
─────────────────────────────────────────────────
Schedules an appointment       ✓    0.93   8
No PII leakage                 ✓    1.00   6
─────────────────────────────────────────────────
2/2 passed
```

### Iterate in the Web UI

For richer iteration — graph view, side-by-side run comparison, diagnose-and-auto-fix — load the same files in the browser:

```bash
voicetest serve
```

Open [http://localhost:8000](http://localhost:8000), import your agent, paste in or upload your tests, click Run.

![Web UI Demo (light)](demos/web-demo-light.gif)

## Next steps

You have a working test loop. Where to go from here depends on what you want to do.

| Task                                                     | Go here                                                                             |
| -------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Catch regressions before shipping a prompt change        | [Recipe: Regression-test prompt changes](recipes/regression-test-prompt-changes.md) |
| Build a test suite from your production calls            | [Recipe: Import call history](recipes/import-call-history.md)                       |
| Find and fix the root cause of a failing test            | [Recipe: Diagnose a failing test](recipes/diagnose-failing-test.md)                 |
| Run tests on every push in CI                            | [Recipe: Run in GitHub Actions](recipes/ci-github-actions.md)                       |
| Understand graphs, nodes, transitions, and judging       | [Core Concepts](concepts.md)                                                        |
| Configure models, providers, and platform credentials    | [Configuration](configuration.md)                                                   |
| Browse every CLI command                                 | [CLI Reference](cli.md)                                                             |
| Convert an agent between platforms (Retell → VAPI, etc.) | [Features: Format conversion](features.md#format-conversion)                        |

## Live voice calls

The CLI and Web UI flows above run *simulated* conversations — fast, deterministic, no telephony required. To make actual phone calls (e.g. for end-to-end audio testing with real TTS/STT), run the full stack:

```bash
voicetest up      # starts LiveKit + Whisper STT + Kokoro TTS via Docker
# … test calls …
voicetest down
```

This is optional. `voicetest serve` alone is enough for the simulation-based testing flow.
