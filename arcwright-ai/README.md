# Arcwright AI

Deterministic orchestration shell for autonomous AI agent execution.

Arcwright AI provides a structured pipeline that takes BMAD planning artifacts (PRD, Architecture, Epics) and autonomously executes them through AI agents while maintaining deterministic control, validation gates, and full decision provenance.

## Installation

```bash
pip install -e ".[dev]"
```

## Usage

```bash
arcwright-ai --help
```

## Development

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint
ruff check .
ruff format --check .

# Type check
mypy --strict src/
```
