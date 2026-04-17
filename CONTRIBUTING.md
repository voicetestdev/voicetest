# Contributing to voicetest

Thanks for your interest in contributing! Here's how to get started.

## Quick setup

```bash
git clone https://github.com/voicetestdev/voicetest
cd voicetest
uv sync
uv run pre-commit install
```

## Development guide

For the full development setup — Docker, manual setup, frontend development, code quality rules, test fixtures, and project structure — see the [Development docs](https://voicetest.dev/docs/development/).

## Running tests

```bash
# Unit tests
uv run pytest tests/unit

# Integration tests (requires Ollama with qwen2.5:0.5b)
uv run pytest tests/integration

# Pre-commit checks
uv run pre-commit run --all-files
```

## Submitting changes

1. Fork the repo and create a branch
1. Make your changes
1. Ensure all tests and pre-commit hooks pass
1. Open a pull request

## Questions?

Open an issue or email [hello@voicetest.dev](mailto:hello@voicetest.dev).
