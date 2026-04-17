# Core Concepts

## Agent graphs

An agent is represented as an **AgentGraph**: a directed graph of nodes connected by transitions. Each node has a prompt, a type, and outgoing edges that control conversation flow. The graph has a single `entry_node_id` where every conversation starts.

## Node types

| Type             | LLM Call         | Speech | Routing                                                                    |
| ---------------- | ---------------- | ------ | -------------------------------------------------------------------------- |
| **Conversation** | Yes              | Yes    | LLM picks a transition via prompt match, or falls back to an `always` edge |
| **Logic**        | No               | No     | Evaluates equations top-to-bottom; first match wins                        |
| **Extract**      | Yes (extraction) | No     | LLM extracts variables from the conversation, then equations route         |

Any node type can also be a **global node** — reachable from any conversation node without explicit edges. See [Global Nodes](#global-nodes) below.

**Conversation nodes** are the standard building block — they generate a spoken response and use LLM judgment (or an `always` edge) to choose the next node.

**Logic nodes** (also called branch nodes) have no prompt and produce no speech. All their transitions use `equation` or `always` conditions, evaluated deterministically without an LLM call.

**Extract nodes** combine LLM extraction with deterministic routing. They define `variables_to_extract` (each with a name, description, type, and optional choices). The engine calls the LLM once to extract all variables from the conversation history, stores them as dynamic variables, then evaluates equation transitions using the extracted values.

## Global nodes

Global nodes are reachable from **any conversation node** in the flow without requiring explicit edges from every source. They are a Retell Conversation Flow concept supported in the IR.

Each global node has a `global_node_setting` containing:

- **`condition`** — An LLM prompt that triggers entry (e.g., "Caller wants to cancel")
- **`go_back_conditions`** — LLM-prompted conditions that return to the originating node

The engine appends global node conditions to every conversation node's transition options. The LLM sees both local transitions and global entry conditions, and picks the best match. When a global node is entered, the engine tracks the originating node. Go-back conditions target the originator, effectively resuming the previous conversation with transcript context intact.

**Stacking**: Global nodes can trigger other global nodes. The engine maintains an originator stack — each go-back pops one level.

**Zero global nodes**: When a flow has no global nodes, behavior is identical to before. The `format_transitions` signature is backward-compatible.

## Dynamic variables

Prompts can reference dynamic variables using `{{variable_name}}` syntax. Variables come from two sources:

- **Test case `dynamic_variables`**: Set before the conversation starts (e.g., `{{caller_name}}`, `{{account_id}}`)
- **Extract node output**: Populated during the conversation when an extract node fires

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

Test cases define simulated conversations to run against an agent:

```json
[
  {
    "name": "Customer billing inquiry",
    "user_prompt": "## Identity\nYour name is Jane.\n\n## Goal\nGet help with a charge on your bill.",
    "metrics": ["Agent greeted the customer and addressed the billing concern"],
    "dynamic_variables": {"caller_name": "Jane", "account_id": "12345"},
    "tool_mocks": [],
    "type": "simulation"
  }
]
```

- **`type: "simulation"`** — The engine simulates both agent and user, running a full multi-turn conversation
- **`metrics`** — LLM judges evaluate each metric against the transcript and produce a 0-1 score
- **`dynamic_variables`** — Key-value pairs injected into `{{var}}` placeholders before the conversation starts
