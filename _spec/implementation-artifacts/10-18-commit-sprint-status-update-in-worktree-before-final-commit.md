# Story 10.18: Commit Sprint-Status Update in Worktree Before Final Commit

Status: review

## Story

As a developer using Arcwright AI for overnight dispatch,
I want the `sprint-status.yaml` "done" update to be written into the story's own git worktree and committed as part of the story's final commit,
so that the status change is actually included in the pushed branch and the PR — instead of silently landing as an uncommitted, orphaned change in the main project checkout.

## Acceptance Criteria

1. **Given** `commit_node` is dispatching a story with `state.worktree_path` set **When** the sprint-status "done" update runs **Then** it writes to `sprint-status.yaml` inside `state.worktree_path` (the story's worktree) — **not** `state.project_root` (the main checkout).
2. **Given** the sprint-status update targets the worktree **When** `commit_story()` subsequently runs `git add .` and commits **Then** the sprint-status.yaml change is included in the same commit as the rest of the story's changes, and is therefore present in the pushed branch and the PR diff.
3. **Given** the current call site occurs after `commit_story()` and `push_branch()` (immediately before `generate_pr_body()`) **When** this story is implemented **Then** that call site is removed, and the sprint-status update is instead invoked **before** `commit_story()` is called, inside the same `if state.worktree_path is not None:` block.
4. **Given** the sprint-status update now runs before `commit_story()` **When** `commit_story()` performs its "is the worktree clean?" check (`git status --porcelain`) **Then** the worktree is correctly detected as dirty (because the sprint-status write touched a tracked file), so a fresh closing commit is always created — even in the case where the coding agent had already committed cleanly and the worktree would otherwise have been clean.
5. **Given** the sprint-status update is now unconditional relative to `push_succeeded` (it happens before `push_branch()` is even attempted) **When** `push_branch()` subsequently fails **Then** the sprint-status change still exists in the local worktree commit (harmless — nothing is published on a failed push either way, matching pre-existing behavior for the rest of the story's code changes).
6. **Given** the helper's first path parameter previously implied "project root" **When** this story is implemented **Then** the parameter is renamed from `project_root` to `repo_root` (and its docstring updated) to accurately reflect that it now always receives a worktree path from its only call site.
7. **Given** any I/O or parsing error occurs during the sprint-status update (missing file, missing key, `OSError`, etc.) **When** the error is caught **Then** it is still logged as before (`scm.sprint_status.not_found` / `scm.sprint_status.key_not_found` / `scm.sprint_status.update_error`) and `commit_node` continues to call `commit_story()` normally — the update remains best-effort and never blocks the commit.
8. **Given** `state.worktree_path` is `None` **When** `commit_node` executes **Then** the sprint-status update is not attempted (matches the existing outer `if state.worktree_path is not None:` guard — no change in behavior for this case).
9. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1 — Relocate the call site in `commit_node` (AC: #1, #2, #3, #4, #5, #8)
  - [x] 1.1 In `engine/nodes.py`, inside `commit_node`, find the current call: `await _update_sprint_status_done(story_slug, project_root, state.config.methodology.artifacts_path)` — located inside `if push_succeeded:`, immediately before the `generate_pr_body()` / `open_pull_request()` block. **Delete this call site entirely.**
  - [x] 1.2 Add a new call **before** the `commit_hash = await commit_story(...)` invocation, still inside the outer `if state.worktree_path is not None:` block: `await _update_sprint_status_done(story_slug, state.worktree_path, state.config.methodology.artifacts_path)`
  - [x] 1.3 Confirm `story_title = _derive_story_title(story_slug)` (already computed just above) is unaffected by the reordering — no dependency between it and the sprint-status call
  - [x] 1.4 Do not wrap the new call in additional try/except at the call site — `_update_sprint_status_done` already catches and logs all its own exceptions internally (verify this remains true after Task 2's rename)

- [x] Task 2 — Rename `project_root` parameter to `repo_root` in the helper (AC: #6)
  - [x] 2.1 In `_update_sprint_status_done(story_slug: str, project_root: Path, artifacts_path: str) -> None`, rename the second parameter to `repo_root: Path`
  - [x] 2.2 Update the docstring's `Args:` entry: `repo_root: Absolute path to the git working directory whose sprint-status.yaml should be updated — the story's worktree when called from commit_node, so the change is staged and committed together with the rest of the story's changes.`
  - [x] 2.3 Update the one internal usage: `sprint_status_path = repo_root / artifacts_path / "implementation-artifacts" / "sprint-status.yaml"`
  - [x] 2.4 Grep for any other reference to this function's second positional argument name to confirm nothing else breaks (it is only called from the one call site touched in Task 1)

- [x] Task 3 — Update existing tests to reflect the corrected call site and parameter (AC: #9)
  - [x] 3.1 In `tests/test_engine/test_commit_node.py`, update all direct calls to `_update_sprint_status_done(slug, tmp_path, "_spec")` — these remain valid as unit tests of the helper itself (the helper doesn't care whether the path it's given is a project root or a worktree root), but rename the local variable/parameter references from `project_root` to `repo_root` where they appear in comments/docstrings for consistency
  - [x] 3.2 Add a new unit test proving the regression is fixed: create **two distinct** `tmp_path`-derived directories — one representing `project_root` (with a sprint-status.yaml showing the target story as `in-progress`) and one representing `worktree_path` (with its own, separately-writable sprint-status.yaml also showing `in-progress`). Call `_update_sprint_status_done(slug, worktree_dir, "_spec")`. Assert the **worktree's** copy is updated to `done`, and assert the **project_root's** copy is left completely unchanged (still `in-progress`). This is the regression test for the original bug.
  - [x] 3.3 Update `test_commit_node_calls_update_sprint_status_when_push_succeeded`: change the assertion from `mock_update.assert_awaited_once_with(slug, tmp_path, ...)` to assert the call used `state.worktree_path` specifically — construct the test with `project_root` and `worktree_path` set to **different** `tmp_path` subdirectories (e.g. `tmp_path / "project"` and `tmp_path / "worktree"`) so the assertion actually distinguishes them, then assert `mock_update.assert_awaited_once_with(slug, state.worktree_path, state.config.methodology.artifacts_path)`
  - [x] 3.4 Rewrite `test_commit_node_does_not_update_sprint_status_when_push_failed`: since the sprint-status update now happens **before** `push_branch()` is even called, this test's premise (update skipped when push fails) no longer holds. Replace it with a test asserting the update **is still called** even when `push_branch` returns `False` — because the update now happens before push is attempted at all. Rename the test to `test_commit_node_updates_sprint_status_even_when_push_fails` and assert `mock_update.assert_awaited_once()`.
  - [x] 3.5 Add a test verifying call ordering: mock both `_update_sprint_status_done` and `commit_story`, and assert (via `unittest.mock` call order tracking, e.g. a shared `MagicMock` recording calls in sequence, or `mock_manager.mock_calls` ordering) that `_update_sprint_status_done` is awaited **before** `commit_story` (AC #3)

- [x] Task 4 — Regression check on the "agent already committed cleanly" fast path (AC #4)
  - [x] 4.1 Locate existing tests covering `commit_story`'s `base_ref` clean-worktree detection (agent already committed, `HEAD != base_ref`, nothing to stage) — likely in `tests/test_scm/test_branch.py` or similar
  - [x] 4.2 Confirm those tests are unaffected: they test `commit_story()` in isolation with an already-clean worktree and do not go through `commit_node`, so this story's change (which dirties the worktree via a file write in `commit_node` before calling `commit_story`) does not alter their behavior or require changes
  - [x] 4.3 No new test is required for this interaction unless the full `commit_node` integration tests (Task 3) reveal a gap — if so, add a targeted integration test asserting a fresh commit is made (not the agent's original commit hash reused) after this story's fix, when the agent had already committed and the sprint-status write is the only remaining change

## Dev Notes

### Problem Context (the bug)

Story 10.16 added `_update_sprint_status_done()` to mark a story `done` in `sprint-status.yaml` automatically. However, its call site passes `project_root` — the **main project checkout** — not `state.worktree_path`, the isolated git worktree where the story's actual code changes live and get committed:

```python
# Current (buggy) call site in commit_node, inside `if push_succeeded:`:
await _update_sprint_status_done(story_slug, project_root, state.config.methodology.artifacts_path)
```

Meanwhile, `commit_story()` (called earlier in the same function) only ever operates with `cwd=worktree_path` — it stages and commits **exclusively** within the worktree:

```python
# scm/branch.py — commit_story()
await git("add", ".", cwd=worktree_path)
...
await git("commit", "-m", message, cwd=worktree_path)
```

The result: the sprint-status.yaml write lands in a **completely different git working directory** than the one that gets committed and pushed. It is:
- Never staged or committed (nothing commits changes sitting in `project_root`'s working tree during a story dispatch)
- Never part of the pushed branch, so it never appears in the PR diff
- Left as a silent, uncommitted local modification in the main checkout — invisible until a human happens to run `git status` there

This exactly matches the reported symptom: "the current functionality changes the status before the PR, and it doesn't seem to be getting committed."

**Why existing tests didn't catch this:** in `tests/test_engine/test_commit_node.py`, the integration tests construct `StoryState` with `project_root=tmp_path` and `worktree_path=tmp_path` — the **same** directory. The bug is invisible when both paths coincide. Task 3.2/3.3 fix this by using two distinct directories.

### The Fix

Two changes, both required:

1. **Target the worktree, not the project root.** Pass `state.worktree_path` instead of `project_root` as the base directory for resolving `sprint-status.yaml`.
2. **Move the call before `commit_story()`, not after.** This ensures the sprint-status write is present in the worktree's working directory *before* `git add .` runs, so it becomes part of the same commit that gets pushed and PR'd — rather than trying to retrofit a second, separate commit after the fact (which the current architecture has no mechanism for).

```python
# After this story, inside `if state.worktree_path is not None:`, BEFORE commit_story():
await _update_sprint_status_done(
    story_slug, state.worktree_path, state.config.methodology.artifacts_path
)

commit_hash = await commit_story(
    story_slug=story_slug,
    story_title=story_title,
    story_path=str(state.story_path),
    run_id=run_id,
    worktree_path=state.worktree_path,
    base_ref=resolved_base_ref,
)
```

The old call site (inside `if push_succeeded:`, right before `generate_pr_body()`) is deleted entirely — the update now happens once, earlier, unconditionally (relative to push/PR outcome) as part of preparing the worktree for its final commit.

### Interaction with the "agent already committed" fast path

`commit_story()` has special handling (added in Story 10.4) for the case where the coding agent already made its own commit(s) and the worktree is otherwise clean: it compares `HEAD` against `base_ref` and, if they differ, reuses the agent's commit hash instead of creating a new one. Writing the sprint-status.yaml change into the worktree *before* calling `commit_story()` means `git status --porcelain` will **always** show a pending change at this point (the file we just touched), so `commit_story()` will always take the "has changes → commit them" path rather than the "clean → reuse agent's hash" path. This is intentional and desirable: it guarantees every successfully-validated story ends with one final commit that includes the done-status update, regardless of whether the agent already committed on its own.

### Why rename `project_root` → `repo_root` in the helper

The parameter was named `project_root` because that's what story 10.16 originally (incorrectly) passed. Once the only call site passes `state.worktree_path`, keeping the parameter named `project_root` would be actively misleading to future readers. The helper itself is agnostic — it just resolves `{base}/{artifacts_path}/implementation-artifacts/sprint-status.yaml` — so `repo_root` accurately describes "whatever git working directory this operation targets."

### Key Files

| File | Change |
|------|--------|
| `arcwright-ai/src/arcwright_ai/engine/nodes.py` | Relocate the `_update_sprint_status_done()` call site (before `commit_story()`, using `state.worktree_path`); rename the helper's `project_root` parameter to `repo_root` |
| `arcwright-ai/tests/test_engine/test_commit_node.py` | Update the two existing integration tests for the new call site/timing; add a regression test proving the worktree copy (not the project-root copy) is updated |

### References

- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py#commit_node] — call site to relocate; `if state.worktree_path is not None:` outer guard; `commit_hash = await commit_story(...)` invocation point
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py#_update_sprint_status_done] — helper to rename the parameter on
- [Source: arcwright-ai/src/arcwright_ai/scm/branch.py#commit_story] — confirms `cwd=worktree_path` scoping for `git add .` / `git commit`; `base_ref` clean-worktree fast path (Story 10.4) whose interaction with this fix is covered in Task 4
- [Source: _spec/implementation-artifacts/10-16-mark-story-done-in-sprint-status-before-pr-creation.md] — original story that introduced the (buggy) call site being corrected here
- [Source: arcwright-ai/tests/test_engine/test_commit_node.py] — existing test file to update; both `project_root` and `worktree_path` are currently set to the same `tmp_path` in fixtures, which is why the bug went undetected

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Relocated the `_update_sprint_status_done()` call in `commit_node` (`engine/nodes.py`) to run **before** `commit_story()`, inside the `if state.worktree_path is not None:` block, passing `state.worktree_path` instead of `project_root`. Deleted the old call site (previously inside `if push_succeeded:`, right before `generate_pr_body()`).
- Renamed the helper's second parameter from `project_root` to `repo_root` (including docstring and internal path-join usage) to accurately describe that it now always receives a worktree path from its only call site.
- Updated `tests/test_engine/test_commit_node.py`: added a regression test (`test_update_sprint_status_targets_worktree_not_project_root`) proving the helper updates only the directory it's given, using two distinct `tmp_path` subdirectories for `project_root` and `worktree_path`; renamed/rewrote the two `commit_node` integration tests to use distinct `project_root`/`worktree_path` directories and assert the call uses `state.worktree_path` (`test_commit_node_calls_update_sprint_status_with_worktree_path`) and that the update still runs when `push_branch` fails (`test_commit_node_updates_sprint_status_even_when_push_fails`); added `test_commit_node_updates_sprint_status_before_commit_story` to assert call ordering.
- Ran full regression suite: `ruff check`, `ruff format --check`, and `mypy --strict` all pass with zero issues on the changed files; full `pytest` suite: 1228 passed (plus 4 pre-existing, unrelated `test_config.py` failures caused by a local machine config file overriding model defaults — confirmed pre-existing via `git stash`).
- Confirmed (Task 4) that `commit_story()`'s `base_ref` clean-worktree fast-path tests operate on `commit_story()` in isolation and are unaffected by this change.
- Sprint status updated: `10-18-commit-sprint-status-update-in-worktree-before-final-commit` → `review`.

### File List

- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/tests/test_engine/test_commit_node.py`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/implementation-artifacts/10-18-commit-sprint-status-update-in-worktree-before-final-commit.md`

### Change Log

- 2026-08-08: Relocated sprint-status "done" update to run before `commit_story()` using `state.worktree_path`; renamed helper parameter `project_root` → `repo_root`; added/updated tests (Story 10.18)
