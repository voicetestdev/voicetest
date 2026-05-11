---
description: Use voicetest diagnose to identify the node at fault for a failing test and propose a prompt fix, with optional auto-iterate.
---

# Diagnose and auto-fix a failing test

**The problem:** A test failed. The judge says "Agent did not confirm the appointment time" but the transcript looks reasonable to you. You don't know which prompt to edit, and rewriting half the graph by hand is exhausting.

**The flow:**

1. Run the failing test through `voicetest diagnose`
1. Let voicetest identify which node is at fault and propose a prompt change
1. (Optional) auto-iterate until the test passes
1. Save the fixed agent

## One-shot diagnose

The simplest case — you already have the failing run on disk and want a single proposed fix:

```bash
voicetest diagnose \
  --agent agent.json \
  --tests tests.json \
  --test "Schedules an appointment"
```

Voicetest analyzes the agent graph, the failing transcript, and the failed metrics, then prints:

- **Fault location** — which node it believes is at fault
- **Root cause** — one-line summary in plain English
- **Proposed change** — the new `state_prompt` text for that node, with a diff

You decide whether to apply it.

## Auto-fix loop

If you trust the diagnosis enough to let it iterate, `--auto-fix` runs a propose-apply-rerun loop until the test passes or the iteration cap is hit:

```bash
voicetest diagnose \
  --agent agent.json \
  --tests tests.json \
  --all \
  --auto-fix \
  --max-iterations 5 \
  --save fixed_agent.json
```

What happens each iteration:

1. Run the failing test(s) against the current agent
1. Identify the worst-scoring metric
1. Propose a prompt edit at the fault node
1. Apply the edit to a copy of the graph
1. Re-run the test
1. If pass → stop. If fail and iterations remain → revise.

`--save fixed_agent.json` writes the final fixed graph. The original `agent.json` is untouched.

!!! tip "Cap iterations defensively"

    Auto-fix can get stuck in a local optimum (the prompt keeps changing but the test keeps failing for the same underlying reason — usually a graph-level issue, not a prompt issue). Cap at 3–5 iterations and review by hand if it doesn't converge.

## In the web UI

The auto-fix loop is also available in the browser, and it's much easier to inspect:

1. Click any failed result in the runs list
1. Click **Diagnose**
1. Review the proposed change in an editable textarea (you can tweak the wording before applying)
1. Click **Apply & Test** — the change is applied to a copy of the graph and the test re-runs
1. A score comparison shows original vs. new with deltas
1. Click **Try Again** to revise based on the latest scores, or **Save Changes** to persist

For end-to-end automation, the **Auto-Fix Mode** toggle runs the same loop without prompting between iterations. Configure stop condition ("On improvement" or "When all pass") and max iterations (1–10).

## What diagnose is good at

- **Single-node prompt errors** — "the verification node skips DOB confirmation when the user says they don't remember" → a clean prompt rewrite usually fixes it.
- **Tone misalignment** — judge says "agent was too curt"; diagnose proposes a softer instruction.
- **Missing edge cases** — "agent handled cancellation but didn't offer a refund window" → the proposed prompt adds the missing instruction.

## What diagnose is not good at

- **Graph-structure problems** — if the issue is that the wrong node is being reached at all, no prompt edit will fix it. Diagnose will keep proposing tweaks at the wrong node and they'll all underperform.
- **Multi-node interactions** — when the bug is "node A and node B have contradicting instructions," diagnose typically only edits one and the contradiction persists.
- **Test-case bugs** — if the user_prompt or metrics are wrong, every prompt change will fail and auto-fix burns iterations chasing a moving target.

When you spot one of these, fall back to manual editing. The diagnosis output still tells you *where* the problem is, even when it can't fix it.

## Related

- [Regression-test prompt changes](regression-test-prompt-changes.md) — when you've made the fix, validate it across the whole suite
- [Features: Diagnosis & auto-fix](../features.md#diagnosis-auto-fix) — full reference
- [CLI Reference: diagnose](../cli.md#testing) — every flag
