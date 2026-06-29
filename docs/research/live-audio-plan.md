# Live audio duplex testing — implementation plan

Sequenced build plan for the "Live audio duplex testing (cascade + speech-to-speech)"
proposal in [proposals.md](proposals.md). Scoped to the LiveKit beachhead. Written to be
picked up incrementally; each step is independently shippable and test-first.

## Implementation status

- **Step 1 — schema** (`AudioMetadata`, `source_kind`, migration #4): implemented, unit +
    integration tested. The legacy flat `metadata["heard"]` convention was migrated to the
    `AudioMetadata` sub-model across the producer (`util/audio.py`) and both judge consumers
    (`rule.py`, `metric.py`); the accessor keeps a legacy-flat read fallback for already-persisted
    transcripts.
- **Step 2 — `VoiceParticipant`**: implemented, tested. Three duplicated `AgentSession` blocks in
    `agent_worker.py` collapsed into `CascadeParticipant`. `RealtimeParticipant` is named provisional
    in the Protocol, not built.
- **Step 3 — observer**: `ObserverTranscript` (`livecall/observer.py`) and `AudioObserver`
    (`livecall/audio_observer.py`) implemented and tested at three tiers — unit (fake `SpeechEvent`
    streams), and a **real-room e2e** (`tests/integration/test_observer_e2e.py`) that publishes
    Kokoro-synthesized speech into a live LiveKit room, observes the subscribed track via
    `rtc.AudioStream` + a VAD-wrapped whisper STT, and asserts the observed transcript. Verified
    green against a local LiveKit + whisper + kokoro stack. The stack is codified for local + CI:
    `scripts/services.sh` (up/down) and a `livecall-integration` job in `.github/workflows/test.yml`.
    - **Contract learned**: livekit's `openai.STT` is non-streaming for whisper, so `observe_track`
        requires a stream-capable STT — the caller supplies `stt.StreamAdapter(stt=whisper, vad=silero)`.
    - **Integration point (finding)**: the observer pairs with a **caller-side worker that observes a
        remote agent**, not the current cascade `agent_worker`. In `agent_worker` the agent runs locally
        via `AgentSession`, which already emits the caller's STT — observing remote audio there would
        duplicate that signal, and the genuinely-new assistant-`heard` needs the agent's *own* published
        track (not cleanly exposed). For a deployed S2S agent (the motivating case) voicetest is the
        caller and the agent is the opaque remote track — exactly what `observe_track` consumes. The
        wiring therefore lands with the deferred caller worker (see [Out of scope](#out-of-scope-fast-follow)),
        which is where it is correct and non-duplicating.
- **Pre-existing blocker fixed**: `livecall/livekit_adapter.py` used the pre-1.0 symbol
    `livekit.agents.llm.Tool` (removed in 1.x; now `FunctionTool | RawFunctionTool`), which made the
    whole live-call subsystem non-importable on the installed `livekit-agents 1.1.7` (the latest
    stable; `>=1.2` is pre-release only). Fixed the annotation + added `from __future__ import annotations`. Subsystem now imports.
- **Pre-existing test-fixture bug (not fixed — unrelated)**: `tests/integration/test_calls.py`
    `simple_graph` builds an `AgentGraph` node missing the now-required `node_type` field (added in
    `46db942`), so `TestAgentWorkerSubprocess::test_agent_worker_starts_and_outputs_status` errors at
    setup. Independent of this work.

## What already exists (do not rebuild)

The proposal's "Shared groundwork → canonical transcript schema" is **already partly built**.
Confirmed against the tree:

- **Canonical schema** = `Message` (`voicetest/models/results.py:11`). Has `role`, `content`,
    optional `timestamp`, open `metadata` dict. No schema surgery needed.
- **Per-platform normalizer pattern** already established at `voicetest/importers/transcripts/`
    (Retell only today: `retell.py`). New sources slot in here.
- **Observer-transcript seam** already seeded: `rule.py:92` reads `metadata.get("heard", content)`.
    This is the `content` (intended) vs `heard` (observed) divergence the proposal generalizes.
- **Audio-metrics landing pad** already present: `TestResult.audio_metric_results` (`results.py:64`),
    currently always empty.
- **Replay/regression mode is shipped** (v0.41). The proposals-doc note that it "is being
    implemented separately" is stale.
- **Source marker**: `status="imported"` is the de-facto discriminator; no `source_kind` column.

Net: the foundation is mostly here. The new work is the **participant abstraction** and the
**observer STT sidecar** — not a schema. The full duplex vertical (synthetic caller worker +
audio-only metrics) and any real S2S backend are deferred (see
[Out of scope](#out-of-scope-fast-follow)).

## Scope decision — S2S is designed-for, not built

A real S2S backend is **not** in this scope. The honest reason it was considered and then cut:
the `VoiceParticipant` interface cannot be *fully validated* for S2S without running a real
audio-to-audio model through it, and that pulls in a provider (OpenAI Realtime — already a dep
via `livekit-plugins-openai`, or a local true-S2S model) plus the duplex infra to drive it.
That is more than this slice should carry.

The deliberate consequence: Step 2 extracts the abstraction from **cascade only** — one real
implementation — and **designs the S2S seam against the documented Realtime API shape** (no
separable LLM, no intended-text channel, optional native transcript) without building it.
The interface is therefore **provisional for S2S** and is expected to change when the first
real `RealtimeParticipant` lands. Designing the seam now is cheap; validating it now is not.

## Resolved decisions

These were the open forks; resolutions are baked into the steps below.

1. **`source_kind` — add an explicit field, not an overloaded `status`.** Two layers:
    - Pydantic: a `source_kind: Literal["simulated", "live", "imported"]` field on `TestResult`
        (`voicetest/models/results.py:56`).
    - ORM: a `source_kind` `String` column on `Result` (`voicetest/storage/models.py:159`),
        with a default + migration backfilling existing rows (treat existing `status="imported"`
        rows as `source_kind="imported"`).
    - **Storage of live results — resolved: reuse `Result`** (`source_kind="live"`, `call_id`
        set), not a `Call`-only path. The existing `RunsView` renders it with no extra UI work, and
        `Result.call_id` already links back to the `Call` row.
1. **Audio metadata — a typed sub-model nested under `metadata`, not flat loose keys and not a
    parallel dict.** Keep `Message.metadata: dict[str, Any]` open for the existing import keys,
    but define a typed Pydantic sub-model (`AudioMetadata` with `heard`, `latency_ms`,
    `audio_ref`) that round-trips into a single reserved key (`metadata["audio"]`). Groups the
    audio fields, stays type-checked, and leaves the Retell importer's existing keys untouched.
1. **Observer e2e — resolved: cover with a single-participant real-audio fixture now**
    (agent-only track, no synthetic caller). Exercises real STT through the observer without the
    deferred duplex infra, keeping all three test tiers without a skip authorization.

One fork remains deferred rather than resolved — see
[Follow-up issues](#follow-up-issues-review-after-steps-13).

______________________________________________________________________

## Step 1 — Formalize transcript `metadata` conventions (shared foundation)

**Goal.** A typed home for the audio/observer fields that ride alongside a `Message`, plus an
explicit `source_kind` discriminator. Covers both the existing import path and the future
observer path without a parallel schema.

- **`AudioMetadata` sub-model** (decision 2). A Pydantic sub-model with `heard` (observed text),
    `latency_ms` (time-to-first-audio for the turn), `audio_ref` (pointer to captured audio). It
    round-trips into a single reserved key, `metadata["audio"]`. `Message.metadata` stays
    `dict[str, Any]` so the Retell importer's existing keys (`call_id`, `duration_ms`,
    `end_reason`, `turn_count`) are untouched. Read `voicetest/importers/transcripts/retell.py`
    first so the audio sub-model sits beside that vocabulary, not on top of it.
- **`source_kind` field** (decision 1). Add to both layers — `Literal` on `TestResult`
    (`models/results.py:56`) and a `String` column on `Result` (`storage/models.py:159`) with a
    default + a migration backfilling existing `imported` rows. Decide here whether live results
    reuse `Result` (lean: yes, with `call_id` set) or ride the `Call` table.
- Add a typed accessor so the `heard` lookup in `rule.py:92` reads `metadata["audio"].heard`
    via the sub-model rather than a bare string key.

**Tests first.** Round-trip a `Message` carrying `AudioMetadata` through persistence; assert
`rule.py`'s `use_heard` path reads `heard` through the sub-model; assert the Retell importer
still emits its existing keys unchanged (regression guard); assert `source_kind` defaults and
the migration backfills `imported` rows.

**Risk.** Lowest. Pure convention + small refactor. No LiveKit server, no real-time cost.

______________________________________________________________________

## Step 2 — `VoiceParticipant` abstraction + builder

**Goal.** Extract the cascade `AgentSession` construction out of `agent_worker.py` into a
participant builder, and shape the interface so a future S2S participant slots in without a
redesign — without building one now.

- Today `agent_worker.py:164-200` hardcodes the cascade triple `AgentSession(stt=, llm=, tts=)`
    across three near-duplicate backend blocks (local/mlx/openai), each also hardcoding
    `allow_interruptions=False` (`:178`, `:190`, `:199`). This triplication is the seam.
- Introduce `VoiceParticipant` with **one shipped implementation**:
    - `CascadeParticipant(stt, llm, tts)` — white-box; can expose intended text (LLM output).
- **Design the seam for S2S, do not implement it.** The interface must not assume a separable
    `llm`, must treat intended-text as an *optional* capability (cascade has it; an S2S model
    would not), and must let observed transcript arrive from the observer regardless of
    architecture. A `RealtimeParticipant(model)` is named in the Protocol docstring as the
    planned second implementation and explicitly marked provisional — expected to adjust the
    interface when first built (see [Scope decision](#scope-decision--s2s-is-designed-for-not-built)).
- `agent_worker.py` builds its participant via this interface. Behavior must be identical for
    the cascade path (pure refactor).

**Interface discipline (how to "get the abstraction correct" without a second impl).** Use the
documented OpenAI Realtime / Gemini Live shape as a *design checklist*, not a built backend:
each capability cascade relies on (separable LLM, intended text, swappable STT/TTS) must be
expressed as an optional/duck-typed seam, not a hard assumption, so the known S2S constraints
are first-class in the type signatures even though no S2S code ships.

**Tests first.** Characterization test that the cascade builder produces an equivalent
`AgentSession` for each of the three backends before refactoring; then refactor to green.
Add an interface-contract test asserting consumers do not hard-depend on intended-text being
present (guards the S2S seam).

**Note / honest constraint.** `CascadeParticipant` drives the shared engine, preserving the
"tests and live calls behave identically" invariant (`agent_worker.py:6-7`). A future
`RealtimeParticipant` **necessarily breaks** that invariant — no text brain to share. That is
correct and expected: it is what testing a deployed S2S agent looks like. Document it on the
Protocol now so the seam is understood before it is filled.

**Risk.** Medium. Refactor of live-call hot path; the characterization tests are the safety net.
The S2S seam carries design risk (unvalidated until built) — accepted per the scope decision.

______________________________________________________________________

## Step 3 — Observer STT sidecar

**Goal.** Transcribe each track's *actually published audio* into canonical `Message`s, so
judges grade the wire regardless of either side's architecture.

- Sidecar subscribes to each participant's published audio track and emits `Message`s with the
    `AudioMetadata` sub-model populated (`heard`, `audio_ref`, `latency_ms` from step 1).
- **Current driver is cascade**: a cascade turn carries both `content` (intended) and `heard`
    (observed). This generalizes the existing `audio_eval` content-vs-heard comparison
    (`voicetest/util/audio.py`) into the live path.
- **Designed for S2S payoff**: a future S2S participant emits `heard` only (no intended text).
    Because the observer derives `heard` from the published audio independent of architecture, an
    S2S participant needs **no observer change** — the analyst reads observed text instead of
    replaying audio. This is the future payoff of the design, not a current deliverable.
- Judges are unchanged — they already read the `heard` fallback.

**Tests first.** Feed a known audio clip through the sidecar, assert the emitted `Message`
carries `heard` and the audio ref; assert a cascade turn carries both `content` and `heard`.
**e2e (resolved):** a single-participant real-audio fixture (agent-only track, no synthetic
caller) drives real STT through the observer end-to-end.

**Risk.** Medium. Real STT = nondeterministic transcripts. The judge-tolerance implication is
tracked as a follow-up (see [Follow-up issues](#follow-up-issues-review-after-steps-13)), not a
blocker for the sidecar itself.

______________________________________________________________________

## Sequencing summary

In scope = cascade live-audio plumbing + an S2S-ready abstraction, no real S2S backend and no
real-time-duplex infra cost.

| Step                                        | Net-new vs refactor         | Infra needed | Risk   |
| ------------------------------------------- | --------------------------- | ------------ | ------ |
| 1 — metadata conventions + `source_kind`    | small refactor + convention | none         | lowest |
| 2 — `VoiceParticipant` (cascade + S2S seam) | refactor of live-call path  | none         | medium |
| 3 — observer STT sidecar                    | net-new                     | STT          | medium |

Steps 1–3 land the cascade live-audio path and leave a clean, documented S2S seam, with no
real-time pacing or LiveKit-server cost. The real S2S backend and the synthetic-caller duplex
vertical are deferred.

## Follow-up issues (review after steps 1–3)

Track these; revisit once the steps above land, not before.

- **Judge tolerance for nondeterministic STT.** Real STT produces flaky transcripts, so
    substring matching in `RuleJudge` (`rule.py`) is brittle against `heard` text. Move to
    tolerance bands / semantic match for audio-mode judging. Low urgency: STT flakiness exists
    independent of S2S, and `RuleJudge` is used less than the LLM judges (`MetricJudge` /
    `FlowJudge`), which already tolerate paraphrase. Revisit when the observer transcript is real.

## Out of scope (fast-follow)

Ordered nearest-term first.

1. **First real `RealtimeParticipant` (S2S backend)** — fills the seam Step 2 leaves. This is
    what validates (and likely adjusts) the abstraction.
    - *Provider*: OpenAI Realtime is the cheapest first target — already a dependency
        (`livekit-plugins-openai`), battle-tested LiveKit `RealtimeModel` plugin, zero new deps,
        only API cost. It isolates "is the interface right" from "did the model bridge work."
    - *Local option, with eyes open*: true local S2S models exist (Moshi, GLM-4-Voice,
        Qwen2.5/3-Omni, Mini-Omni2), but none ships a mature LiveKit `RealtimeModel` plugin, and
        self-hosted *realtime* generation is still immature (optimized streaming "Talker" serving
        is the gap). A local backend therefore means writing a custom `RealtimeModel` adapter —
        worthwhile as the pass that proves the interface generalized beyond a cloud provider, but
        not the first move. A local *cascade* is easy (the `local`/`mlx` backends already exist)
        but does not exercise the S2S seam.
1. **Synthetic caller worker + audio-only metrics judge** (the real-time duplex vertical).
    - *Caller worker*: a second voicetest-controlled participant — mirror of `agent_worker.py`,
        inverted. Wrap `UserSimulator` behind `VoiceParticipant`; publish the caller's mic track,
        subscribe to the agent's audio; join both to one LiveKit room so WebRTC carries real audio
        both directions (STT/TTS/VAD/turn-taking real on both sides).
    - *Audio-only metrics*: latency-to-first-audio, barge-in respected (flip the hardcoded
        `allow_interruptions=False`), talk-over / dead-air duration; land in the existing
        `TestResult.audio_metric_results` slot (`results.py:64`).
    - *Why deferred*: needs a running LiveKit server + real-time pacing + cost.
1. Retell / VAPI / Bland / Telnyx live web-call clients. Their `voicetest/platforms/*.py`
    adapters are REST CRUD only today; each needs a live websocket client. One per platform.
1. PII redaction at ingest (tracked in the transcript-ingestion proposal).
