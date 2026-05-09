---
description: What shipped in each voicetest release. User-facing changes, in reverse chronological order.
---

# Changelog

User-facing changes by release. For the full commit log, see the [GitHub releases](https://github.com/voicetestdev/voicetest/releases).

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
