# M2: Web UI and Persistence

## Overview

**M2** extends voicetest with a web dashboard and persistent storage.

## Goals

1. **Web UI**: Next.js + shadcn dashboard
2. **Persistence**: Store agents, test cases, and runs (SQLite/PostgreSQL)

## Web UI Pages

| Route | Description |
|-------|-------------|
| `/` | Dashboard: recent runs, quick stats |
| `/agents` | Agent list with import |
| `/agents/[id]` | Agent detail: graph visualization, runs |
| `/tests` | Test case management |
| `/runs` | Run history with filters |
| `/runs/[id]` | Run detail: results, transcript viewer |
| `/compare` | Side-by-side run comparison |

## API Extensions

**Agents**: CRUD + graph visualization endpoint
**Tests**: CRUD + import from JSON
**Runs**: SSE streaming for live progress

## Tech Stack

- **Web**: Next.js 14 + shadcn/ui + React Flow (graph viz)
- **DB**: SQLite (dev) / PostgreSQL (prod)
- **ORM**: SQLAlchemy + Alembic

## Future (M3+)

- Vapi importer
- Parquet export
- LiveKit introspection importer
- Multi-tenant auth
- Scheduled runs
- CI/CD integration
- Settings persistence (voicetest config file)
