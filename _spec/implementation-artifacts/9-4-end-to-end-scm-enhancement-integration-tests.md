# Story 9.4: End-to-End SCM Enhancement Integration Tests

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system maintainer,
I want integration tests that verify the full enhanced SCM flow end-to-end,
so that fetch → worktree → commit → push → PR → merge works as an unbroken chain.

## Acceptance Criteria (BDD)

1. **Given** all SCM enhancements from Stories 9.1–9.3 are implemented **When** integration tests execute the full enhanced SCM lifecycle **Then** test scenario 1 (single story, auto-merge enabled): fetch remote → create worktree from remote tip → make changes → commit → push → PR → merge → verify branch deleted and changes on default branch.

2. **Given** test scenario 2 (epic chain, auto-merge enabled) **When** two stories are dispatched sequentially **Then** story 2's worktree starts from story 1's merged changes (verifies fetch-after-merge picks up previous story's work).

3. **Given** test scenario 3 (auto-merge disabled) **When** the full flow runs **Then** it stops at PR creation; PR remains open, no merge attempted.

4. **Given** test scenario 4 (configured default branch) **When** `scm.default_branch` is set to a custom branch name **Then** all operations target that branch, not auto-detected one.

5. **Given** test scenario 5 (network failure simulation) **When** fetch fails **Then** `ScmError` is raised with message `"Failed to fetch from remote — check network connectivity"`.

6. **Given** test scenario 6 (merge conflict) **When** conflicting changes exist on the default branch **Then** auto-merge fails gracefully, story branch remains pushed, and story is still marked SUCCESS.

7. **Given** all new integration tests **When** the test suite runs **Then** all tests are marked `@pytest.mark.slow` (real git operations).

8. **Given** all new integration tests **When** the test suite runs **Then** tests use `tmp_path` fixture with real git repos (local bare remote + working clone).

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 914 existing tests continue to pass.

12. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Add shared `bare_remote_and_clone` fixture to `tests/conftest.py` (AC: #8)
  - [x] 1.1: Add `from __future__ import annotations` if not already present (already present in current conftest.py).
  - [x] 1.2: Add imports: `from arcwright_ai.scm.git import git`.
  - [x] 1.3: Create async fixture `bare_remote_and_clone(tmp_path: Path) -> tuple[Path, Path, Path]` returning `(bare_path, clone_path, scratch_path)`:
    - Create bare repo via `git("init", "--bare", str(bare), cwd=tmp_path)`.
    - Create scratch repo, configure user.email/name, commit README.md, add remote, push to bare via `git("push", "origin", "HEAD:main", cwd=scratch)`.
    - Clone from bare via `git("clone", str(bare), str(clone), cwd=tmp_path)`, configure user.email/name, create `.arcwright-ai/worktrees` dir.
    - Return `(bare, clone, scratch)`.
  - [x] 1.4: Google-style docstring with Args, Returns sections.

- [x] Task 2: Create `tests/test_scm/test_scm_integration.py` with module structure and scenario 1 (AC: #1, #7, #8)
  - [x] 2.1: Module docstring: `"""End-to-end integration tests for SCM enhancements (Stories 9.1–9.3).\n\nAll tests are marked ``@pytest.mark.slow`` and require a real git binary.\nRun with ``pytest -m slow`` to include them.\n"""`
  - [x] 2.2: Imports:
    ```python
    from __future__ import annotations
    from typing import TYPE_CHECKING
    import pytest
    from arcwright_ai.scm.branch import commit_story, fetch_and_sync, push_branch
    from arcwright_ai.scm.git import git
    from arcwright_ai.scm.worktree import create_worktree, remove_worktree
    if TYPE_CHECKING:
        from pathlib import Path
    ```
  - [x] 2.3: Set module-level marks: `pytestmark = [pytest.mark.slow, pytest.mark.asyncio]`.
  - [x] 2.4: Implement `test_single_story_full_chain_auto_merge(bare_remote_and_clone)`:
    - Unpack `bare, clone, scratch = bare_remote_and_clone`.
    - Call `fetch_and_sync("main", "origin", project_root=clone)` → `sha`.
    - Call `create_worktree("single-story", sha, project_root=clone)` → `wt_path`.
    - Write `(wt_path / "feature.py").write_text("def hello(): pass\n")`.
    - Call `commit_story("single-story", "Single Story", "_spec/single-story.md", "run-001", wt_path)` → assert non-empty `commit_hash`.
    - Call `push_branch("arcwright-ai/single-story", project_root=clone, remote="origin", worktree_path=wt_path)` → assert `True`.
    - Verify remote branch exists: `git("branch", "-r", cwd=clone)` stdout contains `"origin/arcwright-ai/single-story"`.
    - Simulate auto-merge via scratch: `git("fetch", "origin", cwd=scratch)` → `git("merge", "origin/arcwright-ai/single-story", "--no-ff", "-m", "Merge PR #1", cwd=scratch)` → `git("push", "origin", "HEAD:main", cwd=scratch)`.
    - Simulate `--delete-branch`: `git("push", "origin", "--delete", "arcwright-ai/single-story", cwd=scratch)`.
    - Verify changes on default branch: `git("fetch", "--prune", "origin", cwd=clone)` → `git("log", "--oneline", "origin/main", cwd=clone)` stdout contains `"Single Story"` or `"Merge PR"`.
    - Verify remote branch deleted: `git("branch", "-r", cwd=clone)` stdout does NOT contain `"origin/arcwright-ai/single-story"`.
    - Cleanup: `remove_worktree("single-story", project_root=clone, delete_branch=True)`.

- [x] Task 3: Add scenario 2 — epic chain with 2 sequential stories (AC: #2, #7, #8)
  - [x] 3.1: Implement `test_epic_chain_two_stories_auto_merge(bare_remote_and_clone)`:
    - **Story 1**: fetch → create worktree "chain-story-1" → write `chain1.py` with `"# Story 1 output\n"` → commit → push → simulate merge via scratch (fetch, merge, push to main, delete remote branch).
    - **Story 2**: call `fetch_and_sync("main", "origin", project_root=clone)` again → assert returned SHA differs from story 1's initial SHA (new commit from merge) → create worktree "chain-story-2" from new SHA → assert `(wt2_path / "chain1.py").exists()` (proves story 2 starts from story 1's merged commit) → write `chain2.py` → commit → push.
    - Verify both story branches were pushed (story 2 still on remote).
    - Cleanup: remove both worktrees with `delete_branch=True`.

- [x] Task 4: Add scenario 3 — auto-merge disabled (AC: #3, #7, #8)
  - [x] 4.1: Implement `test_full_chain_auto_merge_disabled(bare_remote_and_clone)`:
    - fetch → create worktree "no-merge-story" → write file → commit → push.
    - Verify branch exists on remote: `git("branch", "-r", cwd=clone)` contains `"origin/arcwright-ai/no-merge-story"`.
    - Do NOT merge — no merge simulation step.
    - Verify changes are NOT on main: `git("log", "--oneline", "origin/main", cwd=clone)` does NOT contain the story's commit message.
    - Cleanup: remove worktree + delete remote branch via `git("push", "origin", "--delete", "arcwright-ai/no-merge-story", cwd=clone)` (test cleanup only).

- [x] Task 5: Add scenario 4 — configured default branch (AC: #4, #7, #8)
  - [x] 5.1: Implement `test_configured_default_branch(tmp_path)` (uses its own inline fixture, not `bare_remote_and_clone`):
    - Setup: create bare repo, scratch repo that pushes to `HEAD:develop` (not main), clone from bare with `-b develop`.
    - Ensure `.arcwright-ai/worktrees` exists in clone.
    - Set user.email/name in clone.
    - Call `fetch_and_sync("develop", "origin", project_root=clone)` → `sha` (verifies fetch targets `develop`).
    - Create worktree from `sha` → make changes → commit → push.
    - Verify push succeeded and branch exists on remote.
    - Simulate merge into `develop` via scratch: `git("fetch", "origin", cwd=scratch)` → `git("checkout", "develop", cwd=scratch)` → `git("merge", "origin/arcwright-ai/<slug>", "--no-ff", "-m", "Merge", cwd=scratch)` → `git("push", "origin", "HEAD:develop", cwd=scratch)`.
    - Verify changes on `develop`: `git("log", "--oneline", "origin/develop", cwd=clone)` contains the commit.
    - Verify `main` does NOT exist: `git("branch", "-r", cwd=clone)` does NOT contain `"origin/main"`.
    - Cleanup.

- [x] Task 6: Add scenario 5 — network failure simulation (AC: #5, #7, #8)
  - [x] 6.1: Add `import shutil` and `from arcwright_ai.core.exceptions import ScmError` to module imports.
  - [x] 6.2: Implement `test_fetch_failure_graceful_halt(bare_remote_and_clone)`:
    - Unpack `bare, clone, scratch`.
    - Delete the bare repo directory to make the remote unreachable: `shutil.rmtree(bare)`.
    - Call `fetch_and_sync("main", "origin", project_root=clone)` inside `pytest.raises(ScmError, match="Failed to fetch from remote")`.
    - Verify the raised exception has `details` dict with `"remote"` and `"branch"` keys.

- [x] Task 7: Add scenario 6 — merge conflict graceful failure (AC: #6, #7, #8)
  - [x] 7.1: Implement `test_merge_conflict_graceful_failure(bare_remote_and_clone)`:
    - Unpack fixture.
    - Fetch initial SHA first (before conflicting push), create worktree, write story content, commit, push story branch.
    - THEN push conflicting change from scratch to create a true 3-way conflict.
    - Verify story branch exists on remote (push succeeded even though merge will fail).
    - Simulate merge attempt from scratch: raises `ScmError` because both sides modified `README.md`.
    - `git("merge", "--abort", cwd=scratch)` to restore clean state.
    - Verify: story branch still on remote, `origin/main` unchanged (no merge happened).
    - Cleanup: remove worktree, delete remote branch.

- [x] Task 8: Run quality gates (AC: #9, #10, #11, #12)
  - [x] 8.1: `ruff check .` — zero violations against FULL repository.
  - [x] 8.2: `ruff format --check .` — zero formatting issues.
  - [x] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 8.4: `pytest` — all tests pass (existing + new). 914 baseline + new integration tests.
  - [x] 8.5: `pytest -m slow` — all slow-marked tests pass (new integration tests + existing ones).
  - [x] 8.6: Verify Google-style docstrings on all new functions and fixtures.

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] AC #5 exact error message assertion added in integration test (`"Failed to fetch from remote — check network connectivity"`).
- [x] [AI-Review][HIGH] AC #6 SUCCESS outcome assertion added by explicitly asserting story-success semantics before/after merge-conflict attempt.
- [x] [AI-Review][MEDIUM] Merge-conflict assertion tightened from permissive `or` condition to strict negative merge-marker checks.
- [x] [AI-Review][MEDIUM] Story File List expanded to include all related SCM/engine source and companion test files for traceability.

## Dev Notes

### Architecture & Design Context

**Architecture D7 — Git Operations Strategy**: All git calls go through `scm/git.py` wrapper. SCM tests are marked `@pytest.mark.slow` (real git operations with `tmp_path`). No Python Git library — shell out to `git` CLI.

**Architecture D7 — No Force Operations**: Tests must verify the chain works without `--force`, `reset --hard`, or rebase. The only exception is the merge-ours reconciliation in `push_branch` for stale remote branches, which is not a `--force` on the remote.

**Architecture Testing Standards**: pytest with `pytest-asyncio`. Test structure mirrors source structure. SCM integration tests go in `tests/test_scm/`.

**Package Dependency DAG**: This story only adds test files — no source changes to the DAG. Tests import from `scm.branch`, `scm.git`, `scm.worktree`, and `core.exceptions`.

### Current State Analysis — What Already Exists

1. **`scm/branch.py`** (794 lines): `fetch_and_sync()` (line 699), `push_branch()` (line 378), `commit_story()` (line 182), `create_branch()` (line 114). All are async and use the `git()` wrapper.

2. **`scm/pr.py`** (942 lines): `merge_pull_request()` (line 742), `open_pull_request()` (line 612), `get_pull_request_merge_sha()` (line 868). These use `gh` CLI — NOT testable with local bare repos, so integration tests use real git for the git chain and simulate merge effects manually.

3. **`scm/worktree.py`**: `create_worktree(slug, base_ref=None, *, project_root)`, `remove_worktree(slug, *, project_root, delete_branch=False, force=False)`. Both use the `git()` wrapper.

4. **`scm/git.py`**: `async def git(*args, cwd=None) -> GitResult` — the single gateway for all git subprocess calls.

5. **`core/exceptions.py`**: `ScmError(message, details=None)` — raised by `fetch_and_sync()` on network failure.

6. **Existing integration test files** (patterns to follow):
   - `tests/test_scm/test_branch_integration.py` (373 lines) — has its own `git_repo` and `bare_remote_and_clone` fixtures, tests `fetch_and_sync`, `create_branch`, `commit_story`, `push_branch`, `delete_branch`, `list_branches`. Pattern: `pytestmark = [pytest.mark.slow, pytest.mark.asyncio]`.
   - `tests/test_scm/test_worktree_integration.py` (147 lines) — has own `git_repo` fixture, tests `create_worktree`, `remove_worktree`, full lifecycle.
   - `tests/test_scm/test_clean_integration.py` (183 lines) — has own `git_repo` fixture, helper functions `_create_merged_worktree`, `_create_unmerged_worktree`, tests cleanup operations.

7. **`tests/conftest.py`** (32 lines): Currently has `tmp_project` fixture only. This story adds the shared `bare_remote_and_clone` fixture here.

8. **`bare_remote_and_clone` fixture in `test_branch_integration.py`** (lines 257-290): Returns `tuple[Path, Path]` (bare, clone). Creates bare → scratch → initial commit → push to bare → clone from bare. The scratch directory is created but NOT returned — used only during setup. This story's shared fixture in conftest.py follows the same pattern but returns `tuple[Path, Path, Path]` (bare, clone, scratch) because scenario tests need scratch for merge simulation.

9. **914 tests** is the current baseline (collected via `pytest --co`).

### Existing Code to Reuse — DO NOT REINVENT

- **`git()` from `scm/git.py`** — all git subprocess calls MUST go through this wrapper. Direct `subprocess` calls are forbidden. Existing integration tests (test_branch_integration.py, test_worktree_integration.py, test_clean_integration.py) ALL use `git()` for fixture setup too.
- **`create_worktree(slug, base_ref, *, project_root)`** — already handles branch creation and worktree directory creation atomically.
- **`commit_story(story_slug, story_title, story_path, run_id, worktree_path)`** — stages all changes and commits with the standardized message format.
- **`push_branch(branch_name, *, project_root, remote, worktree_path)`** — handles push with merge-ours reconciliation on non-fast-forward.
- **`fetch_and_sync(default_branch, remote, *, project_root)`** — fetches and returns remote tip SHA.
- **`remove_worktree(slug, *, project_root, delete_branch, force)`** — cleans up worktree and optionally deletes the branch.
- **`ScmError` from `core/exceptions.py`** — raised by `fetch_and_sync()` on fetch failure.
- **Existing fixture setup patterns**: `git("init", cwd=...)`, `git("config", "user.email", ...)`, `git("config", "user.name", ...)` — used in all existing integration test fixtures.

### CRITICAL: gh CLI Operations Are NOT Tested

The `open_pull_request()` and `merge_pull_request()` functions call `gh` CLI, which requires GitHub API authentication and a real GitHub repository. These CANNOT be tested with local bare repos. The integration tests in this story verify the **git operation chain** end-to-end:

- Fetch → Worktree → Commit → Push (all real git with bare remote)
- PR creation and merge are **simulated** by directly merging branches in the scratch clone and pushing to the bare remote

This matches the architecture's intent: the git chain is verified with real repos; gh CLI operations have their own unit tests (in `test_pr.py` — 13 tests for `merge_pull_request`, 5+ for `open_pull_request`).

### CRITICAL: Simulating Auto-Merge in Integration Tests

Since `gh pr merge --squash --delete-branch` can't run locally, simulate its effects using the scratch clone:
1. From **scratch**: `git("fetch", "origin", cwd=scratch)` → `git("merge", "origin/arcwright-ai/<slug>", "--no-ff", "-m", "Merge PR", cwd=scratch)` → `git("push", "origin", "HEAD:main", cwd=scratch)`
2. Delete remote branch: `git("push", "origin", "--delete", "arcwright-ai/<slug>", cwd=scratch)`

This produces the same end state as a squash-merge: changes on main, branch deleted on remote. The scratch clone was created during `bare_remote_and_clone` fixture setup and has `origin` pointing to the bare repo.

### CRITICAL: Scenario 2 Epic Chain Verification

The key assertion for scenario 2 is that story 2's worktree contains story 1's file. After story 1's merge is simulated and pushed to the bare remote's main:
1. `fetch_and_sync("main", "origin", project_root=clone)` returns new SHA
2. `create_worktree("chain-story-2", new_sha, project_root=clone)` creates worktree at post-merge state
3. `(wt2_path / "chain1.py").exists()` must be `True` — proves the chain works

### CRITICAL: Scenario 5 Network Failure

Deleting the bare remote directory (`shutil.rmtree(bare)`) before calling `fetch_and_sync()` simulates a network failure (the remote URL points to a non-existent path). `fetch_and_sync()` catches the `ScmError` from `git fetch` and re-raises it with the message `"Failed to fetch from remote — check network connectivity"` and `details={"remote": "origin", "branch": "main"}`.

### CRITICAL: Scenario 6 Merge Conflict Simulation

Create a **real** merge conflict:
1. From scratch: modify `README.md` to `"# Conflicting content"`, commit, push to main
2. In clone: fetch → create worktree → modify `README.md` to `"# Story content"` → commit → push story branch
3. From scratch: fetch → attempt `git("merge", "origin/arcwright-ai/<slug>", cwd=scratch)` → this fails with conflict
4. `git("merge", "--abort", cwd=scratch)` to restore clean state
5. Assertions: story branch still on remote, main unchanged (no merge), push succeeded

### CRITICAL: Test Isolation

Each test function gets a fresh `bare_remote_and_clone` fixture instance via `tmp_path` (pytest creates unique temp dirs per test). No test can interfere with another. All worktrees and branches are cleaned up within each test.

### CRITICAL: remove_worktree Signature

`remove_worktree(story_slug, *, project_root, delete_branch=False, force=False)`. In integration tests, pass `delete_branch=True` to clean up the local branch after removing the worktree. Some scenarios may need `force=True` if the worktree has uncommitted changes.

### CRITICAL: Fixture Must Handle Default Branch Name

Modern git versions may use `main` or `master` as the default. The `bare_remote_and_clone` fixture setup explicitly pushes to `HEAD:main` (not relying on git's default). The scratch repo uses `git("push", "origin", "HEAD:main", cwd=scratch)` to be explicit. For scenario 4 (custom default branch), setup pushes to `HEAD:develop` instead.

### Files Touched

| File | Changes |
|------|---------|
| `tests/conftest.py` | Add shared `bare_remote_and_clone` async fixture returning `(bare, clone, scratch)` |
| `tests/test_scm/test_scm_integration.py` | **New file** — 6 integration test scenarios covering full SCM chain |

### Project Structure Notes

- All test files under `arcwright-ai/tests/` — paths in tasks are relative to this root.
- Source files untouched — this is a test-only story.
- Test file mirrors SCM package structure: `tests/test_scm/test_scm_integration.py`.
- No new source dependencies — all imports are from existing `arcwright_ai.scm.*` and `arcwright_ai.core.*` packages.

### Previous Story Intelligence

**From Story 9.3 (Auto-Merge PR — done):**
- `merge_pull_request()` calls `gh pr merge <number> --squash --delete-branch`. Can't test with local bare repos.
- `commit_node` auto-merge block is gated on `state.config.scm.auto_merge`. Best-effort, non-fatal.
- `get_pull_request_merge_sha()` uses `gh pr view --json mergeCommit`. Also gh-dependent.
- Test patterns: monkeypatch for gh CLI mocks, AsyncMock for controlled responses.
- Autouse fixture in test_nodes.py includes `merge_pull_request` mock.
- 912→914 tests after story 9.3 + review fixes.

**From Story 9.2 (Fetch & Sync — done):**
- `fetch_and_sync()` calls `git fetch` + `git merge --ff-only` + `git rev-parse`. All real git.
- The `bare_remote_and_clone` fixture pattern was established in `test_branch_integration.py`.
- Integration tests verified: real fetch returns correct SHA, diverged local falls back to remote tip, worktree from fetched SHA has correct starting commit.
- ff-merge success logging was added in review fixes.

**From Story 9.1 (ScmConfig Enhancements — done):**
- `ScmConfig.auto_merge: bool = False` exists in `core/config.py` line 238.
- `ScmConfig.default_branch: str = ""` exists in `core/config.py` line 237.
- `_detect_default_branch()` short-circuits when `default_branch` is non-empty.

**From Story 6.5 (Worktree Cleanup — done):**
- `clean_default()` and `clean_all()` have their own integration tests in `test_clean_integration.py`.
- Pattern: `_create_merged_worktree()` and `_create_unmerged_worktree()` helper functions for test setup.

**From Git History (last 10 commits):**
- `dda020a` — feat(scm): add ff-merge success logging and update tests (Story 9.2 review fixes)
- `f835d34` — feat(scm): fetch and sync default branch before worktree creation (Story 9.2)
- `2c6d275` — feat: create story 9.1 — ScmConfig enhancements
- Commit message pattern: `feat(scope): description` (conventional commits)

### References

- [Source: _spec/planning-artifacts/epics.md#L1300-L1338] — Epic 9 Story 9.4 full specification with ACs and files touched
- [Source: _spec/planning-artifacts/architecture.md#L401-L430] — D7 Git Operations Strategy: shell out to git CLI, SCM tests @pytest.mark.slow
- [Source: _spec/planning-artifacts/architecture.md#L155-L165] — Testing standards: pytest + pytest-asyncio, test structure mirrors source, SCM tests slow-marked
- [Source: src/arcwright_ai/scm/branch.py#L699-L794] — `fetch_and_sync()` full implementation
- [Source: src/arcwright_ai/scm/branch.py#L378-L534] — `push_branch()` with merge-ours reconciliation
- [Source: src/arcwright_ai/scm/branch.py#L182-L316] — `commit_story()` full implementation
- [Source: src/arcwright_ai/scm/pr.py#L742-L847] — `merge_pull_request()` gh CLI-based (cannot test locally)
- [Source: src/arcwright_ai/scm/pr.py#L612-L740] — `open_pull_request()` gh CLI-based (cannot test locally)
- [Source: src/arcwright_ai/scm/pr.py#L868-L942] — `get_pull_request_merge_sha()` gh CLI-based
- [Source: src/arcwright_ai/core/exceptions.py] — `ScmError` exception class
- [Source: tests/conftest.py#L1-L32] — Current conftest with `tmp_project` fixture only
- [Source: tests/test_scm/test_branch_integration.py#L257-L290] — Existing `bare_remote_and_clone` fixture pattern
- [Source: tests/test_scm/test_branch_integration.py#L295-L373] — fetch_and_sync integration tests (pattern reference)
- [Source: tests/test_scm/test_worktree_integration.py#L1-L147] — Worktree integration test patterns
- [Source: tests/test_scm/test_clean_integration.py#L1-L183] — Clean integration test patterns with helper functions

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

None — implementation completed without debug halts.

### Completion Notes List

- **Task 1**: Added shared async `bare_remote_and_clone` fixture to `tests/conftest.py` returning `tuple[Path, Path, Path]` (bare, clone, scratch). Follows existing pattern from `test_branch_integration.py` but returns scratch path so scenario tests can simulate PR merges.
- **Task 2**: Created `tests/test_scm/test_scm_integration.py` with full module structure, `pytestmark = [pytest.mark.slow, pytest.mark.asyncio]`, and scenario 1. Used `git fetch --prune origin` after remote branch deletion so tracking refs are updated before assertion.
- **Task 3**: Scenario 2 — key assertion is `chain1.py` exists in story 2's worktree, proving fetch-after-merge picks up story 1's changes.
- **Task 4**: Scenario 3 — push succeeds but `origin/main` log does not contain story commit message (no merge performed).
- **Task 5**: Scenario 4 — inline fixture with `develop` as default branch. Verified `origin/main` does not exist on bare remote.
- **Task 6**: Scenarios 5a+5b (split into two tests) — network failure via `shutil.rmtree(bare)`. Tests both exception message match and `details` dict keys.
- **Task 7**: Scenario 6 — real 3-way conflict by fetching initial SHA first, creating worktree + committing story content, THEN pushing conflicting change from scratch. Both branches diverge from same ancestor; `git merge` raises `ScmError`.
- **Task 8**: All quality gates passed — `ruff check .` (0 violations), `ruff format --check .` (90 files), `mypy --strict src/` (0 errors), `pytest` (921 = 914 + 7 new), `pytest -m slow` (7/7).

### Senior Developer Review (AI)

#### Reviewer

Ed (AI Code Review)

#### Date

2026-03-15

#### Outcome

Changes Requested

#### Summary

- Completed adversarial validation of ACs and completed tasks against implementation and current git delta.
- Verified quality gates in current workspace state: `ruff check .`, `ruff format --check .`, `.venv/bin/python -m mypy --strict src/`, `pytest -q`, and `pytest -q tests/test_scm/test_scm_integration.py` all pass.
- Found 4 review issues: 2 HIGH, 2 MEDIUM.

#### Findings

1. **[HIGH] AC #5 assertion is partial, not exact**
  - Story requires exact error message: `"Failed to fetch from remote — check network connectivity"`.
  - Test currently asserts only `"Failed to fetch from remote"`, which can pass on incomplete/changed messaging.
  - Evidence: `arcwright-ai/tests/test_scm/test_scm_integration.py:347`

2. **[HIGH] AC #6 outcome not fully validated**
  - AC #6 requires that the story is still marked SUCCESS after merge conflict.
  - Current test validates branch/merge-conflict behavior but does not assert story/engine success outcome.
  - Evidence: `arcwright-ai/tests/test_scm/test_scm_integration.py:376`

3. **[MEDIUM] Merge-conflict log assertion is too permissive**
  - Assertion uses `or`:
    - `assert "Merge" not in log_result.stdout or "Merge Story" not in log_result.stdout`
  - This passes in many unintended states; use stricter condition to avoid false positives.
  - Evidence: `arcwright-ai/tests/test_scm/test_scm_integration.py:452`

4. **[MEDIUM] Story documentation does not reflect actual implementation footprint**
  - Story File List includes only two files, while git shows additional modified source/tests tied to Story 9.3/9.4 SCM behavior.
  - This mismatch weakens review/audit traceability.
  - Evidence: `_spec/implementation-artifacts/9-4-end-to-end-scm-enhancement-integration-tests.md:318`

### Change Log

- 2026-03-15: Story created by create-story workflow — comprehensive developer guide assembled from epics, architecture, prior story intelligence (9.1, 9.2, 9.3, 6.5), existing integration test patterns, and code-level source analysis.
- 2026-03-15: Story implemented — added shared `bare_remote_and_clone` fixture to conftest.py and created `tests/test_scm/test_scm_integration.py` with 7 integration tests covering all 6 SCM enhancement scenarios. 921 tests pass (914 + 7 new).
- 2026-03-15: AI code review completed — 4 findings logged (2 HIGH, 2 MEDIUM), follow-up tasks added, story moved to `in-progress` pending follow-up completion.
- 2026-03-15: AI review follow-ups addressed — strengthened AC #5/#6 assertions, tightened merge-conflict checks, expanded File List traceability, and moved story to `review`.
- 2026-03-15: Full validation rerun passed (`pytest -q`, `ruff check .`, `mypy --strict src/`); story accepted and moved to `done`.

### File List

- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/src/arcwright_ai/scm/__init__.py`
- `arcwright-ai/src/arcwright_ai/scm/pr.py`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `tests/conftest.py`
- `arcwright-ai/tests/test_scm/test_pr.py`
- `tests/test_scm/test_scm_integration.py`