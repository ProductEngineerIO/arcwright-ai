# Arcwright AI

Deterministic orchestration shell for autonomous AI agent execution.

Arcwright AI takes BMAD planning artifacts (PRD, Architecture, Epics, Stories) and autonomously executes them through Claude, enforcing validation gates, tracking decision provenance, and writing structured run artifacts after every execution.

---

## Table of Contents

- [Prerequisites](#prerequisites)
- [Installation](#installation)
- [Project Setup](#project-setup)
- [Running Stories](#running-stories)
- [Run Artifacts](#run-artifacts)
- [Understanding the Output](#understanding-the-output)
- [LangGraph Studio](#langgraph-studio)
- [Development](#development)
- [Troubleshooting](#troubleshooting)

---

## Prerequisites

- **Python 3.11+** (3.14 recommended; see [LangGraph Studio](#langgraph-studio) for the exception)
- **Claude API key** (Anthropic): `ARCWRIGHT_API_CLAUDE_API_KEY`
- **BMAD 6.1+** — planning artifacts and dev-story workflow features require BMAD 6.1 or later
- A project initialised with BMAD (`_spec/planning-artifacts/` containing PRD, architecture, epics, and story files)

---

## Installation

**From PyPI** (end users — install in your target project):

```bash
cd /path/to/your/project
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install arcwright-ai
```

To version-control the dependency, add a `requirements.txt` to your project:

```text
arcwright-ai>=0.2.4
```

**From source** (contributors):

```bash
git clone https://github.com/ProductEngineerIO/arcwright-ai.git
cd arcwright-ai/arcwright-ai
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Set your API key (add to your shell profile or `.env`):

```bash
export ARCWRIGHT_API_CLAUDE_API_KEY="sk-ant-..."
```

Or copy the generated `.env.example` and fill in your values:

```bash
cp .env.example .env
# Edit .env — at minimum set ARCWRIGHT_API_CLAUDE_API_KEY
```

> **`.env` files** are loaded automatically by arcwright-ai on startup. The `.env` file is git-ignored by `init` — secrets never enter version control. See `.env.example` for the full list of supported variables.

> **Tip — guaranteed local execution:** Use `python -m arcwright_ai` instead of
> the bare `arcwright-ai` command. This always runs the copy installed in the
> active virtual environment, never a stale global install.

---

## Project Setup

Before dispatching stories, initialise Arcwright AI in your **target project** (the project whose stories you want to implement — not this repo):

```bash
# From inside the target project root (venv activated):
python -m arcwright_ai init

# Or point explicitly:
python -m arcwright_ai init --path /path/to/your/project
```

This creates `.arcwright-ai/` with the following layout:

```
.arcwright-ai/
├── config.yaml       ← project-level configuration (committed)
├── runs/             ← execution artifacts (git-ignored)
├── worktrees/        ← git worktrees (git-ignored)
└── tmp/              ← transient scratch space (git-ignored)
```

It also places a `.env.example` in the project root. Copy it to get started:

```bash
cp .env.example .env
# Fill in at minimum: ARCWRIGHT_API_CLAUDE_API_KEY
```

**`config.yaml` defaults** (edit to suit your project):

```yaml
model:
  version: "claude-opus-4-6"

limits:
  tokens_per_story: 200000
  cost_per_run: 10.0
  retry_budget: 3
  timeout_per_story: 300

methodology:
  artifacts_path: "_bmad-output"   # where your BMAD planning docs live
  type: "bmad"

scm:
  branch_template: "arcwright-ai/{story_slug}"
```

> **API key security**: Never put your API key in `config.yaml`. Use the
> `.env` file (git-ignored), the `ARCWRIGHT_API_CLAUDE_API_KEY` environment
> variable, or the global `~/.arcwright-ai/config.yaml` (user-level, outside
> any repo).

Verify your setup:

```bash
python -m arcwright_ai validate-setup
```

---

## Running Stories

Dispatch a single story by its `epic.story` identifier (e.g., story 4 of epic 2 is `2.4`):

```bash
# From inside the target project root (venv activated):
python -m arcwright_ai dispatch --story 2.4

# Dashes and STORY- prefix also work:
python -m arcwright_ai dispatch --story 2-4
python -m arcwright_ai dispatch --story STORY-2.4
```

The pipeline runs:

```
preflight → budget_check → agent_dispatch → validate → commit → finalize
```

Each node writes artifacts to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/`.

**Exit codes:**

| Code | Meaning |
|------|---------|
| `0`  | Story completed successfully |
| `1`  | Unexpected error (configuration, I/O, etc.) |
| `2`  | Story escalated (validation failed, could not auto-fix) |

### Dispatching Epics

Epic selectors accept all of the following equivalent forms: `2`, `epic-2`, and `EPIC-2`.

```bash
# Dispatch an entire epic
python -m arcwright_ai dispatch --epic 2

# Equivalent epic selector formats
python -m arcwright_ai dispatch --epic epic-2
python -m arcwright_ai dispatch --epic EPIC-2

# Resume a halted epic
python -m arcwright_ai dispatch --epic EPIC-2 --resume
```

---

## Run Artifacts

Every execution produces a run directory:

```
.arcwright-ai/runs/<run-id>/
├── run.yaml                          ← metadata: status, cost, story list
└── stories/<story-slug>/
    ├── context-bundle.md             ← assembled context injected into the agent
    ├── agent-output.md               ← raw output from Claude
    ├── validation.md                 ← V6 invariant + V3 reflexion results and decision log
    ├── halt-report.md                ← populated only on escalation
    └── summary.md                    ← produced by finalize node (success or halt)
```

**Run ID format**: `YYYYMMDD-HHMMSS-<4-char-id>` (e.g. `20260305-022632-4b90`)

### Reading a halt report

When a run escalates, check these files in order:

1. **`halt-report.md`** — escalation reason, retry history, suggested fix
2. **`validation.md`** — exact V6 invariant failures and V3 reflexion AC results
3. **`agent-output.md`** — what Claude produced (verify files actually exist on disk before trusting V6 failures)

---

## Understanding the Output

### `status: escalated` vs. failure

`escalated` means the pipeline ran successfully but validation could not be satisfied within the retry budget. It does **not** mean the agent crashed. The agent's work (files, code) is still on disk in the target project.

Escalation reasons:

| Reason | Meaning |
|--------|---------|
| `v6_invariant_failure` | Hard rule violation (missing file, bad name, syntax error) — retries won't help without a fix |
| `max_retries_exhausted` | V3 reflexion (AC review) kept failing after N retries |
| `budget_exceeded` | Token/cost ceiling hit before validation passed |

### False-positive V6 failures

If `validation.md` shows a `file_existence` failure for a file that **does** exist on disk, check whether the path in the error has a leading backtick (e.g., `` `backend/app/routers/admin.py ``). This is a known pattern when the agent uses inline code formatting in markdown headers. The V6 checker strips backticks as of the current version. If you see this after upgrading from an older run, the files are fine — re-run to get a clean pass.

---

## LangGraph Studio

Arcwright AI ships a [`langgraph.json`](langgraph.json) config so you can visualise and inspect the execution graph in [LangGraph Studio](https://smith.langchain.com/studio/).

### Why a separate venv?

The main `.venv` uses **Python 3.14**. The `langgraph-api` package (required for `langgraph dev`) depends on `pyo3`-based Rust extensions that do not yet publish wheels for Python 3.14 and cannot be compiled without matching support. A separate Python 3.13 venv is used exclusively for Studio.

### One-time setup

Ensure Python 3.13 is available (via Homebrew or pyenv), then:

```bash
cd arcwright-ai/

# Create Studio venv with Python 3.13
python3.13 -m venv .venv-studio

# Install project + LangGraph Studio deps
.venv-studio/bin/pip install -e ".[dev]" "langgraph-cli[inmem]"
```

### Starting Studio

```bash
cd arcwright-ai/
.venv-studio/bin/langgraph dev
```

The server starts at `http://127.0.0.1:2024`. Open the Studio UI at:

```
https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
```

You'll see the `story_graph` with all nodes and conditional edges:

```
START → preflight → budget_check ──(ok)──→ agent_dispatch → validate ──(success)──→ commit → finalize → END
                          │                                       │
                     (exceeded)                               (escalated)
                          └──────────────────────────────────────┴──→ finalize → END
                                                    ↑(retry)
                                          validate ─┘ → budget_check
```

> A free [LangSmith](https://smith.langchain.com) account is required to use the Studio UI. The local API server itself runs without one.

---

## LangSmith Tracing

LangGraph has built-in support for [LangSmith](https://smith.langchain.com) — LangChain's cloud observability platform. When enabled, every graph invocation is recorded as a trace you can inspect in the LangSmith web UI: node inputs/outputs, state transitions, timing, and token usage.

### Setup

1. Create a free account at [smith.langchain.com](https://smith.langchain.com)
2. Go to **Settings → API Keys** and create an API key
3. Set environment variables (add to your `.env` file or shell profile):

```bash
export LANGCHAIN_TRACING_V2=true
export LANGCHAIN_API_KEY="lsv2_pt_..."
export LANGCHAIN_PROJECT="arcwright-ai"  # optional — names your project in the UI
```

The next `python -m arcwright_ai dispatch` will send traces automatically — no code changes required.

To disable, unset `LANGCHAIN_TRACING_V2` or set it to `false`. Tracing is off by default.

> **Note:** LangSmith tracing is independent of the local `.arcwright-ai/runs/` artifacts, which are always written regardless.

---

## Development

All development commands use the main `.venv` (Python 3.14):

```bash
# Install dev dependencies
pip install -e ".[dev]"
# Prefer explicit venv invocation to avoid interpreter mismatch:
.venv/bin/pip install -e ".[dev]"

# Run tests
.venv/bin/python -m pytest -q

# Lint
.venv/bin/ruff check .
.venv/bin/ruff format --check .

# Type check
.venv/bin/python -m mypy --strict src/

# All quality gates in one pass
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/python -m mypy --strict src/ && .venv/bin/python -m pytest -q

# Install local git hooks (recommended)
.venv/bin/pre-commit install
.venv/bin/pre-commit install --hook-type pre-push

# Run hooks manually across the repository
.venv/bin/pre-commit run --all-files
```

### Python version note

The project targets Python 3.11+ and is developed against 3.14. The `.venv-studio` venv (Python 3.13) is **only** for running `langgraph dev`. Do not use it for tests or type checking — results may differ.

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'arcwright_ai'`**

The venv's editable install link may be stale or was not processed correctly on Python 3.14. Re-install:

```bash
cd arcwright-ai/
.venv/bin/pip install -e .
```

This rewrites the `.pth` file. Verify with:

```bash
.venv/bin/python -c "import arcwright_ai; print(arcwright_ai.__file__)"
```

**`langgraph dev` fails with `Required package 'langgraph-api' is not installed`**

You're using the main `.venv` (Python 3.14). Use `.venv-studio` instead:

```bash
.venv-studio/bin/langgraph dev
```

**Story dispatched but files don't match what validation expected**

Check `.arcwright-ai/config.yaml` in the target project. The `methodology.artifacts_path` must point to the directory containing your BMAD planning artifacts (PRD, architecture, epics). Default is `_bmad-output`; adjust if your project uses `_spec/planning-artifacts` or another path.

**Dev agent File List is consistently incomplete or doesn't match `git diff` output after a BMAD update**

The dev-story workflow in this project includes a custom enhancement to `workflow.md` — the Step 9 git diff File List reconciliation audit. This customization lives in `_bmad/bmm/workflows/4-implementation/dev-story/` — a directory that is gitignored and gets overwritten by BMAD framework updates. (Other features that were previously custom — review-continuation detection, `[AI-Review]` follow-up handling, enhanced checklist — are now stock in BMAD 6.1.)

If you have recently run a BMAD update and agent File Lists are again going unaudited, the Step 9 customization was likely overwritten. Re-apply it manually — see the **BMAD Workflow Customizations** section in the root [`README.md`](../README.md#bmad-workflow-customizations) for details.
