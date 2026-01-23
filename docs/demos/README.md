# Demo Recordings

Reproducible demo GIFs for documentation.

## Prerequisites

```bash
# CLI demo (VHS by Charmbracelet)
brew install vhs

# Web UI demo (Playwright + ffmpeg)
cd ../../web
mise exec -- bun add -D @playwright/test
mise exec -- bunx playwright install chromium
brew install ffmpeg
```

## Generate Demos

```bash
cd docs/demos

# Generate all
make all

# CLI demo only
make cli

# Web UI demo only
make web

# Clean generated files
make clean
```

## Files

- `cli-demo.tape` - VHS script for CLI demo
- `../../web/tests/web-demo.ts` - Playwright script for web UI demo
- `Makefile` - Build automation
- `cli-demo.gif` - Generated CLI demo (after `make cli`)
- `web-demo.gif` - Generated web demo (after `make web`)
