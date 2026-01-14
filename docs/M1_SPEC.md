# M1: Voice Agent Test Harness

## Overview

**voicetest** — A generic OSS test harness for voice agent workflows. Tests agents from multiple sources (Retell, Vapi, LiveKit native, custom) using a unified execution and evaluation model.

**Design principle**: Source-agnostic core with pluggable importers. The internal representation and test execution are decoupled from any specific platform.

**Primary use cases**:
1. Test voice agent configs before production deployment
2. Regression testing during prompt/flow iteration  
3. Cross-platform migration (Retell → LiveKit, Vapi → LiveKit, etc.)
4. Unified testing across heterogeneous agent fleet

## Multi-Source Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Source Importers                         │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │ Retell  │  │  Vapi   │  │ LiveKit │  │ Custom (Python) │ │
│  │ Importer│  │ Importer│  │ Importer│  │    Importer     │ │
│  └────┬────┘  └────┬────┘  └────┬────┘  └────────┬────────┘ │
│       │            │            │                │          │
│       └────────────┴────────────┴────────────────┘          │
│                            │                                 │
│                            ▼                                 │
│               ┌─────────────────────────┐                   │
│               │  Unified Agent Model    │                   │
│               │  (Internal IR)          │                   │
│               └───────────┬─────────────┘                   │
│                           │                                  │
└───────────────────────────┼──────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    Test Execution Engine                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Simulator  │  │  LiveKit    │  │    Judges (DSPy)    │  │
│  │  (User LLM) │  │ AgentSession│  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                       Output Layer                           │
│  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────────────┐ │
│  │  JSON   │  │ Parquet │  │   CLI   │  │    Web API      │ │
│  └─────────┘  └─────────┘  └─────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### Unified Agent Model (Internal IR)

All importers convert to a common internal representation:

```python
@dataclass
class AgentNode:
    id: str
    instructions: str                    # System prompt for this node
    tools: list[ToolDefinition]         # Available tools/functions
    transitions: list[Transition]        # How to move to other nodes
    metadata: dict                       # Source-specific extras

@dataclass  
class Transition:
    target_node_id: str
    condition: TransitionCondition       # LLM-evaluated or deterministic
    
@dataclass
class TransitionCondition:
    type: Literal["llm_prompt", "equation", "tool_call", "always"]
    value: str                           # Prompt text, equation, tool name, etc.

@dataclass
class AgentGraph:
    nodes: dict[str, AgentNode]
    entry_node_id: str
    source_type: str                     # "retell", "vapi", "livekit", "custom"
    source_metadata: dict                # Original config reference
```

### Source Importers

| Source | Import Format | M1 | Notes |
|--------|--------------|-----|-------|
| **Retell** | Conversation Flow JSON | ✓ | Primary M1 target |
| **Vapi** | Assistant JSON (via API) | M2 | Similar structure to Retell |
| **LiveKit** | Python Agent classes | M2 | Introspect via decorators/metadata |
| **Custom** | Python function returning AgentGraph | ✓ | Escape hatch for anything |

**Importer interface**:
```python
class SourceImporter(Protocol):
    source_type: str
    
    def can_import(self, path_or_config: str | dict) -> bool:
        """Return True if this importer handles this input."""
        ...
    
    def import_agent(self, path_or_config: str | dict) -> AgentGraph:
        """Convert source format to unified AgentGraph."""
        ...
    
    def export_livekit(self, graph: AgentGraph) -> str:
        """Generate LiveKit Agent Python code (optional)."""
        ...
```

## Key Insight: Retell ≈ Vapi ≈ LiveKit Under the Hood

Both Retell, Vapi, and LiveKit use **LLM-based transition evaluation**:

| System | Graph Definition | Transition Mechanism |
|--------|------------------|----------------------|
| **Retell** | JSON config with nodes/edges | LLM evaluates prompt conditions |
| **Vapi** | Assistant JSON / Squads | LLM decides tool calls, squad transfers |
| **LiveKit** | Python Agent classes with tools | LLM decides to call tools, tools return handoffs |

A Retell edge condition:
```json
{"transition_condition": {"type": "prompt", "prompt": "Customer wants to book appointment"}}
```

Is functionally equivalent to a LiveKit tool:
```python
@function_tool
async def route_to_booking(self, ctx: RunContext):
    """Call when customer wants to book appointment"""
    return BookingAgent(), "I'll help you book."
```

This means we can **convert Retell configs to LiveKit Agents** and leverage LiveKit's mature execution engine and test framework.

## Architecture

### Layered Design

```
┌─────────────────────────────────────────────────────────────┐
│                      Presentation Layer                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │     CLI     │  │   Web UI    │  │   REST API (M2)     │  │
│  │  (Click)    │  │  (Next.js)  │  │   (FastAPI)         │  │
│  └──────┬──────┘  └──────┬──────┘  └──────────┬──────────┘  │
│         │                │                    │              │
│         └────────────────┴────────────────────┘              │
│                          │                                   │
└──────────────────────────┼───────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                       Core API Layer                         │
│                     (voicetest.api)                          │
│                                                              │
│   import_agent(config, source?) -> AgentGraph                │
│   list_importers() -> list[ImporterInfo]                     │
│   export_agent(graph, format) -> str | Path                  │
│   run_test(graph, test_case) -> TestResult                   │
│   run_tests(graph, test_cases) -> TestRun                    │
│   evaluate_transcript(transcript, metrics) -> list[MetricResult] │
│                                                              │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    Implementation Layer                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Importers  │  │   Engine    │  │      Judges         │  │
│  │             │  │  (LiveKit)  │  │      (DSPy)         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  Exporters  │  │  Simulator  │  │   Generic Tests     │  │
│  │             │  │             │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

### Core API

The Core API is the single interface for all consumers. CLI and Web UI are both thin wrappers.

```python
# voicetest/api.py

async def import_agent(
    config: str | Path | dict,
    source: str | None = None,  # auto-detect if None
) -> AgentGraph:
    """Import agent config from any supported source."""
    ...

def list_importers() -> list[ImporterInfo]:
    """List available importers with their capabilities."""
    ...

async def export_agent(
    graph: AgentGraph,
    format: Literal["livekit", "mermaid", "dot"],
    output: Path | None = None,
) -> str:
    """Export agent graph to specified format."""
    ...

async def run_test(
    graph: AgentGraph,
    test_case: TestCase,
    options: RunOptions | None = None,
) -> TestResult:
    """Run a single test case against an agent."""
    ...

async def run_tests(
    graph: AgentGraph,
    test_cases: list[TestCase],
    options: RunOptions | None = None,
) -> TestRun:
    """Run multiple test cases, return aggregated results."""
    ...

async def evaluate_transcript(
    transcript: list[Message],
    metrics: list[str],
) -> list[MetricResult]:
    """Evaluate an existing transcript against metrics (no simulation)."""
    ...
```

### CLI as Thin Wrapper

```python
# voicetest/cli.py

@click.command()
@click.option("--config", required=True)
@click.option("--tests", required=True)
@click.option("--source", default=None)
@click.option("--output", "-o", default=None)
async def run(config, tests, source, output):
    graph = await api.import_agent(config, source=source)
    test_cases = load_test_cases(tests)
    
    result = await api.run_tests(graph, test_cases)
    
    if output:
        Path(output).write_text(result.model_dump_json())
    else:
        render_to_console(result)
```

### REST API as Thin Wrapper (M2)

```python
# voicetest/rest.py

@app.post("/agents/import")
async def import_agent_endpoint(config: dict, source: str | None = None):
    graph = await api.import_agent(config, source=source)
    return graph.model_dump()

@app.post("/runs")
async def create_run(agent_id: str, test_cases: list[TestCase]):
    graph = get_stored_graph(agent_id)  # persistence layer
    result = await api.run_tests(graph, test_cases)
    store_run(result)  # persistence layer
    return result.model_dump()
```

### Web UI Strategy

**Decision**: Build standalone Web UI rather than extending LiveKit's playground.

**Rationale**:
1. LiveKit's `agents-playground` is for **interactive testing** (human talks to agent) — different use case from **automated simulation testing**
2. LiveKit Cloud dashboard is closed-source; can't extend it
3. LiveKit's open-source `components-js` (Agents UI) is for building agent frontends, not test management UIs
4. Our UI needs: test configuration, batch runs, result comparison, transcript analysis — none of which exist in LiveKit ecosystem

**Web UI pages** (M2):
- `/agents` → List imported agent configs
- `/agents/:id` → Agent detail, node graph visualization
- `/tests` → Test case management
- `/runs` → Test run history, results
- `/runs/:id` → Run detail, transcript viewer
- `/compare` → Side-by-side run comparison

## Components

### 1. Retell Config Parser

Parses Retell Conversation Flow JSON.

**Input**: Retell export JSON
```json
{
  "nodes": [
    {
      "id": "greeting",
      "type": "conversation",
      "instruction": { "type": "prompt", "text": "Greet the customer..." },
      "edges": [
        {
          "transition_condition": { "type": "prompt", "prompt": "Customer wants billing help" },
          "destination_node_id": "billing"
        }
      ]
    }
  ],
  "start_node_id": "greeting"
}
```

**Output**: Pydantic models representing Retell schema

### 2. Retell → LiveKit Converter

Converts Retell nodes to LiveKit Agent classes.

**Conversion logic**:
- Each Retell node → LiveKit Agent subclass
- Node instruction → Agent `instructions` parameter
- Each outgoing edge → `@function_tool` that returns handoff
- Edge condition prompt → tool description (LLM uses this to decide when to call)
- Retell functions → LiveKit tools (mocked for testing)

```python
def convert_node_to_agent(node: RetellNode, all_nodes: dict) -> type[Agent]:
    """Generate a LiveKit Agent class from a Retell node."""
    
    # Build transition tools from edges
    tools = []
    for edge in node.edges:
        if edge.transition_condition.type == "prompt":
            @function_tool
            async def transition(ctx: RunContext) -> tuple[Agent, str]:
                # Description comes from edge condition
                return get_agent(edge.destination_node_id), ""
            
            transition.__doc__ = edge.transition_condition.prompt
            transition.__name__ = f"route_to_{edge.destination_node_id}"
            tools.append(transition)
    
    class GeneratedAgent(Agent):
        def __init__(self):
            super().__init__(
                instructions=node.instruction.text,
                tools=tools
            )
    
    GeneratedAgent.__name__ = f"Agent_{node.id}"
    return GeneratedAgent
```

### 3. Conversation Simulator

Extends LiveKit's turn-by-turn test framework with autonomous conversation generation.

**Key addition**: LiveKit's test framework requires manual `user_input` per turn. We add a simulator LLM that generates user messages based on Retell's test case format:

```markdown
## Identity
Your name is Mike. Order number: 7891273.

## Goal
Return package and get refund.

## Personality
Patient but becomes frustrated if unresolved.
```

**Conversation loop**:
```python
async def run_simulated_conversation(
    entry_agent: Agent,
    test_case: TestCase,
    llm: LLM
) -> ConversationResult:
    
    simulator = UserSimulator(test_case.user_prompt)
    node_tracker = NodeTracker()
    
    async with AgentSession(llm=llm) as session:
        await session.start(entry_agent)
        
        transcript = []
        
        for turn in range(test_case.max_turns):
            # Simulator generates user message
            sim_response = await simulator.generate(transcript)
            if sim_response.should_end:
                break
            
            # Execute through LiveKit
            result = await session.run(user_input=sim_response.message)
            
            # Track events
            transcript.append({"role": "user", "content": sim_response.message})
            for event in result.events:
                transcript.append(event_to_message(event))
                if is_handoff(event):
                    node_tracker.record(event.new_agent_id)
            
            if agent_ended_call(result):
                break
        
        return ConversationResult(
            transcript=transcript,
            nodes_visited=node_tracker.visited,
            ...
        )
```

### 4. Judges

Evaluate conversation transcript against success criteria.

**Judge types**:

| Type | Description | Implementation |
|------|-------------|----------------|
| Metric | Retell-style criteria ("Customer got refund") | DSPy signature on full transcript |
| LiveKit | Use LiveKit's `.judge()` on individual messages | Native LiveKit assertion |
| Flow | Validate node traversal, required nodes | Check node_tracker |
| Tool | Validate function calls | Check transcript for tool events |

**Combining LiveKit assertions with conversation-level evaluation**:
```python
# Per-turn assertions (LiveKit native)
result.expect.next_event().is_message(role="assistant")
await result.expect.next_event().judge(llm, intent="Greeting is friendly")

# Conversation-level evaluation (our addition)
for metric in test_case.metrics:
    passed = await metric_judge.evaluate(full_transcript, metric)
```

### 5. Test Runner

Orchestrates the full flow.

```python
async def run_test(retell_config: RetellConfig, test: TestCase) -> TestResult:
    # Convert Retell → LiveKit
    agents = convert_retell_to_livekit(retell_config)
    entry_agent = agents[retell_config.start_node_id]
    
    # Setup mocks
    mock_responses = test.function_mocks or {}
    
    # Run conversation
    with mock_tools(entry_agent, mock_responses):
        result = await run_simulated_conversation(
            entry_agent=entry_agent(),
            test_case=test,
            llm=dspy.LM("openai/gpt-4o-mini")
        )
    
    # Evaluate metrics
    metric_results = []
    for metric in test.metrics:
        evaluation = await metric_judge.evaluate(result.transcript, metric)
        metric_results.append(evaluation)
    
    # Check flow constraints
    flow_violations = check_flow_constraints(
        visited=result.nodes_visited,
        required=test.required_nodes,
        forbidden=test.forbidden_nodes
    )
    
    return TestResult(
        test_id=test.id,
        status="pass" if all_passed(metric_results, flow_violations) else "fail",
        transcript=result.transcript,
        metric_results=metric_results,
        nodes_visited=result.nodes_visited,
        constraint_violations=flow_violations,
        ...
    )
```

## Data Models

### Test Case (Retell-compatible)

```python
@dataclass
class TestCase:
    id: str
    name: str
    
    # User simulation (Retell format)
    user_prompt: str          # Identity/Goal/Personality markdown
    user_model: str = "gpt-4o-mini"
    
    # Evaluation
    metrics: list[str]        # Criteria strings
    
    # Constraints
    max_turns: int = 20
    required_nodes: list[str] | None = None
    forbidden_nodes: list[str] | None = None
    
    # Tool mocking (for LiveKit mock_tools)
    function_mocks: dict[str, Any] | None = None
```

### Test Result

```python
@dataclass
class TestResult:
    test_id: str
    test_name: str
    status: Literal["pass", "fail", "error"]
    
    transcript: list[Message]
    metric_results: list[MetricResult]
    
    # Flow tracking
    nodes_visited: list[str]      # Agent IDs (mapped back to Retell node IDs)
    tools_called: list[ToolCall]
    constraint_violations: list[str]
    
    turn_count: int
    duration_ms: int
    end_reason: str
```

## File Structure

```
voicetest/                         # Project root
├── pyproject.toml
├── README.md
├── voicetest/                     # Package (flat layout)
│   ├── __init__.py
│   ├── api.py                     # Core API (the interface)
│   ├── cli.py                     # CLI (thin wrapper over api)
│   ├── formatting.py              # Shared formatting utilities
│   ├── runner.py                  # Test runner context
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── agent.py               # AgentGraph, AgentNode, Transition (IR)
│   │   ├── test_case.py           # TestCase, RunOptions
│   │   └── results.py             # TestResult, TestRun, MetricResult
│   │
│   ├── importers/
│   │   ├── __init__.py
│   │   ├── base.py                # SourceImporter protocol
│   │   ├── registry.py            # Importer discovery/registration
│   │   ├── retell.py              # Retell JSON importer
│   │   └── custom.py              # Python function importer
│   │
│   ├── exporters/
│   │   ├── __init__.py
│   │   ├── livekit_codegen.py     # Generate LiveKit Agent Python code
│   │   └── graph_viz.py           # Mermaid/DOT graph export
│   │
│   ├── engine/
│   │   ├── __init__.py
│   │   ├── agent_gen.py           # AgentGraph → LiveKit Agent classes
│   │   └── session.py             # Conversation runner with LLM execution
│   │
│   ├── simulator/
│   │   ├── __init__.py
│   │   └── user_sim.py            # User LLM simulator (DSPy)
│   │
│   ├── judges/
│   │   ├── __init__.py
│   │   ├── metric.py              # Conversation-level metric judge
│   │   ├── flow.py                # Node traversal validator
│   │   └── tool.py                # Tool call validator
│   │
│   ├── tui/
│   │   ├── __init__.py
│   │   ├── app.py                 # Full TUI application
│   │   ├── shell.py               # Interactive shell
│   │   └── widgets.py             # Shared TUI widgets
│   │
│   └── generic_tests/
│       ├── __init__.py
│       ├── greeting.py
│       ├── hangup.py
│       └── adversarial.py
│
├── tests/
│   ├── conftest.py
│   ├── unit/                      # Unit tests (mirror voicetest/ structure)
│   │   ├── conftest.py
│   │   ├── fixtures/
│   │   │   └── retell/
│   │   │       ├── sample_config.json
│   │   │       └── sample_tests.json
│   │   ├── models/
│   │   │   ├── test_agent.py
│   │   │   ├── test_test_case.py
│   │   │   └── test_results.py
│   │   ├── importers/
│   │   │   ├── test_base.py
│   │   │   ├── test_registry.py
│   │   │   ├── test_retell.py
│   │   │   └── test_custom.py
│   │   ├── engine/
│   │   │   ├── test_agent_gen.py
│   │   │   └── test_session.py
│   │   ├── simulator/
│   │   │   └── test_user_sim.py
│   │   ├── judges/
│   │   │   ├── test_metric.py
│   │   │   ├── test_flow.py
│   │   │   └── test_tool.py
│   │   ├── test_api.py
│   │   ├── test_cli.py
│   │   ├── test_formatting.py
│   │   └── test_integration.py
│   │
│   └── integration/               # Integration tests (real LLM)
│       └── test_ollama.py
│
└── docs/
    ├── M1_SPEC.md
    ├── M2_SPEC.md
    └── RESEARCH.md
```

## Dependencies

```toml
[project]
name = "voicetest"
dependencies = [
    "livekit-agents>=1.0",
    "livekit-plugins-openai>=1.0",
    "livekit-plugins-silero>=1.0",
    "dspy>=2.6",
    "pydantic>=2.0",
    "click>=8.0",
    "rich>=13.0",
]

[project.optional-dependencies]
api = [
    "fastapi>=0.115",
    "uvicorn>=0.32",
]
parquet = [
    "pyarrow>=18.0",
]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
]
all = ["voicetest[api,parquet,dev]"]

[project.scripts]
voicetest = "voicetest.cli:main"
```

## CLI Interface

```bash
# Run tests (auto-detect source type from file)
voicetest run --config agent.json --tests tests.json

# Explicit source type
voicetest run --source retell --config agent.json --tests tests.json
voicetest run --source vapi --config assistant.json --tests tests.json

# Run specific test
voicetest run --config agent.json --tests tests.json --test-id customer_returns

# Verbose output (shows conversation flow, LLM calls)
voicetest run --config agent.json --tests tests.json -v

# Output formats
voicetest run --config agent.json --tests tests.json -o results.json
voicetest run --config agent.json --tests tests.json -o results.parquet

# Export to LiveKit (code generation)
voicetest export --config agent.json --format livekit -o agents/

# Export graph visualization
voicetest export --config agent.json --format mermaid -o graph.md

# Run generic tests
voicetest generic --config agent.json --tests greeting,hangup

# List available importers
voicetest importers

# Start API server (for Web UI)
voicetest serve --port 8080
```

## Output Format

### Stdout (default)

```
voicetest v0.1.0

Importing agent config...
  Source: retell (auto-detected)
  Nodes: 5 (greeting, verify_identity, billing, support, end_call)
  Entry: greeting

Converting to execution model...
  ✓ greeting → Agent_greeting (3 transitions)
  ✓ verify_identity → Agent_verify_identity (2 transitions)
  ✓ billing → Agent_billing (1 transition)
  ✓ support → Agent_support (1 transition)
  ✓ end_call → Agent_end_call (0 transitions)

Running 3 tests...

✓ customer_returns_package (12 turns, 8.3s)
  Flow: greeting → verify_identity → handle_return → process_refund → end_call
  ✓ Customer successfully returned the package
  ✓ Refund was processed
  ✓ Agent remained professional

✗ angry_customer_escalation (8 turns, 5.1s)
  Flow: greeting → verify_identity → billing → end_call
  ✓ Agent remained calm
  ✗ Customer was transferred to supervisor
    → Expected node 'supervisor' not visited

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Results: 2 passed, 1 failed
```

## Week 1 Deliverables

1. **Project setup**: pyproject.toml, directory structure, LiveKit dependencies
2. **models/agent.py**: AgentGraph, AgentNode, Transition (internal IR)
3. **models/test_case.py**: TestCase, RunOptions models
4. **models/results.py**: TestResult, TestRun, MetricResult models
5. **importers/base.py**: SourceImporter protocol
6. **importers/registry.py**: Importer discovery and auto-detection
7. **importers/retell.py**: Retell JSON → AgentGraph
8. **importers/custom.py**: Python function → AgentGraph
9. **api.py**: Core API stubs (`import_agent`, `list_importers`)
10. **Basic test**: Import sample Retell config via api, verify AgentGraph structure

## Week 2 Deliverables

1. **engine/agent_gen.py**: AgentGraph → LiveKit Agent classes
2. **engine/session.py**: Conversation loop wrapping AgentSession
3. **simulator/user_sim.py**: User persona simulator (DSPy)
4. **judges/metric.py**: Conversation-level metric judge
5. **judges/flow.py**: Node traversal validation
6. **api.py**: Complete `run_test`, `run_tests` implementation
7. **Integration test**: End-to-end via api.run_tests() with sample Retell config

## Week 3 Deliverables

1. **cli.py**: Full CLI implementation with source auto-detection
2. **exporters/livekit_codegen.py**: Generate Python code from AgentGraph
3. **exporters/graph_viz.py**: Mermaid export for visualization
4. **generic_tests/**: Built-in test cases
5. **Output formatting**: Rich console output, JSON export
6. **Documentation**: README, examples
7. **Test suite**: Comprehensive tests for importers and engine

## Handling Retell-Specific Features

### Equation Conditions
Retell supports `type: equation` conditions like `{{user_age}} > 18`. These are evaluated deterministically before prompt conditions.

**Implementation**: Check equation conditions first in agent's tool selection logic, or generate separate tools with strict guards.

### Dynamic Variables
Retell uses `{{variable}}` syntax in prompts and conditions.

**Implementation**: Pass variables through LiveKit's `userdata` or `RunContext`.

### Knowledge Bases
Retell's `knowledge_base_id` enables RAG.

**M1**: Skip or mock. Document as limitation.
**Future**: Integrate with LiveKit's external data / RAG patterns.

### Function Nodes
Retell function nodes call external APIs.

**Implementation**: Convert to LiveKit tools. Use `mock_tools` for testing.

## Fidelity Considerations

The execution engine produces behavior that **approximates** source platform behavior. Differences may occur because:

1. **Different LLM routing**: Each platform has proprietary transition evaluation logic
2. **Timing**: Platforms differ in when transitions are evaluated (after function results, after user done speaking, etc.)
3. **Proprietary features**: Undocumented optimizations and behaviors

**Mitigation**:
- Test against known transcripts from source platform to calibrate
- Allow tuning of tool descriptions to improve fidelity
- Document known behavioral differences per importer

**Note**: Perfect fidelity would require access to each platform's source code or detailed behavioral specifications. The goal is "close enough for useful testing" not "bit-for-bit identical."

## Success Criteria

M1 is complete when:
1. Can load Retell Conversation Flow export via `retell` importer
2. Can define custom agents via Python function (escape hatch)
3. Converts any imported agent to working LiveKit execution
4. Runs autonomous simulated conversations via AgentSession
5. Evaluates against test cases with pass/fail + reasoning
6. CLI works: `voicetest run --config X --tests Y`
7. JSON output is structured for future API consumption
8. Code is organized to cleanly add Vapi importer in M2

## Future (M2+)

### M2: Web UI + Vapi Support
- **Web UI**: Next.js + shadcn dashboard for test management
- **API Server**: FastAPI backend wrapping core library  
- **Vapi Importer**: Parse Vapi Assistant/Squad JSON
- **Run Persistence**: SQLite/Postgres for storing runs and results
- **Graph Visualization**: Interactive node graph in UI

### M3: Advanced Features
- **LiveKit Native Importer**: Introspect Python Agent classes via decorators
- **DSPy Optimization**: Tune judge prompts for accuracy using labeled examples
- **Parallel Test Execution**: Run multiple tests concurrently
- **Voice Testing**: Full audio pipeline via LiveKit (not just text simulation)
- **CI/CD Helpers**: GitHub Actions integration, PR comments with results

### M4: Platform Features
- **Multi-tenant**: Support teams/projects
- **Scheduled Runs**: Cron-based regression testing
- **Alerting**: Slack/email on test failures
- **Analytics**: Metrics dashboard, trend analysis
- **Bidirectional Sync**: Export back to Retell/Vapi format
