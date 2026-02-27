---
description: Convert a voice agent between platform formats
argument-hint: <agent-path> <target-format>
allowed-tools: [Read, Write, Bash, Glob]
---

# voicetest-convert

Convert a voice agent from one platform format to another.

## Steps

1. **Show capabilities** — Run both commands to show what's available:

   ```bash
   voicetest --json importers
   voicetest --json exporters
   ```

1. **Import** — voicetest auto-detects the source format. The import step is implicit
   in the export command — just provide the source file.

1. **Export to target** — Run:

   ```bash
   voicetest --json export -a <source-agent-path> -f <target-format> -o <output-path>
   ```

1. **Report** — Confirm conversion details:

   - Source format (auto-detected)
   - Target format
   - Output file path
   - Node count, transition count

## Common Conversions

| From       | To               | Command                                        |
| ---------- | ---------------- | ---------------------------------------------- |
| Retell     | Mermaid diagram  | `voicetest export -a retell.json -f mermaid`   |
| Retell     | LiveKit Python   | `voicetest export -a retell.json -f livekit`   |
| Retell     | VAPI             | `voicetest export -a retell.json -f vapi`      |
| Any format | Agent Graph JSON | `voicetest export -a agent.json -f agentgraph` |

## DRY Analysis

After conversion, analyze the agent for repeated text:

```bash
voicetest --json snippet analyze --agent <agent-path>
```
