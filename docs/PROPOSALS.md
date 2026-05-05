# voicetest Proposals

Design notes for features under consideration. Not committed work; not on the public roadmap. Living document — expect entries to evolve, merge, or get deleted as we learn.

______________________________________________________________________

## Real-call transcript ingestion

**Context.** Many prospective clients arrive with thousands of production call transcripts and zero test cases. Hand-writing a representative test suite is the bottleneck, and the bottleneck is what kills adoption — not the test runner itself. Three proposals below address different slices of this problem; they share a common ingestion + schema layer.

### Shared groundwork

Before either of these is buildable, voicetest needs:

- **A canonical transcript schema** — message list with `role` ∈ `{user, assistant, tool}`, content, optional timestamps, optional metadata (call duration, agent version, end reason, latency). All platform-specific shapes (Retell `call.transcript`, VAPI artifact, LiveKit egress, plain text) normalize into this.
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

______________________________________________________________________

## Sequencing

Build order if/when this comes off the proposals shelf (replay regression mode is being implemented separately and is not part of this sequence):

1. Shared ingest + canonical schema + storage.
1. Clustering primitive (used by both proposals below).
1. Coverage report — ships first because the output is just a report, no synthesis.
1. Test case synthesis — last, because "review N generated cases" UX needs more polish.
