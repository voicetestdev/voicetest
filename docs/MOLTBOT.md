# OpenClaw (Moltbot) Integration Notes

OpenClaw (formerly Moltbot, formerly Clawdbot) is an open-source personal AI agent by Peter Steinberger. It runs locally and connects to messaging platforms (WhatsApp, Telegram, Discord, Slack, Signal, iMessage).

## Architecture Overview

- **Gateway**: Backend service managing messaging platform connections
- **Agent**: LLM-powered reasoning engine (Claude, GPT, local models via Ollama)
- **Skills**: Modular capability extensions in `SKILL.md` files
- **Memory**: Persistent context via `AGENTS.md`, `TOOLS.md`, `USER.md`

Configuration lives in `~/.openclaw/openclaw.json`. Behavior emerges from prompts and tool policies rather than explicit state machines.

## API Surface

### OpenAI-Compatible Endpoint

OpenClaw exposes `/v1/chat/completions` on the gateway port when `chatCompletions` is enabled. Any OpenAI-compatible client can interact with it.

### WebSocket Chat

Real-time messaging via `wss://<host>/ws?token=<TOKEN>`.

### Session Management

Programmatic tools for multi-session orchestration:

- `sessions_list` - enumerate active sessions
- `sessions_history` - retrieve conversation history
- `sessions_send` - send messages to sessions
- `sessions_spawn` - create new agent sessions

## Integration Opportunities

### 1. Platform Client (Testing Target)

Add OpenClaw as a platform in `voicetest/platforms/` to test OpenClaw-based agents.

**Approach:**

- Connect to `/v1/chat/completions` endpoint
- Send test messages, receive responses
- Evaluate against manually-defined AgentGraph

**Benefits:**

- Test OpenClaw agents for expected behavior
- Validate prompt engineering and tool configurations
- Regression testing when updating prompts/skills

**Limitations:**

- No structured agent definition to import (behavior is prompt-based)
- AgentGraph must be manually authored to represent expected flow

### 2. Test Runner (Orchestrator)

Use OpenClaw as the orchestrator that runs voicetest.

**Approach:**

- OpenClaw skill that invokes `voicetest` CLI commands
- Natural language interface: "run tests for pharmacy agent"
- Results reported back through messaging channel

**Benefits:**

- Run tests from WhatsApp/Telegram/Discord
- Conversational test management
- Accessible to non-technical stakeholders

**Implementation:**

```markdown
# SKILL.md for voicetest
---
name: voicetest
description: Run voice agent tests
---

Commands:
- `voicetest list agents` - show available agents
- `voicetest run <agent>` - execute test suite
- `voicetest status` - show recent results
```

### 3. Parallel Agent Simulation

Use OpenClaw agents as simulated callers in voicetest.

**Approach:**

- Instead of DSPy-based caller simulation, spawn OpenClaw sessions
- OpenClaw agent plays the "caller" role with persona from test case
- Real agent-to-agent conversation

**Benefits:**

- More naturalistic conversation simulation
- Leverage OpenClaw's memory and tool-use for complex scenarios
- Test multi-turn interactions with stateful caller

**Considerations:**

- Higher latency than direct LLM calls
- Requires OpenClaw instance running alongside tests

### 4. Results Dashboard via Messaging

Push test results to messaging platforms through OpenClaw.

**Approach:**

- Webhook or polling integration
- OpenClaw formats and delivers results to team channels
- Alerting on failures

**Benefits:**

- Real-time notifications without dedicated dashboard
- Team visibility in existing communication tools

## Technical Notes

### Authentication

- Gateway token required for API access
- Configure via `OPENCLAW_TOKEN` environment variable

### Deployment Options

- Local: `openclaw` CLI
- Docker: Sandboxed execution
- Cloudflare Workers: `moltworker` for serverless deployment

### Configuration Reference

```json
{
  "agents": {
    "list": [
      {
        "id": "voicetest-runner",
        "tools": {
          "profile": "coding",
          "allow": ["shell", "fs"]
        }
      }
    ]
  }
}
```

## Resources

- [OpenClaw Official Site](https://openclaw.ai/)
- [OpenClaw Documentation](https://docs.openclaw.ai/)
- [GitHub: cloudflare/moltworker](https://github.com/cloudflare/moltworker)
- [OpenRouter Integration Guide](https://openrouter.ai/docs/guides/guides/openclaw-integration)

## Strategic Notes

OpenClaw integration could serve as a validation step before investing in a native voicetest mobile app. Benefits of starting here:

- Messaging integrations already solved (WhatsApp, Telegram, etc.)
- Existing user base familiar with the UX
- Skill implementation is lightweight (markdown + shell)
- Zero friction for users to try voicetest via existing OpenClaw setup
- Validates demand before committing to native app development

If the skill gains traction, a dedicated native app could follow with learnings from real usage patterns.

## Status

Research phase. No implementation started.
