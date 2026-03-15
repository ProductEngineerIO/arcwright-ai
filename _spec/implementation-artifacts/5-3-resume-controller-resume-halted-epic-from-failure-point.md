# Story 5.3: Resume Controller — Resume Halted Epic from Failure Point

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer who fixed the issue that caused a halt,
I want to resume the epic from the failure point without re-running completed stories,
so that I don't waste time or money re-executing work that already passed.

## Acceptance Criteria (BDD)

1. **Given** `cli/dispatch.py` accepts a `--resume` flag on `--epic` dispatch **When** the developer runs `arcwright-ai dispatch --epic EPIC-3 --resume` **Then** it finds the most recent run for the specified epic by scanning `.arcwright-ai/runs/` and matching runs whose `run.yaml` contains story slugs prefixed with the epic number. If multiple runs match, the one with the most recent `start_time` is selected.

2. **Given** a prior halted run is found **When** the resume controller reads `run.yaml` via `output/run_manager.get_run_status()` **Then** it extracts: `last_completed_story` (the slug of the last successfully completed story), `status` (must be `RunStatusValue.HALTED`), `stories` dict (each story's status), and `budget` (accumulated budget state at halt time).

3. **Given** the halted run's `last_completed_story` is known **When** the resume controller rebuilds the story list **Then** it resolves all stories for the epic via `_find_epic_stories()` (same as normal dispatch), identifies which stories are already completed (all stories whose `run.yaml` entry has `status == "success"`), and builds the dispatch list containing only incomplete stories (starting from the first non-`"success"` story). Completed stories are excluded from the graph execution loop entirely.

4. **Given** the halted story's worktree may still exist from the failed attempt **When** the resume controller prepares for re-execution **Then** worktree handling is deferred to Story 6.2 (Worktree Manager). In MVP, worktrees are not yet implemented, so no worktree cleanup is needed. The halted story gets a fresh `StoryState` with `status=TaskState.QUEUED` — it is re-executed from scratch, not resumed mid-story.

5. **Given** budget state from the previous run **When** the resume controller initializes budget for remaining stories **Then** budget state is carried forward from the previous run's `budget` field in `run.yaml`. The first remaining story's `BudgetState` is initialized with: `invocation_count`, `total_tokens`, `estimated_cost` from the previous run's accumulated budget, and `max_invocations=0`, `max_cost=Decimal(str(config.limits.cost_per_run))`. This ensures the run-level cost ceiling is enforced across the entire epic (original run + resumed portion).

6. **Given** `--resume` is used on an already-completed run (status == `RunStatusValue.COMPLETED`) **When** the resume controller evaluates the run status **Then** it outputs an informative message: "Run <run-id> for epic <epic-spec> already completed. All stories passed." and returns exit code 0 per NFR19 idempotency.

7. **Given** `--resume` is used without a prior run for the specified epic **When** no matching run is found **Then** it outputs a clear error: "No previous run found for epic <epic-spec>. Use `arcwright-ai dispatch --epic <epic-spec>` without --resume." and returns exit code 3 (`EXIT_CONFIG`).

8. **Given** the resume controller has identified the remaining stories **When** the dispatch loop executes **Then** a new `run_id` is generated for the resumed dispatch (new run directory, new `run.yaml`). The new run's `run.yaml` includes only the remaining stories (not already-completed ones). The dispatch loop proceeds exactly as normal epic dispatch (from Story 5.1): sequential execution, budget carry-forward between stories, halt on non-SUCCESS, structured logging. The `HaltController` is initialized with the new `run_id`.

9. **Given** the `--resume` flag is combined with `--yes` **When** the resume controller runs **Then** the pre-dispatch confirmation is skipped (same as normal `--yes` behavior). Without `--yes`, the resume-specific confirmation shows: original run ID, stories already completed (skipped), stories to dispatch (remaining), carried-forward budget state.

10. **Given** the `--resume` flag is combined with `--story` **When** the CLI validates arguments **Then** it outputs an error: "Error: --resume can only be used with --epic, not --story." and returns exit code 1.

11. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

12. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

14. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass (530 total at latest count).

15. **Given** new/updated tests in `tests/test_cli/test_dispatch.py` **When** the test suite runs **Then** tests cover:
    (a) `_find_latest_run_for_epic()` — finds most recent halted run when multiple runs exist;
    (b) `_find_latest_run_for_epic()` — returns None when no matching run exists;
    (c) `_find_latest_run_for_epic()` — filters by epic number (ignores runs for other epics);
    (d) `_dispatch_epic_resume_async()` — skips completed stories, dispatches only remaining;
    (e) `_dispatch_epic_resume_async()` — budget carry-forward from halted run;
    (f) `_dispatch_epic_resume_async()` — already-completed run → exit 0 with informative message;
    (g) `_dispatch_epic_resume_async()` — no prior run → exit 3 with error message;
    (h) `_dispatch_epic_resume_async()` — 5-story epic, halt at story 3, resume skips stories 1-2, executes 3-5;
    (i) `--resume` with `--story` → error exit code 1;
    (j) `--resume` with `--yes` → skips confirmation;
    (k) New `run_id` generated for resumed dispatch (different from original);
    (l) `HaltController` initialized with new `run_id` for resumed dispatch.

## Tasks / Subtasks

- [x] Task 1: Add `--resume` flag to `dispatch_command()` (AC: #10)
  - [x] 1.1: Add `resume: Annotated[bool, typer.Option("--resume", help="Resume a halted epic dispatch from the failure point")] = False` to `dispatch_command()` parameters
  - [x] 1.2: Add validation: if `resume` is True and `story` is not None → error "Error: --resume can only be used with --epic, not --story." with exit code 1
  - [x] 1.3: Pass `resume` flag through to `_dispatch_epic_async()` (add `resume: bool = False` parameter) OR create a separate `_dispatch_epic_resume_async()` function that `_dispatch_epic_async()` delegates to when `resume=True`

- [x] Task 2: Implement `_find_latest_run_for_epic()` helper (AC: #1, #7)
  - [x] 2.1: Create `_find_latest_run_for_epic(project_root: Path, epic_spec: str) -> tuple[str, RunStatus] | None` in `cli/dispatch.py`
  - [x] 2.2: Use `list_runs(project_root)` from `output/run_manager` to get all runs sorted by `start_time` descending
  - [x] 2.3: For each run (most recent first), call `get_run_status(project_root, run.run_id)` to load full run data
  - [x] 2.4: Check if the run's `stories` dict contains any story slug prefixed with the epic number (e.g., keys matching `f"{epic_num}-"`)
  - [x] 2.5: Return the first (most recent) matching run as `(run_id, RunStatus)`, or `None` if no match

- [x] Task 3: Implement resume logic in `_dispatch_epic_async()` or separate `_dispatch_epic_resume_async()` (AC: #2, #3, #4, #5, #6, #8, #9)
  - [x] 3.1: When `resume=True`, call `_find_latest_run_for_epic()` to find the prior run
  - [x] 3.2: If no prior run found → output error message (AC#7), return `EXIT_CONFIG`
  - [x] 3.3: If prior run status is `COMPLETED` → output informative message (AC#6), return `EXIT_SUCCESS`
  - [x] 3.4: If prior run status is `HALTED` → extract `last_completed_story`, `stories` dict, `budget` from `RunStatus`
  - [x] 3.5: Resolve all epic stories via `_find_epic_stories()` — same as normal dispatch
  - [x] 3.6: Determine completed story slugs from the prior run's `stories` dict (entries with `status == "success"`)
  - [x] 3.7: Filter the story list to only include stories NOT in the completed set — this is the remaining stories list
  - [x] 3.8: If no remaining stories → all stories were actually completed despite HALTED status (edge case); output informative message, return `EXIT_SUCCESS`
  - [x] 3.9: Reconstruct `BudgetState` from the prior run's `budget` dict (parse `estimated_cost` back to `Decimal`, handle `max_cost` similarly)
  - [x] 3.10: Show resume-specific confirmation (unless `skip_confirm=True`): original run ID, completed stories (skipped), remaining stories, carried-forward budget
  - [x] 3.11: Generate a NEW `run_id` for the resumed dispatch — create a new run directory with only the remaining stories
  - [x] 3.12: Proceed with the standard dispatch loop from Story 5.1: sequential execution, budget carry-forward, halt on non-SUCCESS, structured logging
  - [x] 3.13: Initialize `HaltController` with the new `run_id` (not the original halted run)

- [x] Task 4: Implement resume-specific confirmation display (AC: #9)
  - [x] 4.1: Create `_show_resume_confirmation()` helper or extend `_show_dispatch_confirmation()`
  - [x] 4.2: Display: "Resuming epic {epic_spec} from halted run {original_run_id}"
  - [x] 4.3: Display: "Skipping completed stories:" with list of completed slugs
  - [x] 4.4: Display: "Dispatching remaining stories:" with list of remaining slugs
  - [x] 4.5: Display: "Carried-forward budget: ${cost} | {tokens} tokens | {invocations} invocations"
  - [x] 4.6: Display configured budget ceilings (same as normal dispatch)
  - [x] 4.7: Use `typer.confirm("Proceed with resume?", abort=True)` — same pattern as normal dispatch

- [x] Task 5: Add `get_run_status` and `list_runs` imports to dispatch.py (AC: #2)
  - [x] 5.1: Add to the `from arcwright_ai.output.run_manager import ...` block: `get_run_status`, `list_runs`, `RunStatus`
  - [x] 5.2: Ensure `RunStatus` is only used for type hints — if preferred, use `TYPE_CHECKING` guard

- [x] Task 6: Handle `BudgetState` reconstruction from `run.yaml` budget dict (AC: #5)
  - [x] 6.1: The `RunStatus.budget` field is a `dict[str, Any]` (not a typed `BudgetState`)
  - [x] 6.2: Construct `BudgetState` from the dict: `BudgetState(invocation_count=budget_dict.get("invocation_count", 0), total_tokens=budget_dict.get("total_tokens", 0), estimated_cost=Decimal(str(budget_dict.get("estimated_cost", "0"))), max_invocations=0, max_cost=Decimal(str(config.limits.cost_per_run)))`
  - [x] 6.3: Handle missing/malformed budget dict gracefully — default to fresh `BudgetState()` with a warning log

- [x] Task 7: Create/update tests in `tests/test_cli/test_dispatch.py` (AC: #14, #15)
  - [x] 7.1: Test `_find_latest_run_for_epic()` — multiple runs exist, returns most recent halted run
  - [x] 7.2: Test `_find_latest_run_for_epic()` — no matching run exists → returns None
  - [x] 7.3: Test `_find_latest_run_for_epic()` — filters by epic number, ignores other epics
  - [x] 7.4: Test resume integration — 5-story epic, halt at story 3, resume skips 1-2, dispatches 3-5
  - [x] 7.5: Test resume budget carry-forward — verify initial budget matches prior run's accumulated budget
  - [x] 7.6: Test resume on completed run → exit 0 with message
  - [x] 7.7: Test resume with no prior run → exit 3 with error
  - [x] 7.8: Test `--resume` with `--story` → error exit code 1
  - [x] 7.9: Test `--resume` with `--yes` → confirmation skipped
  - [x] 7.10: Test new `run_id` generated for resumed dispatch
  - [x] 7.11: Test `HaltController` receives new `run_id`
  - [x] 7.12: Use `tmp_path` fixture for project root, mock `run_manager` and engine functions
  - [x] 7.13: Use `@pytest.mark.asyncio` for async test functions
  - [x] 7.14: Verify all 530 existing tests still pass after changes

- [x] Task 8: Run quality gates (AC: #11, #12, #13, #14)
  - [x] 8.1: `ruff check .` — zero violations against FULL repository
  - [x] 8.2: `ruff format --check .` — zero formatting issues
  - [x] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 8.4: `pytest` — all tests pass (530 existing + new tests)
  - [x] 8.5: Verify Google-style docstrings on all public functions
  - [x] 8.6: Verify `git diff --name-only` matches Dev Agent Record file list

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 5.3 adds resume logic within `cli/dispatch.py` and imports additional functions from `output/run_manager.py` (`get_run_status`, `list_runs`, `RunStatus`). This is permitted by the DAG since `cli` can import from any domain package.

**D2 — Halt & Resume Strategy**: Per architecture, halt scope in MVP is "halt the entire epic." Resume picks up from the halted story. The halted story is re-executed from scratch (fresh `StoryState` with `TaskState.QUEUED`) — there is no mid-story resume capability. This is explicit in the architecture: "Resume picks up from the halted story" means re-executing it fully.

**D5 — Run Directory Schema**: Each resume creates a NEW run directory with a new `run_id`. The original halted run's `run.yaml` is read-only (never modified by the resume controller). The new run's `run.yaml` contains only the remaining (non-completed) stories.

**D6 — Exit Code Taxonomy**: Resume-specific errors use the existing taxonomy. No prior run → `EXIT_CONFIG` (3) because it's a user-fixable project setup issue. Invalid flag combinations → exit code 1 (Typer convention). Already-completed run → `EXIT_SUCCESS` (0) per NFR19 idempotency.

**NFR2 — Progress Recovery**: Completed stories are never re-executed — their commits, provenance, and run artifacts from the original run are untouched. The resume controller only needs to know WHICH stories completed; it does not need to access their artifacts.

**NFR19 — Idempotency**: Resuming an already-completed run is a no-op. This prevents accidental re-execution and aligns with the idempotency principle used throughout the codebase (init, cleanup, etc.).

**Budget carry-forward on resume**: The `run.yaml` `budget` field stores the accumulated `BudgetState` at halt time. This is serialized as a dict with `Decimal` fields converted to strings (by `_serialize_budget()` in `run_manager.py`). The resume controller must deserialize this back to a proper `BudgetState` object, converting string representations back to `Decimal`.

### Existing Code to Reuse — DO NOT REINVENT

- **`_find_epic_stories(epic_spec, artifacts_dir)`** from `cli/dispatch.py` — finds and sorts story files. Already works correctly. DO NOT rewrite.
- **`_discover_project_root()`** from `cli/dispatch.py` — walks up to find `.arcwright-ai/` or `_spec/`. Unchanged.
- **`_show_dispatch_confirmation()`** from `cli/dispatch.py` — confirmation display. Reuse pattern for resume confirmation.
- **`_setup_run_logging(run_dir)`** from `cli/dispatch.py` — JSONL handler attachment. Unchanged.
- **`_coerce_task_state(raw_status)`** from `cli/dispatch.py` — normalizes graph output status. Unchanged.
- **`_exit_code_for_terminal_status(status)`** from `cli/dispatch.py` — maps status to exit code. Unchanged.
- **`build_story_graph()`** from `engine/graph.py` — builds per-story LangGraph. Unchanged.
- **`create_run(project_root, run_id, config, story_slugs)`** from `output/run_manager.py` — creates run dir + run.yaml. Call for the new resume run.
- **`generate_run_id()`** from `output/run_manager.py` — canonical run ID generator.
- **`get_run_status(project_root, run_id) -> RunStatus`** from `output/run_manager.py` — reads `run.yaml` into typed model. Key dependency for resume. Returns `RunStatus` with `status`, `last_completed_story`, `stories` dict, `budget` dict.
- **`list_runs(project_root) -> list[RunSummary]`** from `output/run_manager.py` — lists all runs sorted by `start_time` descending. Used to find matching runs for an epic.
- **`update_run_status()`, `update_story_status()`** from `output/run_manager.py` — same as Story 5.1 dispatch loop.
- **`RunStatusValue`** from `output/run_manager.py` — enum: QUEUED, RUNNING, COMPLETED, HALTED, TIMED_OUT.
- **`RunStatus`** from `output/run_manager.py` — typed model with `run_id`, `status`, `stories`, `budget`, `last_completed_story`.
- **`RunSummary`** from `output/run_manager.py` — lightweight model with `run_id`, `status`, `start_time`, `story_count`, `completed_count`.
- **`HaltController`** from `cli/halt.py` — halt coordination. Instantiate with the NEW `run_id` for resumed dispatch.
- **`StoryState`** from `engine/state.py` — per-story mutable state. Used directly for remaining stories.
- **`ProjectState`** from `engine/state.py` — multi-story tracking state.
- **`BudgetState`** from `core/types.py` — frozen model. Reconstruct from `run.yaml` budget dict.

### Relationship to Other Stories in Epic 5

- **Story 5.1 (done):** Full epic dispatch with ProjectState, budget carry-forward, confirmation, run_manager integration. The resume controller reuses the same dispatch loop for executing remaining stories.
- **Story 5.2 (done):** Halt controller writes correct halt state to `run.yaml` (status=HALTED, `last_completed_story`, accumulated `budget`). The resume controller reads this exact state to determine where to pick up.
- **Story 5.3 (this):** Adds `--resume` flag that reads `run.yaml` to find `last_completed_story` and rebuilds the dispatch targeting only remaining stories, with budget carry-forward.
- **Story 5.4 (next):** Halt & Resume artifact integration — on resume, new entries are appended to the existing `summary.md`. Depends on 5.3 creating a new run for the resumed portion.
- **Story 5.5 (Run Status Command):** Reads `run.yaml` to display status — shows both original and resumed runs.

### Relationship to Completed Stories

- **Story 2.7 (done):** Created the original `_dispatch_epic_async()`. Story 5.1 replaced the basic loop; Story 5.2 upgraded error handling. Story 5.3 adds resume capability on top.
- **Story 4.2 (done):** Created `run_manager.py` with `create_run()`, `update_run_status()`, `get_run_status()`, `list_runs()` — all consumed by this story's resume logic.
- **Story 4.3 (done):** Created `summary.py` with `write_halt_report()` — the halt reports include the resume command.
- **Story 4.4 (done):** Wired `run_manager` and `summary` into engine graph nodes.

### Testing Patterns

- **Mock `get_run_status()`**: Use `monkeypatch.setattr("arcwright_ai.cli.dispatch.get_run_status", ...)` to return predetermined `RunStatus` objects with configurable `status`, `last_completed_story`, `stories`, and `budget`.
- **Mock `list_runs()`**: Use `monkeypatch.setattr("arcwright_ai.cli.dispatch.list_runs", ...)` to return synthetic `RunSummary` lists.
- **Mock `build_story_graph()` and `graph.ainvoke()`**: Same as Story 5.1 — mock the graph to return predetermined `StoryState` objects with configurable `status` and `budget`. Do NOT invoke the real graph in dispatch tests.
- **Mock `create_run()`**: Return a `tmp_path`-based run directory.
- **Mock `typer.confirm()`**: Patch to return True (confirm) or raise `typer.Abort` (reject).
- **Create synthetic `run.yaml` state**: Build `RunStatus` with `status=RunStatusValue.HALTED`, `last_completed_story="5-2-halt-controller"`, and `stories` dict with mixed `"success"` and `"halted"` entries.
- **Budget reconstruction verification**: Create a `RunStatus` with known `budget` dict (string-serialized Decimals), verify the reconstructed `BudgetState` has correct `Decimal` values.
- **Use `tmp_path` fixture** for project root and artifacts directory.
- **Use `@pytest.mark.asyncio`** for async test functions.
- **Capture stderr** using `capsys` fixture to verify resume output messages.
- **Mock at callsite**: When patching functions in `dispatch.py`, use `monkeypatch.setattr("arcwright_ai.cli.dispatch.get_run_status", ...)`, NOT `monkeypatch.setattr("arcwright_ai.output.run_manager.get_run_status", ...)`.

### Design Decision: Resume Creates a New Run

The resume controller creates a **new** run directory with a new `run_id` instead of modifying the original halted run. Reasons:

1. **Immutability**: The original run's artifacts are a forensic record of what happened. Modifying them would corrupt the audit trail.
2. **Simplicity**: A new run follows the exact same `create_run()` → dispatch loop → `update_run_status()` lifecycle as a fresh dispatch. No special "resume mode" is needed in the dispatch loop itself.
3. **Provenance**: The new run's `log.jsonl` captures only the resumed execution events. Combined with the original run's log, the full execution history is preserved across two runs.
4. **Budget enforcement**: The new run starts with the carried-forward budget, so the `budget_check` node enforces the cumulative ceiling.

### Design Decision: Finding the Prior Run

The resume controller finds the prior run by:
1. Calling `list_runs()` to get all runs sorted by `start_time` descending (most recent first).
2. For each run, loading `get_run_status()` and checking if the run's story slugs match the epic number.
3. Returning the first (most recent) match.

This is O(N) in run count but runs are time-sorted and the match is typically the most recent run, so in practice it returns immediately. No index or caching is needed for MVP.

### Import Structure Changes for `cli/dispatch.py`

Add to the existing `from arcwright_ai.output.run_manager import ...` block:
```python
from arcwright_ai.output.run_manager import (
    RunStatus,
    RunStatusValue,
    RunSummary,
    create_run,
    generate_run_id,
    get_run_status,
    list_runs,
    update_run_status,
    update_story_status,
)
```

### Project Structure Notes

Files modified by this story:
```
src/arcwright_ai/cli/dispatch.py     # MODIFIED: add --resume flag, resume logic, _find_latest_run_for_epic()
tests/test_cli/test_dispatch.py      # MODIFIED: add resume tests
```

Files NOT modified (confirmed unchanged):
```
src/arcwright_ai/cli/halt.py         # Unchanged — HaltController API unchanged
src/arcwright_ai/cli/app.py          # Unchanged — no new commands
src/arcwright_ai/engine/graph.py     # Unchanged — graph shape unchanged
src/arcwright_ai/engine/nodes.py     # Unchanged — node logic unchanged
src/arcwright_ai/engine/state.py     # Unchanged — StoryState, ProjectState unchanged
src/arcwright_ai/output/run_manager.py  # Unchanged — all needed functions exist
src/arcwright_ai/output/summary.py   # Unchanged — called as-is
src/arcwright_ai/output/provenance.py   # Unchanged — called as-is
src/arcwright_ai/core/types.py       # Unchanged — BudgetState unchanged
src/arcwright_ai/core/constants.py   # Unchanged — all needed constants exist
src/arcwright_ai/core/exceptions.py  # Unchanged — all needed exceptions exist
```

### Known Pitfalls from Epics 1-5.2

1. **`__all__` ordering must be alphabetical** — ruff enforces this. New exports in `dispatch.py`'s `__all__` must be sorted.
2. **No aspirational exports** — only export symbols that actually exist.
3. **`from __future__ import annotations`** at the top of every module.
4. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just `ruff check src/arcwright_ai/cli/`).
5. **File list in Dev Agent Record must match actual git changes**.
6. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
7. **Best-effort artifact writes**: All `run_manager` calls in the resume path must be wrapped in `try: ... except Exception: logger.warning(...)`. Artifact writes must NEVER prevent the resume from returning an exit code.
8. **`BudgetState` is frozen** — do not attempt mutation. Use `model_copy(update={...})` for updates.
9. **`Decimal` for cost** — `BudgetState.estimated_cost` and `max_cost` are `Decimal`. When reconstructing from `run.yaml` budget dict (which stores them as strings), use `Decimal(str(value))`.
10. **Mock at callsite, not source module** — when patching `get_run_status` in tests, use `monkeypatch.setattr("arcwright_ai.cli.dispatch.get_run_status", ...)`.
11. **Two-venv environment** — `.venv` (Python 3.14) for dev/test, `.venv-studio` (Python 3.13) for LangGraph Studio.
12. **`_dispatch_epic_async()` preserves the happy path** — the resume branch should diverge early and rejoin the standard dispatch loop with modified inputs (filtered stories, carried-forward budget). Do NOT duplicate the dispatch loop.
13. **`RunStatus.budget` is a `dict[str, Any]`** — it's the raw YAML dict, not a typed `BudgetState`. Reconstruction to `BudgetState` must handle all edge cases (missing keys, string-encoded Decimals, etc.).
14. **`list_runs()` returns `RunSummary` (lightweight)** — to get full `RunStatus` with `stories` dict, you must call `get_run_status(project_root, run_summary.run_id)` for each candidate. Optimize by checking `RunSummary.status` first (skip runs that are `COMPLETED` or `QUEUED`).
15. **`RunStatus.stories` is `dict[str, StoryStatusEntry]`** — each `StoryStatusEntry` has a `status: str` field. Check for `status == "success"` to identify completed stories.
16. **`RunError` for run.yaml issues** — `get_run_status()` raises `RunError` if `run.yaml` is missing or malformed. The resume controller should catch this and return `EXIT_CONFIG` with an informative message.

### Git Intelligence

Recent commits (last 5):
1. `chore: mark story 5-2 done` — sprint status update
2. `feat(story-5.2): halt controller — graceful halt on unrecoverable failure` — HaltController class, consolidated exception handling
3. `feat(epic-5): complete story 5-1 epic dispatch CLI-to-engine pipeline` — full epic dispatch with budget carry-forward
4. `chore: ignore .langgraph_api/ runtime state directory` — housekeeping
5. `docs: document BMAD workflow customizations` — documentation

Patterns established:
- Epic dispatch loop and HaltController are stable (from 5.1 and 5.2)
- Output package (provenance, run_manager, summary) is complete and stable
- `get_run_status()` and `list_runs()` are fully implemented and tested in run_manager
- Best-effort artifact writes are the standard pattern across all existing code
- 530 tests passing, quality gates clean

### References

- [Source: _spec/planning-artifacts/epics.md — Epic 5, Story 5.3]
- [Source: _spec/planning-artifacts/architecture.md — Decision 2: Retry & Halt Strategy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy]
- [Source: _spec/planning-artifacts/architecture.md — NFR2: Progress Recovery]
- [Source: _spec/planning-artifacts/architecture.md — NFR19: Idempotency]
- [Source: _spec/implementation-artifacts/5-1-epic-dispatch-cli-to-engine-pipeline.md — dispatch loop structure, budget carry-forward]
- [Source: _spec/implementation-artifacts/5-2-halt-controller-graceful-halt-on-unrecoverable-failure.md — HaltController API, halt state writing to run.yaml]
- [Source: src/arcwright_ai/cli/dispatch.py — _dispatch_epic_async(), _find_epic_stories(), dispatch_command()]
- [Source: src/arcwright_ai/cli/halt.py — HaltController class]
- [Source: src/arcwright_ai/output/run_manager.py — get_run_status(), list_runs(), RunStatus, RunSummary, create_run(), update_run_status()]
- [Source: src/arcwright_ai/core/types.py — BudgetState (frozen, Decimal fields)]
- [Source: src/arcwright_ai/engine/state.py — StoryState, ProjectState]
- [Source: src/arcwright_ai/core/constants.py — EXIT_* codes]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Implemented `_find_latest_run_for_epic()` async helper that scans all runs via `list_runs()`, checks each for epic-prefixed story slugs via `get_run_status()`, and returns the most recent match as `(run_id, RunStatus)` or `None`.
- Implemented `_reconstruct_budget_from_dict()` to safely deserialize string-encoded Decimal fields from `run.yaml` budget dict back into a typed `BudgetState`, with graceful fallback and warning log on malformed input.
- Implemented `_show_resume_confirmation()` to display original halted run ID, skipped completed stories, remaining stories to dispatch, carried-forward budget, and budget ceilings — same `typer.confirm(abort=True)` pattern as normal dispatch.
- Extended `_dispatch_epic_async()` with `resume: bool = False` parameter. Resume branch diverges early: finds prior run, handles COMPLETED/missing run edge cases per NFR19, filters story list, reconstructs budget, shows resume confirmation — then rejoins the standard dispatch loop with a new run_id and HaltController instance. No dispatch loop duplication.
- Hardened resume gating: `--resume` now rejects prior runs that are not `HALTED` (except `COMPLETED` idempotent no-op), returning `EXIT_CONFIG` with a clear message.
- Updated `dispatch_command()` to accept `--resume` flag with validation that `--resume` cannot be combined with `--story` (exit code 1).
- Added 12 new tests: 3 async unit tests for `_find_latest_run_for_epic()` (most recent match, no match, filters by epic number) and 9 CLI integration tests covering all resume ACs (5-story epic halt-at-3 resume, budget carry-forward, completed-run idempotency, no-prior-run error, non-halted-run rejection, --resume+--story conflict, --yes skips confirm, new run_id, HaltController gets new run_id).
- Quality gates: `ruff check .` ✅, `ruff format --check .` ✅, `mypy --strict src/` ✅, 542 tests pass (530 existing + 12 new) ✅.

### File List

- arcwright-ai/src/arcwright_ai/cli/dispatch.py
- arcwright-ai/tests/test_cli/test_dispatch.py
- _spec/implementation-artifacts/5-3-resume-controller-resume-halted-epic-from-failure-point.md
- _spec/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-03-06: Story 5.3 implemented — resume controller added. `_find_latest_run_for_epic()`, `_reconstruct_budget_from_dict()`, `_show_resume_confirmation()` added to `cli/dispatch.py`. `_dispatch_epic_async()` extended with `resume: bool = False` parameter and diverging resume branch. `dispatch_command()` updated with `--resume` flag and `--resume`+`--story` conflict validation. 12 tests added to `test_dispatch.py`. All quality gates pass (542 tests, ruff, mypy).
- 2026-03-06: Code review follow-up fixes applied — enforced HALTED-only resume gating, added non-halted resume rejection test, removed contradictory duplicate unchecked task block, and reconciled Dev Agent Record file list with actual changed files.