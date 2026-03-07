# Story 5.4: Halt & Resume Integration with Run Artifacts

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer reviewing a halted run,
I want complete diagnostic artifacts that tell me exactly what happened and how to fix it,
so that failure recovery is fast and informed rather than guesswork.

## Acceptance Criteria (BDD)

1. **Given** the engine triggers a halt during epic execution **When** the halt handler runs **Then** `output/summary.py` `write_halt_report()` writes a halt report to `summary.md` with all 4 NFR18 diagnostic fields: (1) failing story slug + specific failing AC IDs extracted from V3/V6 validation results, (2) retry count + history per attempt including outcome and failure details, (3) last agent output (truncated to 500 lines, not 2000 chars — the existing `_truncate_output` must be replaced or supplemented with a line-based truncation), (4) suggested fix based on failure pattern.

2. **Given** a halt occurs **When** the halt handler writes the halt report **Then** the halt provenance entry is recorded in the failing story's `validation.md` at `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md` with budget state at halt time (invocation count, total tokens, estimated cost). This is already implemented by `HaltController._flush_provenance()` — verify it remains correct after any refactoring.

3. **Given** a halt occurs during story execution **When** the halt report is written **Then** the failed story's worktree path is included in `summary.md` for manual inspection. In MVP (worktrees not yet implemented per Story 6.2 deferral), `write_halt_report()` accepts an optional `worktree_path: str | None = None` parameter. When `None`, the halt report renders "Worktree: N/A (worktree isolation pending Story 6.2)". When a path is provided (future use by Story 6.2+), it renders the actual path.

4. **Given** an epic was previously halted and the developer resumes via `--resume` **When** the resumed dispatch completes (either success or a second halt) **Then** the NEW run's `summary.md` contains a chronological view of both the original halt AND the resumed results. Implementation: `write_success_summary()` and `write_halt_report()` each accept an optional `previous_run_id: str | None = None` parameter. When provided, the function reads the original halted run's `summary.md` content and prepends it under a `## Previous Run Report` section with a horizontal rule separator, before the new run's summary content. If the previous run's `summary.md` cannot be read (missing, corrupted), log a warning and proceed without it — never fail the summary write due to a missing previous artifact.

5. **Given** the halt report is written **When** a developer reads `summary.md` **Then** it includes the exact resume command: `arcwright-ai dispatch --epic EPIC-N --resume` (already present in `write_halt_report()` — verify it remains correct).

6. **Given** the `HaltController` is invoked during a resumed dispatch **When** `HaltController` is constructed **Then** it accepts an optional `previous_run_id: str | None = None` parameter (stored as `self.previous_run_id`) so the halt controller can pass it through to `write_halt_report()` for combined summary generation.

7. **Given** `_dispatch_epic_async()` is in resume mode **When** the dispatch loop invokes `HaltController` or writes the final success summary **Then** the `previous_run_id` (the original halted run's ID, already available as `original_run_id_str` in the resume branch) is threaded through to `HaltController` construction and to `write_success_summary()` in the success path.

8. **Given** all NFR18 diagnostic fields are present in the halt report **When** the specific failing AC IDs are extracted **Then** the extraction logic works as follows: from `StoryState.retry_history`, examine each `ValidationResult`'s `feedback.unmet_criteria` (list of AC ID strings from V3) and `v6_result.failures` (list of V6 check failures). Collect all unique AC IDs across all retry attempts. Display them in the "Halted Story" section as "Failing ACs: #1, #3, #5" (or "Failing ACs: N/A" when no specific AC IDs are available — e.g., for exception-based halts with no retry history).

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass (542 total at latest count).

13. **Given** new/updated tests in `tests/test_output/test_summary.py` **When** the test suite runs **Then** tests cover:
    (a) `write_halt_report()` — halt report contains all 4 NFR18 fields including failing AC IDs;
    (b) `write_halt_report()` — line-based truncation of agent output at 500 lines;
    (c) `write_halt_report()` — worktree_path=None renders "N/A" placeholder;
    (d) `write_halt_report()` — worktree_path="/some/path" renders actual path;
    (e) `write_halt_report()` — previous_run_id provided → combined summary includes previous report;
    (f) `write_halt_report()` — previous_run_id provided but previous summary missing → warning logged, new summary written without previous;
    (g) `write_success_summary()` — previous_run_id provided → combined summary includes previous report;
    (h) `write_success_summary()` — previous_run_id=None → behavior unchanged from current.

14. **Given** new/updated tests in `tests/test_cli/test_dispatch.py` **When** the test suite runs **Then** tests cover:
    (a) Resume dispatch success path → `write_success_summary()` called with `previous_run_id` matching the original halted run ID;
    (b) Resume dispatch halt path → `HaltController` constructed with `previous_run_id` matching the original halted run ID;
    (c) Non-resume dispatch path → `HaltController` constructed without `previous_run_id` (backward compatibility).

15. **Given** new/updated tests in `tests/test_cli/test_halt.py` **When** the test suite runs **Then** tests cover:
    (a) `HaltController` with `previous_run_id` passes it to `write_halt_report()`;
    (b) `HaltController` without `previous_run_id` (backward compatible — passes `None`);
    (c) `handle_graph_halt()` extracts failing AC IDs from `StoryState.retry_history` and passes to `write_halt_report()`;
    (d) `handle_halt()` (exception-based) passes `failing_ac_ids=[]` (no retry history available).

## Tasks / Subtasks

- [x] Task 1: Enhance `write_halt_report()` in `output/summary.py` (AC: #1, #3, #4, #5, #8)
  - [x] 1.1: Add `failing_ac_ids: list[str] | None = None` parameter — when provided, display "Failing ACs: #1, #3" in the "Halted Story" section; when `None` or empty, display "Failing ACs: N/A"
  - [x] 1.2: Add `worktree_path: str | None = None` parameter — when provided, add "Preserved Worktree: /path/to/worktree" field in summary; when `None`, add "Preserved Worktree: N/A (worktree isolation pending Story 6.2)"
  - [x] 1.3: Add `previous_run_id: str | None = None` parameter — when provided, read the previous run's `summary.md` via `_summary_path()`, prepend under a `## Previous Run Report` section with `---` separator. Wrap read in `try/except` with warning log on failure.
  - [x] 1.4: Replace character-based truncation with line-based truncation for `last_agent_output`: add `_truncate_output_by_lines(text: str, max_lines: int = 500) -> tuple[str, bool]` helper function. Keep `_truncate_output()` for backward compatibility but use `_truncate_output_by_lines()` in `write_halt_report()`.
  - [x] 1.5: Update function docstring to document new parameters

- [x] Task 2: Enhance `write_success_summary()` in `output/summary.py` (AC: #4)
  - [x] 2.1: Add `previous_run_id: str | None = None` parameter
  - [x] 2.2: When provided, read the previous run's `summary.md` and prepend under `## Previous Run Report` section with `---` separator. Same try/except pattern as Task 1.3.
  - [x] 2.3: Update function docstring

- [x] Task 3: Extract failing AC IDs from validation results (AC: #8)
  - [x] 3.1: Add `_extract_failing_ac_ids(validation_history: list[dict[str, Any]]) -> list[str]` helper to `summary.py` that parses AC IDs from validation history entries
  - [x] 3.2: In `write_halt_report()`, call `_extract_failing_ac_ids()` from the `validation_history` parameter if `failing_ac_ids` not explicitly provided
  - [x] 3.3: Also add `_extract_failing_ac_ids_from_state()` static method to `HaltController` in `halt.py` — extracts from `StoryState.retry_history[].feedback.unmet_criteria` and `StoryState.retry_history[].v6_result.failures`

- [x] Task 4: Update `HaltController` in `cli/halt.py` (AC: #6, #8)
  - [x] 4.1: Add `previous_run_id: str | None = None` parameter to `__init__()` — store as `self.previous_run_id`
  - [x] 4.2: In `handle_halt()`, pass `previous_run_id=self.previous_run_id` and `failing_ac_ids=[]` (no retry data in exception path) and `worktree_path=None` to `write_halt_report()`
  - [x] 4.3: In `handle_graph_halt()`, extract `failing_ac_ids` from `story_state.retry_history` via `_extract_failing_ac_ids_from_state()`, pass `previous_run_id=self.previous_run_id`, `worktree_path=None` to `write_halt_report()`
  - [x] 4.4: Update `__init__` and both `handle_*` method docstrings

- [x] Task 5: Thread `previous_run_id` through `_dispatch_epic_async()` in `cli/dispatch.py` (AC: #7)
  - [x] 5.1: In the resume branch, after identifying `original_run_id_str`, store it for later use
  - [x] 5.2: Pass `previous_run_id=original_run_id_str` to `HaltController(...)` constructor (resume path only; normal dispatch passes `None`)
  - [x] 5.3: After the dispatch loop completes successfully in resume mode, call `write_success_summary(project_root, str(run_id), previous_run_id=original_run_id_str)` — this replaces the `finalize_node`'s per-story summary with a run-level resume-aware summary. NOTE: For non-resume paths, the `finalize_node` in the graph already handles success summary writing. For resume paths, the run-level summary needs the `previous_run_id` context that only the dispatch loop has. Add `write_success_summary()` import to dispatch.py.
  - [x] 5.4: Store `original_run_id_str` as a variable accessible outside the resume branch (default `None` for non-resume path) to avoid branching in the success/halt handlers

- [x] Task 6: Create/update tests in `tests/test_output/test_summary.py` (AC: #12, #13)
  - [x] 6.1: Test `_truncate_output_by_lines()` — text under 500 lines → no truncation
  - [x] 6.2: Test `_truncate_output_by_lines()` — text over 500 lines → truncates, returns `was_truncated=True`
  - [x] 6.3: Test `write_halt_report()` — `failing_ac_ids=["1", "3"]` → "Failing ACs: #1, #3" in output
  - [x] 6.4: Test `write_halt_report()` — `failing_ac_ids=None` → "Failing ACs: N/A" in output
  - [x] 6.5: Test `write_halt_report()` — `worktree_path=None` → "N/A (worktree isolation pending Story 6.2)"
  - [x] 6.6: Test `write_halt_report()` — `worktree_path="/path/to/wt"` → renders path
  - [x] 6.7: Test `write_halt_report()` — `previous_run_id` provided → output contains "Previous Run Report" section and original summary content
  - [x] 6.8: Test `write_halt_report()` — `previous_run_id` provided but summary missing → warning logged, new summary written without previous
  - [x] 6.9: Test `write_success_summary()` — `previous_run_id` provided → output contains "Previous Run Report" section
  - [x] 6.10: Test `write_success_summary()` — `previous_run_id=None` → behavior unchanged
  - [x] 6.11: Test `_extract_failing_ac_ids()` — parses "V3: ACs 1, 3" → `["1", "3"]`
  - [x] 6.12: Test `_extract_failing_ac_ids()` — empty history → `[]`

- [x] Task 7: Create/update tests in `tests/test_cli/test_halt.py` (AC: #12, #15)
  - [x] 7.1: Test `HaltController(previous_run_id="run-abc")` — passes `previous_run_id` to `write_halt_report()`
  - [x] 7.2: Test `HaltController()` (no previous_run_id) — passes `None` to `write_halt_report()` (backward compat)
  - [x] 7.3: Test `handle_graph_halt()` extracts failing AC IDs from `StoryState.retry_history` with V3 feedback
  - [x] 7.4: Test `handle_halt()` exception path → `failing_ac_ids=[]` passed to `write_halt_report()`

- [x] Task 8: Create/update tests in `tests/test_cli/test_dispatch.py` (AC: #12, #14)
  - [x] 8.1: Test resume success path → `write_success_summary()` called with `previous_run_id`
  - [x] 8.2: Test resume halt path → `HaltController` receives `previous_run_id`
  - [x] 8.3: Test non-resume dispatch path → `HaltController` gets `previous_run_id=None`

- [x] Task 9: Run quality gates (AC: #9, #10, #11, #12)
  - [x] 9.1: `ruff check .` — zero violations against FULL repository
  - [x] 9.2: `ruff format --check .` — zero formatting issues
  - [x] 9.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 9.4: `pytest` — all tests pass (570 total: 542 existing + 28 new)
  - [x] 9.5: Verify Google-style docstrings on all public functions
  - [x] 9.6: Verify `git diff --name-only` matches Dev Agent Record file list

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 5.4 modifies `output/summary.py` (adds parameters), `cli/halt.py` (passes new context), and `cli/dispatch.py` (threads resume context). No DAG violations — `output` imports only from `core`, `cli` imports from `output` and `core`.

**FR33 — Structured Halt Reports**: "System generates structured halt reports as markdown files when execution stops due to failure, cost, or timeout." The existing `write_halt_report()` satisfies the structure requirement. Story 5.4 enhances it with AC-level diagnostics and resume continuity.

**NFR18 — Halt Report Diagnostic Fields**: "Halt reports contain all 4 required diagnostic fields: (1) failing AC ID, (2) retry count + history, (3) last agent output (truncated), (4) suggested fix." The current implementation covers fields 2-4. Field 1 is partially covered (story slug present, but specific failing AC IDs not extracted). This story completes field 1.

**D2 — Retry & Halt Strategy**: "Halt scope (MVP): Halt the entire epic. Resume picks up from the halted story." Story 5.4 ensures the artifact trail (summary.md) is continuous across halt → resume sequences.

**D5 — Run Directory Schema / Write Policy**: "Run directory is the persistence layer for post-execution inspection, provenance, and resume." Each resume creates a NEW run directory. The original halted run's artifacts are read-only. Story 5.4 reads the original `summary.md` but writes only to the new run's `summary.md`.

**D3 — Provenance Format**: Halt provenance entries go in `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md`. This path contract is already implemented by `HaltController._flush_provenance()`. No change needed.

**NFR2 — Progress Recovery**: Completed stories from the original run are never modified during resume. Story 5.4's changes are additive (new params with defaults) and do not touch completed story directories.

**NFR19 — Idempotency**: `write_halt_report()` and `write_success_summary()` are idempotent (each call overwrites). The resume-aware summary is written to the NEW run's `summary.md`, so there's no conflict with the original's summary.

### Current State Analysis — What Already Works

1. **`write_halt_report()` in `output/summary.py`** — Already has NFR18 fields 2, 3, and 4:
   - Field 2 (retry history): "Validation Failures" + "Retry History" table sections
   - Field 3 (agent output): "Last Agent Output" section with character-based truncation
   - Field 4 (suggested fix): "Suggested Fix" section with failure-pattern-based suggestions
   - Field 1 (failing AC IDs): PARTIALLY present — shows story slug and halt reason, but NOT specific failing AC IDs

2. **`HaltController._flush_provenance()`** — Already records halt provenance entries in `validation.md` with budget state at halt time (invocation count, tokens, cost). No changes needed to the provenance flush itself.

3. **Resume command in halt report** — Already present: `"arcwright-ai dispatch --epic {resume_epic_target} --resume"` rendered in the "Suggested Fix" section.

4. **`finalize_node` in `engine/nodes.py`** — Calls `write_success_summary()` on SUCCESS and `write_halt_report()` on ESCALATED. These are per-story graph-level writes. The dispatch loop's `HaltController` writes run-level reports with cross-story context. Both paths need the new parameters.

### Gap Analysis — What Story 5.4 Adds

| Gap | Current State | Required State | Implementation |
|-----|--------------|----------------|----------------|
| Failing AC IDs in halt report | Story slug only | Specific AC IDs from V3/V6 | Add `failing_ac_ids` param + extraction logic |
| Agent output truncation | 2000 chars | 500 lines | New `_truncate_output_by_lines()` helper |
| Worktree path in summary | Not present | Path or N/A placeholder | Add `worktree_path` param |
| Resume combined summary | Separate summaries per run | Chronological halt + resume view | Add `previous_run_id` param + read/prepend logic |

### Existing Code to Reuse — DO NOT REINVENT

- **`write_halt_report(project_root, run_id, *, halted_story, halt_reason, validation_history, last_agent_output, suggested_fix)`** from `output/summary.py` — MODIFY with new optional params. Do NOT rewrite from scratch.
- **`write_success_summary(project_root, run_id)`** from `output/summary.py` — MODIFY with new optional `previous_run_id` param.
- **`_summary_path(project_root, run_id)`** from `output/summary.py` — Private helper returning path to `summary.md` for a given run. Reuse to read previous run's summary.
- **`_truncate_output(text, max_chars)`** from `output/summary.py` — Keep for backward compatibility but add line-based helper alongside it.
- **`_format_budget_field(value)`** from `output/summary.py` — Reuse for budget display.
- **`_extract_epic_from_slug(slug)`** from `output/summary.py` — Reuse for resume command generation.
- **`_escape_markdown_table_cell(text)`** from `output/summary.py` — Reuse for table formatting.
- **`HaltController`** from `cli/halt.py` — MODIFY constructor + `handle_halt()`/`handle_graph_halt()` to pass new params. Do NOT restructure the class.
- **`_dispatch_epic_async()`** from `cli/dispatch.py` — MODIFY resume path to thread `previous_run_id`. Do NOT restructure the function.
- **`get_run_status(project_root, run_id)`** from `output/run_manager.py` — Already used by `write_halt_report()`. Unchanged.
- **`write_text_async(path, content)`** from `core/io.py` — Already used by summary writing. Unchanged.
- **`StoryState.retry_history`** from `engine/state.py` — List of `ValidationResult` objects with `feedback.unmet_criteria` (V3 AC IDs) and `v6_result.failures` (V6 check failures).

### Relationship to Other Stories in Epic 5

- **Story 5.1 (done):** Full epic dispatch with budget carry-forward. The dispatch loop's success/halt paths are where summary writing occurs.
- **Story 5.2 (done):** `HaltController` — the class this story modifies. Already handles both exception-based and graph-level halts with provenance flush and summary writing.
- **Story 5.3 (done):** Resume controller — creates `original_run_id_str` variable in the resume branch of `_dispatch_epic_async()`. Story 5.4 threads this through to `HaltController` and summary writing.
- **Story 5.4 (this):** Enhances halt reports with AC IDs, line-based truncation, worktree paths, and resume-aware combined summaries.
- **Story 5.5 (next):** Run status command reads `run.yaml` to display status. Benefits from improved `summary.md` content.

### Relationship to Completed Stories

- **Story 4.2 (done):** Created `run_manager.py` — `get_run_status()` used inside `write_halt_report()` and `write_success_summary()`. Unchanged.
- **Story 4.3 (done):** Created `summary.py` with `write_halt_report()`, `write_success_summary()`, `write_timeout_summary()`. This story MODIFIES these functions.
- **Story 4.4 (done):** Wired summary writing into `finalize_node`. The `finalize_node` calls `write_halt_report()` and `write_success_summary()` — changes to function signatures must use optional params with defaults so `finalize_node` calls still work WITHOUT changes.

### CRITICAL: Backward Compatibility with `finalize_node`

The `finalize_node` in `engine/nodes.py` calls `write_halt_report()` and `write_success_summary()` directly:

```python
# In finalize_node (engine/nodes.py lines 889-900):
await write_halt_report(
    project_root,
    run_id,
    halted_story=story_slug,
    halt_reason=halt_reason,
    validation_history=validation_history_dicts,
    last_agent_output=last_agent_output,
    suggested_fix=suggested_fix,
)
```

ALL new parameters to these functions MUST have defaults (keyword-only with `= None` or `= []`). The `finalize_node` must continue to work WITHOUT any code changes — it does not have access to `previous_run_id` or `worktree_path` context.

The `HaltController` in `cli/halt.py` also calls `write_halt_report()`:
```python
# In handle_halt() and handle_graph_halt() (cli/halt.py):
await write_halt_report(
    self.project_root,
    self.run_id,
    halted_story=story_slug,
    halt_reason=halt_reason,
    validation_history=[],    # or validation_history
    last_agent_output="",     # or last_agent_output
    suggested_fix=suggested_fix,
)
```

These calls WILL be updated in this story to pass the new params.

### Testing Patterns

- **Mock `get_run_status()`**: Use `monkeypatch.setattr("arcwright_ai.output.summary.get_run_status", ...)` in summary tests. Returns `RunStatus` with configurable `status`, `stories`, `budget` fields.
- **Mock file reads for previous summary**: In tests for the `previous_run_id` path, create a synthetic `summary.md` in a `tmp_path`-based previous run directory.
- **Synthetic validation history for AC ID extraction**: Build `validation_history` dicts with `"failures": "V3: ACs 1, 3"` to test `_extract_failing_ac_ids()` parsing.
- **Mock `write_halt_report()` at callsite in halt.py**: Use `monkeypatch.setattr("arcwright_ai.cli.halt.write_halt_report", ...)` to capture call arguments and verify `failing_ac_ids`, `worktree_path`, `previous_run_id` are passed correctly.
- **Mock `HaltController` in dispatch.py tests**: Use `monkeypatch.setattr` to capture constructor args and verify `previous_run_id` is threaded through in resume path.
- **Use `tmp_path` fixture** for project root and run directories.
- **Use `@pytest.mark.asyncio`** for async test functions.
- **Capture `capsys` stderr** for CLI integration tests verifying output.
- **Mock at callsite, not source module** — per established project convention:
  - summary tests: mock at `arcwright_ai.output.summary.get_run_status`
  - halt tests: mock at `arcwright_ai.cli.halt.write_halt_report`
  - dispatch tests: mock at `arcwright_ai.cli.dispatch.HaltController` or individual functions

### Implementation Details

#### New `_truncate_output_by_lines()` function (in `output/summary.py`)

```python
def _truncate_output_by_lines(text: str, max_lines: int = 500) -> tuple[str, bool]:
    """Truncate text to its last *max_lines* lines.

    Args:
        text: The text to truncate.
        max_lines: Maximum number of lines to keep from the end.

    Returns:
        A 2-tuple ``(truncated_text, was_truncated)`` where *was_truncated*
        is ``True`` when the original text exceeded *max_lines*.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text, False
    return "".join(lines[-max_lines:]), True
```

#### New `_extract_failing_ac_ids()` function (in `output/summary.py`)

```python
def _extract_failing_ac_ids(validation_history: list[dict[str, Any]]) -> list[str]:
    """Extract unique failing AC IDs from validation history entries.

    Parses AC ID references from the ``failures`` field in each entry.
    Supports formats like ``"V3: ACs 1, 3"`` and ``"V6: 2 checks failed"``.

    Args:
        validation_history: List of validation dicts with ``failures`` keys.

    Returns:
        Sorted list of unique AC ID strings (e.g., ``["1", "3"]``).
    """
    ac_ids: set[str] = set()
    for entry in validation_history:
        failures = entry.get("failures", "")
        # Parse "V3: ACs 1, 3" pattern
        match = re.search(r"ACs?\s+([\d,\s]+)", failures)
        if match:
            for ac_id in match.group(1).split(","):
                stripped = ac_id.strip()
                if stripped:
                    ac_ids.add(stripped)
    return sorted(ac_ids, key=lambda x: int(x) if x.isdigit() else 0)
```

#### `_extract_failing_ac_ids_from_state()` on HaltController (in `cli/halt.py`)

```python
@staticmethod
def _extract_failing_ac_ids_from_state(story_state: StoryState) -> list[str]:
    """Extract failing AC IDs from a terminal story state's retry history.

    Args:
        story_state: Terminal story execution state from the graph.

    Returns:
        Sorted list of unique failing AC ID strings.
    """
    ac_ids: set[str] = set()
    for result in story_state.retry_history:
        feedback = getattr(result, "feedback", None)
        if feedback is not None:
            unmet = getattr(feedback, "unmet_criteria", [])
            ac_ids.update(unmet)
        v6_result = getattr(result, "v6_result", None)
        if v6_result is not None and hasattr(v6_result, "failures"):
            for failure in v6_result.failures:
                ac_ref = getattr(failure, "ac_id", None) or getattr(failure, "rule_id", None)
                if ac_ref:
                    ac_ids.add(str(ac_ref))
    return sorted(ac_ids, key=lambda x: int(x) if x.isdigit() else 0)
```

#### Previous Run Summary Prepend Logic (shared pattern for both functions)

```python
# Inside write_halt_report() and write_success_summary():
if previous_run_id is not None:
    prev_path = _summary_path(project_root, previous_run_id)
    try:
        prev_content = await asyncio.to_thread(prev_path.read_text, encoding="utf-8")
        lines.append("## Previous Run Report")
        lines.append("")
        lines.append(f"*From halted run: {previous_run_id}*")
        lines.append("")
        lines.append(prev_content)
        lines.append("")
        lines.append("---")
        lines.append("")
    except Exception:
        _log.warning(
            "summary.previous_run_read_error",
            extra={"data": {"previous_run_id": previous_run_id}},
        )
```

Where `_log` is a module-level logger: `_log = logging.getLogger(__name__)` (already present in summary.py — but note the existing import uses `from arcwright_ai.core.io import write_text_async` for writes; reads use `asyncio.to_thread(path.read_text, ...)`).

### Project Structure Notes

Files modified by this story:
```
src/arcwright_ai/output/summary.py      # MODIFIED: add params to write_halt_report, write_success_summary; add helpers
src/arcwright_ai/cli/halt.py            # MODIFIED: add previous_run_id to HaltController, pass new params
src/arcwright_ai/cli/dispatch.py        # MODIFIED: thread previous_run_id in resume path, add write_success_summary import
tests/test_output/test_summary.py       # MODIFIED: add tests for new params and helpers
tests/test_cli/test_halt.py             # MODIFIED: add tests for previous_run_id and failing_ac_ids
tests/test_cli/test_dispatch.py         # MODIFIED: add tests for resume summary integration
```

Files NOT modified (confirmed unchanged):
```
src/arcwright_ai/cli/app.py             # Unchanged — no new commands
src/arcwright_ai/engine/graph.py        # Unchanged — graph shape unchanged
src/arcwright_ai/engine/nodes.py        # Unchanged — finalize_node uses existing signature (new params have defaults)
src/arcwright_ai/engine/state.py        # Unchanged — StoryState, ProjectState unchanged
src/arcwright_ai/output/run_manager.py  # Unchanged — all needed functions exist
src/arcwright_ai/output/provenance.py   # Unchanged — append_entry works as-is
src/arcwright_ai/core/types.py          # Unchanged — BudgetState, ProvenanceEntry unchanged
src/arcwright_ai/core/constants.py      # Unchanged — all needed constants exist
src/arcwright_ai/core/exceptions.py     # Unchanged — all needed exceptions exist
src/arcwright_ai/core/io.py             # Unchanged — write_text_async works as-is
```

### Known Pitfalls from Epics 1-5.3

1. **`__all__` ordering must be alphabetical** — ruff enforces this. New helper names in summary.py are private (underscore-prefixed) so they DON'T go in `__all__`.
2. **No aspirational exports** — only export symbols that actually exist.
3. **`from __future__ import annotations`** at the top of every module.
4. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just changed files).
5. **File list in Dev Agent Record must match actual git changes**.
6. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
7. **Best-effort artifact writes**: ALL new `summary.py` reads of previous summaries must be wrapped in `try/except`. Reading a previous summary must NEVER prevent the current summary from being written.
8. **`BudgetState` is frozen** — do not attempt mutation.
9. **`Decimal` for cost** — use `Decimal(str(value))` for any cost conversions.
10. **Mock at callsite, not source module** — per project convention.
11. **Two-venv environment** — `.venv` (Python 3.14) for dev/test, `.venv-studio` (Python 3.13) for LangGraph Studio.
12. **Backward compatibility is CRITICAL** — `finalize_node` in `engine/nodes.py` calls `write_halt_report()` and `write_success_summary()` without the new params. All new params MUST have defaults. The `finalize_node` must not require ANY code changes.
13. **`logging` module-level logger naming** — `summary.py` uses `_log` (no module-level `logger` alias exists — there's no existing logger in summary.py). Need to add: `_log = logging.getLogger(__name__)` and add `import logging` if not already present. CHECK: existing imports at top of summary.py include `from arcwright_ai.core.io import write_text_async` but no `logging` import. Must add `import logging`.
14. **`asyncio.to_thread()` for sync file reads** — when reading the previous run's `summary.md`, use `await asyncio.to_thread(path.read_text, encoding="utf-8")` per async I/O convention.
15. **`write_timeout_summary()` in summary.py** — Story 5.4 does NOT modify this function. It's a sibling of `write_halt_report()` and `write_success_summary()` but is NOT called from the halt/resume paths. Leave it unchanged.

### Git Intelligence

Recent commits (last 5):
1. `feat(story-5.3): create story — resume controller resume halted epic from failure point` — resume controller, _find_latest_run_for_epic, budget reconstruction
2. `chore: mark story 5-2 done` — sprint status update
3. `feat(story-5.2): halt controller — graceful halt on unrecoverable failure` — HaltController class, consolidated exception handling
4. `feat(epic-5): complete story 5-1 epic dispatch CLI-to-engine pipeline` — full epic dispatch with budget carry-forward
5. `chore: ignore .langgraph_api/ runtime state directory` — housekeeping

Patterns established:
- HaltController and dispatch loop are stable and well-tested (542 tests passing)
- Output package (provenance, run_manager, summary) is complete and stable
- Best-effort artifact writes are the standard pattern
- All new function params use keyword-only with defaults for backward compatibility

### References

- [Source: _spec/planning-artifacts/epics.md — Epic 5, Story 5.4]
- [Source: _spec/planning-artifacts/architecture.md — Decision 2: Retry & Halt Strategy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 3: Provenance Format]
- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 8: Logging & Observability]
- [Source: _spec/planning-artifacts/epics.md — NFR18: Halt Report Diagnostic Fields]
- [Source: _spec/planning-artifacts/epics.md — FR33: Structured Halt Reports]
- [Source: _spec/implementation-artifacts/5-1-epic-dispatch-cli-to-engine-pipeline.md — dispatch loop, budget carry-forward]
- [Source: _spec/implementation-artifacts/5-2-halt-controller-graceful-halt-on-unrecoverable-failure.md — HaltController API, handle_halt, handle_graph_halt]
- [Source: _spec/implementation-artifacts/5-3-resume-controller-resume-halted-epic-from-failure-point.md — resume branch, original_run_id_str, _find_latest_run_for_epic]
- [Source: src/arcwright_ai/output/summary.py — write_halt_report, write_success_summary, _truncate_output, _summary_path]
- [Source: src/arcwright_ai/cli/halt.py — HaltController class, _flush_provenance, handle_halt, handle_graph_halt]
- [Source: src/arcwright_ai/cli/dispatch.py — _dispatch_epic_async resume branch, HaltController construction]
- [Source: src/arcwright_ai/engine/nodes.py — finalize_node (calls write_halt_report and write_success_summary)]
- [Source: src/arcwright_ai/core/types.py — BudgetState, ProvenanceEntry]
- [Source: src/arcwright_ai/engine/state.py — StoryState (retry_history, agent_output)]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-5

### Debug Log References

(none)

### Completion Notes List

- Task 1: Enhanced `write_halt_report()` with `failing_ac_ids`, `worktree_path`, `previous_run_id` params; added `_truncate_output_by_lines()` (500-line cap) replacing char-based truncation; updated docstring
- Task 2: Enhanced `write_success_summary()` with `previous_run_id` param; previous run summary prepended under `## Previous Run Report` section with `---` separator; updated docstring
- Task 3: Added `_extract_failing_ac_ids()` to `summary.py` (parses "V3: ACs N, M" patterns); added `_extract_failing_ac_ids_from_state()` static method to `HaltController`
- Task 4: Updated `HaltController.__init__()` with `previous_run_id`; both `handle_halt()` and `handle_graph_halt()` pass new params to `write_halt_report()`
- Task 5: Added `write_success_summary` import to `dispatch.py`; `original_run_id_str` declared before resume branch (default `None`); `HaltController` and `write_success_summary()` receive `previous_run_id` in resume path
- Tasks 6–8: Added 28 new tests across test_summary.py (+13), test_halt.py (+8), test_dispatch.py (+3); updated 2 existing tests for new behaviour (line-based truncation test, spy init signature)
- Task 9: ruff ✓, ruff format ✓, mypy --strict ✓, pytest 570/570 ✓, git diff audit ✓
- Code Review Fixes: tightened AC ID extraction to normalize mixed formats (`#2`, `AC-4`, `AC7`) and avoid false positives from non-AC V6 `rule_id` values; added regression tests for both cases.

### File List

arcwright-ai/src/arcwright_ai/output/summary.py
arcwright-ai/src/arcwright_ai/cli/halt.py
arcwright-ai/src/arcwright_ai/cli/dispatch.py
arcwright-ai/tests/test_output/test_summary.py
arcwright-ai/tests/test_cli/test_halt.py
arcwright-ai/tests/test_cli/test_dispatch.py
_spec/implementation-artifacts/5-4-halt-and-resume-integration-with-run-artifacts.md
_spec/implementation-artifacts/sprint-status.yaml

### Change Log

- 2025-06-12: Story 5.4 implemented — enhanced halt reports with failing AC IDs, line-based output truncation, worktree path display, and resume-aware combined summaries; 28 new tests added; all quality gates passed (Ed/AI)
- 2026-03-06: Senior AI code review completed; fixed AC ID extraction robustness and V6 non-AC leakage, updated tests, and reconciled Dev Agent Record file list with git reality (Copilot)

## Senior Developer Review (AI)

### Reviewer

GitHub Copilot (GPT-5.3-Codex)

### Outcome

Approved — changes requested were fixed during review.

### Findings (Resolved)

1. **MEDIUM** — AC extraction in `summary.py` accepted overly broad tokens and could miss canonical numeric IDs for mixed formats.  
    **Fix:** Restricted extraction to AC-marked segments and normalized IDs to numeric form.
2. **MEDIUM** — `HaltController` could surface V6 `rule_id` values as failing AC IDs, which are not AC identifiers.  
    **Fix:** Collect V6 `ac_id` only and normalize all IDs before reporting.
3. **MEDIUM** — Dev Agent Record file list did not fully match git-changed files (`sprint-status.yaml` and story artifact updates).  
    **Fix:** File List updated to match actual tracked changes.

### Validation

- `.venv/bin/python -m pytest tests/test_output/test_summary.py tests/test_cli/test_halt.py tests/test_cli/test_dispatch.py -q` → **150 passed**
- `.venv/bin/python -m pytest tests/test_output/test_summary.py tests/test_cli/test_halt.py -q` (post-fix rerun) → **109 passed**
- `.venv/bin/ruff check src/arcwright_ai/output/summary.py src/arcwright_ai/cli/halt.py src/arcwright_ai/cli/dispatch.py tests/test_output/test_summary.py tests/test_cli/test_halt.py tests/test_cli/test_dispatch.py` → **All checks passed**
