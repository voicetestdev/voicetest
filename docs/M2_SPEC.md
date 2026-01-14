# M2: API Server, Web UI, and Persistence

## Overview

**M2** extends voicetest with an API server, web dashboard, and persistent storage.

**Prerequisite**: M1 complete (Retell importer, CLI, TUI, shell, real LLM execution).

## Goals

1. **REST API**: FastAPI server wrapping core library
2. **Web UI**: Next.js + shadcn dashboard
3. **Persistence**: Store agents, test cases, and runs (SQLite/PostgreSQL)

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

## API Endpoints

**Agents**: CRUD + graph visualization endpoint
**Tests**: CRUD + import from JSON
**Runs**: Create, list, get results, compare, SSE streaming

## Tech Stack

- **API**: FastAPI + SQLAlchemy + Alembic
- **Web**: Next.js 14 + shadcn/ui + React Flow (graph viz)
- **DB**: SQLite (dev) / PostgreSQL (prod)

## File Structure (M2 additions)

```
voicetest/
├── voicetest/
│   ├── ...                        # Existing M1 code
│   └── rest.py                    # FastAPI server (thin wrapper over api)
│
├── web/                           # Web UI (Next.js)
│   ├── package.json
│   ├── next.config.js
│   └── src/
│       ├── app/
│       │   ├── page.tsx           # Dashboard
│       │   ├── agents/
│       │   ├── tests/
│       │   ├── runs/
│       │   └── compare/
│       └── components/
│           ├── graph-viewer.tsx   # React Flow integration
│           └── transcript.tsx
│
└── tests/
    └── integration/
        └── test_api.py            # API integration tests
```

## Future (M3+)

- Vapi importer
- Parquet export
- LiveKit introspection importer
- Multi-tenant auth
- Scheduled runs
- CI/CD integration
