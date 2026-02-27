---
description: Run voicetest tests against a voice agent definition
argument-hint: <agent-path> <tests-path> [--test NAME]
allowed-tools: [Read, Bash, Glob, Grep]
---

# voicetest-run

Run voice agent tests from the CLI, parse results, and report findings.

## Steps

1. **Locate files** — Find the agent definition file and test cases file. If paths
   are not provided as arguments, search the workspace for likely candidates:

   - Agent files: `*.json` files containing `general_prompt` or `nodes`
   - Test files: `*.json` files containing arrays with `user_prompt` and `metrics`

1. **Discover source type** — Run `voicetest --json importers` to list available
   importers and auto-detect the agent format.

1. **Run tests** — Execute:

   ```bash
   voicetest --json run -a <agent-path> -t <tests-path> --all
   ```

   Or for specific tests:

   ```bash
   voicetest --json run -a <agent-path> -t <tests-path> --test "Test Name"
   ```

1. **Parse results** — The JSON output is a `TestRun` object with:

   - `results[]` — array of test results
   - Each result has `test_name`, `status` (pass/fail/error), `metric_results[]`,
     `transcript[]`, `nodes_visited[]`, `turn_count`, `duration_ms`

1. **Report** — Summarize pass/fail counts. For failures, show:

   - Which metrics failed and why (from `metric_results[].reasoning`)
   - Key transcript excerpts
   - Suggested fixes based on failure patterns

1. **Diagnose failures** — If tests fail, offer to run diagnosis:

   ```bash
   voicetest --json diagnose -a <agent-path> -t <tests-path> --test "Failing Test"
   ```

   Or with auto-fix:

   ```bash
   voicetest --json diagnose -a <agent-path> -t <tests-path> --auto-fix -s fixed_agent.json
   ```

## Additional Commands

- List agents in DB: `voicetest --json agent list`
- View run history: `voicetest --json runs list <agent-id>`
- Evaluate a transcript: `voicetest --json evaluate -t transcript.json -m "Agent was polite"`
