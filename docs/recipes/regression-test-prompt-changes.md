---
description: Snapshot your test suite before a prompt change, re-run after, compare runs side by side to catch regressions before they ship.
---

# Regression-test prompt changes

**The problem:** You've maintained a voice agent for months. Today you want to edit a prompt — tighten an instruction, change a tone, add a new transition condition. You're 90% sure the change is safe, but you've been burned before: a one-word edit that broke identity verification on a flow nobody had touched in weeks.

**The flow:**

1. Snapshot current behavior with the existing test suite
1. Make the prompt change
1. Re-run the same suite
1. Compare runs side by side

## Before you change anything: snapshot

Pull the current agent definition and run the suite to capture today's baseline. The web UI keeps the run on disk:

```bash
voicetest serve
```

In the UI, import the agent, load your tests, click **Run**. When it finishes, the run lands in the runs list with an ID and timestamp. That's your baseline.

CLI alternative — save the run for later comparison:

```bash
voicetest run \
  --agent agent.json \
  --tests tests.json \
  --all \
  --output baseline.json
```

## Make the change

Edit `agent.json` (or use **Push to Platform** from the UI if you maintain the agent on Retell/VAPI/etc.). Keep the change small and focused — one edit per regression cycle is the cleanest.

!!! tip "Version control your agent"

    Commit `agent.json` to git before every change. The diff is the single most useful artifact when you're trying to figure out what broke.

## Re-run and compare

```bash
voicetest run \
  --agent agent.json \
  --tests tests.json \
  --all \
  --output after-change.json
```

In the web UI, the runs list shows both runs. Click each to compare:

- **Pass/fail summary** — did any test flip from green to red?
- **Score deltas** — even passing tests can degrade. A score that drops from 0.93 to 0.71 is worth investigating.
- **Turn counts** — a conversation that used to take 8 turns now taking 14 means the agent is working harder for the same outcome.
- **Transcript diffs** — open a test in both runs, scroll the transcripts side by side.

## What to look for

| Signal                                             | What it usually means                                                                                                                                                                 |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| New failures on tests you didn't touch             | The prompt change has a side-effect. Common cause: changing one node's instructions affects how the LLM interprets transition conditions from neighbouring nodes.                     |
| Same pass/fail but lower scores                    | The agent is *technically* meeting the criteria but in a way the judge finds less complete. Often a sign that conciseness or tone has shifted.                                        |
| Tests get stuck in the wrong node                  | A transition condition you didn't edit is now being interpreted differently. Usually fixed by tightening the global prompt or the affected transition's natural-language description. |
| Test passes but with a wildly different turn count | Path through the graph has changed. Worth a transcript scan to confirm the new path is acceptable.                                                                                    |

## Catch it before it ships

Once you've manually validated the loop a few times, automate it. The [GitHub Actions recipe](ci-github-actions.md) shows how to run the same suite on every push and block merges that regress.

## Related

- [Diagnose a failing test](diagnose-failing-test.md) — when a regression appears, voicetest can propose the fix
- [Run in GitHub Actions](ci-github-actions.md) — make this loop automatic
- [Features: Diagnosis & auto-fix](../features.md#diagnosis-auto-fix) — full reference
