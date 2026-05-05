# Importing real call transcripts

voicetest can ingest real production call transcripts as Runs, alongside the simulated test runs the harness generates. Imported transcripts share the same storage and UI surfaces as simulated runs and can be **replayed** against the agent's current graph to detect behavioral drift.

## Two operations

| Operation        | What it does                                                                                             | UI                                       | CLI                                                         | REST                                            |
| ---------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------- | ----------------------------------------------------------- | ----------------------------------------------- |
| **Import calls** | Parse a platform-specific transcript dump and persist as a Run with `status="imported"` Results          | "Import Calls…" button on the agent page | `voicetest import-call --agent <id> --transcript file.json` | `POST /api/agents/{id}/import-call` (multipart) |
| **Replay**       | Drive a fresh conversation against the agent's current graph using a source Run's user turns as a script | "Replay" button on the run detail page   | `voicetest replay <run-id>`                                 | `POST /api/runs/{id}/replay`                    |

## Supported formats

### Retell

voicetest accepts both:

- The Retell call object as returned by `GET /v2/get-call/{call_id}` (single call)
- The Retell post-call webhook payload (call object wrapped in `{"event": ..., "call": {...}}`)

Either shape can be a single object or an array. Examples:

```json
// Single call
{
  "call_id": "call_abc123",
  "transcript_object": [
    {"role": "agent", "content": "Hi, how can I help?"},
    {"role": "user", "content": "I need to cancel my order."}
  ],
  "duration_ms": 60000,
  "start_timestamp": 1700000000000,
  "end_timestamp": 1700000060000
}

// Webhook envelope
{
  "event": "call_ended",
  "call": { /* same call object as above */ }
}

// Array of either
[ { /* call */ }, { /* call */ } ]
```

The adapter maps `role: "agent"` → `role: "assistant"` (voicetest convention) and ignores word-level timing details.

Other platforms (VAPI, LiveKit, Telnyx, Bland) are **not yet supported** — `--format` is parameterized so they can be added without breaking changes.

## Data model

- **Imported run**: a `Run` whose `Result`s have `status="imported"`, `test_case_id=null`, `call_id=null`. Each Result holds one call's transcript.
- **Replay run**: a `Run` produced by replaying a source Run. Results have `status="pass"` (replay results are passive captures of live behavior; judging happens later when metrics are configured).

Both kinds of runs render in the existing runs UI alongside simulated runs. The runs list shows an "imported" badge for runs whose Results are all imported.

## Replay semantics

- For each source Result, `ScriptedUserSimulator` yields the source's recorded user turns in order.
- The live agent's responses replace the recorded ones; the source's agent turns are not used.
- If the live agent diverges from the recorded conversation (asks a different question), the next recorded user turn may not fit perfectly. The replay continues anyway — the regression signal is still useful because the conversation as a whole can be evaluated.
- Replay is **best-effort**: there's no LLM-based divergence handling in v1.

## Limitations

- Single-platform support (Retell only).
- No PII redaction at import time — clients with sensitive data should redact before ingesting.
- No diff view between source and replay yet; they're separate runs in the UI.
- No batch import via UI — large dumps are easier via CLI.

For more advanced workflows (clustering, coverage analysis, test-case generation from real calls), see the proposals in [PROPOSALS.md](PROPOSALS.md).
