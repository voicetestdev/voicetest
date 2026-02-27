# Demo Recordings

Reproducible demo GIFs for documentation. Each web/dry demo is recorded in both
light and dark theme variants.

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

# Generate all (cli + web + dry, both themes)
make all

# CLI demo only
make cli

# Web UI demos (light + dark)
make web

# DRY analysis demos (light + dark)
make dry

# Clean generated files
make clean
```

## Files

- `cli-demo.tape` — VHS script for CLI demo
- `../../web/demo/web-demo.ts` — Playwright script for web UI demo
- `../../web/demo/dry-demo.ts` — Playwright script for DRY analysis demo
- `../../web/demo/dry-agent.json` — Demo agent data for DRY demo
- `Makefile` — Build automation

### Generated Assets

| Demo         | Light                | Dark                |
| ------------ | -------------------- | ------------------- |
| Web UI       | `web-demo-light.gif` | `web-demo-dark.gif` |
| DRY analysis | `dry-demo-light.gif` | `dry-demo-dark.gif` |
| CLI          | `cli-demo.gif`       | *(terminal theme)*  |
