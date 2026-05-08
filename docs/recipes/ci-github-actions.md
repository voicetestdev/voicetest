# Run in GitHub Actions

**The problem:** Manual testing of voice agents doesn't scale. You run a few conversations in the dashboard, ship the change, and find out from a customer that your prompt edit broke the appointment flow. The feedback loop is days, not minutes.

**The flow:**

1. Commit the agent JSON and the test cases JSON to git
1. Add a workflow that runs `voicetest run --all` on every push
1. Block PRs that fail

## Repo layout

```
.
├── agents/
│   └── receptionist.json    # exported from your platform, version-controlled
├── tests/
│   └── receptionist.json    # voicetest test cases
└── .github/
    └── workflows/
        └── voice-tests.yml
```

Keep the agent JSON in git, not just in your platform's UI. Diffs on a JSON file tell you exactly what changed; "the agent" in someone's Retell account does not.

## The workflow

```yaml
name: Voice Agent Tests

on:
  pull_request:
    paths:
      - "agents/**"
      - "tests/**"
  push:
    branches: [main]
    paths:
      - "agents/**"
      - "tests/**"

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install voicetest
      - name: Run voice agent tests
        run: |
          voicetest run \
            --agent agents/receptionist.json \
            --tests tests/receptionist.json \
            --all \
            --output run.json
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: voicetest-run
          path: run.json
```

## Why this layout

- **`paths` filter** — the suite only runs when agent or tests change. Saves CI minutes and Groq tokens on unrelated PRs.
- **`uv tool install`** — voicetest installs in seconds (versus minutes for a full `pip install`). The setup-uv action caches the binary across runs.
- **`--output run.json`** — the run artifact is uploaded on every CI run, including failures. You can download it and re-open in `voicetest serve` for a full UI investigation.
- **`if: always()`** — uploads the artifact even if the test step failed, which is exactly when you need it most.

## Multi-platform matrix

If you maintain the same agent on multiple platforms (e.g. Retell as primary, VAPI as failover), use a matrix to test all of them against the same test suite:

```yaml
jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        agent:
          - agents/retell-receptionist.json
          - agents/vapi-receptionist.json
          - agents/bland-receptionist.json
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install voicetest
      - run: |
          voicetest run \
            --agent ${{ matrix.agent }} \
            --tests tests/receptionist.json \
            --all
        env:
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
```

`fail-fast: false` keeps every platform's job running even when one fails — you want to know whether a regression hits Retell only or all three.

## Required repository secrets

| Secret           | Why                                                                               |
| ---------------- | --------------------------------------------------------------------------------- |
| `GROQ_API_KEY`   | Default judge / agent model provider. Free tier covers most CI volumes.           |
| `OPENAI_API_KEY` | Optional. Use if your suite is configured for OpenAI models.                      |
| `RETELL_API_KEY` | Only if you push the validated agent back to Retell on `main` merges (see below). |

## Block bad merges

Configure GitHub to require the workflow to pass before merging:

1. Settings → Branches → Branch protection rules → `main`
1. Tick **Require status checks to pass before merging**
1. Add `Voice Agent Tests / test` to the required list

A red voice-tests check is now a hard merge block.

## Auto-deploy on green

For teams that maintain the agent in voicetest and *push* it back to the platform, extend the workflow to deploy on `main` after a passing test:

```yaml
  deploy:
    needs: test
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
      - run: uv tool install voicetest
      - name: Push agent to Retell
        run: |
          voicetest sync \
            --agent agents/receptionist.json \
            --platform retell \
            --agent-id <retell-agent-id>
        env:
          RETELL_API_KEY: ${{ secrets.RETELL_API_KEY }}
```

The pattern is: **PR runs tests, main runs tests + deploy**. Production never sees a config that hasn't passed the suite.

## Related

- [Test a Retell Agent in CI (blog post)](https://voicetest.dev/blog/test-retell-agent-ci-github-actions/) — narrative walkthrough with screenshots
- [Regression-test prompt changes](regression-test-prompt-changes.md) — what the suite is actually catching
- [CLI Reference](../cli.md) — every command and flag
