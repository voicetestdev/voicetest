---
description: What shipped in each voicetest release. User-facing changes, in reverse chronological order.
---

# Changelog

User-facing changes by release. For the full commit log, see the [GitHub releases](https://github.com/voicetestdev/voicetest/releases).

## v0.54 — Full run history

- **All runs are reachable.** The Runs tab badge shows the agent's total run count instead of stopping at 50, and **Show older runs** at the bottom of the list loads the next 50 in place.
- Agent and simulator replies no longer appear as raw JSON (`{"message": "..."}`) in transcripts.
- REST: `GET /api/agents/{id}/runs/count`, and an `offset` parameter on `GET /api/agents/{id}/runs`.

## v0.53 — User-first simulations

- **Choose who speaks first.** Simulations can open with the user instead of the agent. The opener comes from the agent page's **Speaks first** toggle, then the agent template (Retell `start_speaker`, VAPI `firstMessageMode`), then the global `start_speaker` setting, and otherwise defaults to the agent. See [Configuration: Who speaks first](configuration.md#who-speaks-first).
- Replays follow the speaking order of the recorded call.
- The VAPI importer and exporter round-trip `firstMessageMode`.
- Redesigned agent page header: one row of actions, and a settings table that shows each setting's effective value and where it comes from.
- REST: `PUT /api/agents/{id}/start-speaker`.

## v0.52 — Event-based judging

- **Structured judge input.** Set `judge_input = "events"` to give metric judges a timeline of speech, keypad input, tool activity, and node transitions, with timing when known, instead of a plain transcript. See [Configuration: Judge input](configuration.md#judge-input).
- Each result records the judge input and voicetest version it was judged with.
- DSPy is pinned to 3.4.x so judge prompt formatting stays stable.

## v0.51

- Dependency upgrades.
- When an LLM response fails to parse, the retry asks the model again instead of replaying the cached response.

## v0.50 — Live calls

- **Hear what the caller heard.** Live calls over LiveKit record both what the agent meant to say and what was heard on the line, by transcribing the agent's own audio. Audio metrics judge the heard text. See [Features: Live audio testing](features.md#live-audio-testing).
- Results record where they came from: `simulated`, `live`, or `imported`.
- The live-call stack (LiveKit, faster-whisper, Kokoro, Ollama) runs locally with no external API keys.
- Agents whose linked source file was moved or deleted still open, and can be deleted.

## v0.49 — Cancel feedback

- Cancelling a run or a test is acknowledged right away in the Web UI.
- Tests cancelled before they start are recorded with a new `cancelled` status.

## v0.48 — Retell API v3

- Retell call import and agent listing use Retell's current API endpoints.

## v0.47 — Function nodes

- **Function nodes.** Retell `function` (tool-call) nodes import, export, and run. The tool itself is not executed yet: the engine logs a warning and continues.
- Retell `branch` nodes now route as logic nodes; previously they were treated as conversation nodes.
- Equation transitions on conversation nodes are evaluated deterministically instead of by the LLM.

## v0.46

- Fixed the LiveKit status endpoint returning a 500 error.

## v0.45

- Editing tweaks in the Tests and Runs views.
- Transient Claude Code passthrough errors (5xx responses) are retried.

## v0.44

- Internal refactor with no behavior changes. The Python `generic_tests` factories were replaced by the [starter test suite recipe](recipes/starter-test-suite.md).

## v0.43

- Fixed `POST /api/evaluate` ignoring the configured judge model and falling back to the Groq default.

## v0.42 — Docs overhaul

- New docs: [Recipes](recipes/index.md), a [models guide](models.md), and this changelog.
- Fixed a crash when opening a run that was still in progress when the server stopped.

## v0.41 — Import transcripts

- **Transcript import & replay.** New `voicetest import-call` command ingests Retell call dumps as Runs; `voicetest replay <run-id>` drives the recorded user turns against the agent's current graph. See the [Import call history recipe](recipes/import-call-history.md).
- New `ScriptedUserSimulator` for replay drives conversations from a fixed user-turn script.
- REST endpoints: `POST /api/agents/{id}/import-call`, `POST /api/runs/{id}/replay`.

## v0.40 — Timeout retries

- **Per-exception retry caps.** Timeouts now retry at most 2 times (vs. the default 8), bounding worst-case wallclock. Other failure classes (rate limits, connection errors) keep the higher cap.
- `subprocess.TimeoutExpired` from the Claude Code passthrough is now translated to `litellm.Timeout` so the standard retry path handles it.
- Default Claude Code subprocess timeout raised to 600s.

## v0.39

- Bug fix for a graph traversal edge case (`None` error in node resolution).

## v0.38 — Runs UI reorganization

- Runs list and run detail are now distinct views in the Web UI.
- Cleaner navigation when comparing multiple runs.

## v0.37

- Dynamic favicon based on test run status.
- DuckDB concurrency fix for parallel test execution.
- `voicetest up` now uses `uvx` for ephemeral tool runs.
- Pre-release versions are no longer auto-installed.

## v0.36

- Web UI styling moved into shared modules; spinner added for long-running operations.
- Additional DuckDB concurrency hardening.

## v0.35 — Interface cleanup, OOC errors

- Out-of-context (quota exhausted) errors are caught and surfaced as `status="error"` results with clear messages instead of stacktraces.
- General Web UI interface cleanup.

## v0.34 — Global nodes

- **Global nodes.** Nodes can be marked reachable from any conversation node via `global_node_setting`, with `go_back_conditions` for resumable interrupts. The engine maintains an originator stack to support stacked global flows.
- Round-trip fidelity for global nodes through the Retell CF importer/exporter.
- See [Concepts: Global nodes](concepts.md#global-nodes) and the [Five Node Types blog post](https://voicetest.dev/blog/node-types-global-interrupts-voicetest-graph-ir/).

## v0.33

- New graph-generation utilities (`gengraph`).
- Snippet detection improvements: file paths and RDBMS connection strings are now special-cased rather than flagged as duplicate text.

## v0.32

- Split-and-clean refactor: the IR layer is now cleanly separated from importers and exporters.

## v0.31 — Extract nodes

- **Extract nodes.** New node type that runs an LLM extraction over the conversation, populates dynamic variables, then routes via equation transitions. See [Concepts: Node types](concepts.md#node-types).

## v0.30 — Cache layer

- DSPy LLM response cache with disk and S3 backends. See [Features: LLM response cache](features.md#llm-response-cache).
- `--no-cache` CLI flag and `no_cache` run option for cache-bypass on demand.
