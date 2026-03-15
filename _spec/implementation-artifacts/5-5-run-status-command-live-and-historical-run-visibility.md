# Story 5.5: Run Status Command — Live & Historical Run Visibility

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer monitoring an in-progress run or reviewing past runs,
I want a status command that shows run state, story progress, and cost at a glance,
so that I can check on overnight runs without digging through files.

## Acceptance Criteria (BDD)

1. **Given** `cli/status.py` implementing the `arcwright-ai status` command **When** the developer runs `arcwright-ai status` **Then** it reads the latest `run.yaml` (via `list_runs()` → most recent → `get_run_status()`) and displays: run ID, status (running/completed/halted/timed_out), stories completed/pending/failed (with story slugs), elapsed time (computed from `start_time` to now or to last story `completed_at`), cost consumed (formatted human-readable from budget dict). Output goes to stderr per D8.

2. **Given** the `arcwright-ai status <run-id>` command **When** the developer runs `arcwright-ai status abc-123` **Then** it shows the same information for that specific historical run via `get_run_status(project_root, run_id)`. If the run-id is not found (`RunError`), display a clear error message: `"Run not found: <run-id>. Use 'arcwright-ai status' to list recent runs."` and exit with code 1.

3. **Given** the `arcwright-ai status` command **When** there are no active or historical runs (empty `.arcwright-ai/runs/` or directory does not exist) **Then** display a clear message: `"No runs found. Use 'arcwright-ai dispatch' to start a run."` and exit with code 0.

4. **Given** a run is in progress **When** `arcwright-ai status` is called **Then** the status reflects live state from the current `run.yaml` (not cached) — every invocation re-reads `run.yaml` from disk via `get_run_status()`.

5. **Given** the status command output **When** displayed to the user **Then** output uses `typer.echo(..., err=True)` for all output per D8 (Rich/Typer formatting to stderr). Story slugs are displayed with their status. Budget/cost fields use the same human-readable formatting as `summary.py` (`_format_budget_field` pattern).

6. **Given** story implementation is complete **When** `arcwright-ai status` is registered in `cli/app.py` **Then** `app.command(name="status")(status_command)` is present, the import is updated, and the command appears in `arcwright-ai --help`.

7. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

8. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

9. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

10. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass (572 total at latest count).

11. **Given** new tests in `tests/test_cli/test_status.py` **When** the test suite runs **Then** tests cover:
    (a) `status_command` with no run-id argument, one existing run → displays latest run info to stderr;
    (b) `status_command` with no run-id argument, no runs → displays "No runs found" message;
    (c) `status_command` with specific run-id → displays that run's info;
    (d) `status_command` with invalid run-id → displays "Run not found" error, exit code 1;
    (e) `status_command` displays correct story breakdown: completed, pending, failed counts with slugs;
    (f) `status_command` displays budget/cost info from `run.yaml` budget dict;
    (g) `status_command` with a running run shows status "running";
    (h) `status_command` with a halted run shows status "halted" with halt context;
    (i) `status_command` all output goes to stderr (capture `capsys.err`).

## Tasks / Subtasks

- [x] Task 1: Implement `status_command` in `cli/status.py` (AC: #1, #2, #3, #4, #5)
  - [x] 1.1: Add `status_command` function with Typer-compatible signature: `status_command(run_id: Annotated[str | None, typer.Argument(help="...")] = None, path: str = typer.Option(".", ...)) -> None`
  - [x] 1.2: When `run_id` is `None` → call `list_runs(project_root)` to get the latest run. If empty list → display "No runs found" message, `raise typer.Exit(0)`.
  - [x] 1.3: When `run_id` is `None` and runs exist → take the first entry from `list_runs()` (most recent, already sorted descending) and call `get_run_status(project_root, run_summary.run_id)`.
  - [x] 1.4: When `run_id` is provided → call `get_run_status(project_root, run_id)` directly. Catch `RunError` → display "Run not found" message, `raise typer.Exit(1)`.
  - [x] 1.5: Display formatted output to stderr via `typer.echo(..., err=True)`: run ID, status, start time, elapsed time, story breakdown (completed/pending/failed with slugs), cost summary.
  - [x] 1.6: Compute elapsed time: parse `start_time` ISO 8601 → `datetime`, diff against `datetime.now(tz=UTC)` for running runs or last `completed_at` for finished runs. Format as human-readable `HH:MM:SS` or `Xh Ym Zs`.
  - [x] 1.7: Story breakdown: iterate `run_status.stories`, categorize by status into completed (status in `{"success", "completed", "done"}`), failed (status in `{"failed", "halted", "escalated"}`), and pending (everything else). Display counts and slug lists.
  - [x] 1.8: Cost display: read `run_status.budget` dict for `invocation_count`, `total_tokens`, `estimated_cost`. Format using same pattern as `_format_budget_field` (inline the logic — don't import from `output/summary.py` to avoid DAG violation).

- [x] Task 2: Add necessary imports to `cli/status.py` (AC: #6)
  - [x] 2.1: Add `import asyncio` for wrapping async calls
  - [x] 2.2: Add `from datetime import UTC, datetime` for elapsed time computation
  - [x] 2.3: Add `from typing import Annotated` for Typer argument annotation
  - [x] 2.4: Add `from arcwright_ai.core.constants import EXIT_VALIDATION` (for exit code 1)
  - [x] 2.5: Add `from arcwright_ai.core.exceptions import RunError`
  - [x] 2.6: Add `from arcwright_ai.output.run_manager import RunStatusValue, get_run_status, list_runs`
  - [x] 2.7: Update `__all__` to include `"status_command"` (maintain alphabetical order)

- [x] Task 3: Register `status` command in `cli/app.py` (AC: #6)
  - [x] 3.1: Add `status_command` to the import from `arcwright_ai.cli.status`
  - [x] 3.2: Add `app.command(name="status")(status_command)` alongside existing command registrations

- [x] Task 4: Create tests in `tests/test_cli/test_status.py` (AC: #10, #11)
  - [x] 4.1: Test `status_command()` — no run-id, one existing run → displays run info
  - [x] 4.2: Test `status_command()` — no run-id, no runs → "No runs found" message
  - [x] 4.3: Test `status_command(run_id="abc")` — valid run-id → displays specific run info
  - [x] 4.4: Test `status_command(run_id="invalid")` — invalid run-id → "Run not found", exit code 1
  - [x] 4.5: Test story breakdown — correct categorization of completed/pending/failed
  - [x] 4.6: Test budget/cost display — invocation_count, total_tokens, estimated_cost formatted
  - [x] 4.7: Test running run → status "running" displayed
  - [x] 4.8: Test halted run → status "halted" displayed
  - [x] 4.9: Test all output goes to stderr (verify via mock_echo err=True)

- [x] Task 5: Run quality gates (AC: #7, #8, #9, #10)
  - [x] 5.1: `ruff check .` — zero violations against FULL repository
  - [x] 5.2: `ruff format --check .` — zero formatting issues
  - [x] 5.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 5.4: `pytest` — all tests pass (585 total: 572 existing + 13 new)
  - [x] 5.5: Verify Google-style docstrings on all public functions
  - [x] 5.6: Verify `git diff --name-only` matches Dev Agent Record file list

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Elapsed time for terminal runs can be overstated because `last_completed_at` is only collected from `_COMPLETED_STATUSES`; halted/failed stories with `completed_at` are excluded. Update elapsed-end selection to use the latest valid story completion timestamp regardless of category. [src/arcwright_ai/cli/status.py]
- [x] [AI-Review][MEDIUM] `completed_at` ordering currently uses lexicographic string comparison (`entry.completed_at > last_completed_at`) instead of parsed datetimes; this can misorder timestamps with differing offsets/format variants. Compare parsed datetimes. [src/arcwright_ai/cli/status.py]
- [x] [AI-Review][MEDIUM] Halted-run test validates `result.output` instead of `result.stderr`, so it does not enforce D8 stderr behavior for that path. Assert against `result.stderr`. [tests/test_cli/test_status.py]
- [x] [AI-Review][MEDIUM] Missing explicit `timed_out` status scenario test for `status_command`; add coverage for output and categorization behavior. [tests/test_cli/test_status.py]
- [x] [AI-Review][MEDIUM] Dev Agent Record file list does not include `_spec/implementation-artifacts/sprint-status.yaml` even though it is changed in git, creating story/git discrepancy. Reconcile File List entries before marking done. [_spec/implementation-artifacts/sprint-status.yaml]

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 5.5 adds code ONLY to `cli/status.py` and `cli/app.py`. The status command calls `output/run_manager.py` functions (`get_run_status`, `list_runs`) and uses types from `core/`. This is a valid dependency: `cli → output → core`. No DAG violations.

**FR31 — Run Visibility**: "Developer can check current or last run status via CLI, including completion state and cost summary." The `output/run_manager.py` module already provides `get_run_status(project_root, run_id) → RunStatus` and `list_runs(project_root) → list[RunSummary]` — both are fully implemented and tested. Story 5.5 is a thin CLI wrapper over these existing functions.

**D8 — Logging & Observability**: "User output: Formatted text (Rich/Typer) → Human at terminal → stderr." ALL `status_command` output MUST go through `typer.echo(..., err=True)`. This is the established pattern used by `init_command` and `validate_setup_command` in the same file.

**Architecture File Mapping**: `cli/status.py` is explicitly mapped as the home for `arcwright init, status, validate-setup, clean` commands. [Source: architecture.md — Complete Project Tree]

**PRD Command Table**: `arcwright-ai status [--run RUN-ID]` — Current/last run status (or specific run), includes cost summary. Note the PRD uses `--run RUN-ID` flag syntax but the epics use `arcwright-ai status <run-id>` positional argument syntax. The positional argument approach is more natural for Typer and consistent with the single-value lookup pattern. Use positional `typer.Argument` with default `None`.

**Decision 6 — Exit Codes**: Exit 0 on success. Exit 1 for "run not found" (maps to EXIT_VALIDATION=1 which is the general "user-fixable" error code). The `RunError` exception maps to EXIT_INTERNAL=5 in the D6 taxonomy, but for a status lookup failure, exit 1 is more appropriate (per AC #6 in the epics). Handle `RunError` explicitly in the status command and exit with code 1.

### Current State Analysis — What Already Works

1. **`get_run_status(project_root, run_id) → RunStatus`** in `output/run_manager.py` — Reads `run.yaml`, validates via Pydantic, returns typed model with `run_id`, `status` (RunStatusValue enum), `start_time` (ISO 8601 str), `config_snapshot` (dict), `budget` (dict with `invocation_count`, `total_tokens`, `estimated_cost`, `max_cost`), `stories` (dict[str, StoryStatusEntry]), `last_completed_story` (str | None). Raises `RunError` if run not found.

2. **`list_runs(project_root) → list[RunSummary]`** in `output/run_manager.py` — Scans `.arcwright-ai/runs/`, returns lightweight summaries sorted by `start_time` descending (most recent first). Each `RunSummary` has `run_id`, `status`, `start_time`, `story_count`, `completed_count`. Returns empty list if no runs exist. Silently skips malformed directories.

3. **`RunStatusValue` enum** — `QUEUED`, `RUNNING`, `COMPLETED`, `HALTED`, `TIMED_OUT`.

4. **`StoryStatusEntry` model** — `status: str`, `retry_count: int`, `started_at: str | None`, `completed_at: str | None`.

5. **`RunStatus` model** — `run_id: str`, `status: RunStatusValue`, `start_time: str`, `config_snapshot: dict`, `budget: dict`, `stories: dict[str, StoryStatusEntry]`, `last_completed_story: str | None`.

6. **Existing CLI patterns in `cli/status.py`** — `init_command` and `validate_setup_command` both use `typer.echo(..., err=True)` for output and `raise typer.Exit(code)` for exit codes. Both accept `--path` option for project root. Follow the same patterns.

7. **`_format_budget_field` in `summary.py`** — Returns `"N/A"` for zero/null values, string representation otherwise. DO NOT import this from `output/summary.py` — this would work for the DAG (cli → output) but the function is private (underscore-prefixed). Instead, inline the same formatting logic.

### Relationship to Other Stories in Epic 5

- **Story 5.1 (done):** Full epic dispatch — creates `run.yaml` with story entries and budget state. The status command reads these.
- **Story 5.2 (done):** `HaltController` — sets run status to `halted` in `run.yaml`. Status command displays halted runs correctly.
- **Story 5.3 (done):** Resume controller — creates new run on resume. Status command shows both the halted and resumed runs.
- **Story 5.4 (done):** Enhanced halt reports — improved `summary.md` content. Status command reads `run.yaml` only (not `summary.md`), but the improved halt artifacts benefit the developer who then reads summary after checking status.
- **Story 5.5 (this):** CLI thin wrapper over existing `run_manager.py` functions.

### Existing Code to Reuse — DO NOT REINVENT

- **`get_run_status(project_root, run_id) → RunStatus`** from `output/run_manager.py` — CALL directly. Do NOT re-read `run.yaml` manually.
- **`list_runs(project_root) → list[RunSummary]`** from `output/run_manager.py` — CALL directly. Do NOT scan `.arcwright-ai/runs/` manually.
- **`RunStatus`**, **`RunSummary`**, **`StoryStatusEntry`**, **`RunStatusValue`** from `output/run_manager.py` — USE these typed models. Do NOT create new models.
- **`RunError`** from `core/exceptions.py` — CATCH for invalid run-id handling.
- **`typer.echo(..., err=True)` pattern** — REUSE from existing `init_command` and `validate_setup_command` in the same file.
- **`typer.Exit(code)` pattern** — REUSE from existing commands.
- **`asyncio.run()`** — WRAP async `get_run_status` and `list_runs` calls (these are async functions; the CLI command is sync). Follow the same pattern as `dispatch_command` which wraps `_dispatch_epic_async()` via `asyncio.run()`.

### CRITICAL: Async Wrapping in Sync CLI Command

Both `get_run_status()` and `list_runs()` are async functions. The Typer CLI command is synchronous. You MUST wrap async calls with `asyncio.run()`. Two approaches:

**Approach A (Preferred — matches dispatch pattern):** Create a private `async def _status_async(project_root, run_id)` function that does all the async work, then call `asyncio.run(_status_async(...))` from the sync `status_command`.

**Approach B (Simpler):** Use `asyncio.run()` inline for each async call. This is acceptable for a simple command with only 1-2 async calls.

Choose Approach A if the status formatting logic is complex enough to benefit from the separation. Choose Approach B if it's straightforward.

### CRITICAL: Do NOT Import Private Functions from Other Modules

The `_format_budget_field` function in `output/summary.py` is private (underscore-prefixed). Even though the import DAG allows `cli → output`, do NOT import private symbols. Inline the formatting logic:

```python
def _format_cost_value(value: Any) -> str:
    """Format a budget/cost value for display."""
    if value is None or value == 0 or value == "0" or value == "":
        return "N/A"
    return str(value)
```

### CRITICAL: Story Status Categorization

The `StoryStatusEntry.status` field is a plain `str`, not a `RunStatusValue` enum. Story statuses in `run.yaml` use TaskState values: `"queued"`, `"running"`, `"success"`, `"failed"`, `"halted"`, `"escalated"`. Categorize as follows:

```python
_COMPLETED_STATUSES = {"success", "completed", "done"}
_FAILED_STATUSES = {"failed", "halted", "escalated"}
# Everything else is "pending" (queued, running, validating, etc.)
```

### CRITICAL: Elapsed Time Computation

`RunStatus.start_time` is an ISO 8601 string (e.g., `"2026-03-06T14:30:52.123456+00:00"`). Parse with `datetime.fromisoformat()`. For running runs, compute elapsed as `datetime.now(tz=UTC) - start_time`. For completed/halted runs, use the maximum `completed_at` value from stories (if available) or fall back to current time. Format as `"Xh Ym Zs"`.

### Testing Patterns

- **Mock `list_runs()` at callsite**: `monkeypatch.setattr("arcwright_ai.cli.status.list_runs", ...)` — returns `list[RunSummary]` or empty list.
- **Mock `get_run_status()` at callsite**: `monkeypatch.setattr("arcwright_ai.cli.status.get_run_status", ...)` — returns `RunStatus` or raises `RunError`.
- **Use `typer.testing.CliRunner`**: Invoke `status_command` via the Typer test runner to capture output and exit codes. Previous CLI tests in the project may use this or direct function calls.
- **Use `tmp_path` fixture** for project root.
- **Capture stderr output**: `CliRunner` can capture stderr. Or use `capsys.readouterr().err`.
- **Build synthetic `RunStatus` and `RunSummary`**: Create with realistic data for each test scenario.
- **Mock at callsite, not source module** — per established project convention.
- **Check existing test files** for patterns: `tests/test_cli/test_status.py` already exists with tests for `init_command` and `validate_setup_command`. Add new tests alongside existing ones.

### Implementation Details

#### `status_command` Signature

```python
def status_command(
    run_id: Annotated[str | None, typer.Argument(help="Run ID to inspect. Shows latest run if omitted.")] = None,
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
) -> None:
```

#### Display Format (D8-Compliant)

```
Arcwright AI — Run Status
──────────────────────────

  Run ID:    20260306-143052-a1b2c3
  Status:    completed
  Started:   2026-03-06T14:30:52+00:00
  Elapsed:   2h 15m 32s

Stories (5 total):
  ✓ 3 completed: setup-scaffold, core-types, config-system
  ✗ 1 failed: agent-invoker
  ◦ 1 pending: validation-pipeline

Cost:
  Invocations: 12
  Tokens:      145,230
  Est. Cost:   $3.42
```

#### Output Module `__all__` Impact

No changes to `output/__init__.py` or `output/run_manager.py` — these modules are unchanged.

#### `cli/status.py` `__all__` Update

```python
__all__: list[str] = [
    "init_command",
    "status_command",
    "validate_setup_command",
]
```

### Project Structure Notes

Files modified by this story:
```
src/arcwright_ai/cli/status.py          # MODIFIED: add status_command, new imports
src/arcwright_ai/cli/app.py             # MODIFIED: register status command, update import
tests/test_cli/test_status.py           # MODIFIED: add tests for status_command
```

Files NOT modified (confirmed unchanged):
```
src/arcwright_ai/output/run_manager.py  # Unchanged — all needed functions exist
src/arcwright_ai/output/summary.py      # Unchanged — status command reads run.yaml not summary.md
src/arcwright_ai/cli/dispatch.py        # Unchanged — no new dispatch behavior
src/arcwright_ai/cli/halt.py            # Unchanged — no halt changes
src/arcwright_ai/cli/__init__.py        # Unchanged — already exports app
src/arcwright_ai/engine/                # Unchanged — no engine changes
src/arcwright_ai/core/                  # Unchanged — all needed types/constants exist
```

### Known Pitfalls from Epics 1-5.4

1. **`__all__` ordering must be alphabetical** — ruff enforces this. `"status_command"` goes between `"init_command"` and `"validate_setup_command"`.
2. **No aspirational exports** — only export symbols that actually exist.
3. **`from __future__ import annotations`** at the top of every module.
4. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just changed files).
5. **File list in Dev Agent Record must match actual git changes**.
6. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
7. **Two-venv environment** — `.venv` (Python 3.14) for dev/test, `.venv-studio` (Python 3.13) for LangGraph Studio.
8. **Mock at callsite, not source module** — per project convention.
9. **All user output to stderr** — `typer.echo(..., err=True)` per D8.
10. **Exit codes**: 0 = success, 1 = run not found (per AC). Do NOT use `EXIT_INTERNAL=5` for "run not found" — that's a user-facing lookup, not an internal error.
11. **`asyncio.run()` for async wrapping** — the Typer command is sync. Wrap async calls properly.
12. **Decimal cost formatting** — `estimated_cost` may be a `str` or `Decimal` in the budget dict (serialized via `_serialize_budget` in run_manager). Handle both.

### Git Intelligence

Recent commits (last 5):
1. `feat(story-5.4): halt and resume integration with run artifacts` — enhanced halt reports with AC IDs, combined summaries
2. `feat(story-5.3): create story — resume controller resume halted epic from failure point` — resume controller, budget carry-forward
3. `chore: mark story 5-2 done` — sprint status update
4. `feat(story-5.2): halt controller — graceful halt on unrecoverable failure` — HaltController class
5. `feat(epic-5): complete story 5-1 epic dispatch CLI-to-engine pipeline` — full epic dispatch

Patterns established:
- CLI commands are sync wrappers over async domain functions
- All user output goes to stderr via `typer.echo(..., err=True)`
- `typer.Exit(code)` is raised (not returned) for exit codes
- Tests mock at callsite using `monkeypatch.setattr`
- `--path` option available on all CLI commands for project root override

### References

- [Source: _spec/planning-artifacts/epics.md — Epic 5, Story 5.5]
- [Source: _spec/planning-artifacts/prd.md — FR31: Run status via CLI]
- [Source: _spec/planning-artifacts/prd.md — MVP CLI Command Table]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy (exit codes)]
- [Source: _spec/planning-artifacts/architecture.md — Decision 8: Logging & Observability (stderr output)]
- [Source: _spec/planning-artifacts/architecture.md — Complete Project Tree (cli/status.py maps to init, status, validate-setup, clean)]
- [Source: _spec/planning-artifacts/architecture.md — FR31 → output/run_manager.py mapping]
- [Source: _spec/planning-artifacts/architecture.md — Architectural Boundary 1: CLI ↔ Engine]
- [Source: src/arcwright_ai/output/run_manager.py — get_run_status, list_runs, RunStatus, RunSummary, StoryStatusEntry, RunStatusValue]
- [Source: src/arcwright_ai/cli/status.py — init_command, validate_setup_command patterns (typer.echo err=True, typer.Exit)]
- [Source: src/arcwright_ai/cli/app.py — Typer app, command registration patterns]
- [Source: src/arcwright_ai/cli/dispatch.py — asyncio.run() wrapping pattern for async functions]
- [Source: src/arcwright_ai/output/summary.py — _format_budget_field pattern for cost display]
- [Source: src/arcwright_ai/core/constants.py — EXIT_SUCCESS=0, EXIT_VALIDATION=1]
- [Source: src/arcwright_ai/core/exceptions.py — RunError]
- [Source: src/arcwright_ai/core/types.py — BudgetState fields (invocation_count, total_tokens, estimated_cost, max_cost)]
- [Source: _spec/implementation-artifacts/5-4-halt-and-resume-integration-with-run-artifacts.md — previous story learnings and patterns]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No debug log entries — implementation proceeded without blockers.

### Completion Notes List

- Implemented `status_command` in `cli/status.py` as a sync Typer command wrapping `async def _status_async()` via `asyncio.run()` (Approach A from Dev Notes).
- Added `_format_cost_value()` helper (inlined `_format_budget_field` logic per DAG constraint — no import from `output/summary.py`).
- Added `_format_elapsed()` helper that parses ISO 8601 timestamps and formats elapsed duration as `Xh Ym Zs`.
- Story categorization uses `_COMPLETED_STATUSES` and `_FAILED_STATUSES` frozensets as specified.
- All output routed to stderr via `typer.echo(..., err=True)` per D8.
- Used `from None` on `raise typer.Exit` inside `except RunError` to suppress exception chain (B904).
- Registered `status` command in `cli/app.py` alongside existing commands.
- Created `tests/test_cli/test_status.py` with 13 tests covering all AC scenarios.
- Tests use `monkeypatch.setattr` at callsite (`arcwright_ai.cli.status.list_runs`, `arcwright_ai.cli.status.get_run_status`) per project convention.
- Tests for stderr verification mock `typer.echo` and invoke `_status_async` directly (bypass CliRunner which mixes stdout/stderr).
- Addressed AI review follow-ups: terminal elapsed-time endpoint now uses latest parsed `completed_at` across stories, not just completed statuses.
- Addressed AI review follow-ups: replaced lexicographic timestamp max logic with datetime-based comparison.
- Addressed AI review follow-ups: corrected halted-status assertion to use stderr and added explicit timed_out status test.
- Re-ran quality gates and full suite after fixes: 585 tests pass. Zero ruff, format, and mypy violations.

### File List

- `src/arcwright_ai/cli/status.py` — MODIFIED: added `status_command`, `_status_async`, `_format_cost_value`, `_format_elapsed`, `_COMPLETED_STATUSES`, `_FAILED_STATUSES`; updated imports and `__all__`
- `src/arcwright_ai/cli/app.py` — MODIFIED: added `status_command` import and `app.command(name="status")` registration
- `tests/test_cli/test_status.py` — CREATED: 13 tests covering all AC scenarios
- `_spec/implementation-artifacts/sprint-status.yaml` — MODIFIED: story 5.5 tracking status transitions (review workflow sync)

### Change Log

- 2026-03-06: Story 5.5 — Implemented `arcwright-ai status` CLI command with live/historical run visibility (run ID, status, elapsed time, story breakdown, cost summary). Added 13 tests. All quality gates pass.
- 2026-03-06: Senior Developer Review (AI) completed. 1 HIGH and 4 MEDIUM issues identified; story moved to `in-progress` and follow-up tasks added.
- 2026-03-06: Implemented and validated all AI review follow-up fixes; story moved back to `review`.

## Senior Developer Review (AI)

### Reviewer

Ed (AI Code Review)

### Date

2026-03-06

### Outcome

Changes Requested

### Summary

- Verified implementation against ACs, story tasks, and git state.
- Confirmed command registration and core run-status behavior are implemented.
- Re-ran quality gates and tests: `ruff check .`, `ruff format --check .`, `.venv/bin/python -m mypy --strict src/`, and `pytest` (585 passed).
- Identified correctness and coverage gaps that block `done` status.

### Findings

1. **[HIGH] Elapsed time end-point can be wrong for halted/failed terminal runs**  
  In `_status_async`, `last_completed_at` is only updated inside the `_COMPLETED_STATUSES` branch. For terminal runs where the latest completed timestamp belongs to a failed/halted/escalated story, elapsed falls back to now, overstating historical duration.  
  Evidence: `src/arcwright_ai/cli/status.py` (`if st in _COMPLETED_STATUSES` and elapsed calculation using `last_completed_at` only).

2. **[MEDIUM] Timestamp ordering uses string comparison, not datetime comparison**  
  `entry.completed_at > last_completed_at` compares ISO strings lexicographically. This is brittle across offsets/format variants and can choose the wrong maximum timestamp.  
  Evidence: `src/arcwright_ai/cli/status.py` line with `entry.completed_at > last_completed_at`.

3. **[MEDIUM] Halted-run stderr behavior is not properly validated in tests**  
  `test_status_halted_run_shows_halted_status` asserts on `result.output` instead of `result.stderr`, leaving D8 stderr compliance unverified for that case.  
  Evidence: `tests/test_cli/test_status.py` halted test assertion line.

4. **[MEDIUM] Missing explicit `timed_out` status test case**  
  No dedicated test validates display behavior for `RunStatusValue.TIMED_OUT`, despite CLI support and AC status set.  
  Evidence: no `timed_out` scenario present in `tests/test_cli/test_status.py`.

5. **[MEDIUM] Story/git file-list discrepancy**  
  Git shows `_spec/implementation-artifacts/sprint-status.yaml` modified, but Dev Agent Record File List only documents three code/test files.  
  Evidence: `git diff --name-only` vs story `### File List` section.

### Re-Review (AI) — 2026-03-06

#### Outcome

Approved

#### Resolution Summary

- Re-ran adversarial checks after follow-up fixes; no remaining HIGH or MEDIUM issues.
- Verified no story/git discrepancies in current working tree.
- Confirmed all prior findings are resolved in code/tests and documented as completed in Review Follow-ups.
- Validation rerun passed: `pytest tests/test_cli/test_status.py` (13 passed), `ruff check .`, `ruff format --check .`, `mypy --strict src/`, and full suite `pytest` (585 passed).

#### Final Decision

Story 5.5 is accepted and moved to `done`.
