# voicetest Research Notes

Background research informing design decisions.

______________________________________________________________________

## OSS Voice Agent Testing Landscape

### voice-lab (saharmor/voice-lab)

Apache 2.0 licensed testing framework. 159 stars.

**What it does:**

- Text-only testing of LLM + prompt combinations
- Custom metrics via JSON + LLM-as-judge
- Model comparison (e.g., GPT-4 vs GPT-4-mini)
- Persona-based simulation

**What it lacks:**

- No workflow/conversation flow support
- No Retell/Vapi/LiveKit format compatibility
- No node traversal validation
- No multi-turn conversation orchestration

**Conclusion:** Good for prompt iteration, not for workflow testing.

### LiveKit Agents Test Framework

Built into livekit-agents SDK.

**What it does:**

```python
async with AgentSession(llm=llm) as sess:
    await sess.start(MyAgent())
    result = await sess.run(user_input="Hello")
    result.expect.next_event().is_message(role="assistant")
    await result.expect.next_event().judge(llm, intent="should ask what user wants")
```

**Characteristics:**

- Turn-by-turn (not autonomous simulation)
- Per-turn assertions and LLM judging
- Requires LiveKit Agent implementation
- No support for external configs (Retell/Vapi)

**Conclusion:** Good for LiveKit-native agents, not for cross-platform testing.

______________________________________________________________________

## Commercial Voice Agent Testing Tools

| Tool           | Approach                                          | Platforms            | Pricing    |
| -------------- | ------------------------------------------------- | -------------------- | ---------- |
| **Hamming AI** | Auto-generates tests, two-step LLM evaluation     | Vapi, Retell, 11Labs | $400+/mo   |
| **Coval**      | Langfuse integration, simulation                  | Custom               | Enterprise |
| **Maxim AI**   | Full platform (simulation + eval + observability) | Custom               | Enterprise |
| **Cekura**     | Auto-generates scenarios from agent description   | Custom               | Unknown    |
| **Roark**      | Voice-specific latency + ASR quality testing      | Custom               | Enterprise |

**Key insight from Hamming:** 95-96% agreement with human evaluators using two-step pipeline:

1. Extract facts from transcript
1. Judge against criteria using extracted facts

______________________________________________________________________

## Platform Testing Approaches

### Retell Simulation Testing

Built-in dashboard feature.

**Test case format:**

```markdown
## Identity
Your name is Mike.
Your date of birth is June 10, 1999.
Your order number is 7891273.

## Goal
Your primary objective is to return the package you received and get a refund.

## Personality  
You are a patient customer. However, if the conversation becomes too long 
or complicated, you will show signs of impatience.
```

**Metrics:** Numbered criteria evaluated by LLM after conversation completes.

**Limitations:**

- Dashboard-only (no API)
- No CI/CD integration
- No cross-platform testing

### Vapi Evals

API-based testing framework.

**Judge types:**

- `exact` — String match
- `regex` — Pattern match
- `ai` — LLM judge with custom prompt

**Features:**

- Mock conversations via API
- Tool call validation
- `continuePlan` for flow control (exit on failure, override responses)
- Squad handoff testing

**Test structure:**

```json
{
  "messages": [
    {"role": "user", "content": "Hello"},
    {"role": "assistant", "judgePlan": {"type": "regex", "content": ".*help.*"}}
  ]
}
```

**Limitation:** Turn-by-turn scripting, not autonomous simulation.

**Implementation (v0.1):** VAPI importer and exporter added:

- `voicetest/importers/vapi.py` — Imports VAPI assistant JSON
- `voicetest/exporters/vapi.py` — Exports AgentGraph to VAPI format

VAPI assistants are single-node (no multi-state workflow like Retell CF). The importer extracts:

- System prompt from `model.messages`
- Tools from the function-style tool array
- Voice/transcriber configuration as metadata

Key format differences from Retell:

- Tools use `{type: "function", function: {name, description, parameters}}` structure
- System prompt in `model.messages` array vs `general_prompt` field
- No state machine support (single assistant per config)

______________________________________________________________________

## DSPy vs BAML Analysis

### BAML Strengths

- Schema-aligned parsing (SAP) — recovers from minor formatting errors
- ~300 fewer prompt tokens than JSON schema
- 2-4x faster than OpenAI function calling
- Type-safe structured outputs

### DSPy Strengths

- Prompt optimization (GEPA, MIPROv2)
- LiteLLM integration for provider flexibility
- Composable signatures
- Assertions and metrics built-in

### DSPy + BAML Together

```python
from dspy.adapters.baml_adapter import BAMLAdapter

llm = dspy.LM("openai/gpt-4o-mini")
dspy.configure(lm=llm, adapter=BAMLAdapter())
```

BAML adapter uses BAML's prompting format inside DSPy, getting benefits of both.

**Decision:** Use DSPy with BAMLAdapter for judges. Enables prompt optimization while getting efficient structured outputs.

**Implementation (v0.1):** BAMLAdapter is configured globally in `api.py`:

```python
import dspy
from dspy.adapters.baml_adapter import BAMLAdapter
dspy.configure(adapter=BAMLAdapter())
```

Benefits observed:

- ~5% reliability improvement for structured output parsing
- Better performance with smaller models (important for cost efficiency)
- Token-efficient prompting

______________________________________________________________________

## LiveKit Plugin Architecture (Background)

### Core Plugin Model

Abstract base classes for STT, TTS, LLM, VAD:

```python
class CustomTTS(tts.TTS):
    async def synthesize(self, text: str) -> AsyncGenerator[SynthesizedAudio, None]:
        ...
```

### Available Plugins (48+)

- **LLM:** OpenAI, Anthropic, Google, Mistral, Groq, Cerebras, Azure
- **STT:** Deepgram, AssemblyAI, Google, OpenAI Whisper, Azure
- **TTS:** Cartesia, ElevenLabs, Rime, OpenAI, Google, Azure
- **VAD:** Silero (default)

### AgentSession

Orchestrates STT → LLM → TTS pipeline with turn detection.

Key for voicetest: AgentSession works in **text-only mode** — no audio pipeline required for testing. Pass `user_input` string directly.

______________________________________________________________________

## Platform Transition Model Equivalence

All three platforms use LLM-based transition evaluation:

| Platform    | Transition Mechanism                                      |
| ----------- | --------------------------------------------------------- |
| **Retell**  | LLM evaluates edge condition prompts                      |
| **Vapi**    | LLM decides tool calls / squad transfers                  |
| **LiveKit** | LLM calls tools that return `(Agent, str)` handoff tuples |

**Implication:** Can model all as "LLM decides when to call transition tool" → unified execution via LiveKit AgentSession with generated tools per transition.

______________________________________________________________________

## Fidelity Considerations

Execution engine **approximates** source platform behavior. Expected differences:

1. **LLM routing** — Each platform has proprietary logic for when/how transitions are evaluated
1. **Timing** — When transition conditions are checked relative to response generation
1. **Prompt wrapping** — Undocumented system prompts added by platforms
1. **Tool call formatting** — Subtle differences in how tools are presented to LLM

**Mitigation strategy:**

- Test against known transcripts from production
- Allow tuning tool descriptions in test config
- Document behavioral differences per importer
- Accept "close enough for useful testing" not "bit-for-bit identical"

______________________________________________________________________

## Key Research Conclusions

1. **No good OSS option exists** for testing voice agent workflows across platforms

1. **Retell's Identity/Goal/Personality format** is a good simulation prompt structure — widely understood, easy to author

1. **DSPy with BAMLAdapter** is optimal for judges — combines optimization with efficient structured outputs

1. **LiveKit AgentSession** can serve as execution engine even for non-LiveKit agents — text-only mode, no infrastructure dependency

1. **Autonomous simulation** (not turn-by-turn scripting) is the key differentiator — matches how Retell does it, more realistic testing

1. **Platform transition models are functionally equivalent** — all reducible to "LLM calls tools to trigger transitions"

______________________________________________________________________

## Implementation Architecture Decisions

### Dependency Injection (Punq)

After evaluating FastAPI Depends vs dedicated DI containers, chose **Punq** for:

- Lightweight (~200 LOC)
- No decorator pollution
- Works cleanly with FastAPI without coupling
- Scope support (singleton for ImporterRegistry)

Container setup in `voicetest/container.py`:

```python
import punq

def create_container() -> punq.Container:
    container = punq.Container()
    container.register(ImporterRegistry, factory=_create_registry, scope=punq.Scope.singleton)
    container.register(AgentRepository, factory=lambda: AgentRepository(get_connection()))
    # ... other registrations
    return container
```

Usage pattern:

```python
from voicetest.container import get_container
repo = get_container().resolve(AgentRepository)
```

### Async Pattern for Blocking LLM Calls

DSPy predictor calls are synchronous and block the event loop. This caused WebSocket connection delays during test execution.

**Solution:** Wrap all DSPy calls in `asyncio.to_thread()`:

```python
async def _evaluate_with_llm(self, transcript, criterion, threshold) -> MetricResult:
    def run_predictor():
        with dspy.context(lm=lm):
            predictor = dspy.Predict(MetricJudgeSignature)
            return predictor(transcript=..., criterion=...)

    result = await asyncio.to_thread(run_predictor)
    return MetricResult(...)
```

Applied to:

- `voicetest/judges/metric.py` — MetricJudge
- `voicetest/judges/flow.py` — FlowJudge
- `voicetest/simulator/user_sim.py` — UserSimulator
- `voicetest/engine/session.py` — Agent LLM calls

### Score-Based Metric Evaluation

Instead of binary pass/fail, judges return a 0-1 score with configurable threshold:

```python
class MetricResult(BaseModel):
    metric: str
    score: float           # 0-1 how well criterion was met
    passed: bool           # Derived: score >= threshold
    reasoning: str
    threshold: float       # Threshold used for this evaluation
    confidence: float | None
```

Benefits:

- Nuanced evaluation (0.65 vs 0.35 both "fail" but very different)
- Configurable per-agent and per-metric thresholds
- Better visibility into near-misses

### Global Metrics Architecture

Global metrics stored as `metrics_config` column in agents table (not inside `graph_json`):

```python
class MetricsConfig(BaseModel):
    threshold: float = 0.7
    global_metrics: list[GlobalMetric] = Field(default_factory=list)
```

Rationale:

- Works with both linked and imported agents
- Original agent definition files remain unmodified
- Keeps all metrics configuration together
- Enables per-metric threshold overrides
