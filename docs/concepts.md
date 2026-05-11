---
description: AgentGraphs, node types, transitions, dynamic variables, test cases, runs, and results — the core voicetest concepts.
---

# Core Concepts

## Agent graphs

An agent is represented as an **AgentGraph**: a directed graph of nodes connected by transitions. Each node has a prompt, a type, and outgoing edges that control conversation flow. The graph has a single `entry_node_id` where every conversation starts.

Voicetest's AgentGraph is the unified internal representation that every importer converts to and every exporter renders from. See [Features: Format conversion](features.md#format-conversion) for the round-trip pipeline.

## Node types

| Type             | LLM call         | Speaks?     | Routing                                                                                |
| ---------------- | ---------------- | ----------- | -------------------------------------------------------------------------------------- |
| **Conversation** | Yes              | Yes         | LLM picks a transition via prompt match, or falls back to an `always` edge             |
| **Logic**        | No               | No          | Evaluates equations top-to-bottom; first match wins                                    |
| **Extract**      | Yes (extraction) | No          | LLM extracts variables from the conversation, then equations route                     |
| **End**          | Optional         | If prompted | Terminates the call. With a `state_prompt`, agent speaks one final turn before ending  |
| **Transfer**     | Optional         | If prompted | Same as End structurally, but the call status reflects a transfer rather than a hangup |

Any node type can also be a **global node** — reachable from any conversation node without explicit edges. See [Global Nodes](#global-nodes) below.

**Conversation nodes** are the standard building block — they generate a spoken response and use LLM judgment (or an `always` edge) to choose the next node.

**Logic nodes** (also called branch nodes) have no prompt and produce no speech. All their transitions use `equation` or `always` conditions, evaluated deterministically without an LLM call.

**Extract nodes** combine LLM extraction with deterministic routing. They define `variables_to_extract` (each with a name, description, type, and optional choices). The engine calls the LLM once to extract all variables from the conversation history, stores them as dynamic variables, then evaluates equation transitions using the extracted values.

**End nodes** terminate the call cleanly. If `state_prompt` is empty, the call ends immediately; if non-empty, the agent generates one final response (e.g. "Thanks for calling, goodbye.") before the engine sets `end_call_invoked`.

**Transfer nodes** are structurally identical to End but mark the disconnect as a transfer rather than a hangup — useful for handoffs to a human agent or another phone number.

For a visual walkthrough with all five node types in one diagram, see [Five Node Types and Global Interrupts](https://voicetest.dev/blog/node-types-global-interrupts-voicetest-graph-ir/).

## Global nodes

Global nodes are reachable from **any conversation node** in the flow without requiring explicit edges from every source. Useful for "transfer to manager," "I want to start over," and similar interrupts that should fire from anywhere.

Each global node has a `global_node_setting` containing:

- **`condition`** — An LLM prompt that triggers entry (e.g., "Caller wants to cancel")
- **`go_back_conditions`** — LLM-prompted conditions that return to the originating node

The engine appends global node conditions to every conversation node's transition options. The LLM sees both local transitions and global entry conditions, and picks the best match. When a global node is entered, the engine pushes the originating node onto a stack. Go-back conditions target the originator; on go-back the stack is popped and the conversation resumes at the originating node with full transcript context.

**Stacking:** Global nodes can trigger other global nodes. Each go-back pops one level.

**Zero global nodes:** When a flow has no global nodes, behavior is identical to before. The `format_transitions` signature is backward-compatible.

## Dynamic variables

Prompts can reference dynamic variables using `{{variable_name}}` syntax. Variables come from two sources:

- **Test case `dynamic_variables`** — set before the conversation starts (e.g., `{{caller_name}}`, `{{account_id}}`)
- **Extract node output** — populated during the conversation when an extract node fires

Expansion order: snippet references `{%name%}` are resolved first, then `{{variable}}` placeholders are substituted into the result. Unknown variables are left as-is.

## Equations

Equation conditions on transitions support these operators:

| Operator          | Example                    | Notes                                             |
| ----------------- | -------------------------- | ------------------------------------------------- |
| `==`              | `status == "active"`       | String equality                                   |
| `!=`              | `tier != "free"`           | String inequality                                 |
| `>` `>=` `<` `<=` | `age >= 18`                | Numeric coercion; non-numeric values return false |
| `contains`        | `notes contains "urgent"`  | Substring match                                   |
| `not_contains`    | `reply not_contains "err"` | Substring absence                                 |
| `exists`          | `email exists`             | Variable is set                                   |
| `not_exist`       | `phone not_exist`          | Variable is absent                                |

Multiple clauses combine with `logical_operator`: `"and"` (default, all must match) or `"or"` (any must match).

## Test cases

Test cases define simulated conversations to run against an agent. Two types are supported.

**LLM tests** (`type: "llm"`) use a judge LLM to evaluate semantic metrics against the transcript:

```json
{
  "name": "Customer billing inquiry",
  "user_prompt": "## Identity\nYour name is Jane.\n\n## Goal\nGet help with a charge on your bill.",
  "metrics": ["Agent greeted the customer and addressed the billing concern"],
  "dynamic_variables": {"caller_name": "Jane", "account_id": "12345"},
  "type": "llm"
}
```

**Rule tests** (`type: "rule"`) use deterministic pattern matching — no LLM involved in judging:

```json
{
  "name": "No PII leakage",
  "user_prompt": "You mention your full SSN 123-45-6789 mid-conversation.",
  "excludes": ["123-45-6789", "123456789"],
  "patterns": ["REF-[A-Z0-9]+"],
  "type": "rule"
}
```

| Field               | Applies to | Description                                                                     |
| ------------------- | ---------- | ------------------------------------------------------------------------------- |
| `name`              | both       | Display name, also used to select tests via `--test`                            |
| `user_prompt`       | both       | Persona and goal description for the simulated user                             |
| `dynamic_variables` | both       | Key-value pairs injected into `{{var}}` placeholders before the conversation    |
| `tool_mocks`        | both       | Stub tool responses for tools the agent calls during the conversation           |
| `llm_model`         | both       | Per-test agent model override (only honored when `test_model_precedence` is on) |
| `metrics`           | LLM        | List of natural-language criteria the judge scores (0–1) against the transcript |
| `includes`          | rule       | Substrings that **must** appear in the transcript                               |
| `excludes`          | rule       | Substrings that **must not** appear in the transcript                           |
| `patterns`          | rule       | Regex patterns that must match somewhere in the transcript                      |

Legacy values `"simulation"` and `"unit"` are accepted and mapped to `"llm"` and `"rule"` respectively, but new test cases should use the canonical names.

## Runs and results

A **Run** is a recorded execution of one or more test cases against an agent at a specific point in time. Each Run contains a list of **Result** records, one per test case (or one per conversation, when imported from a transcript dump).

| Run kind  | How it's created                             | Result `status` values   |
| --------- | -------------------------------------------- | ------------------------ |
| Simulated | `voicetest run --all` or "Run" in the Web UI | `pass`, `fail`, `error`  |
| Imported  | `voicetest import-call --transcript ...`     | `imported`               |
| Replay    | `voicetest replay <run-id>`                  | `pass` (passive capture) |

Each Result captures:

- **`transcript`** — list of user/assistant/tool messages
- **`metric_results`** — score and reasoning per LLM metric
- **`audio_metric_results`** — same shape, evaluated against the TTS/STT round-tripped transcript
- **`nodes_visited`** and **`tools_called`** — the path through the graph and any tool invocations
- **`turn_count`**, **`duration_ms`**, **`end_reason`** — call metadata
- **`error_message`** — populated when `status="error"`

Runs persist to DuckDB at `.voicetest/data.duckdb` (configurable via `VOICETEST_DB_PATH`). Both simulated and imported runs render side by side in the runs UI, can be exported as JSON, and can be replayed against the agent's current graph.

## Snippets

Named, reusable text blocks defined at the agent level and referenced in prompts via `{%snippet_name%}`. Useful for compliance disclaimers, sign-off phrases, or any text repeated across multiple node prompts.

See [Features: Prompt snippets](features.md#prompt-snippets) for the snippet system and the DRY-analysis tooling that finds candidates for extraction.

## See it in action

- **[Recipe: Regression-test prompt changes](recipes/regression-test-prompt-changes.md)** — uses the run/result model to compare two snapshots of an agent.
- **[Recipe: Import call history](recipes/import-call-history.md)** — turns production calls into Runs you can replay.
- **[Recipe: Diagnose a failing test](recipes/diagnose-failing-test.md)** — walks the graph to find which node owns a failing metric.
