---
description: Voice agent testing with voicetest. Activate when discussing voice agents, Retell, VAPI, LiveKit, Bland, Telnyx, agent graphs, conversation flow testing, or voicetest.
---

# voicetest — Voice Agent Test Harness

voicetest is a CLI tool and library for testing voice agent workflows across platforms.
It imports agent definitions, runs simulated conversations, evaluates results against
metrics, and exports to different formats.

## Core Workflow

```
import → test → evaluate → export
```

1. **Import**: Auto-detects source format (Retell, VAPI, LiveKit, Bland, Telnyx, custom)
1. **Test**: Runs simulated conversations using LLM-based user simulation
1. **Evaluate**: Judges agent responses against natural language metrics
1. **Export**: Converts between platform formats

## CLI Commands

### Testing

```bash
voicetest run -a agent.json -t tests.json --all          # Run all tests
voicetest run -a agent.json -t tests.json --test "Name"  # Run specific test
voicetest --json run -a agent.json -t tests.json --all   # JSON output for parsing
```

### Agent Management (DB-backed)

```bash
voicetest agent list                           # List agents in database
voicetest agent get <id>                       # Get agent details
voicetest agent create -a agent.json           # Create from file
voicetest agent update <id> --name "New Name"  # Update properties
voicetest agent delete <id>                    # Delete agent
voicetest agent graph <id>                     # Show graph structure
```

### Test Case Management

```bash
voicetest test list <agent-id>                 # List test cases
voicetest test create <agent-id> -f test.json  # Create from file
voicetest test link <agent-id> tests.json      # Link external file
voicetest test export <agent-id>               # Export all tests
```

### Run History

```bash
voicetest runs list <agent-id>                 # List past runs
voicetest runs get <run-id>                    # Get run details
```

### Snippet Management (DRY Analysis)

```bash
voicetest snippet analyze --agent agent.json   # Find repeated text
voicetest snippet list --agent agent.json      # List defined snippets
voicetest snippet set --agent agent.json greeting "Hello!" # Set snippet
```

### Export and Conversion

```bash
voicetest export -a agent.json -f mermaid      # Mermaid diagram
voicetest export -a agent.json -f livekit      # LiveKit Python agent
voicetest export -a agent.json -f vapi         # VAPI format
voicetest importers                            # List importers
voicetest exporters                            # List export formats
```

### Platform Integration

```bash
voicetest platforms                                       # List platforms
voicetest platform configure retell --api-key <key>       # Set credentials
voicetest platform list-agents retell                     # List remote agents
voicetest platform import retell <agent-id> -o agent.json # Import agent
voicetest platform push retell -a agent.json              # Push to platform
```

### Evaluation and Diagnosis

```bash
voicetest evaluate -t transcript.json -m "Agent was polite"    # Evaluate transcript
voicetest diagnose -a agent.json -t tests.json --auto-fix      # Auto-fix failures
voicetest chat -a agent.json                                   # Interactive chat
```

### Settings

```bash
voicetest settings                                     # Show settings
voicetest settings --set models.agent=openai/gpt-4o    # Set a value
voicetest settings --defaults                          # Show defaults
```

## The --json Flag

All commands support `--json` for machine-parseable output. Progress messages go to
stderr, structured data goes to stdout.

```bash
voicetest --json agent list | jq '.[].name'
voicetest --json run -a agent.json -t tests.json --all | jq '.results[] | {name: .test_name, status}'
```

## LLM Configuration

voicetest uses three LLM roles:

- **agent**: Powers the voice agent responses (default from settings)
- **simulator**: Simulates the user in tests (default from settings)
- **judge**: Evaluates test results against metrics (default from settings)

Configure via `.voicetest.toml` or CLI:

```bash
voicetest settings --set models.agent=openai/gpt-4o
voicetest settings --set models.judge=anthropic/claude-sonnet-4-20250514
```

## Test Case Format

See `references/test-format.md` for the full JSON schema.

## Platform Details

See `references/platforms.md` for platform-specific notes.
