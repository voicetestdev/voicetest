---
description: List available voicetest importers, exporters, platforms, and settings
allowed-tools: [Bash]
---

# voicetest-info

Show all available voicetest capabilities.

## Steps

1. **List importers** — Show supported agent formats:

   ```bash
   voicetest --json importers
   ```

1. **List exporters** — Show available export formats:

   ```bash
   voicetest --json exporters
   ```

1. **List platforms** — Show platform integrations and configuration status:

   ```bash
   voicetest --json platforms
   ```

1. **Show settings** — Display current configuration:

   ```bash
   voicetest --json settings
   ```

1. **Present summary** — Combine all information into a clear overview:

   - Available source types (importers)
   - Available export formats
   - Platform integrations (configured/unconfigured)
   - Current model settings (agent, simulator, judge)
   - Run configuration (max_turns, verbose, etc.)

## Agent Database

If agents are loaded in the database:

```bash
voicetest --json agent list
```
