# Story 5.2: Halt Controller — Graceful Halt on Unrecoverable Failure

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running an overnight dispatch,
I want the system to halt loudly on unrecoverable failure while preserving all completed work,
so that I never get silent breakage and can trust that completed stories are safe.

## Acceptance Criteria (BDD)

1. **Given** the engine encounters an unrecoverable condition during story execution **When** halt triggers on any of 3 conditions per D2: (1) validation fail count exhausted (`retry_count >= config.limits.retry_budget`), (2) budget exceeded (invocation count or cost ceiling), (3) agent error (SDK crash, sandbox violation, `AgentError`, `AgentBudgetError`, `AgentTimeoutError`, `SandboxViolation`) **Then** a `HaltController` in `cli/halt.py` is invoked to coordinate the halt sequence.

2. **Given** the halt controller is invoked **When** it handles the halt **Then** it calls `write_halt_report()` from `output/summary.py` with all NFR18 diagnostic fields: (1) failing story slug + AC IDs (from `PipelineResult.feedback.unmet_criteria` if available), (2) retry count + validation history per attempt, (3) last agent output (truncated to 2000 chars), (4) suggested fix based on failure pattern. This ensures exception-based halts that escape the graph also produce run-level halt reports, not just graph-level ESCALATED states.

3. **Given** the halt controller coordinates the halt sequence **When** it completes cleanup **Then** it flushes any unflushed provenance entries by recording a halt provenance entry via `output/provenance.append_entry()` to the failing story's `validation.md` with: halt reason, budget state at halt time, and timestamp. This covers halts from exceptions that escape the graph (bypassing `finalize_node`).

4. **Given** the halt controller updates run artifacts **When** `run.yaml` is updated **Then** `update_run_status()` is called with `status=RunStatusValue.HALTED`, `last_completed_story` set to the last successfully completed story slug (or `None` if the first story failed), and `budget` set to the accumulated budget state at halt time. This call is best-effort — failure to update `run.yaml` does not prevent the halt from completing.

5. **Given** the halt controller produces CLI output **When** the structured halt summary is displayed **Then** it shows: stories completed (list of slugs), story that caused halt, halt reason (one of: "validation exhaustion", "budget exceeded", "agent error", "SDK error", "sandbox violation", "SCM error", "config/context error", "internal error"), current budget consumption (tokens and cost), and the exact resume command `arcwright-ai dispatch --epic EPIC-N --resume`.

6. **Given** an `AgentBudgetError` is raised during story execution **When** the halt controller determines the exit code **Then** exit code is 2 (`EXIT_AGENT`).

7. **Given** validation exhaustion occurs (graph returns ESCALATED with `retry_count >= retry_budget`) **When** the halt controller determines the exit code **Then** exit code is 1 (`EXIT_VALIDATION`), aligning with D6 taxonomy where validation failures map to exit code 1.

8. **Given** an `ScmError` (including `WorktreeError`, `BranchError`) is raised **When** the halt controller determines the exit code **Then** exit code is 4 (`EXIT_SCM`).

9. **Given** NFR3 enforcement: an unexpected SDK error occurs (network timeout via `asyncio.TimeoutError`, API 500 via `ConnectionError`/`httpx.HTTPStatusError`, malformed response) **When** the error is caught in the dispatch loop **Then** it is wrapped as an `AgentError` with the original exception as context, logged with full traceback and story context (story_id, retry_count, budget state), and routed through the halt controller — never an unhandled exception crash. Exit code is 2 (`EXIT_AGENT`).

10. **Given** completed stories exist when halt occurs **When** the halt controller preserves completed work **Then** all previously completed stories' commits, provenance files, and run artifacts are untouched per NFR2. The halt controller does NOT modify any files under `.arcwright-ai/runs/<run-id>/stories/<completed-story-slug>/`. Only the failing story's directory and run-level files (`run.yaml`, `summary.md`) are updated.

11. **Given** `_dispatch_epic_async()` currently has 6 nearly-identical exception handlers **When** Story 5.2 refactors the halt handling **Then** the exception handlers are consolidated into calls to `HaltController.handle_halt()`, eliminating code duplication. The consolidated handler accepts: `story_id`, `epic_spec`, `exception`, `accumulated_budget`, `completed_stories`, `last_completed`, `project_root`, `run_id` — and performs all halt operations (run status update, halt report write, provenance flush, CLI output, JSONL event).

12. **Given** the non-SUCCESS graph result path (story completes but with ESCALATED/RETRY status) **When** Story 5.2 refactors this path **Then** it also routes through `HaltController.handle_graph_halt()` which accepts: `story_state` (with terminal status, validation_result, retry_history, budget, agent_output), `epic_spec`, `completed_stories`, `last_completed`, `project_root`, `run_id` — and performs the same halt operations with richer diagnostic data extracted from the graph result.

13. **Given** the halt controller is a new module `cli/halt.py` **When** it is created **Then** it imports only from: `core/constants`, `core/exceptions`, `core/types`, `core/lifecycle`, `output/run_manager`, `output/summary`, `output/provenance` — respecting the package dependency DAG (`cli → engine → {validation, agent, context, output, scm} → core`).

14. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

15. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

16. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

17. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass (478 total at latest count).

18. **Given** new tests in `tests/test_cli/test_halt.py` and updated tests in `tests/test_cli/test_dispatch.py` **When** the test suite runs **Then** tests cover:
    (a) `HaltController.handle_halt()` — each exception type produces correct exit code;
    (b) `HaltController.handle_halt()` — halt summary output contains all required fields (completed stories, failing story, halt reason, budget, resume command);
    (c) `HaltController.handle_graph_halt()` — ESCALATED from validation exhaustion produces correct halt report with retry history;
    (d) `HaltController.handle_graph_halt()` — ESCALATED from budget exceeded produces correct halt report;
    (e) Provenance flush — halt provenance entry written to failing story's `validation.md`;
    (f) `write_halt_report()` called for exception-based halts (not just graph-level ESCALATED);
    (g) NFR3 — `asyncio.TimeoutError` caught and routed through halt controller (not unhandled);
    (h) NFR3 — `ConnectionError` caught and routed through halt controller;
    (i) NFR2 — completed story directories are not modified after halt;
    (j) Best-effort artifact writes — halt controller continues if `write_halt_report()` or `update_run_status()` raise;
    (k) Exit code mapping: `AgentBudgetError` → 2, validation exhaustion → 1, `ScmError` → 4, `ConfigError` → 3, unhandled `Exception` → 5;
    (l) Updated dispatch tests — verify exception handlers now delegate to `HaltController`.

## Tasks / Subtasks

- [ ] Task 1: Create `src/arcwright_ai/cli/halt.py` with `HaltController` class (AC: #1, #11, #12, #13)
  - [ ] 1.1: Define `HaltController` class with `__init__(self, *, project_root: Path, run_id: str, epic_spec: str)` storing common halt context
  - [ ] 1.2: Implement `async handle_halt(self, *, story_id: StoryId, exception: Exception, accumulated_budget: BudgetState, completed_stories: list[str], last_completed: str | None) -> int` — returns exit code
  - [ ] 1.3: Implement `async handle_graph_halt(self, *, story_state: StoryState, accumulated_budget: BudgetState, completed_stories: list[str], last_completed: str | None) -> int` — returns exit code for non-SUCCESS graph results
  - [ ] 1.4: Implement `_determine_exit_code_for_exception(exception: Exception) -> int` — static method mapping exception types to exit codes per D6
  - [ ] 1.5: Implement `_determine_exit_code_for_graph_state(story_state: StoryState) -> int` — maps ESCALATED/RETRY terminal states to exit codes based on halt reason
  - [ ] 1.6: Implement `_halt_reason_for_exception(exception: Exception) -> str` — maps exception types to human-readable halt reason strings
  - [ ] 1.7: Implement `_halt_reason_for_graph_state(story_state: StoryState) -> str` — derives halt reason from graph terminal state using `_derive_halt_reason()` logic
  - [ ] 1.8: Add `__all__` export, `from __future__ import annotations`, Google-style docstrings on all public methods

- [ ] Task 2: Implement halt report writing in `HaltController` (AC: #2)
  - [ ] 2.1: In `handle_halt()`, call `write_halt_report()` from `output/summary.py` with: `halted_story=str(story_id)`, `halt_reason`, `validation_history=[]` (no retry history available for exception-based halts), `last_agent_output=""` (may not be available), `suggested_fix` derived from exception type
  - [ ] 2.2: In `handle_graph_halt()`, call `write_halt_report()` with full diagnostic data extracted from `story_state`: validation_history from `_build_validation_history_dicts()`, last_agent_output from `story_state.agent_output`, suggested_fix from `_derive_suggested_fix()`
  - [ ] 2.3: Both calls are best-effort — wrapped in `try/except Exception` with `logger.warning()`

- [ ] Task 3: Implement provenance flush in `HaltController` (AC: #3)
  - [ ] 3.1: In both `handle_halt()` and `handle_graph_halt()`, construct a `ProvenanceEntry` with: `decision="Halt: {halt_reason}"`, `alternatives=[]`, `rationale="Budget state: invocations={n}, tokens={n}, cost=${n}"`, `ac_references=[]`, `timestamp=datetime.now(tz=UTC).isoformat()`
  - [ ] 3.2: Call `append_entry()` to write to `{project_root}/.arcwright-ai/runs/{run_id}/stories/{story_slug}/validation.md`
  - [ ] 3.3: Best-effort — wrapped in `try/except Exception` with `logger.warning()`
  - [ ] 3.4: Create the story checkpoint directory if it doesn't exist (it may not for very early halts)

- [ ] Task 4: Implement run status update and JSONL logging in `HaltController` (AC: #4, #5)
  - [ ] 4.1: Call `update_run_status()` with `status=RunStatusValue.HALTED`, `last_completed_story`, `budget` — best-effort
  - [ ] 4.2: Emit `run.halt` JSONL event with `halted_story`, `reason`, `completed_count`, `budget_cost`, `budget_tokens`
  - [ ] 4.3: Output structured halt summary to stderr via `typer.echo()`: completed stories list, failing story, halt reason, budget consumption, resume command
  - [ ] 4.4: The JSONL logger reference should be passed via the `arcwright_ai` root logger (already available in the dispatch context)

- [ ] Task 5: Implement NFR3 SDK error catching (AC: #9)
  - [ ] 5.1: In `_dispatch_epic_async()`, add catch blocks for `asyncio.TimeoutError` and `ConnectionError` (base class for network errors)
  - [ ] 5.2: Wrap caught errors as `AgentError(f"SDK communication failure: {exc}", details={"original_error": type(exc).__name__, "story": str(story_id), "retry_count": ...})` 
  - [ ] 5.3: Route wrapped errors through `HaltController.handle_halt()` like any other `AgentError`
  - [ ] 5.4: Log the full traceback at DEBUG level before wrapping

- [ ] Task 6: Refactor `_dispatch_epic_async()` to use `HaltController` (AC: #11, #12)
  - [ ] 6.1: After `create_run()` and before the dispatch loop, instantiate `HaltController(project_root=project_root, run_id=str(run_id), epic_spec=epic_spec)`
  - [ ] 6.2: Replace the non-SUCCESS graph result handling block with `exit_code = await halt_controller.handle_graph_halt(...)`
  - [ ] 6.3: Replace all 6 exception handler blocks with a consolidated handler that calls `exit_code = await halt_controller.handle_halt(...)`
  - [ ] 6.4: Keep the `finally` block for logging cleanup unchanged
  - [ ] 6.5: Remove `_halt_reason_from_exit_code()` from dispatch.py (logic moved to `HaltController`)
  - [ ] 6.6: Add import: `from arcwright_ai.cli.halt import HaltController`
  - [ ] 6.7: Update `cli/__init__.py` if it re-exports dispatch symbols (check if `_halt_reason_from_exit_code` was exported)

- [ ] Task 7: Ensure NFR2 completed story preservation (AC: #10)
  - [ ] 7.1: Verify that `HaltController` never writes to completed story directories — only to the failing story's directory and run-level files
  - [ ] 7.2: Add an assertion/guard in `handle_halt()` that the story slug being written to (`story_id`) is NOT in the `completed_stories` list
  - [ ] 7.3: Add a test that creates synthetic completed-story dirs, triggers a halt, and verifies those dirs are unmodified

- [ ] Task 8: Create `tests/test_cli/test_halt.py` (AC: #18 a-k)
  - [ ] 8.1: Test `_determine_exit_code_for_exception()`: `AgentBudgetError` → 2, `AgentTimeoutError` → 2, `SandboxViolation` → 2, `AgentError` → 2, `ScmError` → 4, `WorktreeError` → 4, `ConfigError` → 3, `ProjectError` → 3, `ContextError` → 3, `ValidationError` → 1, `ArcwrightError` → 5, `Exception` → 5
  - [ ] 8.2: Test `handle_halt()` output contains all required fields: completed stories, failing story, halt reason, budget, resume command
  - [ ] 8.3: Test `handle_graph_halt()` with ESCALATED + validation exhaustion → exit code 1, halt report has retry history
  - [ ] 8.4: Test `handle_graph_halt()` with ESCALATED + budget exceeded → exit code 2, halt report written
  - [ ] 8.5: Test provenance flush — mock `append_entry`, verify it's called with halt reason and budget info
  - [ ] 8.6: Test `write_halt_report()` called for exception-based halts — mock it, verify call args
  - [ ] 8.7: Test NFR3 — `asyncio.TimeoutError` wrapped as `AgentError` and handled
  - [ ] 8.8: Test NFR3 — `ConnectionError` wrapped as `AgentError` and handled
  - [ ] 8.9: Test NFR2 — completed story dirs not modified
  - [ ] 8.10: Test best-effort — `write_halt_report` raises, halt controller still returns exit code
  - [ ] 8.11: Test best-effort — `update_run_status` raises, halt controller still returns exit code
  - [ ] 8.12: Use `tmp_path` fixture for project root, mock `run_manager` and `summary` functions

- [ ] Task 9: Update `tests/test_cli/test_dispatch.py` (AC: #17, #18l)
  - [ ] 9.1: Update existing halt-on-failure tests to verify `HaltController` is used (mock `HaltController.handle_halt`)
  - [ ] 9.2: Update existing graph-result halt tests to verify `HaltController.handle_graph_halt` is used
  - [ ] 9.3: Verify all 478 existing tests still pass after refactoring

- [ ] Task 10: Run quality gates (AC: #14, #15, #16, #17)
  - [ ] 10.1: `ruff check .` — zero violations against FULL repository
  - [ ] 10.2: `ruff format --check .` — zero formatting issues
  - [ ] 10.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [ ] 10.4: `pytest` — all tests pass (478 existing + new tests)
  - [ ] 10.5: Verify Google-style docstrings on all public functions
  - [ ] 10.6: Verify `git diff --name-only` matches Dev Agent Record file list

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Expand SDK-error handling in `_dispatch_epic_async()` to include API/server/malformed-response classes required by AC#9 (`httpx.HTTPStatusError`, `json.JSONDecodeError`) in addition to timeout/connection handling. [arcwright-ai/src/arcwright_ai/cli/dispatch.py]
- [x] [AI-Review][HIGH] Log full traceback and complete story context (including budget state) when wrapping SDK errors for NFR3. [arcwright-ai/src/arcwright_ai/cli/dispatch.py]
- [x] [AI-Review][MEDIUM] Add explicit `"SDK error"` halt-reason mapping for SDK transport/service failures to satisfy AC#5 reason taxonomy. [arcwright-ai/src/arcwright_ai/cli/halt.py]
- [x] [AI-Review][MEDIUM] Add NFR2 completed-story guard parity in `handle_graph_halt()` (matching `handle_halt()`). [arcwright-ai/src/arcwright_ai/cli/halt.py]
- [x] [AI-Review][MEDIUM] Align Dev Agent Record evidence with claims by recording focused validation run outputs after remediation. [ _spec/implementation-artifacts/5-2-halt-controller-graceful-halt-on-unrecoverable-failure.md ]

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 5.2 adds a new `cli/halt.py` module. The `cli` package can import from any domain package, so `halt.py` importing from `output/run_manager`, `output/summary`, `output/provenance`, `core/types`, `core/exceptions`, `core/constants`, `core/lifecycle` is fully permitted.

**D2 — Retry & Halt Strategy**: Per architecture, 3 halt triggers exist:
1. **Validation exhaustion** — V3 reflexion failures exhaust retry budget (`retry_count >= config.limits.retry_budget`). The graph's `validate_node` transitions to ESCALATED with reason "max_retries_exhausted". Only V3 failures retry; V6 invariant failures are immediate ESCALATED.
2. **Budget exceeded** — invocation count ceiling OR cost ceiling hit. The `budget_check_node` transitions to ESCALATED via `route_budget_check`. Also, `AgentBudgetError` can be raised by the SDK wrapper.
3. **Agent error** — SDK crash, sandbox violation, network timeout, malformed response. These surface as `AgentError` (or subclasses) and escape the graph.

**Halt scope (MVP)**: Halt the entire epic. No partial continuation, no story skipping. Story 5.3 adds resume capability.

**D6 — Exit Code Taxonomy** (already implemented in `core/constants.py`):
- `EXIT_SUCCESS` = 0 — all stories passed
- `EXIT_VALIDATION` = 1 — validation failure (incl. exhausted retries)
- `EXIT_AGENT` = 2 — agent/budget error (incl. SDK communication failures)
- `EXIT_CONFIG` = 3 — config/context/project errors
- `EXIT_SCM` = 4 — SCM errors
- `EXIT_INTERNAL` = 5 — unhandled/unexpected errors

**Note on epics AC exit code discrepancy**: The epics AC states "validation exhaustion → exit code 3" but D6 taxonomy clearly maps validation failures to exit code 1. This story aligns with D6 (EXIT_VALIDATION = 1 for validation exhaustion) since the architecture document is the authoritative source and the implementation already follows D6.

**Two halt paths exist in the dispatch loop**:
1. **Graph-level halt**: Story completes graph execution but returns with ESCALATED or non-SUCCESS status. The graph's `finalize_node` has already written a per-story halt report to `stories/<slug>/halt-report.md`. What's missing: run-level `summary.md` halt report via `write_halt_report()`, provenance flush for the halt decision itself.
2. **Exception-based halt**: An exception escapes the graph invocation (`graph.ainvoke()`). The graph's `finalize_node` did NOT run. What's missing: everything — halt report, provenance, run status update, structured CLI output.

**Story 5.1 provides the basic structure** — `_dispatch_epic_async()` has exception handlers that catch typed errors and return exit codes. But the handling is duplicated 6 times with nearly identical code in each catch block. Story 5.2 extracts this into a proper `HaltController`.

### Existing Code to Reuse — DO NOT REINVENT

- **`write_halt_report(project_root, run_id, *, halted_story, halt_reason, validation_history, last_agent_output, suggested_fix)`** from `output/summary.py` — writes structured halt report to `summary.md` with all NFR18 fields. Call as-is for both halt paths.
- **`update_run_status(project_root, run_id, *, status, last_completed_story, budget)`** from `output/run_manager.py` — updates run-level fields in `run.yaml`. Already used in dispatch; halt controller wraps this call.
- **`append_entry(path, entry)`** from `output/provenance.py` — appends a `ProvenanceEntry` to a markdown file. Used for provenance flush on halt.
- **`_derive_halt_reason(state)`** from `engine/nodes.py` — derives halt reason string from `StoryState`. Reuse the logic but expose it from the halt controller (or import from nodes).
- **`_build_validation_history_dicts(state)`** from `engine/nodes.py` — builds validation history list for `write_halt_report()`. Reuse the logic.
- **`_derive_suggested_fix(state)`** from `engine/nodes.py` — derives suggested fix string. Reuse the logic.
- **`_summarize_failures(result)`** from `engine/nodes.py` — summarizes validation failures. Used by `_build_validation_history_dicts()`.
- **`RunStatusValue`** from `output/run_manager.py` — enum for run status values. Already imported in dispatch.
- **`ProvenanceEntry`** from `core/types.py` — frozen Pydantic model for provenance entries.
- **`BudgetState`** from `core/types.py` — frozen model with `invocation_count`, `total_tokens`, `estimated_cost`, `max_invocations`, `max_cost`.
- **`StoryState`** from `engine/state.py` — per-story mutable state with all graph result data.
- **All exception classes** from `core/exceptions.py` — full hierarchy used for exit code mapping.
- **`_coerce_task_state(raw_status)`** from `cli/dispatch.py` — normalizes graph output status. Unchanged.
- **`_exit_code_for_terminal_status(status)`** from `cli/dispatch.py` — maps status to exit code. Will be enhanced in halt controller to differentiate ESCALATED reasons.

### Relationship to Other Stories in Epic 5

- **Story 5.1 (done):** Full epic dispatch with ProjectState, budget carry-forward, confirmation, run_manager integration. Provides the basic halt handling that this story upgrades.
- **Story 5.2 (this):** Adds structured halt controller with provenance flush, halt reports for exception-based halts, NFR3 enforcement, and consolidated error handling.
- **Story 5.3 (Resume Controller):** Depends on 5.2 writing correct halt state to `run.yaml` (status=HALTED, `last_completed_story`). The resume controller reads this state to determine where to pick up.
- **Story 5.4 (Halt & Resume Artifact Integration):** Integrates halt reports into run directory artifacts. Depends on 5.2's `write_halt_report()` calls producing correctly-structured `summary.md`.
- **Story 5.5 (Run Status Command):** Reads `run.yaml` to display status — depends on 5.2 writing correct run state on halt.

### Relationship to Completed Stories

- **Story 2.7 (done):** Created the original `_dispatch_epic_async()` with basic sequential dispatch. Story 5.1 replaced the basic loop; Story 5.2 upgrades the error handling.
- **Story 4.2 (done):** Created `run_manager.py` with `create_run()`, `update_run_status()` — all consumed by this story's halt controller.
- **Story 4.3 (done):** Created `summary.py` with `write_halt_report()`, `write_success_summary()` — the halt controller calls `write_halt_report()` for exception-based halts.
- **Story 4.4 (done):** Wired `run_manager` and `summary` into engine graph nodes. The `finalize_node` already writes halt reports for ESCALATED graph states. Story 5.2 ensures exception-based halts also produce these reports.
- **Story 3.4 (done):** Validate node and retry loop integration. The `validate_node` handles V6/V3 routing and ESCALATED transitions. Story 5.2 consumes the graph's terminal state.

### Testing Patterns

- **Mock `write_halt_report()`**: Use `monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", ...)` to verify call arguments without actually writing files.
- **Mock `update_run_status()`**: Use `monkeypatch.setattr("arcwright_ai.cli.halt.update_run_status", ...)` to verify halt updates. Also test the best-effort path where it raises.
- **Mock `append_entry()`**: Use `monkeypatch.setattr("arcwright_ai.cli.halt.append_entry", ...)` for provenance flush verification.
- **Create synthetic `StoryState` for graph-halt tests**: Build `StoryState` with known `status=TaskState.ESCALATED`, `retry_history`, `validation_result`, `agent_output`, `budget` to test `handle_graph_halt()`.
- **Test NFR3 wrapping**: Directly test that `asyncio.TimeoutError` and `ConnectionError` are properly caught and wrapped as `AgentError` before reaching the halt controller.
- **Test NFR2 preservation**: Create completed-story directories with known content, trigger a halt on a subsequent story, verify completed directories are byte-identical.
- **Use `tmp_path` fixture** for project root.
- **Use `@pytest.mark.asyncio`** for async test functions.
- **Capture stderr** using `capsys` fixture to verify structured halt summary output.
- **Mock at callsite**: When patching functions in `halt.py`, use `monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", ...)`, NOT `monkeypatch.setattr("arcwright_ai.output.summary.write_halt_report", ...)`.

### Design Decision: `HaltController` API

The `HaltController` consolidates all halt-related operations. Two entry points cover the two halt paths:

```python
class HaltController:
    """Coordinates graceful halt operations for unrecoverable failures.

    Handles both exception-based halts (errors escaping the graph) and
    graph-level halts (non-SUCCESS terminal states).
    """

    def __init__(self, *, project_root: Path, run_id: str, epic_spec: str) -> None: ...

    async def handle_halt(
        self,
        *,
        story_id: StoryId,
        exception: Exception,
        accumulated_budget: BudgetState,
        completed_stories: list[str],
        last_completed: str | None,
    ) -> int:
        """Handle exception-based halt. Returns exit code."""
        ...

    async def handle_graph_halt(
        self,
        *,
        story_state: StoryState,
        accumulated_budget: BudgetState,
        completed_stories: list[str],
        last_completed: str | None,
    ) -> int:
        """Handle non-SUCCESS graph result. Returns exit code."""
        ...
```

**Why a class**: The `project_root`, `run_id`, and `epic_spec` are common to all halt operations within a single dispatch run. Storing them in the constructor avoids passing them to every method call. The controller is instantiated once per dispatch run.

**Why in `cli/halt.py`**: The halt controller is CLI-level orchestration — it coordinates output (typer.echo), artifact writes (summary, provenance), and exit codes. It sits above the engine, not inside it.

### Import Structure for `cli/halt.py`

```python
from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, VALIDATION_FILENAME,
    EXIT_AGENT, EXIT_CONFIG, EXIT_INTERNAL, EXIT_SCM, EXIT_SUCCESS, EXIT_VALIDATION,
)
from arcwright_ai.core.exceptions import (
    AgentBudgetError, AgentError, AgentTimeoutError,
    ArcwrightError, ConfigError, ContextError,
    ProjectError, SandboxViolation, ScmError, ValidationError,
)
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ProvenanceEntry, StoryId
from arcwright_ai.output.provenance import append_entry
from arcwright_ai.output.run_manager import RunStatusValue, update_run_status
from arcwright_ai.output.summary import write_halt_report
```

Note: `engine/state.py`'s `StoryState` is imported only for type hints in `handle_graph_halt()`. Use `TYPE_CHECKING` guard to avoid a direct runtime dependency:
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from arcwright_ai.engine.state import StoryState
```

This keeps the runtime dependency surface clean while allowing the type system to verify the API.

### Project Structure Notes

Files created by this story:
```
src/arcwright_ai/cli/halt.py         # NEW: HaltController class
tests/test_cli/test_halt.py          # NEW: Tests for HaltController
```

Files modified by this story:
```
src/arcwright_ai/cli/dispatch.py     # MODIFIED: refactor exception handlers to use HaltController
tests/test_cli/test_dispatch.py      # MODIFIED: update halt tests for HaltController delegation
```

Files NOT modified (confirmed unchanged):
```
src/arcwright_ai/cli/app.py          # Unchanged — no new commands
src/arcwright_ai/engine/graph.py     # Unchanged — graph shape unchanged
src/arcwright_ai/engine/nodes.py     # Unchanged — node logic unchanged (helper functions reuse is via logic duplication or import)
src/arcwright_ai/engine/state.py     # Unchanged — StoryState, ProjectState unchanged
src/arcwright_ai/output/run_manager.py  # Unchanged — called as-is
src/arcwright_ai/output/summary.py   # Unchanged — called as-is
src/arcwright_ai/output/provenance.py   # Unchanged — called as-is
src/arcwright_ai/core/types.py       # Unchanged — BudgetState, ProvenanceEntry unchanged
src/arcwright_ai/core/constants.py   # Unchanged — all needed constants exist
src/arcwright_ai/core/exceptions.py  # Unchanged — all needed exceptions exist
```

### Known Pitfalls from Epics 1-5.1

1. **`__all__` ordering must be alphabetical** — ruff enforces this. Ensure `halt.py`'s `__all__` and any additions to `dispatch.py`'s `__all__` are sorted.
2. **No aspirational exports** — only export symbols that actually exist. Do NOT pre-export Story 5.3+ symbols (e.g., resume handler).
3. **`from __future__ import annotations`** at the top of every module.
4. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just `ruff check src/arcwright_ai/cli/`), and failures in ANY file must be reported honestly.
5. **File list in Dev Agent Record must match actual git changes** — verify against `git status` and `git diff --name-only` before claiming completion.
6. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
7. **Best-effort artifact writes**: EVERY `run_manager` call, `write_halt_report()` call, and `append_entry()` call in the halt controller must be wrapped in `try: ... except Exception: logger.warning(...)`. Artifact writes must NEVER prevent the halt controller from returning an exit code.
8. **`BudgetState` is frozen** — do not attempt mutation. Use `model_dump()` for serialization.
9. **`Decimal` for cost** — `BudgetState.estimated_cost` and `max_cost` are `Decimal`. Format with `str()` or `${budget.estimated_cost}` in output strings.
10. **Mock at callsite, not source module** — when patching `write_halt_report` in tests, use `monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", ...)`.
11. **Two-venv environment** — `.venv` (Python 3.14) for dev/test, `.venv-studio` (Python 3.13) for LangGraph Studio.
12. **`_dispatch_epic_async()` refactoring must preserve the happy path** — only the error handling paths change. The success path (all stories complete → COMPLETED status → run.complete event) must remain identical.
13. **`finalize_node` already handles graph-level ESCALATED** — the graph's `finalize_node` calls `write_halt_report()` from `summary.py` for ESCALATED states. The halt controller's `handle_graph_halt()` should NOT duplicate this call. Instead, it should: (a) check if `summary.md` already exists (written by finalize_node), (b) only call `write_halt_report()` if not already written. Alternatively, since `write_halt_report()` is idempotent (overwrites), calling it again is safe but redundant. **Decision**: Call it anyway — idempotent overwrite ensures the run-level summary always reflects the halt controller's view, which includes cross-story context (completed stories list) that `finalize_node` does not have.
14. **Run_manager expects string `run_id`** — `update_run_status()` takes `str` not `RunId`. Convert with `str(run_id)`.
15. **The `_halt_reason_from_exit_code()` function in dispatch.py** should be removed after refactoring, as its logic moves into `HaltController`. However, if any tests reference it directly, update them.
16. **`StoryState` typing** — import `StoryState` under `TYPE_CHECKING` only. At runtime, the halt controller receives it as a parameter but doesn't need the runtime import since it only accesses attributes via duck typing. Using `TYPE_CHECKING` keeps the dependency graph clean.

### Git Intelligence

Recent commits (last 5 relevant):
1. `feat(epic-5): complete story 5-1 epic dispatch CLI-to-engine pipeline` — full epic dispatch with budget carry-forward, confirmation, run_manager integration
2. `chore: ignore .langgraph_api/ runtime state directory` — housekeeping
3. `docs: document BMAD workflow customizations` — documentation
4. `feat(workflow): add git diff audit step to dev-story workflow` — workflow improvement
5. `chore: Epic 4 retrospective, close sprint tracking` — retro with action items

Patterns established:
- Epic dispatch loop structure is stable (from 5.1)
- Output package (provenance, run_manager, summary) is complete and stable
- Engine nodes handle per-story lifecycle; CLI handles run-level lifecycle
- Best-effort artifact writes are the standard pattern across all existing code
- 478 tests passing, quality gates clean

### References

- [Source: _spec/planning-artifacts/epics.md — Epic 5, Story 5.2]
- [Source: _spec/planning-artifacts/architecture.md — Decision 2: Retry & Halt Strategy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 8: Logging & Observability]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/prd.md — FR4 (halt on max retries), NFR2 (progress recovery), NFR3 (graceful error handling)]
- [Source: _spec/implementation-artifacts/5-1-epic-dispatch-cli-to-engine-pipeline.md — current dispatch implementation, halt handling basics]
- [Source: src/arcwright_ai/cli/dispatch.py — _dispatch_epic_async() exception handlers (6 duplicated blocks)]
- [Source: src/arcwright_ai/engine/nodes.py — finalize_node, _derive_halt_reason(), _build_validation_history_dicts(), _derive_suggested_fix()]
- [Source: src/arcwright_ai/output/summary.py — write_halt_report() API and NFR18 field structure]
- [Source: src/arcwright_ai/output/run_manager.py — update_run_status(), RunStatusValue]
- [Source: src/arcwright_ai/output/provenance.py — append_entry()]
- [Source: src/arcwright_ai/core/types.py — BudgetState, ProvenanceEntry]
- [Source: src/arcwright_ai/core/exceptions.py — full exception hierarchy]
- [Source: src/arcwright_ai/core/constants.py — EXIT_* codes]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- 2026-03-06: `.venv/bin/python -m mypy --strict src/arcwright_ai/cli/dispatch.py src/arcwright_ai/cli/halt.py` → success (no issues)
- 2026-03-06: `.venv/bin/ruff check src/arcwright_ai/cli/dispatch.py src/arcwright_ai/cli/halt.py tests/test_cli/test_halt.py` → all checks passed
- 2026-03-06: `.venv/bin/pytest tests/test_cli/test_halt.py tests/test_cli/test_dispatch.py -q` → 80 passed
- 2026-03-06: `.venv/bin/ruff check .` → all checks passed
- 2026-03-06: `.venv/bin/python -m mypy --strict src/` → success (no issues found in 38 source files)
- 2026-03-06: `.venv/bin/pytest -q` → 530 passed, 313 warnings in 5.07s

### Completion Notes List

- Created `src/arcwright_ai/cli/halt.py` with `HaltController` class consolidating all halt coordination (Tasks 1–7).
- Refactored `_dispatch_epic_async()` in `dispatch.py` to delegate to `HaltController`; removed `_halt_reason_from_exit_code()` and six duplicated exception handlers; now single `except Exception` block (Task 6, AC#11, #12).
- Added NFR3 SDK error wrapping with expanded coverage around `graph.ainvoke()` (`TimeoutError`, `ConnectionError`, `httpx.HTTPStatusError`, `json.JSONDecodeError`) — routes through `AgentError` with full traceback + story/budget context (AC#9).
- NFR2 guard: `assert story_slug not in completed_stories` raises `AssertionError` with actionable message if invoked on a completed story (AC#10).
- All artifact writes (`write_halt_report`, `update_run_status`, `append_entry`) are best-effort — wrapped in `try/except Exception` so failures never suppress the exit code (AC#2, #3, #4 notes).
- Ruff UP041 fix applied (`asyncio.TimeoutError` → builtin `TimeoutError`); TC003 fix applied (moved `Path` to `TYPE_CHECKING` block); RUF100 fix applied (removed unused BLE001 noqa directives).
- Updated `tests/test_cli/test_dispatch.py` `_patch_epic_deps` to patch `arcwright_ai.cli.halt.*` callsites, fixing 1 pre-existing test regression (Task 9).
- Updated `tests/test_cli/test_halt.py` to include additional NFR3/AC coverage (`HTTPStatusError` wrapping, graph-halt completed-story guard, explicit SDK halt-reason mapping) in addition to existing D6/NFR2/best-effort coverage.
- Full quality gate result: 530 tests pass, ruff 0 violations across 75 files, mypy --strict 0 issues across 38 source files.

### File List

- `arcwright-ai/src/arcwright_ai/cli/halt.py` (NEW)
- `arcwright-ai/src/arcwright_ai/cli/dispatch.py` (MODIFIED)
- `arcwright-ai/tests/test_cli/test_halt.py` (NEW)
- `arcwright-ai/tests/test_cli/test_dispatch.py` (MODIFIED)
- `_spec/implementation-artifacts/sprint-status.yaml` (MODIFIED)
- `_spec/implementation-artifacts/5-2-halt-controller-graceful-halt-on-unrecoverable-failure.md` (MODIFIED)

### Change Log

| Change | Reason |
|---|---|
| Created `cli/halt.py` — `HaltController` class | Consolidate halt coordination from 6 duplicated exception handlers into one tested module (AC#11, AC#12) |
| Removed `_halt_reason_from_exit_code()` from `dispatch.py` | Logic moved into `HaltController._halt_reason_for_exception()` |
| Removed `ScmError`, `ValidationError`, `EXIT_SCM` imports from `dispatch.py` | No longer needed after delegation to `HaltController` |
| Added NFR3 inner `try/except (TimeoutError, ConnectionError)` in `dispatch.py` | Wrap SDK transport errors as `AgentError` before they reach halt controller (AC#9) |
| Updated `_patch_epic_deps` in `test_dispatch.py` | Patch halt.py callsites so existing dispatch tests remain green after delegation refactor |
| Added `_noop_write_halt_report`, `_noop_append_entry` stubs in `test_dispatch.py` | Support new halt.py patches in dispatch test helpers |
| Created `tests/test_cli/test_halt.py` — 49 tests | Full AC coverage: D6 taxonomy, halt reasons, NFR2, NFR3, best-effort, resume command (AC#18) |
| Senior Developer Review (AI) completed | Initial pass identified 2 HIGH + 3 MEDIUM issues and generated follow-up actions |
| Follow-up remediation pass completed | All HIGH/MEDIUM follow-ups implemented with additional defensive coverage; status returned to review |

## Senior Developer Review (AI)

### Reviewer

GitHub Copilot (GPT-5.3-Codex)

### Date

2026-03-06

### Outcome

Approved (Post-Remediation)

### Approval Timestamp

2026-03-06T00:00:00Z

### Remediation Status

- 2026-03-06 remediation pass completed: all previously logged HIGH and MEDIUM findings addressed in code/tests.
- Full-suite verification completed: `ruff check .`, `mypy --strict src/`, and `pytest -q` all passed (530 tests).
- Story remains in `review` and is approved for handoff.

### Scope Reviewed

- Story file and ACs for Story 5.2
- Claimed file list vs git working tree changes
- Implementation files: `arcwright-ai/src/arcwright_ai/cli/halt.py`, `arcwright-ai/src/arcwright_ai/cli/dispatch.py`
- Test files: `arcwright-ai/tests/test_cli/test_halt.py`, `arcwright-ai/tests/test_cli/test_dispatch.py`

### Git vs Story File List Audit

- Files present in git status and documented in File List are aligned.
- Note: `git diff --name-only` does not include untracked files; untracked files were confirmed via `git status --porcelain`.

### Findings (Resolved)

- Initial review findings are fully remediated.
- AC#9 SDK coverage now includes `TimeoutError`, `ConnectionError`, `httpx.HTTPStatusError`, and `json.JSONDecodeError` wrapping.
- NFR3 traceback and story/budget context logging is now emitted when SDK failures are wrapped.
- AC#5 reason taxonomy now emits explicit `"SDK error"` classification for SDK transport/service failures.
- NFR2 guard parity is present in both `handle_halt()` and `handle_graph_halt()`.
- Dev Agent Record evidence now includes focused and full-suite gate outputs, including 530 passing tests.

### Validation Checks Performed During Review

- `pytest tests/test_cli/test_halt.py -q` → 49 passed.
- `pytest tests/test_cli/test_dispatch.py -q` → 28 passed.
- `.venv/bin/ruff check .` → all checks passed.
- `.venv/bin/python -m mypy --strict src/` → success (no issues found in 38 source files).
- `.venv/bin/pytest -q` → 530 passed, 313 warnings in 5.07s.

### Recommendation

- Findings from the initial pass are resolved; proceed with normal review/merge flow.
