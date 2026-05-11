---
description: Use Claude Code as your LLM backend (no API key needed) and install voicetest's Claude Code plugin for slash commands.
---

# Claude Code Integration

Voicetest integrates with [Claude Code](https://claude.ai/claude-code) in two complementary ways:

1. **LLM backend passthrough** — route voicetest's agent / simulator / judge model calls through the `claude` CLI, using your existing Claude Code authentication. No separate API key required.
1. **Plugin** — slash commands and auto-activating skills that let Claude Code itself drive voicetest workflows (run tests, export agents, convert formats).

## Passthrough as an LLM backend

If you already have Claude Code installed and authenticated, set any of the model roles to `claudecode/<model>` in `.voicetest/settings.toml`:

```toml
[models]
agent = "claudecode/sonnet"
simulator = "claudecode/haiku"
judge = "claudecode/sonnet"
```

Available model strings:

- `claudecode/sonnet` — Claude Sonnet
- `claudecode/opus` — Claude Opus
- `claudecode/haiku` — Claude Haiku

Each call invokes the `claude` CLI as a subprocess, using your existing Claude Code authentication.

### Subprocess timeout

Each call has a 600-second timeout on the `claude` CLI subprocess. If a request exceeds it, voicetest translates the failure into a retryable timeout error. Timeouts are capped at **2 attempts** (vs. the default 8 used for rate limits and connection errors) because each attempt costs the full timeout — bounding worst-case wallclock at roughly twice the timeout. If both attempts fail, the test surfaces as `status="error"` with a clear message rather than a raw `subprocess.TimeoutExpired` stacktrace.

If you consistently hit the timeout on legitimate long generations, raise the `timeout` argument when constructing the LM (Python API), or split the workload into smaller prompts.

## Plugin

The Claude Code plugin gives Claude Code itself voicetest superpowers — slash commands and auto-activating skills that drive importers, exporters, runs, and format conversions.

**For repo contributors** (automatic):

Skills and commands load automatically from `.claude/` (symlinked to `claude-plugin/`).

**Install as a marketplace plugin:**

```
/plugin marketplace add voicetestdev/voicetest
/plugin install voicetest@voicetest-plugins
```

**For pip-installed users:**

```bash
cd your-project
voicetest init-claude
```

**Available slash commands:**

| Command              | What it does                                               |
| -------------------- | ---------------------------------------------------------- |
| `/voicetest-run`     | Run tests against an agent                                 |
| `/voicetest-export`  | Export an agent to a different format                      |
| `/voicetest-convert` | Convert between platform formats (e.g. Retell → VAPI)      |
| `/voicetest-info`    | List importers, exporters, platforms, and current settings |

**Plugin path** (for manual plugin loading):

```bash
claude --plugin-dir $(voicetest claude-plugin-path)
```
