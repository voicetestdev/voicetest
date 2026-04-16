# CLI Reference

## Testing

```bash
# Run tests against an agent definition
voicetest run --agent agent.json --tests tests.json --all

# Chat with an agent interactively
voicetest chat -a agent.json --model openai/gpt-4o --var name=Jane --var account=12345

# Evaluate a transcript against metrics (no simulation)
voicetest evaluate -t transcript.json -m "Agent was polite" -m "Agent resolved the issue"

# Diagnose test failures and suggest fixes
voicetest diagnose -a agent.json -t tests.json
voicetest diagnose -a agent.json -t tests.json --auto-fix --save fixed_agent.json

# Decompose an agent into sub-agents
voicetest decompose -a agent.json -o output/ [--num-agents N] [--model ID]
```

## Agent management

| Command                                                                    | Description                            |
| -------------------------------------------------------------------------- | -------------------------------------- |
| `voicetest agent list`                                                     | List agents in the database            |
| `voicetest agent create -a agent.json --name "My Agent"`                   | Create an agent from a definition file |
| `voicetest agent get <agent-id>`                                           | Get agent details                      |
| `voicetest agent update <agent-id> --name "Renamed" --model openai/gpt-4o` | Update agent properties                |
| `voicetest agent delete <agent-id>`                                        | Delete an agent                        |
| `voicetest agent graph <agent-id>`                                         | Display agent graph structure          |

## Test case management

| Command                                         | Description                  |
| ----------------------------------------------- | ---------------------------- |
| `voicetest test list <agent-id>`                | List test cases for an agent |
| `voicetest test create <agent-id> -f test.json` | Create a test case from JSON |
| `voicetest test link <agent-id> tests.json`     | Link external test file      |
| `voicetest test unlink <agent-id> tests.json`   | Unlink external test file    |
| `voicetest test export <agent-id>`              | Export test cases            |

## Run history

| Command                          | Description                   |
| -------------------------------- | ----------------------------- |
| `voicetest runs list <agent-id>` | List past test runs           |
| `voicetest runs get <run-id>`    | View run details with results |
| `voicetest runs delete <run-id>` | Delete a run                  |

## Snippets

```bash
# Analyze agent prompts for repeated text
voicetest snippet analyze --agent agent.json

# List defined snippets
voicetest snippet list --agent agent.json

# Create or update a snippet
voicetest snippet set --agent agent.json greeting "Hello, how can I help?"

# Apply snippets to prompts
voicetest snippet apply --agent agent.json --snippets '[{"name": "greeting", "text": "Hello!"}]'
```

## Export

```bash
voicetest export --agent agent.json --format mermaid         # Diagram
voicetest export --agent agent.json --format livekit         # Python code
voicetest export --agent agent.json --format retell-llm      # Retell LLM JSON
voicetest export --agent agent.json --format retell-cf       # Retell Conversation Flow JSON
voicetest export --agent agent.json --format vapi-assistant  # VAPI Assistant JSON
voicetest export --agent agent.json --format vapi-squad      # VAPI Squad JSON
voicetest export --agent agent.json --format bland           # Bland AI JSON
voicetest export --agent agent.json --format telnyx          # Telnyx AI JSON
voicetest export --agent agent.json --format voicetest       # Voicetest JSON (.vt.json)
```

## Settings and platforms

```bash
# Show current settings
voicetest settings

# Set a configuration value
voicetest settings --set models.agent=openai/gpt-4o

# List available platforms with configuration status
voicetest platforms

# Configure platform credentials
voicetest platform configure retell --api-key sk-xxx

# List agents on a remote platform
voicetest platform list-agents retell

# Import an agent from a platform
voicetest platform import retell <agent-id> -o imported.json

# Push a local agent to a platform
voicetest platform push retell -a agent.json
```

## Import formats

```bash
# List available importers
voicetest importers
```

## JSON output

All commands support `--json` for machine-parseable output (progress goes to stderr):

```bash
voicetest --json agent list
voicetest --json run -a agent.json -t tests.json --all
voicetest --json snippet analyze --agent agent.json
```

## Server and infrastructure

```bash
# Start REST API server with Web UI
voicetest serve

# Start infrastructure (LiveKit, Whisper, Kokoro) + backend for live calls
voicetest up

# Stop infrastructure services
voicetest down
```

| Service   | URL                   | Description                              |
| --------- | --------------------- | ---------------------------------------- |
| `livekit` | ws://localhost:7880   | LiveKit server for real-time voice calls |
| `whisper` | http://localhost:8001 | Faster Whisper STT server                |
| `kokoro`  | http://localhost:8002 | Kokoro TTS server                        |
