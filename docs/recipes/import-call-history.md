# Import call history as a regression suite

**The problem:** You have a synthetic test suite, but it's bounded by the imagination of whoever wrote it. Real callers say things you didn't anticipate — filler, hedging, unusual order combinations, intents your suite doesn't cover. You want production traffic to be the regression net for the cases you haven't thought of.

**The flow:**

1. Pull a batch of recent calls from your platform
1. Import them as a voicetest **Run**
1. Replay them against the agent's current graph
1. Diff source vs. replay

This works for ~1000 production calls in about a minute end-to-end after the initial setup.

## 1. Pull a batch of calls

=== "Retell"

    ```bash
    # Yesterday's calls in one file
    curl -X POST https://api.retellai.com/v2/list-calls \
      -H "Authorization: Bearer $RETELL_API_KEY" \
      -H "Content-Type: application/json" \
      -d '{"filter_criteria": {"start_timestamp": {"after": 1714780800000}}, "limit": 1000}' \
      > prod-calls.json
    ```

    Voicetest accepts both the single-call shape and the post-call webhook envelope, as a single object or an array.

Other platforms (VAPI, LiveKit, Telnyx, Bland) are not yet supported in v1 of the transcript importer. See [Importing transcripts](../transcripts.md) for the format reference.

## 2. Import as a Run

```bash
voicetest import-call \
  --agent <your-agent-id> \
  --transcript prod-calls.json
# Imported 312 conversation(s) into run prod-2026-05-08
```

Each call becomes a `Result` inside one `Run`, with `status="imported"`. The run renders in the UI alongside your simulated runs and is fully searchable.

!!! warning "Redact PII before ingest"

    Voicetest does not redact transcripts at import time. If your calls contain personal data, redact in the dump file *before* running `import-call`.

## 3. Replay against the current graph

Replaying drives a fresh conversation against the agent's *current* configuration using the source's recorded user turns as a script. The live agent's responses replace the recorded ones.

```bash
voicetest replay prod-2026-05-08
# Replayed 312 conversation(s) into run replay-abc123
```

The new run lands next to the source in the runs UI.

## 4. Compare source vs. replay

In the web UI, open the source run on the left and the replay on the right. Scroll the transcripts side by side. You're looking for:

| Divergence                                            | What it usually means                                                                                               |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Live agent asks a different question than recorded    | A prompt change altered the path. The next scripted user turn won't fit perfectly — replay continues anyway.        |
| Live agent fails to extract a variable that worked    | An extract-node prompt regressed. Usually fixable with one targeted edit.                                           |
| Live agent ends the call earlier than recorded        | Either an end-condition is firing too eagerly, or the agent is now resolving faster — read the transcripts to tell. |
| Live agent escalates ("transfer to human") more often | Confidence in routing has dropped. Check whether routing prompts changed or whether new global nodes are firing.    |

Replay is **best-effort** — there is no LLM-driven divergence repair in v1. When the live agent diverges from the script, the regression signal is "this conversation is now incoherent," which is exactly the thing you want to know about.

## Turning replays into named tests

The replay run gives you signal but not a permanent named test case. To promote a particular conversation to the synthetic suite:

1. Open the source result in the UI
1. Click **Convert to test case**
1. Give it a name and edit the metrics list
1. Save — it now lives in your `tests.json` and runs on every `voicetest run --all`

Curating ~20 of your most common production patterns into the synthetic suite typically catches >80% of meaningful regressions, and a replay sweep on a fresh batch of calls catches the rest.

## A repeatable rhythm

A practical weekly cadence for teams running production agents:

```bash
# Monday: pull the past week of calls
./scripts/dump-retell-calls.sh > weekly-calls.json
voicetest import-call --agent receptionist --transcript weekly-calls.json

# Friday afternoon: replay against whatever's been merged this week
voicetest replay $(latest_weekly_run_id)

# Then scan the diffs in the UI before the weekend deploy freeze
```

## Related

- [Replay Production Call Transcripts (blog post)](https://voicetest.dev/blog/replay-production-call-transcripts-voice-agent-regression/) — narrative walkthrough
- [Importing transcripts](../transcripts.md) — full reference for the import + replay APIs
- [Regression-test prompt changes](regression-test-prompt-changes.md) — the synthetic-suite version of the same loop
