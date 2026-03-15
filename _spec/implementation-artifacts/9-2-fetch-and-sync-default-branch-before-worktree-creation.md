# Story 9.2: Fetch & Sync Default Branch Before Worktree Creation

Status: todo

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer dispatching stories overnight,
I want each story's worktree to start from the latest upstream code,
so that stories don't build on stale commits and merge conflicts are minimized.

## Acceptance Criteria (BDD)

1. **Given** `scm/branch.py` module **When** `fetch_and_sync(default_branch: str, remote: str = "origin", *, project_root: Path) → str` is called **Then** it runs `git fetch <remote> <default_branch>` to fetch the latest commits from the remote **And** runs `git rev-parse <remote>/<default_branch>` to resolve the fetched tip to a commit SHA **And** returns the resolved SHA string.

2. **Given** `fetch_and_sync()` is called **When** the local checkout is on the default branch **Then** it attempts `git merge --ff-only <remote>/<default_branch>` to fast-forward the local branch **And** if the fast-forward succeeds, logs a `git.fetch_and_sync.ff_merge` event **And** if the fast-forward fails (local has diverged), logs a warning and continues — the returned SHA is still the remote tip.

3. **Given** `fetch_and_sync()` is called **When** the local checkout is NOT on the default branch (e.g., on `HEAD` detached or another branch) **Then** the `git merge --ff-only` step is skipped entirely **And** only fetch + rev-parse is performed.

4. **Given** `fetch_and_sync()` is called **When** the `git fetch` command fails due to network error **Then** `ScmError` is raised with message "Failed to fetch from remote — check network connectivity" **And** the error includes the remote name and default branch in `details`.

5. **Given** `engine/nodes.py` `preflight_node` **When** it is about to create a worktree for a story **Then** it calls `fetch_and_sync(default_branch, remote, project_root=state.project_root)` before `create_worktree()` **And** passes the returned SHA as `base_ref` to `create_worktree()`.

6. **Given** the user passed `--base-ref <ref>` on the CLI **When** `preflight_node` runs **Then** `fetch_and_sync()` is skipped entirely **And** the user-provided `base_ref` is passed directly to `create_worktree()`.

7. **Given** the default branch name **When** `preflight_node` needs to resolve it **Then** it calls `_detect_default_branch(project_root, story_slug, default_branch_override=state.config.scm.default_branch)` from `scm/pr.py` (added in Story 9.1) to get the branch name.

8. **Given** an epic dispatch with multiple stories **When** `fetch_and_sync()` is called for each story **Then** fetch runs per-story (not cached across the run) — this ensures each story picks up the latest state including auto-merged changes from prior stories in the same run.

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

13. **Given** new unit tests in `tests/test_scm/test_branch.py` **When** the test suite runs **Then** tests cover:
    (a) `fetch_and_sync` calls `git fetch <remote> <default_branch>` with correct args;
    (b) `fetch_and_sync` calls `git rev-parse <remote>/<default_branch>` to resolve SHA;
    (c) `fetch_and_sync` returns the resolved SHA string;
    (d) `fetch_and_sync` on default branch: attempts `git merge --ff-only` and succeeds;
    (e) `fetch_and_sync` on default branch: ff-only fails → logs warning, returns remote SHA anyway;
    (f) `fetch_and_sync` not on default branch: skips merge, returns remote SHA;
    (g) `fetch_and_sync` fetch fails → raises `ScmError` with network error message;
    (h) Structured log events emitted for fetch, merge, and error operations.

14. **Given** integration tests marked `@pytest.mark.slow` **When** the integration test suite runs **Then** tests cover:
    (a) `fetch_and_sync` with real git + bare remote → fetches commits and returns correct SHA;
    (b) `fetch_and_sync` with diverged local → ff-only fails gracefully, returns remote tip SHA;
    (c) Worktree created with returned SHA as base_ref has the correct starting commit.

## Tasks / Subtasks

- [ ] Task 1: Implement `fetch_and_sync` function in `scm/branch.py` (AC: #1, #2, #3, #4)
  - [ ] 1.1: Function signature: `async def fetch_and_sync(default_branch: str, remote: str = "origin", *, project_root: Path) -> str`.
  - [ ] 1.2: Call `await git("fetch", remote, default_branch, cwd=project_root)`. Catch `ScmError` → re-raise as `ScmError("Failed to fetch from remote — check network connectivity", details={"remote": remote, "branch": default_branch})`.
  - [ ] 1.3: Call `await git("rev-parse", f"{remote}/{default_branch}", cwd=project_root)` to resolve remote tip SHA. Store as `remote_sha = result.stdout.strip()`.
  - [ ] 1.4: Detect current branch: `await git("rev-parse", "--abbrev-ref", "HEAD", cwd=project_root)`. If result matches `default_branch`, attempt ff-only merge.
  - [ ] 1.5: If on default branch, call `await git("merge", "--ff-only", f"{remote}/{default_branch}", cwd=project_root)`. Catch `ScmError` on ff-only failure → log warning `git.fetch_and_sync.ff_failed`, continue (non-fatal).
  - [ ] 1.6: If NOT on default branch, skip merge step.
  - [ ] 1.7: Log success as `git.fetch_and_sync` structured event with `remote`, `default_branch`, `remote_sha`, `ff_merged` (bool).
  - [ ] 1.8: Return `remote_sha`.
  - [ ] 1.9: Google-style docstring with Args, Returns, Raises.

- [ ] Task 2: Update `__all__` and package exports (AC: #1)
  - [ ] 2.1: Add `"fetch_and_sync"` to `scm/branch.py` `__all__`.
  - [ ] 2.2: Add `fetch_and_sync` to `scm/__init__.py` imports and `__all__`.

- [ ] Task 3: Add `base_ref` field to `StoryState` (AC: #5, #6)
  - [ ] 3.1: Add `base_ref: str | None = None` field to `StoryState` in `engine/state.py`. This stores the user-provided `--base-ref` if given, or `None` to indicate "fetch and use remote tip".
  - [ ] 3.2: Update `StoryState` docstring to document the new field.

- [ ] Task 4: Wire `fetch_and_sync` into `preflight_node` (AC: #5, #6, #7, #8)
  - [ ] 4.1: Add import for `fetch_and_sync` from `scm/branch.py`.
  - [ ] 4.2: Add import for `_detect_default_branch` from `scm/pr.py`.
  - [ ] 4.3: Before `create_worktree()` call, check if `state.base_ref` is set (user-provided `--base-ref`).
  - [ ] 4.4: If `state.base_ref` is **not** set:
    - Resolve default branch name: `default_branch = await _detect_default_branch(project_root, story_slug, default_branch_override=state.config.scm.default_branch)`.
    - Resolve remote: `remote = state.config.scm.remote.strip() or "origin"`.
    - Call `resolved_base_ref = await fetch_and_sync(default_branch, remote, project_root=project_root)`.
    - Pass `base_ref=resolved_base_ref` to `create_worktree()`.
  - [ ] 4.5: If `state.base_ref` **is** set, pass `base_ref=state.base_ref` to `create_worktree()` directly (skip fetch).
  - [ ] 4.6: Handle `ScmError` from `fetch_and_sync` — escalate story (cannot guarantee fresh base).
  - [ ] 4.7: Update the stale worktree retry path to also pass `base_ref` to the second `create_worktree()` call.

- [ ] Task 5: Create unit tests for `fetch_and_sync` (AC: #12, #13)
  - [ ] 5.1: In `tests/test_scm/test_branch.py` add test `test_fetch_and_sync_calls_git_fetch` — verify correct args.
  - [ ] 5.2: Test `test_fetch_and_sync_resolves_remote_sha` — verify `git rev-parse` call and return value.
  - [ ] 5.3: Test `test_fetch_and_sync_ff_merge_on_default_branch` — on default branch, `git merge --ff-only` is called.
  - [ ] 5.4: Test `test_fetch_and_sync_ff_merge_failure_continues` — ff-only fails, warning logged, SHA still returned.
  - [ ] 5.5: Test `test_fetch_and_sync_skips_merge_not_on_default` — not on default branch, merge not called.
  - [ ] 5.6: Test `test_fetch_and_sync_network_failure_raises_scm_error` — fetch fails → ScmError raised.
  - [ ] 5.7: Test `test_fetch_and_sync_logs_structured_event` — success event logged.

- [ ] Task 6: Create unit tests for `preflight_node` fetch integration (AC: #12)
  - [ ] 6.1: In `tests/test_engine/test_nodes.py` add test `test_preflight_calls_fetch_and_sync` — verify fetch called before worktree creation.
  - [ ] 6.2: Test `test_preflight_base_ref_bypasses_fetch` — when `state.base_ref` is set, fetch_and_sync is NOT called.
  - [ ] 6.3: Test `test_preflight_passes_fetch_sha_to_create_worktree` — verify resolved SHA threaded to create_worktree.

- [ ] Task 7: Create integration tests (AC: #14)
  - [ ] 7.1: All tests marked `@pytest.mark.slow` and `@pytest.mark.asyncio`.
  - [ ] 7.2: Create `bare_remote_and_clone` fixture — init bare repo, clone it, make initial commit.
  - [ ] 7.3: Test `test_fetch_and_sync_real_git` — push new commit to bare, fetch_and_sync returns updated SHA.
  - [ ] 7.4: Test `test_fetch_and_sync_diverged_local` — create diverged local, verify ff-only fails gracefully.
  - [ ] 7.5: Test `test_worktree_from_fetched_sha` — fetch + create_worktree with returned SHA, verify worktree is at correct commit.

- [ ] Task 8: Run quality gates (AC: #9, #10, #11, #12)
  - [ ] 8.1: `ruff check .` — zero violations against FULL repository.
  - [ ] 8.2: `ruff format --check .` — zero formatting issues.
  - [ ] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [ ] 8.4: `pytest` — all tests pass (existing + new).
  - [ ] 8.5: Verify Google-style docstrings on all modified/new functions.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: This story touches `scm/branch.py` (new function), `engine/nodes.py` (wiring), and `engine/state.py` (new field). Valid paths: `engine → scm → core`. No DAG violations.

**Decision 7 — Git Operations Strategy (Updated)**: The architecture specifies: "`preflight_node` fetches latest from remote default branch and fast-forward merges to ensure worktrees start from current upstream state." This story implements that behavior.

### Current State Analysis — What Already Exists

1. **`scm/branch.py`** (691 lines): Has `branch_exists`, `create_branch`, `commit_story`, `push_branch`, `delete_branch`, `delete_remote_branch`, `list_branches`. No fetch/sync function exists. This story adds `fetch_and_sync`.

2. **`engine/nodes.py` `preflight_node`** (lines ~80-170): Currently creates worktree with no `base_ref` argument:
   ```python
   worktree_path = await create_worktree(story_slug, project_root=state.project_root)
   ```
   This story inserts `fetch_and_sync()` before this call and passes the returned SHA as `base_ref`.

3. **`engine/state.py` `StoryState`**: Has `worktree_path: Path | None = None` and `pr_url: str | None = None`. This story adds `base_ref: str | None = None` for user-provided base ref override.

4. **`scm/worktree.py` `create_worktree()`**: Signature is `async def create_worktree(story_slug: str, base_ref: str | None = None, *, project_root: Path) -> Path`. Already accepts `base_ref` — defaults to `HEAD` when `None`. **No changes needed to worktree.py**.

5. **`scm/pr.py` `_detect_default_branch()`**: After Story 9.1, accepts `default_branch_override: str = ""`. This story calls it from `preflight_node` to resolve the branch name.

### Existing Code to Reuse — DO NOT REINVENT

- **`git()`** from `scm/git.py` — used for `git fetch`, `git rev-parse`, `git merge --ff-only`.
- **`create_worktree(base_ref=)`** from `scm/worktree.py` — already accepts a `base_ref` parameter.
- **`_detect_default_branch()`** from `scm/pr.py` — resolves default branch name with config override.
- **`ScmError`** from `core/exceptions.py` — raise for fetch failures.
- **`BRANCH_PREFIX`** from `core/constants.py` — not needed directly in `fetch_and_sync` but used by caller.

### CRITICAL: Fetch Per-Story, Not Per-Run

The epic states "fetch runs once per dispatch when processing multiple stories in an epic (cached after first fetch for the duration of the run, not per-story)". However, after further analysis for the auto-merge chain scenario, **fetch must run per-story** so that story N+1 picks up story N's auto-merged changes. The implementation does NOT cache the fetch result — each story calls `fetch_and_sync` independently. This is correct for the auto-merge chain in Story 9.3.

### CRITICAL: ff-only Merge is Optional and Non-Fatal

The ff-only merge attempt is a convenience to keep the local default branch up-to-date. If it fails (diverged history), the worktree is still created from the remote tip SHA (`origin/main`). This is safe because worktrees can be based off any ref, including remote tracking refs. The merge failure does NOT block story execution.

### CRITICAL: Detecting Current Branch

Use `git rev-parse --abbrev-ref HEAD` to get the current branch name. If the result is `"HEAD"` (detached state), skip the merge step. If it matches the `default_branch`, attempt ff-only merge. Otherwise skip.

### CRITICAL: `preflight_node` Error Handling for Fetch

If `fetch_and_sync()` raises `ScmError` (network failure), the story should be escalated — same handling as existing `ScmError` in `preflight_node`. The existing `except ScmError` block at the outer level already handles this, so just let the exception propagate from the `fetch_and_sync` call.

### Files Touched

| File | Changes |
|------|---------|
| `scm/branch.py` | New `fetch_and_sync()` function, `__all__` update |
| `scm/__init__.py` | Add `fetch_and_sync` to imports and `__all__` |
| `engine/nodes.py` | Call `fetch_and_sync()` before `create_worktree()` in `preflight_node` |
| `engine/state.py` | Add `base_ref: str \| None = None` to `StoryState` |
| `tests/test_scm/test_branch.py` | Unit tests for `fetch_and_sync` |
| `tests/test_scm/test_branch_integration.py` | Integration tests with real git remote |
| `tests/test_engine/test_nodes.py` | Preflight fetch integration tests |
