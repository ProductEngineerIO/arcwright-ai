# Story 12.4: Dispatch Loop Halt on Merge Failure

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the epic dispatch loop,
I want to inspect the `merge_outcome` on a completed story's state and halt the epic when CI failed or timed out,
So that subsequent stories never build on stale, unmerged code.

## Acceptance Criteria (BDD)

### AC 1: Halt on CI failure

**Given** `_dispatch_epic_async()` story loop in `cli/dispatch.py` (~L632–717)
**When** `graph.ainvoke()` returns a story with status SUCCESS
**And** `result.merge_outcome` is `"ci_failed"`
**Then** the loop breaks with a warning log: _"Epic halted: Story {slug} PR merge failed (CI ci_failed). Fix the PR and run `arcwright dispatch --resume` to continue."_
**And** the dispatch function returns and the run is marked HALTED

### AC 2: Halt on timeout

**Given** the same story loop
**When** `result.merge_outcome` is `"timeout"`
**Then** the loop halts with the same pattern as AC 1 (different outcome string in the log message)
**And** the log message is: _"Epic halted: Story {slug} PR merge failed (CI timeout). Fix the PR and run `arcwright dispatch --resume` to continue."_

### AC 3: Continue on merged, skipped, or None

**Given** the same story loop
**When** `result.merge_outcome` is `"merged"`, `"skipped"`, or `None`
**Then** the loop continues to the next story without halting

### AC 4: Story SUCCESS status preserved

**Given** a story completes with status SUCCESS but `merge_outcome` is `"ci_failed"` or `"timeout"`
**When** the dispatch loop halts
**Then** the story's SUCCESS status is NOT changed — the story code was valid, only the merge failed
**And** the halt is at the epic level, not the story level

### AC 5: Backward compatibility with None merge_outcome

**Given** pre-existing stories without the `merge_outcome` field (`merge_outcome is None`)
**When** the dispatch loop checks `merge_outcome`
**Then** the loop continues (None is not a halt condition)

### AC 6: Import MergeOutcome enum for comparison

**Given** the merge outcome check in `dispatch.py`
**When** comparing `merge_outcome` values
**Then** `MergeOutcome` is imported from `arcwright_ai.scm` (enum, not bare strings) for the comparison:
```python
from arcwright_ai.scm import MergeOutcome

if final_story_state.merge_outcome in (MergeOutcome.CI_FAILED.value, MergeOutcome.TIMEOUT.value):
    ...
```
**And** the comparison uses `.value` since `StoryState.merge_outcome` is `str | None`, not `MergeOutcome`

### AC 7: Unit tests

**Given** the test suite
**When** tests are run
**Then** tests verify:
  - `test_dispatch_halts_on_ci_failed_merge_outcome`
  - `test_dispatch_halts_on_timeout_merge_outcome`
  - `test_dispatch_continues_on_merged_outcome`
  - `test_dispatch_continues_on_none_outcome`
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

## Tasks / Subtasks

- [x] Task 1: Add merge outcome check to story loop (AC: #1, #2, #3, #4, #5)
  - [x] 1.1: In `src/arcwright_ai/cli/dispatch.py`, add import at the top of the file:
    ```python
    from arcwright_ai.scm import MergeOutcome
    ```
    Verify this is valid per package DAG: `cli → scm → core` is a legal edge. `dispatch.py` already imports from `arcwright_ai.scm` (if not, it imports from `arcwright_ai.engine` which imports from `scm`).

  - [x] 1.2: In `_dispatch_epic_async()`, after the SUCCESS path check (~L776, after `last_completed = story_slug` and `completed_stories.append(story_slug)`) — but BEFORE moving to the next iteration — add the merge outcome halt check:
    ```python
    # Check merge outcome for epic chain integrity (Story 12.4 / D10)
    if final_story_state.merge_outcome in (
        MergeOutcome.CI_FAILED.value,
        MergeOutcome.TIMEOUT.value,
    ):
        logger.warning(
            "dispatch.epic.halt.merge_failed",
            extra={
                "data": {
                    "story": story_slug,
                    "merge_outcome": final_story_state.merge_outcome,
                    "epic": str(epic_id),
                }
            },
        )
        typer.echo(
            f"⚠ Epic halted: Story {story_slug} PR merge failed "
            f"(CI {final_story_state.merge_outcome}). "
            f"Fix the PR and run `arcwright dispatch --resume` to continue.",
            err=True,
        )
        # Mark run as halted and return
        try:
            await update_run_status(
                project_root,
                str(run_id),
                status=RunStatusValue.HALTED,
                last_completed_story=last_completed,
                budget=accumulated_budget,
            )
        except Exception:
            logger.warning(
                "run_manager.write_error",
                extra={"data": {"operation": "update_run_status", "status": "HALTED"}},
            )
        return EXIT_HALT
    ```

  - [x] 1.3: **Placement detail:** The check goes AFTER the `exit_code != EXIT_SUCCESS` block (which handles story-level failures) and AFTER `completed_stories.append(story_slug)`. This is because the story IS successful — the code was valid. The halt is an epic-level decision about chain integrity, not a story-level failure. The exact insertion point is after L780 (after `project_state.completed_stories = len(completed_stories)`).

  - [x] 1.4: **Define `EXIT_HALT`:** Check if `EXIT_HALT` constant already exists in `dispatch.py`. If not, define it near the existing `EXIT_SUCCESS` constant. Use exit code `2` (distinct from `EXIT_SUCCESS=0` and typical error `EXIT_FAILURE=1`). If the project uses a different halt exit code convention, match it.

  - [x] 1.5: **Alternative: Reuse halt_controller.** If the project's halt_controller pattern is the preferred way to handle halts (see L770–775 where `halt_controller.handle_graph_halt()` is called for non-SUCCESS stories), consider routing through the halt controller instead of directly returning. Review `halt_controller.handle_graph_halt()` to see if it accepts a "merge failed" scenario, or if a new method like `handle_merge_halt()` is needed. **Preferred approach:** Keep it simple with a direct `break` and return, since this is a clean halt (not an error) and the halt_controller is designed for graph-level failures.

- [x] Task 2: Unit tests (AC: #7)
  - [x] 2.1: In `tests/test_cli/test_dispatch.py`, add `test_dispatch_halts_on_ci_failed_merge_outcome`:
    - Mock `graph.ainvoke()` to return a `StoryState` with `status=TaskState.SUCCESS` and `merge_outcome="ci_failed"`
    - Assert dispatch returns `EXIT_HALT` (or appropriate halt code)
    - Assert only 1 story was dispatched (second story should not start)
    - Assert warning log `"dispatch.epic.halt.merge_failed"` was emitted

  - [x] 2.2: Add `test_dispatch_halts_on_timeout_merge_outcome`:
    - Same as 2.1 but with `merge_outcome="timeout"`
    - Assert same halt behavior

  - [x] 2.3: Add `test_dispatch_continues_on_merged_outcome`:
    - Mock `graph.ainvoke()` to return `StoryState` with `merge_outcome="merged"` for 2 stories
    - Assert both stories dispatched
    - Assert no halt log emitted

  - [x] 2.4: Add `test_dispatch_continues_on_none_outcome`:
    - Mock `graph.ainvoke()` to return `StoryState` with `merge_outcome=None`
    - Assert dispatch continues normally (backward compat)

  - [x] 2.5: Run full suite: `uv run ruff check src/ tests/ && uv run mypy --strict src/ && uv run pytest` — zero failures, zero regressions

## Dev Notes

### Architecture Compliance

- **Package DAG (Mandatory):** `cli → scm → core` is valid. Adding `from arcwright_ai.scm import MergeOutcome` to `dispatch.py` follows the same pattern as `cli → engine → scm` (dispatch already imports from engine).
- **D10 (CI-Aware Merge Wait):** This is the final piece — the dispatch loop halt that prevents stale-code chaining. Without this, a CI failure would be logged but the next story would still proceed.
- **NFR2 (Recoverable partial completion):** The halt preserves completed stories. The `--resume` flag (existing mechanism) allows the developer to fix the failing PR, let auto-merge complete, and then resume the epic from the halted point. No changes to `--resume` logic needed.
- **Best-effort SCM pattern preserved:** The story status remains SUCCESS. The epic halt is an orchestration-level decision, consistent with the principle that SCM failures don't invalidate code quality.

### Exact Code Location for Insertion

In `_dispatch_epic_async()`, the story loop success path is at approximately L776–780:

```python
                last_completed = story_slug
                completed_stories.append(story_slug)
                project_state.completed_stories = len(completed_stories)
                # ← INSERT merge outcome check HERE
        # (end of for loop)
```

The check must go BEFORE the `for` loop's next iteration. After the check, if halt conditions are not met, the loop naturally continues to `idx + 1`.

### Dispatch Exit Codes

Review existing exit code constants in `dispatch.py`:
- `EXIT_SUCCESS = 0` — all stories completed
- Check for `EXIT_FAILURE`, `EXIT_HALT`, or similar constants
- The halt controller in the existing non-SUCCESS path returns an exit code from `handle_graph_halt()`
- For the merge-halt case, use a distinct exit code that signals "halted due to merge failure, resume possible"

### Existing halt_controller Pattern

The non-SUCCESS path (~L770) uses:
```python
exit_code = await halt_controller.handle_graph_halt(
    story_state=project_state.stories[idx],
    accumulated_budget=accumulated_budget,
    completed_stories=completed_stories,
    last_completed=last_completed,
)
return exit_code
```

For the merge halt, we could either:
1. **Direct return** (simpler) — log, update run status, return exit code
2. **Route through halt_controller** — if it has a generic interface

Prefer option 1 unless the halt_controller already handles arbitrary halt reasons.

### Previous Story Intelligence (Story 12.3)

- Story 12.3 sets `state.merge_outcome` in `commit_node`. This story reads it in the dispatch loop.
- The `merge_outcome` field is `str | None` on `StoryState` — compare against `MergeOutcome.CI_FAILED.value` (string `"ci_failed"`) and `MergeOutcome.TIMEOUT.value` (string `"timeout"`).
- When `auto_merge=False`, `merge_outcome` is `"skipped"` — the loop should continue.
- When `merge_outcome is None` (no auto-merge block ran, e.g. no worktree), the loop should continue.

### Test Patterns (test_dispatch.py)

The existing dispatch tests (~L259–330) show:
- Mocking pattern for `graph.ainvoke()` with `AsyncMock`
- Story state construction with `StoryState(...)`
- SCM function mocking: `commit_story`, `create_worktree`, etc.
- Exit code assertions

For new tests, mock `graph.ainvoke()` to return a `StoryState` (or dict) with the desired `merge_outcome` value set, and assert the dispatch function's return value and log output.

### Files Touched

- `src/arcwright_ai/cli/dispatch.py` — Merge outcome check after story SUCCESS, import `MergeOutcome`
- `tests/test_cli/test_dispatch.py` — 4 new dispatch halt tests

### References

- [Source: _spec/implementation-artifacts/ci-aware-merge-wait.md#Task 4] — Task 4 implementation plan
- [Source: _spec/planning-artifacts/architecture.md#D10] — CI-Aware Merge Wait architectural decision
- [Source: _spec/planning-artifacts/epics.md#Story 12.4] — Epic story definition with AC
- [Source: src/arcwright_ai/cli/dispatch.py#L632–780] — Story loop in `_dispatch_epic_async()`
- [Source: src/arcwright_ai/cli/dispatch.py#L770–775] — Existing halt_controller usage for non-SUCCESS stories
- [Source: tests/test_cli/test_dispatch.py#L259–330] — Existing dispatch test patterns

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6 (GitHub Copilot)

### Debug Log References

N/A — no debug issues encountered.

### Completion Notes List

- Imported `MergeOutcome` from `arcwright_ai.scm` and `EXIT_SCM` from constants (used exit code 4 for SCM merge failures, matching existing convention — no `EXIT_HALT` needed)
- Added merge outcome halt check in `_dispatch_epic_async()` after `completed_stories.append(story_slug)` and before next loop iteration
- Enhanced the non-StoryState result path to propagate `merge_outcome` from the graph result into `final_story_state` — ensures robustness when result is a dict or mock object
- Used direct return pattern (option 1 from Dev Notes) rather than routing through halt_controller, since this is a clean orchestration-level halt
- Story SUCCESS status is preserved — the halt is epic-level, not story-level (AC #4)
- All 4 required tests added and passing: ci_failed halt, timeout halt, merged continue, None continue
- Full suite: 960 passed, ruff clean, mypy --strict clean

### File List

- `_spec/implementation-artifacts/12-4-dispatch-loop-halt-on-merge-failure.md` — Updated status/tasks/dev record during implementation and code-review follow-up
- `_spec/implementation-artifacts/sprint-status.yaml` — Updated story status to `review`
- `arcwright-ai/src/arcwright_ai/cli/dispatch.py` — Added merge outcome halt check in story loop, `merge_outcome` propagation in non-StoryState else branch, and routed merge halts through `HaltController.handle_merge_halt()`
- `arcwright-ai/src/arcwright_ai/cli/halt.py` — Added `handle_merge_halt()` to generate halt report/provenance/status/telemetry for epic-level merge-failure halts
- `arcwright-ai/tests/test_cli/test_dispatch.py` — Added 4 tests: `test_dispatch_halts_on_ci_failed_merge_outcome`, `test_dispatch_halts_on_timeout_merge_outcome`, `test_dispatch_continues_on_merged_outcome`, `test_dispatch_continues_on_none_outcome`
