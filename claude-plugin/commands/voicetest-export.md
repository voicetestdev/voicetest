---
description: Export a voice agent to a different format (mermaid, livekit, retell, vapi, etc.)
argument-hint: <agent-path> [--format FORMAT]
allowed-tools: [Read, Write, Bash, Glob]
---

# voicetest-export

Export a voice agent definition to a different format.

## Steps

1. **List formats** — Run `voicetest --json exporters` to show available export formats.
   Common formats: `mermaid` (flowchart), `livekit` (Python agent), `retell-llm`,
   `vapi`, `bland`, `agentgraph`.

1. **Locate agent** — Find the agent definition file. If not specified, search the
   workspace for JSON files with agent-like structure.

1. **Choose format** — If not specified, ask which format to export to. Show the
   available formats from step 1.

1. **Export** — Run:

   ```bash
   voicetest --json export -a <agent-path> -f <format>
   ```

   This writes the export content to stdout.

   To save to a file:

   ```bash
   voicetest --json export -a <agent-path> -f <format> -o <output-path>
   ```

1. **Present result** — Show the exported content or confirm the file was created.

## Platform Operations

For platform-specific operations:

- List platforms: `voicetest --json platforms`
- Import from platform: `voicetest --json platform import <platform> <agent-id>`
- Push to platform: `voicetest --json platform push <platform> -a <agent-path>`
- Configure credentials: `voicetest platform configure <platform> --api-key <key>`
