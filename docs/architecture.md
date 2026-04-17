# Architecture

## Conversation engine

The `ConversationEngine.advance()` method traverses the agent graph from the current node until it produces speech or settles:

1. Call `_process_node()` on the current node
1. If the node produced a response (conversation node), return it
1. If the node is silent (logic or extract node) and transitioned, follow the edge and repeat
1. Maximum 20 hops per `advance()` call to prevent infinite loops

Silent nodes auto-fire: logic nodes evaluate equations deterministically, extract nodes call the LLM once for variable extraction then evaluate equations. Tool messages record transitions and extractions in the transcript.

**Transition evaluation** uses a structured two-phase output within a single LLM call. The signature includes an `objectives_complete` (bool) gate that the LLM must fill before selecting a transition target. If the node's objectives aren't met — for example, the agent asked a question the user hasn't addressed — the transition is blocked regardless of whether a condition matches. The evaluator also receives the agent's `last_agent_message` as a dedicated input to ground its completion assessment.

**Metric evaluation** filters internal tool messages (transitions, variable extractions) from the transcript before sending it to the judge LLM. The judge only sees the user/assistant conversation, reducing noise that could cause false negatives.

## DI container (Punq)

The project uses Punq for dependency injection. Key singletons:

- `Engine`, `sessionmaker`, `Session` — SQLAlchemy database layer (DuckDB-backed)
- `ImporterRegistry`, `ExporterRegistry`, `PlatformRegistry` — Registries

Repositories are transient but share the singleton session:

- `AgentRepository`, `TestCaseRepository`, `RunRepository`, `CallRepository`

Get instances via `voicetest.container`:

```python
from voicetest.container import get_session, get_importer_registry
```

**When to use DI:**

- Use `get_*` helpers for app code (REST handlers, CLI commands)
- Use `container.resolve(Type)` when you need the container directly
- For tests, use `reset_container()` to get fresh state
- Don't instantiate repositories directly; let Punq inject the session

## DSPy signatures

When defining DSPy signatures, type the fields accurately:

```python
class MySignature(dspy.Signature):
    """Docstring becomes the prompt context."""

    input_text: str = dspy.InputField(desc="What this input contains")
    count: int = dspy.InputField(desc="Numeric input")

    result: str = dspy.OutputField(desc="What the LLM should produce")
    score: float = dspy.OutputField(desc="Numeric score from 0.0 to 1.0")
    items: list[str] = dspy.OutputField(desc="List of extracted items")
    valid: bool = dspy.OutputField(desc="True/False judgment")
```

The type annotations (`str`, `int`, `float`, `bool`, `list[str]`) guide the LLM's output format. The `desc` should clarify semantics, not just repeat the type.

## Storage

Data persists to `.voicetest/data.duckdb` (or `VOICETEST_DB_PATH` env var).

Tests are scoped to agents via `agent_id` foreign key in `test_cases` table.

## Terminal tool conversion (Retell)

When importing Retell LLM format agents, terminal tools (`end_call`, `transfer_call`) are converted to proper CF node types during export rather than remaining as tools in the tools array:

- `end_call` tools become `type=end` nodes in the Conversation Flow
- `transfer_call` tools become `type=transfer_call` nodes with `transfer_destination` and `transfer_option`
- Tool metadata carries `transfer_destination` and `transfer_option` through the import/export pipeline
- The agent envelope (voice_id, language, etc.) is preserved from LLM format through CF export for Retell UI re-import
