# Story 10.6: Auto-Merge Success Marked Error on Branch Cleanup Failure

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer running unattended dispatch with auto-merge,
I want merge outcome reporting to distinguish merge success from local cleanup failures,
So that a successfully merged PR is not incorrectly treated as a merge failure that can halt epic progression.

## Bug Report

**Observed behavior:**
During auto-merge flow, PR merge can succeed remotely but the system records `merge_outcome: error` when local post-merge branch cleanup fails (for example, trying to delete a branch still checked out by a worktree).

**Impact:**
- A successful merge may be interpreted as failure.
- Downstream dispatch logic may halt or misreport status based on incorrect merge outcome.
- Operator trust decreases because reported state conflicts with GitHub PR state.

## Acceptance Criteria (BDD)

### AC 1: Merge outcome reflects actual PR merge result

**Given** auto-merge is enabled and the remote PR merge succeeds
**When** local branch deletion/cleanup fails afterward
**Then** merge outcome is recorded as success for merge semantics
**And** cleanup failure is recorded separately as a warning/non-blocking cleanup result.

### AC 2: Cleanup errors are non-blocking after successful merge

**Given** PR is merged on GitHub
**When** local cleanup raises an error
**Then** story status remains success
**And** epic dispatch does not halt due to cleanup-only failure.

### AC 3: Structured logging separates merge and cleanup phases

**Given** merge and cleanup both execute
**When** events are emitted
**Then** logs include distinct events for:
- merge result (merged / not merged / failed)
- cleanup result (success / warning / failed)
**And** events include story slug, PR URL, and merge SHA when available.

### AC 4: Run artifact summary is unambiguous

**Given** run artifacts are generated
**When** validation/provenance/summary are written
**Then** summary clearly states PR merged status independently from cleanup status
**And** no `status=error` wording is used for merge when merge actually succeeded.

### AC 5: Regression tests cover split outcome model

**Given** SCM unit/integration tests
**When** tests run
**Then** there are tests for:
- merge success + cleanup failure
- merge failure + cleanup success (if possible)
- merge success + cleanup success
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Split merge result from cleanup result in SCM/engine flow (AC: #1, #2)
  - [x] 1.1: Identify where merge result is overwritten by cleanup failure.
  - [x] 1.2: Preserve successful merge outcome even if local cleanup fails.

- [x] Task 2: Improve event and provenance semantics (AC: #3, #4)
  - [x] 2.1: Emit separate structured events for merge and cleanup.
  - [x] 2.2: Update summary/provenance wording to avoid false merge error.

- [x] Task 3: Add regression tests (AC: #5)
  - [x] 3.1: Add focused tests in SCM + engine node layers for split outcomes.
  - [x] 3.2: Confirm dispatch routing behavior remains correct for cleanup-only failures.

- [x] Task 4: Run quality gates (AC: #5)
  - [x] 4.1: Run `ruff check src/ tests/`.
  - [x] 4.2: Run `mypy --strict src/`.
  - [x] 4.3: Run `pytest`.

## Dev Notes

### Candidate Files

- `src/arcwright_ai/scm/pr.py`
- `src/arcwright_ai/scm/worktree.py`
- `src/arcwright_ai/engine/nodes.py`
- `src/arcwright_ai/output/summary.py`
- `tests/test_scm/`
- `tests/test_engine/`

### Scope Boundaries

- Do not alter successful merge behavior.
- Do not suppress cleanup failures; record them as warnings.
- Keep auto-merge optional behavior unchanged.

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Completion Notes

**Root Cause:** `_merge_immediate` and `_step_a_queue_auto_merge` in `scm/pr.py` returned `MergeOutcome.ERROR` on any non-zero exit from `gh pr merge --delete-branch`, including the case where the merge itself succeeded on GitHub but local branch deletion failed because the branch was still checked out in a git worktree.

**Fix applied (split-outcome model):**
- `_merge_immediate`: After a non-zero exit, calls `_check_pr_state` to verify actual GitHub PR state. If the PR is MERGED, logs `scm.pr.post_merge_cleanup.failed` (warning) and returns `MergeOutcome.MERGED`. Only returns `ERROR` when the PR was genuinely not merged.
- `_step_a_queue_auto_merge`: After a non-zero exit, uses `_is_branch_cleanup_error(stderr)` to detect local-branch-checkout failures. If matched, logs `scm.pr.post_merge_cleanup.failed` and continues to the CI-wait step (returns `None`). Other errors still return `ERROR`.
- Added `_is_branch_cleanup_error(stderr)` helper that checks for "checked out at" / "cannot delete branch" patterns.
- `nodes.py`: Updated `remove_worktree` call to pass `delete_branch=True` when `merge_outcome == MERGED`, ensuring local branch cleanup after successful merge (whether or not `gh --delete-branch` was able to delete it while the worktree was active).
- Provenance rationale updated from `status=` to `merge_status=` to unambiguously reflect PR merge result.

**Tests added (7 new):**
- `test_pr.py`: merge-success+cleanup-failure→MERGED, real-failure→ERROR, success+success→MERGED, auto-queue+cleanup-failure continues to CI-wait, auto-queue real failure→ERROR
- `test_nodes.py`: remove_worktree receives `delete_branch=True` on MERGED, `delete_branch=False` on skipped/error

**All quality gates:** `ruff check` ✅ · `mypy --strict` ✅ · `pytest` 971 passed ✅

### File List

- `arcwright-ai/src/arcwright_ai/scm/pr.py`
- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/tests/test_scm/test_pr.py`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `_spec/implementation-artifacts/10-6-auto-merge-success-marked-error-on-branch-cleanup-failure.md`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/planning-artifacts/epics.md` (pre-existing: epic story count updated when 10.5/10.6 were added)

### Change Log

- 2026-03-18: Implemented split-outcome model — `_merge_immediate` verifies actual PR state after non-zero exit; `_step_a_queue_auto_merge` detects cleanup-only errors and continues; `nodes.py` passes `delete_branch=True` to `remove_worktree` on MERGED; provenance uses `merge_status=` field; 7 new regression tests added; 971 tests pass.
- 2026-03-18: Adversarial code review completed with no HIGH/MEDIUM findings; status advanced to done.
