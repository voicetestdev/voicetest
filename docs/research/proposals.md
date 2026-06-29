# voicetest Proposals

Design notes for features under consideration. Not committed work; not on the public roadmap. Living document — expect entries to evolve, merge, or get deleted as we learn.

The first two entries push voicetest along the same axis — away from white-box transcript judging, toward **black-box behavioral verification**: grade on what actually went over the wire and what the agent actually did, not on the text it intended. They are otherwise independent (different layers: transport vs grading) and can ship in either order. The transcript-ingestion entries below them are an orthogonal track about getting real-world coverage into the suite; they share a canonical transcript schema with the live-audio work.

______________________________________________________________________

## Live audio duplex testing (cascade + speech-to-speech)

**Context.** The test loop today is text/transcript-level. `UserSimulator` (`voicetest/simulator/user_sim.py`) emits text, `ConversationRunner.run()` (`voicetest/engine/session.py:71`) drives the agent turn-by-turn, and the judges read the resulting transcript. Real audio only appears post-hoc via `AudioRoundTrip` (`voicetest/util/audio.py`) and in live calls (`voicetest/livecall/agent_worker.py`) — never inside a test. That leaves three things invisible that only audio exposes:

- **The agent's own ear.** The test hands the agent clean text, bypassing its real STT. Whether the agent mishears a real caller, and whether the flow survives the mishearing, is never tested.
- **Full-duplex behavior.** Barge-in, interruption handling, turn-taking, end-of-speech detection — the transcript loop is strictly half-duplex.
- **Latency.** Time-to-first-response has no transcript equivalent.

A peer org already runs exactly this kind of live-audio testing; the gap is real and externally validated.

**The enabling fact.** `agent_worker.py:147-152` already drives a real LiveKit `AgentSession` from a text engine by wrapping it as a LiveKit LLM (`VoicetestLLM`, `voicetest/livecall/livekit_adapter.py`). A live call has exactly one voicetest-controlled participant (the agent under test) and then waits for a human to join (`agent_worker.py:243`). The harness is: **run that same trick a second time for the caller** — wrap `UserSimulator` behind the same participant interface, join both to one room, and let WebRTC carry real audio in both directions. STT, TTS, VAD, and turn-taking are then real on both sides because LiveKit already does the duplex mechanics. Gaps above fall out of the transport.

Everything downstream is reused unchanged: `MetricJudge` / `RuleJudge` / `FlowJudge` consume the same `Message` list, persona/metrics config is identical, the AgentGraph IR is untouched. Only the transport layer is new.

### Must support cascade AND native speech-to-speech

The agent under test (and the caller) may be a **cascade** pipeline (STT → LLM → TTS) or a **native speech-to-speech (S2S)** model (OpenAI Realtime, Gemini Live, or a customer's own end-to-end model) where there is no separable LLM — audio in, audio out. The cascade triple `AgentSession(stt=, llm=, tts=)` currently hardcoded at `agent_worker.py:164-200` cannot represent S2S. Any new interface must treat cascade as one case, not the assumption.

**Design — grade on the wire, not the internals.**

- **`VoiceParticipant` abstraction**, used for both roles. Two implementations:
    - `CascadeParticipant(stt, llm, tts)` — white-box; can expose intended text (the LLM output).
    - `RealtimeParticipant(model)` — S2S; black-box, audio↔audio, exposes the model's own transcript channel if it has one, else nothing.
- **Observer STT sidecar** transcribes each track's *actual published audio* into canonical `Message`s. Judges grade on the observer transcript regardless of either side's architecture. The `metadata["heard"]` pattern (`voicetest/util/audio.py:78`) is the seed: cascade carries both `content` (intended) and `heard` (observed); S2S carries only `heard`. `Message` already has `timestamp` + `metadata` (`voicetest/models/results.py:11`), so this is metadata, not schema surgery. The divergence between `content` and `heard` *is* the existing `audio_eval` comparison, generalized.
- **White-box vs black-box becomes explicit.** Cascade agent → voicetest may still drive the shared engine (preserves the "tests and live calls behave identically" invariant, `agent_worker.py:6-7`). S2S agent → that invariant necessarily breaks (no text brain to share); voicetest is purely caller + observer + judge against an opaque endpoint — which is exactly what testing a deployed S2S agent looks like.
- **Audio-only metrics** (latency-to-first-audio, barge-in respected — flip `allow_interruptions`, hardcoded `False` at `agent_worker.py:199` — talk-over / dead-air duration) measure the wire, so they are architecture-independent and land in the existing `TestResult.audio_metric_results` slot (`voicetest/models/results.py:64`).

**Build order.**

1. **Phase 0** — `VoiceParticipant` + observer layer. Refactors the cascade `AgentSession` construction out of `agent_worker.py` into a participant builder (cascade or realtime).
1. **Phase 1** — caller worker on top of the participant interface (mirror of `agent_worker.py`, inverted: publishes the caller's mic, subscribes to the agent's audio).
1. **Phase 2** — audio-only metrics judge.

LiveKit-only beachhead first, because all the audio plumbing already lives in `voicetest/livecall/`. Retell/VAPI/Bland/Telnyx need per-platform **live web-call/websocket** clients — their `voicetest/platforms/*.py` adapters are REST CRUD only today — so they are a fast-follow, one per platform.

**Open risks.**

- **Nondeterminism.** Real STT means flaky transcripts; judges need tolerance bands / semantic match, not the substring matching `RuleJudge` does today. (This is partly the point — it's what's under test — but it changes the pass/fail contract.)
- **Infra + cost + wall-clock.** Needs a running LiveKit server and real-time-paced execution. Keep text mode the default fast path; audio mode is opt-in like `audio_eval`.

**Overlap.** Observer transcripts use the canonical transcript schema defined under [Real-call transcript ingestion → Shared groundwork](#shared-groundwork); audio metadata (latency, `heard` text, audio refs) is an extension of that schema, not a separate one.

______________________________________________________________________

## tau2-bench hard grading integration

**Context.** voicetest's judges (`voicetest/judges/metric.py`, `rule.py`, `flow.py`) all read the transcript — they score "did the conversation *sound* right?" Soft, LLM-judged, on the text the agent intended to say. tau2-bench grades *behavior*: did the agent call the right tool with the right arguments, does the simulated backend's end-state match ground truth, and **pass^k** (the same task run k times, scored on reliability rather than a single lucky pass). voicetest already records `ToolCall(name, arguments, result)` (`voicetest/models/results.py:20`) but never asserts on it against ground truth. That is the hole, and it's the opportunity — not speech.

This is the same philosophy as the live-audio entry above (verify behavior, not claims), applied to the grading layer instead of the transport layer.

### Shape 1 — methodology import (domain-independent; the product)

Add an **environment / state judge**: a stateful simulated backend that the agent's tool calls mutate, plus ground-truth assertions on the resulting end-state, plus **pass^k** reliability runs. This moves voicetest from "sounds right" to "provably did the right thing."

- **Hooks.** Existing `ToolCall` capture; new stateful tool backend the calls drive; new assertion layer over end-state; new pass^k aggregation over repeated `TestResult`s.
- **Honest cost.** Someone authors the environment + ground-truth per agent — the rigor *is* the ground-truth, there's no free lunch. tau2 ships both for its own domains; a custom agent needs them written.

### Shape 2 — agent-provider (domain-gated; the demo)

Write a `VoicetestAgentFactory` that wraps an AgentGraph (or a live Retell/VAPI endpoint) as a tau2 agent, register it through tau2's factory interface, and run `tau2 --domain X --agent voicetest` → a leaderboard-comparable score on the customer's own agent (e.g. *"your bot scores 0.71 pass^k on tau2-telecom"*).

- **Hard constraint.** Tool-surface alignment. tau2's domain tasks call tau2's domain tools; an arbitrary customer agent doesn't implement them. Works out-of-the-box only when the customer's domain ≈ a tau2 domain (retail support, telecom).
- **License.** tau2-bench is a sierra-research repo; permissive-license/vendoring status is unconfirmed. Flag before taking a dependency.

**Read.** Shape 1 is the durable differentiator (domain-independent behavioral grading); Shape 2 is a same-week demo when domains align. Pursue Shape 2 as a spike to validate the agent-provider plumbing; bank Shape 1 as the roadmap item.

**Weak link to the ingestion track below.** Test metrics synthesized from real transcripts (next section) could graduate from transcript criteria to environment-state assertions once Shape 1 exists.

______________________________________________________________________

## Real-call transcript ingestion

**Context.** Many prospective clients arrive with thousands of production call transcripts and zero test cases. Hand-writing a representative test suite is the bottleneck, and the bottleneck is what kills adoption — not the test runner itself. Three proposals below address different slices of this problem; they share a common ingestion + schema layer.

### Shared groundwork

Before either of these is buildable, voicetest needs:

- **A canonical transcript schema** — message list with `role` ∈ `{user, assistant, tool}`, content, optional timestamps, optional metadata (call duration, agent version, end reason, latency). All platform-specific shapes (Retell `call.transcript`, VAPI artifact, LiveKit egress, plain text) normalize into this. This is the same schema the live-audio harness's observer layer emits (see [Live audio duplex testing](#live-audio-duplex-testing-cascade--speech-to-speech)) — audio runs are just another source that normalizes into it, with `heard`-text and latency riding in `metadata`.
- **An ingest path** — single command/endpoint that accepts a directory of transcripts (one JSON per call, or one JSONL with many calls) and stores normalized records in the existing run/results storage. Reuse the existing `RunRecord`/`RunResultRecord` tables where possible; add a `source_kind` column distinguishing `simulated` from `live`.
- **PII hooks** — opt-in redaction pass during ingest (regex or LLM-based for names/phones/SSNs/emails/account numbers). Default off; clients with sensitive data flip it on. Out of scope for the first proposal pass but should be designed-for in the schema.

Persisting live calls in the same store as test runs lets the runs UI render them with the existing `RunsView` component — adjacent value with no extra UI work.

______________________________________________________________________

### Transcript-driven test case generation

**Problem.** A client has 10k production transcripts and 0 test cases. Hand-writing 50 hand-tuned cases takes a week and misses the long tail.

**Idea.** Cluster the transcript corpus into "caller types" by intent + persona signal, then synthesize one voicetest `TestCase` per cluster. The generated cases use the existing simulator + judge plumbing — they're not replay; they're synthesized personas grounded in real distributions.

**Pipeline.**

1. **Normalize.** Run all transcripts through the canonical schema.
1. **Embed + cluster.** Compute embeddings per transcript (or per opening 2–3 user turns, where intent is usually clearest). Cluster using HDBSCAN or k-means with silhouette-based k selection. Output: N clusters, each with a representative sample.
1. **Per cluster, extract a persona.** Prompt an LLM with the cluster's representative transcripts to fill the existing Identity / Goal / Personality template. Goal must be derivable from observed user behavior, not hallucinated.
1. **Per cluster, extract metrics.** From the cluster's transcripts, infer what "success" looks like for that caller type (e.g. "agent collected the account number and confirmed the refund"). Emit as `metrics` on the generated `TestCase`.
1. **Write `tests/generated/*.toml`** — one file per cluster, with provenance metadata (cluster id, sample size, source transcript ids).
1. **Open a PR-like review** — the user reviews/edits/discards before any case is "live."

**Hard parts.**

- **De-duplication vs coverage.** 10k transcripts may collapse into 30 clusters or 300 — picking the right granularity per client is fiddly. Probably needs an interactive knob ("merge clusters with similarity > X").
- **Goal extraction is the bottleneck.** "What did this caller want?" is often only clear after the agent figured it out. Conditioning the LLM on the full transcript helps, but risks generating goals biased toward what the agent (correctly or incorrectly) inferred.
- **Eval metrics are only as good as the corpus.** If production calls themselves are buggy, generated metrics inherit those bugs.

**Why it's high-leverage.** Replaces "write 50 cases over a week" with "review 30 generated cases over an hour." This is the moment a 10k-transcript client decides whether voicetest is worth the lift.

**Dependencies.** Builds on the shared ingestion + schema layer. Subsumes most of the coverage proposal below — clustering naturally surfaces "patterns the existing test suite doesn't cover."

______________________________________________________________________

### Coverage / gap analysis against an existing suite

**Problem.** A client has both production transcripts AND an existing voicetest suite. They want to know: "what real-world patterns am I not testing?" without auto-generating tests they didn't ask for.

**Idea.** Same ingest + clustering as the test-generation proposal above, but instead of generating test cases, emit a coverage report.

**Pipeline.**

1. **Normalize + cluster** (shared with the test-generation flow above).
1. **Embed existing test cases** (use their `user_prompt` + a synthetic transcript expansion).
1. **Match clusters to test cases.** For each transcript cluster, find the nearest test case in embedding space. If max similarity < threshold, the cluster is "uncovered."
1. **Render a coverage report.** Per-cluster:
    - Sample size (how often this pattern shows up in production)
    - Nearest existing test case + similarity score
    - 2–3 representative transcript snippets
    - "Generate test case from this cluster?" CTA (links into the test-generation flow above)

**Hard parts.**

- **Threshold choice.** "Similar enough to count as covered" is squishy. Probably ship with a tunable knob and good defaults rather than try to learn it.
- **Weighting matters.** A pattern that's 40% of production traffic but missing from the suite is far more important than a 0.1% edge case. Report should sort by traffic weight, not just by gap size.

**Why it's worth its own line.** Some clients explicitly don't want auto-generated test cases — they want to keep the suite hand-curated. For them, "show me what I'm missing" is the entire deliverable. Same plumbing as the test-generation flow, different output mode.

**Dependencies.** Reuses the shared ingestion + clustering. Independently shippable once that exists.

### Sequencing (transcript-ingestion track)

Build order if/when this comes off the proposals shelf (replay regression mode shipped in v0.41 and is not part of this sequence):

1. Shared ingest + canonical schema + storage.
1. Clustering primitive (used by both proposals below).
1. Coverage report — ships first because the output is just a report, no synthesis.
1. Test case synthesis — last, because "review N generated cases" UX needs more polish.
