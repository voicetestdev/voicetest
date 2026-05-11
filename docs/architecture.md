---
description: How voicetest is structured — the AgentGraph IR, the conversation engine, and how tests, runs, and storage fit together.
---

# Architecture

## System overview

Voicetest is built around one central data structure — the **AgentGraph IR** — and a thin layering above and below it:

```
              ┌─────────────────────────────────────────┐
  Surfaces    │  CLI    Web UI / REST    Shell    Plugin│
              └────────────────────┬────────────────────┘
                                   │
              ┌────────────────────▼────────────────────┐
  Services    │  agents · runs · diagnosis · snippets   │
              └────────────────────┬────────────────────┘
                                   │
                       ┌───────────┼───────────┐
                       ▼           ▼           ▼
  Core             Importers     Engine     Exporters
                       │       + Judges        ▲
                       │           │           │
                       └──▶ AgentGraph IR ◀────┘
                                   │
                                   ▼
                              TestResult
                                   │
                                   ▼
  Storage           DuckDB  (.voicetest/data.duckdb)
```

The surfaces are thin wrappers — CLI commands, REST handlers, the interactive shell, and the Claude Code plugin all delegate to the **service layer**. Services orchestrate the **core** components: importers parse platform configs into the IR, exporters render the IR out to other formats, the engine drives an IR through a conversation, and judges evaluate the resulting transcripts. Everything persists to DuckDB through a shared repository layer.

## The AgentGraph IR

Every importer converts platform-specific configs into the AgentGraph; every exporter renders one back out. This is the central architectural choice: it keeps the conversation engine, judges, and tooling agnostic to where an agent originally came from. For the import/export matrix, see [Features: Format conversion](features.md#format-conversion).

The IR captures:

- **Nodes** — five types (Conversation, Logic, Extract, End, Transfer), any of which can be marked global. See [Concepts: Node types](concepts.md#node-types).
- **Transitions** — typed edges (`llm_prompt`, `equation`, `tool_call`, `always`) between nodes.
- **Variables** — extract-node outputs and per-call dynamic variables.
- **Snippets** — named reusable prompt fragments referenced via `{%name%}`.
- **Tools** — function definitions available to the agent at each node.

Round-trip fidelity is preserved when the source and target platforms share a feature; lossy steps are annotated by the exporter. The voicetest native format (`.vt.json`) is lossless and is the recommended format for version control.

## Conversation engine

The `ConversationEngine.advance()` method traverses the agent graph from the current node until it produces speech or settles:

1. Call `_process_node()` on the current node.
1. If the node produced a response (conversation node), return it.
1. If the node is silent (logic or extract), follow the resulting transition and repeat.
1. Maximum 20 hops per `advance()` call to prevent infinite loops.

Silent nodes auto-fire: logic nodes evaluate equations deterministically; extract nodes call the LLM once for variable extraction, then evaluate equations against the extracted values. Tool messages record transitions and extractions in the transcript without surfacing as user-visible turns.

**Transition evaluation** uses a structured two-phase output within a single LLM call. The signature includes an `objectives_complete` (bool) gate that the LLM must fill before selecting a transition target. If the node's objectives aren't met — for example, the agent asked a question the user hasn't addressed — the transition is blocked regardless of whether a condition matches. The evaluator also receives the agent's `last_agent_message` as a dedicated input to ground its completion assessment.

**Metric evaluation** filters internal tool messages (transitions, variable extractions) from the transcript before sending it to the judge LLM. The judge sees only user/assistant turns, reducing noise that could cause false negatives.

**Global node handling** maintains an originator stack. Entering a global node pushes the current node; a go-back transition pops it and resumes at the originator. Forward exits from a global also pop, since the previous "where was I?" is now stale.

## Storage

Runs, results, agents, and test cases persist to **DuckDB** at `.voicetest/data.duckdb` (overridable via `VOICETEST_DB_PATH`).

| Concept    | Where it lives                                                                                |
| ---------- | --------------------------------------------------------------------------------------------- |
| Agents     | `agents` table — name, source type, graph JSON, model overrides, metric config                |
| Test cases | `test_cases` table — scoped to an agent via `agent_id` foreign key                            |
| Runs       | `runs` table — one row per `voicetest run` invocation, with metadata and aggregated counts    |
| Results    | `results` table — one row per test case execution, with transcript, scores, and call metadata |

Imported and replay runs share the same tables as simulated runs, with status differentiation (`status="imported"` vs `status="pass"|"fail"|"error"`).

The Web UI, REST API, and CLI all read and write through the same repository layer; no surface holds private state.

## Layered structure

| Layer         | Responsibility                                                                 |
| ------------- | ------------------------------------------------------------------------------ |
| **Importers** | Parse platform-specific JSON into AgentGraph                                   |
| **Exporters** | Render AgentGraph back to platform-specific JSON, code, or diagrams            |
| **Engine**    | Drive an AgentGraph through a conversation, producing TestResults              |
| **Judges**    | Evaluate TestResult transcripts against metrics (LLM) or rules (deterministic) |
| **Services**  | Orchestrate above for the CLI, REST, and Web UI surfaces                       |
| **Storage**   | DuckDB-backed repositories                                                     |

Voicetest's three top-level surfaces (CLI, REST + Web UI, interactive shell) are thin wrappers over the service layer. Adding a new surface means writing a new entry point, not reimplementing logic.

## Where to look in the source

For a quick map of the source tree (importers, engine, services, etc.), see [Development: Project structure](development.md#project-structure). For dependency injection and DSPy conventions, see [Development: Internals](development.md#internals).
