# voicetest Platform Reference

## Supported Importers

Each importer auto-detects its format from the input file.

### retell (Retell AI)

- **File patterns**: `*.json`
- **Detection**: JSON with `general_prompt` and `states` array
- **Variants**: `retell-llm` (LLM config) and `retell-cf` (Conversational Flow)
- **Source types**: `retell-llm`, `retell-cf`

### vapi (VAPI)

- **File patterns**: `*.json`
- **Detection**: JSON with `model` and `firstMessage`
- **Source type**: `vapi`

### livekit (LiveKit Agents)

- **File patterns**: `*.py`
- **Detection**: Python files with LiveKit agent class definitions
- **Source type**: `livekit`

### bland (Bland AI)

- **File patterns**: `*.json`
- **Detection**: JSON with `prompt` and `pathway` structure
- **Source type**: `bland`

### telnyx (Telnyx)

- **File patterns**: `*.json`
- **Detection**: JSON with Telnyx-specific configuration
- **Source type**: `telnyx`

### xlsform (XLSForm / ODK)

- **File patterns**: `*.xlsx`, `*.xls`
- **Detection**: Excel files with `survey` and `choices` sheets
- **Source type**: `xlsform`

### custom (Manual Definition)

- **File patterns**: `*.json`
- **Detection**: JSON with `nodes` dict and `entry_node_id`
- **Source type**: `custom`

### agentgraph (voicetest Native)

- **File patterns**: `*.json`
- **Detection**: JSON matching `AgentGraph` schema directly
- **Source type**: `agentgraph`

## Export Formats

List available formats with `voicetest --json exporters`.

Common formats:

- `mermaid` — Flowchart diagram (Markdown `.md`)
- `livekit` — LiveKit Agents Python code (`.py`)
- `retell-llm` — Retell LLM config (`.json`)
- `vapi` — VAPI config (`.json`)
- `bland` — Bland AI config (`.json`)
- `agentgraph` — voicetest native format (`.json`)
- `cloudflare` — Cloudflare Workers AI (`.json`)

## Platform API Integration

Platforms with API integration support remote operations:

```bash
# Configure credentials
voicetest platform configure retell --api-key sk-xxx

# List agents on the platform
voicetest platform list-agents retell

# Import an agent from the platform
voicetest platform import retell agent_abc123 -o imported.json

# Push a local agent to the platform
voicetest platform push retell -a agent.json --agent-name "My Agent"
```

Platform credentials are stored in `.voicetest.toml` under `[env]`.

## Auto-Detection

When importing, voicetest tries each importer in order until one succeeds.
Specify `--source <type>` to skip auto-detection:

```bash
voicetest run -a agent.json -t tests.json --source retell-llm --all
```
