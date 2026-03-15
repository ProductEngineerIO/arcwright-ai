# Story 1.1: Project Scaffold & Package Structure

Status: done

## Story

As a developer contributing to Arcwright AI,
I want a fully scaffolded Python project with the 8-package structure defined in the architecture,
So that all subsequent stories have a working build, test, and lint pipeline to develop against.

## Acceptance Criteria (BDD)

1. **Given** an empty project directory **When** the scaffold is created **Then** the directory structure matches the architecture doc exactly: `src/arcwright_ai/` with `cli/`, `engine/`, `validation/`, `agent/`, `context/`, `output/`, `scm/`, `core/` packages

2. **Given** the scaffold is created **When** `pyproject.toml` is inspected **Then** it defines metadata, dependencies (LangGraph, Typer, Pydantic, PyYAML, Claude Code SDK), `[dev]` extras (pytest, pytest-asyncio, ruff, mypy), and build config

3. **Given** every package has `__init__.py` **When** inspected **Then** each defines `__all__` with re-exports only, no logic

4. **Given** the scaffold is complete **When** checking for PEP 561 support **Then** `py.typed` marker file exists at `src/arcwright_ai/py.typed`

5. **Given** the scaffold is complete **When** `.pre-commit-config.yaml` is inspected **Then** it configures ruff + mypy hooks

6. **Given** the scaffold is complete **When** `.github/workflows/ci.yml` is inspected **Then** it runs `pytest` + `ruff check` + `ruff format --check` + `mypy --strict`

7. **Given** the scaffold is complete **When** running `pip install -e ".[dev]"` **Then** it succeeds and `arcwright-ai --help` shows "Arcwright AI" with no commands (empty Typer app)

8. **Given** the scaffold is complete **When** running `ruff check .` **Then** zero violations

9. **Given** the scaffold is complete **When** running `mypy --strict src/` **Then** zero errors

10. **Given** the scaffold is complete **When** running `pytest` **Then** zero tests collected (test directories exist, no test files yet)

## Tasks / Subtasks

- [x] Task 1: Create root project files (AC: #2, #4, #5, #6)
  - [x] 1.1: Create `pyproject.toml` with all metadata, dependencies, dev extras, build config, ruff/mypy inline config
  - [x] 1.2: Create `README.md` with project description placeholder
  - [x] 1.3: Create `LICENSE` (choose license appropriate for open-source)
  - [x] 1.4: Create `.gitignore` with Python, venv, `.arcwright-ai/tmp/`, `.arcwright-ai/runs/` entries
  - [x] 1.5: Create `.pre-commit-config.yaml` with ruff + mypy hooks
  - [x] 1.6: Create `.github/workflows/ci.yml` with pytest + ruff + mypy jobs

- [x] Task 2: Create source package structure (AC: #1, #3, #4)
  - [x] 2.1: Create `src/arcwright_ai/__init__.py` with `__all__ = ["__version__"]` and `__version__ = "0.1.0"`
  - [x] 2.2: Create `src/arcwright_ai/py.typed` (empty file, PEP 561 marker)
  - [x] 2.3: Create `src/arcwright_ai/cli/__init__.py` with `__all__ = ["app"]`
  - [x] 2.4: Create `src/arcwright_ai/cli/app.py` — Typer app, empty command registration
  - [x] 2.5: Create `src/arcwright_ai/cli/dispatch.py` — empty module placeholder
  - [x] 2.6: Create `src/arcwright_ai/cli/status.py` — empty module placeholder
  - [x] 2.7: Create `src/arcwright_ai/engine/__init__.py` with `__all__ = ["build_graph", "run_epic"]`
  - [x] 2.8: Create `src/arcwright_ai/engine/graph.py` — placeholder
  - [x] 2.9: Create `src/arcwright_ai/engine/state.py` — placeholder
  - [x] 2.10: Create `src/arcwright_ai/engine/nodes.py` — placeholder
  - [x] 2.11: Create `src/arcwright_ai/validation/__init__.py` with `__all__ = ["validate_story_output"]`
  - [x] 2.12: Create `src/arcwright_ai/validation/v3_reflexion.py` — placeholder
  - [x] 2.13: Create `src/arcwright_ai/validation/v6_invariant.py` — placeholder
  - [x] 2.14: Create `src/arcwright_ai/validation/pipeline.py` — placeholder
  - [x] 2.15: Create `src/arcwright_ai/agent/__init__.py` with `__all__ = ["invoke_agent"]`
  - [x] 2.16: Create `src/arcwright_ai/agent/invoker.py` — placeholder
  - [x] 2.17: Create `src/arcwright_ai/agent/sandbox.py` — placeholder
  - [x] 2.18: Create `src/arcwright_ai/agent/prompt.py` — placeholder
  - [x] 2.19: Create `src/arcwright_ai/context/__init__.py` with `__all__ = ["resolve_context", "lookup_answer"]`
  - [x] 2.20: Create `src/arcwright_ai/context/injector.py` — placeholder
  - [x] 2.21: Create `src/arcwright_ai/context/answerer.py` — placeholder
  - [x] 2.22: Create `src/arcwright_ai/output/__init__.py` with `__all__ = ["RunManager", "write_provenance", "generate_summary"]`
  - [x] 2.23: Create `src/arcwright_ai/output/provenance.py` — placeholder
  - [x] 2.24: Create `src/arcwright_ai/output/run_manager.py` — placeholder
  - [x] 2.25: Create `src/arcwright_ai/output/summary.py` — placeholder
  - [x] 2.26: Create `src/arcwright_ai/scm/__init__.py` with `__all__ = ["create_worktree", "remove_worktree", "commit_story"]`
  - [x] 2.27: Create `src/arcwright_ai/scm/git.py` — placeholder
  - [x] 2.28: Create `src/arcwright_ai/scm/worktree.py` — placeholder
  - [x] 2.29: Create `src/arcwright_ai/scm/branch.py` — placeholder
  - [x] 2.30: Create `src/arcwright_ai/scm/pr.py` — placeholder
  - [x] 2.31: Create `src/arcwright_ai/core/__init__.py` with `__all__` re-exporting key public types
  - [x] 2.32: Create `src/arcwright_ai/core/types.py` — placeholder
  - [x] 2.33: Create `src/arcwright_ai/core/lifecycle.py` — placeholder
  - [x] 2.34: Create `src/arcwright_ai/core/config.py` — placeholder
  - [x] 2.35: Create `src/arcwright_ai/core/constants.py` — placeholder
  - [x] 2.36: Create `src/arcwright_ai/core/exceptions.py` — placeholder
  - [x] 2.37: Create `src/arcwright_ai/core/events.py` — placeholder
  - [x] 2.38: Create `src/arcwright_ai/core/io.py` — placeholder

- [x] Task 3: Create test directory structure (AC: #10)
  - [x] 3.1: Create `tests/conftest.py` — empty placeholder
  - [x] 3.2: Create `tests/fixtures/mock_sdk.py` — empty placeholder
  - [x] 3.3: Create `tests/fixtures/projects/valid_project/README.md`
  - [x] 3.4: Create `tests/fixtures/projects/invalid_project/README.md`
  - [x] 3.5: Create `tests/fixtures/projects/partial_project/README.md`
  - [x] 3.6: Create empty test directories: `tests/test_cli/`, `tests/test_engine/`, `tests/test_validation/`, `tests/test_agent/`, `tests/test_context/`, `tests/test_output/`, `tests/test_scm/`, `tests/test_core/`, `tests/integration/`

- [x] Task 4: Validate the scaffold (AC: #7, #8, #9, #10)
  - [x] 4.1: Run `pip install -e ".[dev]"` — must succeed
  - [x] 4.2: Run `arcwright-ai --help` — must show "Arcwright AI"
  - [x] 4.3: Run `ruff check .` — must pass with zero violations
  - [x] 4.4: Run `mypy --strict src/` — must pass with zero errors
  - [x] 4.5: Run `pytest` — must report zero tests collected (test directories exist, no test files)

### Review Follow-ups (AI)

- [x] [AI-Review][High] Fixed false exports: 6 package `__init__.py` files changed aspirational `__all__` to empty list with planned-export comments [engine, validation, agent, context, output, scm `__init__.py`]
- [x] [AI-Review][High] Added planned-export comment to `core/__init__.py` documenting future public types (TaskState, ArchwrightConfig, etc.) [src/arcwright_ai/core/__init__.py]
- [x] [AI-Review][High] Added `__init__.py` to all 9 test subdirectories for robust pytest import resolution [tests/test_*/]
- [x] [AI-Review][Med] Updated story Dev Notes version table — `claude-code-sdk` corrected from `>=0.1` to `>=0.0.10` [story file]
- [x] [AI-Review][Med] Removed redundant duplicate docstring from `app.main()` callback [src/arcwright_ai/cli/app.py]
- [x] [AI-Review][Med] Added `known-first-party = ["arcwright_ai"]` to ruff isort config [pyproject.toml]
- [x] [AI-Review][Med] Updated pre-commit mypy rev from `v1.13.0` to `v1.15.0` [.pre-commit-config.yaml]
- [x] [AI-Review][Med] Updated CI yaml pytest step to tolerate exit code 5 (no tests collected) [.github/workflows/ci.yml]
- [x] [AI-Review][Med] Added `tmp_project` fixture and `MockClaudeCodeSDK` interface stub to test fixtures [tests/conftest.py, tests/fixtures/mock_sdk.py]

## Dev Notes

### Critical Architecture Constraints

This is the **very first story** — it establishes the entire project skeleton that every subsequent story builds on. Correctness is paramount.

#### Package Dependency DAG (MANDATORY — violation is blocking)
```
cli → engine → {validation, agent, context, output, scm} → core
```
- `core` depends on nothing (stdlib + Pydantic only)
- Domain packages (`scm`, `context`, `output`, `validation`, `agent`) depend only on `core`
- `engine` depends on all domain packages + `core`
- `cli` depends on `engine` + `core`
- **Cross-domain imports are FORBIDDEN** — `scm` must never import from `agent`, `context` must never import from `output`, etc.

#### `__init__.py` Convention
Every `__init__.py` must explicitly define `__all__` listing the public API. **No logic in `__init__.py` files** — re-exports only. Agents import from the package level (`from arcwright_ai.core import TaskState`), not deep module paths.

#### Placeholder Module Pattern
Each placeholder `.py` file must:
- Include `from __future__ import annotations` at the top
- Include a module docstring describing its future purpose
- Define an empty `__all__: list[str] = []` (for modules that don't yet have public API) OR be ready for imports referenced in their package `__init__.py`
- Pass `ruff check` and `mypy --strict` with zero errors/violations

### Technical Stack — Exact Versions & Dependencies

#### Runtime Dependencies (in `pyproject.toml` `[project.dependencies]`)
| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `langgraph` | `>=0.2,<1.0` | Orchestration engine — StateGraph runtime |
| `typer[all]` | `>=0.12,<1.0` | CLI framework with Rich integration |
| `pydantic` | `>=2.7,<3.0` | Data models, config validation |
| `pyyaml` | `>=6.0,<7.0` | YAML I/O for config and artifacts |
| `claude-code-sdk` | `>=0.0.10` | Claude Code SDK for agent invocation |

#### Dev Dependencies (in `pyproject.toml` `[project.optional-dependencies.dev]`)
| Package | Version Constraint | Purpose |
|---------|-------------------|---------|
| `pytest` | `>=8.0` | Test runner |
| `pytest-asyncio` | `>=0.24` | Async test support |
| `ruff` | `>=0.8` | Linting + formatting (replaces flake8/isort/black) |
| `mypy` | `>=1.13` | Static type checking |
| `pre-commit` | `>=4.0` | Git hooks |

#### Python Version
- **Minimum: Python 3.11** (LangGraph requirement)
- `requires-python = ">=3.11"` in `pyproject.toml`

#### Build System
- **Backend:** `hatchling` (modern, PEP 621 native)
- `[build-system]` in `pyproject.toml`:
  ```toml
  [build-system]
  requires = ["hatchling"]
  build-backend = "hatchling.build"
  ```

### `pyproject.toml` Structure

The `pyproject.toml` must include the following sections:

```toml
[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[project]
name = "arcwright-ai"
version = "0.1.0"
description = "Deterministic orchestration shell for autonomous AI agent execution"
requires-python = ">=3.11"
license = { text = "MIT" }
authors = [{ name = "Ed" }]
dependencies = [
    "langgraph>=0.2,<1.0",
    "typer[all]>=0.12,<1.0",
    "pydantic>=2.7,<3.0",
    "pyyaml>=6.0,<7.0",
    "claude-code-sdk>=0.1",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
    "pre-commit>=4.0",
]

[project.scripts]
arcwright-ai = "arcwright_ai.cli.app:app"

[tool.ruff]
target-version = "py311"
src = ["src"]
line-length = 120

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "SIM", "TCH", "RUF"]

[tool.mypy]
python_version = "3.11"
strict = true
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = true

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "slow: marks tests that use real git operations (deselect with '-m \"not slow\"')",
]

[tool.hatch.build.targets.wheel]
packages = ["src/arcwright_ai"]
```

### CLI App Setup (`cli/app.py`)

The Typer app must be a **minimal empty shell** for this story:

```python
from __future__ import annotations

import typer

app = typer.Typer(
    name="arcwright-ai",
    help="Arcwright AI — Deterministic orchestration shell for autonomous AI agent execution",
    no_args_is_help=True,
)
```

This creates the entry point so `arcwright-ai --help` works. Commands will be added in later stories (1.4, 1.5, 2.7).

### `.pre-commit-config.yaml` Content

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        additional_dependencies: [pydantic>=2.7, typer>=0.12]
        args: [--strict]
```

### `.github/workflows/ci.yml` Content

```yaml
name: CI
on: [push, pull_request]
jobs:
  lint-test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.11", "3.12", "3.13"]
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
      - run: pip install -e ".[dev]"
      - run: ruff check .
      - run: ruff format --check .
      - run: mypy --strict src/
      - run: pytest
```

### `.gitignore` Must Include

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
dist/
build/
.eggs/

# Virtual environments
.venv/
venv/

# IDE
.idea/
.vscode/
*.swp

# Arcwright AI runtime (never committed)
.arcwright-ai/tmp/
.arcwright-ai/runs/

# mypy
.mypy_cache/

# pytest
.pytest_cache/

# ruff
.ruff_cache/
```

### Project Structure Notes

The complete directory tree for this story (all files to create):

```
arcwright-ai/                         # NEW — project root (inside workspace root)
├── pyproject.toml
├── README.md
├── LICENSE
├── .gitignore
├── .pre-commit-config.yaml
├── .github/
│   └── workflows/
│       └── ci.yml
├── src/
│   └── arcwright_ai/
│       ├── __init__.py
│       ├── py.typed                  # Empty file — PEP 561 marker
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── dispatch.py
│       │   └── status.py
│       ├── engine/
│       │   ├── __init__.py
│       │   ├── graph.py
│       │   ├── state.py
│       │   └── nodes.py
│       ├── validation/
│       │   ├── __init__.py
│       │   ├── v3_reflexion.py
│       │   ├── v6_invariant.py
│       │   └── pipeline.py
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── invoker.py
│       │   ├── sandbox.py
│       │   └── prompt.py
│       ├── context/
│       │   ├── __init__.py
│       │   ├── injector.py
│       │   └── answerer.py
│       ├── output/
│       │   ├── __init__.py
│       │   ├── provenance.py
│       │   ├── run_manager.py
│       │   └── summary.py
│       ├── scm/
│       │   ├── __init__.py
│       │   ├── git.py
│       │   ├── worktree.py
│       │   ├── branch.py
│       │   └── pr.py
│       └── core/
│           ├── __init__.py
│           ├── types.py
│           ├── lifecycle.py
│           ├── config.py
│           ├── constants.py
│           ├── exceptions.py
│           ├── events.py
│           └── io.py
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── mock_sdk.py
│   │   └── projects/
│   │       ├── valid_project/
│   │       │   └── README.md
│   │       ├── invalid_project/
│   │       │   └── README.md
│   │       └── partial_project/
│   │           └── README.md
│   ├── integration/                  # Empty dir (tests added in later stories)
│   ├── test_cli/                     # Empty dir
│   ├── test_engine/                  # Empty dir
│   ├── test_validation/              # Empty dir
│   ├── test_agent/                   # Empty dir
│   ├── test_context/                 # Empty dir
│   ├── test_output/                  # Empty dir
│   ├── test_scm/                     # Empty dir
│   └── test_core/                    # Empty dir
└── .github/
    └── workflows/
        └── ci.yml
```

**IMPORTANT:** The `arcwright-ai/` project directory is created as a **subdirectory** of the workspace root (`bmad-graph-swarm/`). The workspace root contains `_spec/`, `_bmad/`, `docs/`, and the new `arcwright-ai/` project.

### References

- [Architecture: Starter Template Evaluation](../planning-artifacts/architecture.md#starter-template-evaluation) — rationale for custom scaffold
- [Architecture: Project Structure](../planning-artifacts/architecture.md#project-structure) — 8-package structure definition
- [Architecture: Complete Project Tree](../planning-artifacts/architecture.md#complete-project-tree) — full file listing
- [Architecture: Design Principles](../planning-artifacts/architecture.md#design-principles-embedded-in-structure) — constraints per file
- [Architecture: Package Dependency DAG](../planning-artifacts/architecture.md#package-dependency-dag-mandatory) — import rules
- [Architecture: Python Code Style Patterns](../planning-artifacts/architecture.md#python-code-style-patterns) — naming, imports, docstrings
- [Architecture: Enforcement Guidelines](../planning-artifacts/architecture.md#enforcement-guidelines) — 10 mandatory rules + anti-patterns
- [PRD: Executive Summary](../planning-artifacts/prd.md#executive-summary) — project description for README
- [PRD: Technical Stack](../planning-artifacts/prd.md#mvp--minimum-viable-product) — MVP capability list
- [Epics: Story 1.1](../planning-artifacts/epics.md#story-11-project-scaffold--package-structure) — original story definition

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (GitHub Copilot)

### Debug Log References

- Fixed `claude-code-sdk` version constraint from `>=0.1` to `>=0.0.10` (no 0.1.x releases exist yet)
- Added Typer callback to `app.py` to resolve `RuntimeError: Could not get a command for this Typer instance` when running with no commands
- Sorted `__all__` lists alphabetically in context, output, and scm `__init__.py` files to satisfy ruff RUF022

### Completion Notes List

- Task 1: Created all 6 root project files (pyproject.toml, README.md, LICENSE, .gitignore, .pre-commit-config.yaml, ci.yml)
- Task 2: Created all 38 source files across 8 packages (cli, engine, validation, agent, context, output, scm, core) with proper `__all__`, docstrings, and `from __future__ import annotations`
- Task 3: Created test directory structure with conftest.py, fixture files, and 9 empty test directories with .gitkeep files
- Task 4: All 5 validation checks pass — install, CLI help, ruff, mypy --strict, pytest
- Code Review: Fixed 3 HIGH and 6 MEDIUM issues; all quality gates (ruff, mypy --strict, pytest) still pass after fixes

### File List

arcwright-ai/pyproject.toml (new)
arcwright-ai/README.md (new)
arcwright-ai/LICENSE (new)
arcwright-ai/.gitignore (new)
arcwright-ai/.pre-commit-config.yaml (new)
arcwright-ai/.github/workflows/ci.yml (new)
arcwright-ai/src/arcwright_ai/__init__.py (new)
arcwright-ai/src/arcwright_ai/py.typed (new)
arcwright-ai/src/arcwright_ai/cli/__init__.py (new)
arcwright-ai/src/arcwright_ai/cli/app.py (new)
arcwright-ai/src/arcwright_ai/cli/dispatch.py (new)
arcwright-ai/src/arcwright_ai/cli/status.py (new)
arcwright-ai/src/arcwright_ai/engine/__init__.py (new)
arcwright-ai/src/arcwright_ai/engine/graph.py (new)
arcwright-ai/src/arcwright_ai/engine/state.py (new)
arcwright-ai/src/arcwright_ai/engine/nodes.py (new)
arcwright-ai/src/arcwright_ai/validation/__init__.py (new)
arcwright-ai/src/arcwright_ai/validation/v3_reflexion.py (new)
arcwright-ai/src/arcwright_ai/validation/v6_invariant.py (new)
arcwright-ai/src/arcwright_ai/validation/pipeline.py (new)
arcwright-ai/src/arcwright_ai/agent/__init__.py (new)
arcwright-ai/src/arcwright_ai/agent/invoker.py (new)
arcwright-ai/src/arcwright_ai/agent/sandbox.py (new)
arcwright-ai/src/arcwright_ai/agent/prompt.py (new)
arcwright-ai/src/arcwright_ai/context/__init__.py (new)
arcwright-ai/src/arcwright_ai/context/injector.py (new)
arcwright-ai/src/arcwright_ai/context/answerer.py (new)
arcwright-ai/src/arcwright_ai/output/__init__.py (new)
arcwright-ai/src/arcwright_ai/output/provenance.py (new)
arcwright-ai/src/arcwright_ai/output/run_manager.py (new)
arcwright-ai/src/arcwright_ai/output/summary.py (new)
arcwright-ai/src/arcwright_ai/scm/__init__.py (new)
arcwright-ai/src/arcwright_ai/scm/git.py (new)
arcwright-ai/src/arcwright_ai/scm/worktree.py (new)
arcwright-ai/src/arcwright_ai/scm/branch.py (new)
arcwright-ai/src/arcwright_ai/scm/pr.py (new)
arcwright-ai/src/arcwright_ai/core/__init__.py (new)
arcwright-ai/src/arcwright_ai/core/types.py (new)
arcwright-ai/src/arcwright_ai/core/lifecycle.py (new)
arcwright-ai/src/arcwright_ai/core/config.py (new)
arcwright-ai/src/arcwright_ai/core/constants.py (new)
arcwright-ai/src/arcwright_ai/core/exceptions.py (new)
arcwright-ai/src/arcwright_ai/core/events.py (new)
arcwright-ai/src/arcwright_ai/core/io.py (new)
arcwright-ai/tests/conftest.py (new)
arcwright-ai/tests/fixtures/mock_sdk.py (new)
arcwright-ai/tests/fixtures/projects/valid_project/README.md (new)
arcwright-ai/tests/fixtures/projects/invalid_project/README.md (new)
arcwright-ai/tests/fixtures/projects/partial_project/README.md (new)
arcwright-ai/tests/test_cli/.gitkeep (new)
arcwright-ai/tests/test_engine/.gitkeep (new)
arcwright-ai/tests/test_validation/.gitkeep (new)
arcwright-ai/tests/test_agent/.gitkeep (new)
arcwright-ai/tests/test_context/.gitkeep (new)
arcwright-ai/tests/test_output/.gitkeep (new)
arcwright-ai/tests/test_scm/.gitkeep (new)
arcwright-ai/tests/test_core/.gitkeep (new)
arcwright-ai/tests/integration/.gitkeep (new)

_Modified during code review:_
arcwright-ai/src/arcwright_ai/engine/__init__.py (modified)
arcwright-ai/src/arcwright_ai/validation/__init__.py (modified)
arcwright-ai/src/arcwright_ai/agent/__init__.py (modified)
arcwright-ai/src/arcwright_ai/context/__init__.py (modified)
arcwright-ai/src/arcwright_ai/output/__init__.py (modified)
arcwright-ai/src/arcwright_ai/scm/__init__.py (modified)
arcwright-ai/src/arcwright_ai/core/__init__.py (modified)
arcwright-ai/src/arcwright_ai/cli/app.py (modified)
arcwright-ai/pyproject.toml (modified)
arcwright-ai/.pre-commit-config.yaml (modified)
arcwright-ai/.github/workflows/ci.yml (modified)
arcwright-ai/tests/conftest.py (modified)
arcwright-ai/tests/fixtures/mock_sdk.py (modified)
arcwright-ai/tests/test_cli/__init__.py (new)
arcwright-ai/tests/test_engine/__init__.py (new)
arcwright-ai/tests/test_validation/__init__.py (new)
arcwright-ai/tests/test_agent/__init__.py (new)
arcwright-ai/tests/test_context/__init__.py (new)
arcwright-ai/tests/test_output/__init__.py (new)
arcwright-ai/tests/test_scm/__init__.py (new)
arcwright-ai/tests/test_core/__init__.py (new)
arcwright-ai/tests/integration/__init__.py (new)

## Change Log

- 2026-03-02 (dev): Created full project scaffold — 6 root files, 8 source packages (37 Python files), test directory structure; all quality gates passing
- 2026-03-02 (code-review): Fixed 3 HIGH + 6 MEDIUM review findings; added 9 test package `__init__.py` files, fixture stubs, CI/config hardening

## Senior Developer Review (AI)

**Reviewer:** GitHub Copilot (Claude Sonnet 4.6)
**Date:** 2026-03-02
**Outcome:** ✅ Approved (after fixes applied in same session)

### Severity Summary
| Severity | Found | Fixed | Deferred |
|----------|-------|-------|----------|
| High | 3 | 3 | 0 |
| Medium | 6 | 6 | 0 |
| Low | 4 | 0 | 4 (non-blocking) |

### Action Items

- [x] [High] Fixed false `__all__` exports in engine, validation, agent, context, output, scm packages — aspirational string declarations replaced with empty lists and planned-export comments
- [x] [High] Added planned-export comment to `core/__init__.py` — documents future public type surface from architecture doc
- [x] [High] Added `__init__.py` to all 9 test subdirectories — prevents fragile implicit namespace package behaviour
- [x] [Med] Dev Notes version table corrected: `claude-code-sdk>=0.1` → `>=0.0.10`
- [x] [Med] Removed duplicate docstring from `cli/app.py` `main()` callback
- [x] [Med] Added `known-first-party = ["arcwright_ai"]` to `[tool.ruff.lint.isort]` in `pyproject.toml`
- [x] [Med] Updated pre-commit mypy hook rev `v1.13.0` → `v1.15.0`
- [x] [Med] CI `pytest` step updated to tolerate exit code 5 (no tests — expected for scaffold story)
- [x] [Med] Added `tmp_project` pytest fixture stub and `MockClaudeCodeSDK` class interface stub

### Remaining Low Severity (Non-Blocking)

- [L1] `.gitignore` at `arcwright-ai/.gitignore` covers project internals; workspace root `bmad-graph-swarm/` has no Python ignore rules
- [L2] `LICENSE` copyright year 2026 (trivial)
- [L3] `engine/__init__.py` planned exports are mixed-concern (`build_graph`, `run_epic`) — separate when symbols are implemented
- [L4] No `.editorconfig` for editor consistency with `line-length = 120`
