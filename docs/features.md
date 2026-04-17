# Features

## Format conversion

voicetest converts between agent formats via its unified AgentGraph representation:

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

Import from any supported format, then export to any other:

```bash
# Convert Retell Conversation Flow to Retell LLM format
voicetest export --agent retell-cf-agent.json --format retell-llm > retell-llm-agent.json

# Convert VAPI assistant to Retell LLM format
voicetest export --agent vapi-assistant.json --format retell-llm > retell-agent.json

# Convert Retell LLM to VAPI format
voicetest export --agent retell-llm-agent.json --format vapi-assistant > vapi-agent.json
```

## Platform integration

voicetest connects directly to voice platforms to import and push agent configurations.

| Platform | Import | Push | Sync | API Key Env Var                          |
| -------- | ------ | ---- | ---- | ---------------------------------------- |
| Retell   | ✓      | ✓    | ✓    | `RETELL_API_KEY`                         |
| VAPI     | ✓      | ✓    | ✓    | `VAPI_API_KEY`                           |
| Bland    | ✓      | ✓    |      | `BLAND_API_KEY`                          |
| Telnyx   | ✓      | ✓    | ✓    | `TELNYX_API_KEY`                         |
| LiveKit  | ✓      | ✓    | ✓    | `LIVEKIT_API_KEY` + `LIVEKIT_API_SECRET` |

In the Web UI, go to the "Platforms" tab to configure credentials, browse remote agents, import, push, and sync.

## Prompt snippets

Agent prompts often repeat text across nodes — sign-off phrases, compliance disclaimers, tone instructions, etc. **Snippets** are named, reusable text blocks defined at the agent level and referenced in prompts via `{%snippet_name%}`.

| Snippet Name | Text                                                             |
| ------------ | ---------------------------------------------------------------- |
| `sign_off`   | "Thank you for calling. Is there anything else I can help with?" |
| `hipaa_warn` | "I need to verify your identity before sharing medical info."    |

Use `{%name%}` (with percent signs) in any node prompt or general prompt:

```
Welcome the caller and introduce yourself.

{%hipaa_warn%}

When the conversation ends:
{%sign_off%}
```

Snippets are expanded **before** dynamic variables (`{{var}}`), so you can combine both:

```
Hello {{caller_name}}, {%greeting%}
```

Click **Analyze DRY** to scan all prompts for repeated or near-identical text. Exact matches can be auto-extracted into snippets; fuzzy matches (above 80%) are flagged for review.

![DRY Analysis Demo (light)](demos/dry-demo-light.gif)

When exporting, choose **Raw (.vt.json)** to preserve `{%snippet%}` references, or **Expanded** to resolve them to plain text for platform deployment.

## Global metrics

Global metrics are compliance-style checks that run on every test for an agent. Configure them in the "Metrics" tab in the Web UI.

Each agent has:

- **Pass threshold**: Default score (0-1) required for metrics to pass (default: 0.7)
- **Global metrics**: List of criteria evaluated on every test run

Each global metric has:

- **Name**: Display name (e.g., "HIPAA Compliance")
- **Criteria**: What the LLM judge evaluates (e.g., "Agent must verify patient identity before sharing medical information")
- **Threshold override**: Optional per-metric threshold (uses agent default if not set)
- **Enabled**: Toggle to skip without deleting

Example use cases:

- HIPAA compliance checks for healthcare agents
- PCI-DSS validation for payment processing
- Brand voice consistency across all conversations
- Safety guardrails and content policy adherence

## Diagnosis & auto-fix

When a test fails, voicetest can diagnose the root cause and suggest concrete prompt changes to fix it.

1. **Diagnose** — Click "Diagnose" on a failed result. The LLM analyzes the graph, transcript, and failed metrics to identify fault locations and root cause.
1. **Review & Edit** — Proposed changes are shown as editable textareas. Modify the suggested text before applying.
1. **Apply & Test** — Click "Apply & Test" to apply changes to a copy of the graph and rerun the test. A score comparison table shows original vs. new scores with deltas.
1. **Iterate** — If not all metrics pass, click "Try Again" to revise the fix based on the latest results.
1. **Save** — Click "Save Changes" to persist the fix to the agent graph.

**Auto-Fix Mode** runs an automated diagnose-apply-revise loop. Configure stop condition ("On improvement" or "When all pass") and max iterations (1-10, default 3).

## Audio evaluation

Text-only evaluation has a blind spot: when an agent produces "415-555-1234", an LLM judge sees correct digits and passes. But TTS might speak it as "four hundred fifteen, five hundred fifty-five..." — which a caller can't use. Audio evaluation catches these issues by round-tripping agent messages through TTS/STT and judging what would actually be *heard*.

```
Conversation runs normally (text-only)
    ↓
Judges evaluate raw text → metric_results
    ↓
Agent messages → TTS → audio → STT → "heard" text
    ↓
Judges evaluate heard text → audio_metric_results
```

Both sets of results are stored. The original message text is preserved alongside what was heard, with a word-level diff shown in the UI.

Enable `audio_eval` in settings or toggle "Audio evaluation" in the Web UI. On-demand: click "Run audio eval" on any completed result.

Audio evaluation requires the TTS and STT services from `voicetest up`:

| Service   | URL                   | Description        |
| --------- | --------------------- | ------------------ |
| `whisper` | http://localhost:8001 | Faster Whisper STT |
| `kokoro`  | http://localhost:8002 | Kokoro TTS         |

## Agent decomposition

Split a large agent into smaller, focused sub-agents:

```bash
voicetest decompose -a agent.json -o output/ [--num-agents N] [--model ID]
```

Three-phase LLM pipeline: **analyze** the graph → **refine** the decomposition plan → **build** sub-agent JSON files. Produces one `.json` file per sub-agent plus a `manifest.json` with handoff rules and sub-agent registry.

Options:

- `--num-agents N` — Target number of sub-agents (default: let the LLM decide)
- `--model ID` — LLM model override (defaults to judge model from settings)

## LLM response cache

DSPy LLM responses are cached to avoid redundant API calls. Default backend is local disk.

For shared caching across CI runners or team members, use the S3 backend:

```toml
# .voicetest/settings.toml
[cache]
cache_backend = "s3"
s3_bucket = "my-bucket"
s3_prefix = "dspy-cache/"
s3_region = "us-east-1"
```

Disable caching for a run with `no_cache = true` in run options or `--no-cache` on the CLI.

## Web UI

Start the server and open http://localhost:8000:

```bash
voicetest serve
```

The web UI provides:

- Agent import and graph visualization
- Export agents to multiple formats (Mermaid, LiveKit, Retell, VAPI, Bland, Telnyx)
- Platform integration: import, push, and sync agents with Retell, VAPI, LiveKit, Telnyx
- Test case management with persistence
- Global metrics configuration (compliance checks that run on all tests)
- Test execution with real-time streaming transcripts
- Cancel in-progress tests
- Run history with detailed results, transcript inspection, and pass/fail filtering
- Dynamic variables and models used shown per result (collapsible)
- Audio evaluation with word-level diff of original vs. heard text
- Settings configuration (models, max turns, streaming, audio eval)

Data is persisted to `.voicetest/data.duckdb` (configurable via `VOICETEST_DB_PATH`).

The REST API is available at http://localhost:8000/api. Full API documentation is at [voicetest.dev/api](https://voicetest.dev/api/).
