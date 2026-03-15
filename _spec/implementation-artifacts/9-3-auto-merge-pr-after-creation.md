# Story 9.3: Auto-Merge PR After Creation

Status: todo

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running overnight dispatches,
I want PRs to auto-merge after creation when configured,
so that completed stories flow through to the default branch without manual intervention.

## Acceptance Criteria (BDD)

1. **Given** `scm/pr.py` module **When** `merge_pull_request(pr_url: str, strategy: str = "squash", *, project_root: Path) → bool` is called **Then** it extracts the PR number from `pr_url` (last path segment of the URL) **And** runs `gh pr merge <pr_number> --<strategy> --delete-branch` **And** returns `True` on success.

2. **Given** `merge_pull_request()` is called **When** the `gh pr merge` command fails (merge conflicts, required reviews pending, gh not available) **Then** the function returns `False` without raising an exception **And** the failure is logged as a warning `scm.pr.merge.failed` with reason, stderr, and return code.

3. **Given** `merge_pull_request()` is called **When** `gh` CLI is not on PATH **Then** the function returns `False` immediately **And** logs `scm.pr.merge.skipped` with reason `"gh_not_found"`.

4. **Given** `merge_pull_request()` is called **When** the merge succeeds **Then** the `--delete-branch` flag causes `gh` to delete the remote `arcwright-ai/<story-slug>` branch at merge time **And** a `scm.pr.merge` structured log event is emitted with: `pr_url`, `strategy`, `success=True`.

5. **Given** `engine/nodes.py` `commit_node` **When** a PR is successfully created (pr_url is not None) **And** `state.config.scm.auto_merge` is `True` **Then** `merge_pull_request(pr_url, project_root=project_root)` is called **And** the merge result (True/False) is logged.

6. **Given** `engine/nodes.py` `commit_node` **When** `state.config.scm.auto_merge` is `False` (default) **Then** `merge_pull_request()` is never called — existing behavior preserved.

7. **Given** `merge_pull_request()` fails (returns `False`) **When** the commit_node processes the result **Then** the story status remains `SUCCESS` — merge failure is non-fatal **And** the PR remains open for manual merge **And** a provenance entry logs the merge failure as a warning.

8. **Given** `commit_node` calls `open_pull_request()` **When** the config has `scm.default_branch` set (from Story 9.1) **Then** `open_pull_request` is called with `default_branch=state.config.scm.default_branch` to ensure the PR targets the correct branch.

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

13. **Given** new unit tests **When** the test suite runs **Then** tests cover:
    (a) `merge_pull_request` with valid PR URL → extracts PR number, calls correct `gh` command, returns `True`;
    (b) `merge_pull_request` with `gh pr merge` failure → returns `False`, logs warning;
    (c) `merge_pull_request` with `gh` not on PATH → returns `False` immediately;
    (d) `merge_pull_request` with `strategy="merge"` → uses `--merge` instead of `--squash`;
    (e) `commit_node` with `auto_merge=True` and successful PR → calls `merge_pull_request`;
    (f) `commit_node` with `auto_merge=False` → does NOT call `merge_pull_request`;
    (g) `commit_node` with `auto_merge=True` and merge failure → story still SUCCESS;
    (h) `commit_node` passes `default_branch` from config to `open_pull_request`.

## Tasks / Subtasks

- [ ] Task 1: Implement `merge_pull_request` function in `scm/pr.py` (AC: #1, #2, #3, #4)
  - [ ] 1.1: Function signature: `async def merge_pull_request(pr_url: str, strategy: str = "squash", *, project_root: Path) -> bool`.
  - [ ] 1.2: Check `gh` availability via `shutil.which("gh")`. If not found, log `scm.pr.merge.skipped` and return `False`.
  - [ ] 1.3: Extract PR number from `pr_url`: split URL by `/`, take last segment, verify it's numeric. If extraction fails, log warning and return `False`.
  - [ ] 1.4: Build command: `gh pr merge <pr_number> --<strategy> --delete-branch`.
  - [ ] 1.5: Run via `asyncio.create_subprocess_exec("gh", "pr", "merge", pr_number, f"--{strategy}", "--delete-branch", cwd=str(project_root), stdout=PIPE, stderr=PIPE)`.
  - [ ] 1.6: On success (returncode 0): log `scm.pr.merge` event with pr_url, strategy, success=True. Return `True`.
  - [ ] 1.7: On failure (returncode != 0): log `scm.pr.merge.failed` warning with stderr, returncode. Return `False`.
  - [ ] 1.8: Wrap entire subprocess block in `try/except Exception` — any unexpected error logs warning and returns `False` (never raises).
  - [ ] 1.9: Google-style docstring with Args, Returns.

- [ ] Task 2: Update `__all__` and package exports (AC: #1)
  - [ ] 2.1: Add `"merge_pull_request"` to `scm/pr.py` `__all__`.
  - [ ] 2.2: Add `merge_pull_request` to `scm/__init__.py` imports and `__all__`.

- [ ] Task 3: Wire auto-merge into `commit_node` (AC: #5, #6, #7, #8)
  - [ ] 3.1: Add import for `merge_pull_request` from `scm/pr.py` (or from `scm/__init__`).
  - [ ] 3.2: After the existing `open_pull_request()` succeeds (pr_url is not None), add:
    ```python
    # Auto-merge PR if configured (Story 9.3)
    if pr_url is not None and state.config.scm.auto_merge:
        try:
            merged = await merge_pull_request(pr_url, project_root=project_root)
            if merged:
                logger.info(
                    "scm.pr.merge",
                    extra={"data": {"story": story_slug, "pr_url": pr_url, "strategy": "squash"}},
                )
            else:
                logger.warning(
                    "scm.pr.merge.failed",
                    extra={"data": {"story": story_slug, "pr_url": pr_url, "reason": "merge_returned_false"}},
                )
        except Exception as exc:
            logger.warning(
                "scm.pr.merge.error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )
    ```
  - [ ] 3.3: Update the `open_pull_request()` call to pass `default_branch=state.config.scm.default_branch`:
    ```python
    pr_url = await open_pull_request(
        branch_name,
        story_slug,
        pr_body,
        project_root=project_root,
        default_branch=state.config.scm.default_branch,
    )
    ```
  - [ ] 3.4: Ensure the auto-merge block comes AFTER `pr_url` is stored in `run.yaml` but BEFORE `remove_worktree()`.

- [ ] Task 4: Create unit tests for `merge_pull_request` (AC: #12, #13a-d)
  - [ ] 4.1: In `tests/test_scm/test_pr.py` add test `test_merge_pull_request_success` — mock subprocess, returncode=0, returns `True`.
  - [ ] 4.2: Test `test_merge_pull_request_extracts_pr_number` — verify PR number extracted from URL.
  - [ ] 4.3: Test `test_merge_pull_request_failure_returns_false` — returncode=1, returns `False`, logs warning.
  - [ ] 4.4: Test `test_merge_pull_request_gh_not_found` — `shutil.which` returns None, returns `False`.
  - [ ] 4.5: Test `test_merge_pull_request_merge_strategy` — verify `--merge` flag when strategy="merge".
  - [ ] 4.6: Test `test_merge_pull_request_invalid_url` — malformed URL, returns `False`.
  - [ ] 4.7: Test `test_merge_pull_request_subprocess_exception` — exception during subprocess, returns `False`.

- [ ] Task 5: Create unit tests for `commit_node` auto-merge wiring (AC: #12, #13e-h)
  - [ ] 5.1: In `tests/test_engine/test_nodes.py` add test `test_commit_node_auto_merge_enabled` — verify `merge_pull_request` called when `auto_merge=True` and `pr_url` exists.
  - [ ] 5.2: Test `test_commit_node_auto_merge_disabled` — verify `merge_pull_request` NOT called when `auto_merge=False`.
  - [ ] 5.3: Test `test_commit_node_auto_merge_failure_non_fatal` — merge returns `False`, story status still SUCCESS.
  - [ ] 5.4: Test `test_commit_node_passes_default_branch_to_open_pr` — verify `default_branch` kwarg passed to `open_pull_request`.

- [ ] Task 6: Run quality gates (AC: #9, #10, #11, #12)
  - [ ] 6.1: `ruff check .` — zero violations against FULL repository.
  - [ ] 6.2: `ruff format --check .` — zero formatting issues.
  - [ ] 6.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [ ] 6.4: `pytest` — all tests pass (existing + new).
  - [ ] 6.5: Verify Google-style docstrings on all modified/new functions.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: This story touches `scm/pr.py` (new function), `engine/nodes.py` (wiring), and `scm/__init__.py` (exports). Valid paths: `engine → scm → core`. No DAG violations.

**Decision 7 — Git Operations Strategy (Updated)**: Architecture says "Push + PR: after successful validation, `push_branch()` pushes to remote; `open_pull_request()` creates PR; optional auto-merge via `gh pr merge --squash` when `scm.auto_merge` is enabled."

### Current State Analysis — What Already Exists

1. **`scm/pr.py`** (708 lines): Has `_detect_default_branch()`, `open_pull_request()`, `generate_pr_body()`. No merge function exists. This story adds `merge_pull_request`.

2. **`scm/pr.py` `open_pull_request()`** (line 600): After Story 9.1, accepts `default_branch: str = ""` parameter. Currently called from `commit_node` WITHOUT `default_branch`. This story threads it from config.

3. **`engine/nodes.py` `commit_node`** (lines 1305-1500): After successful commit, calls `push_branch()` then `open_pull_request()`. PR URL stored in state and run.yaml. Worktree removal is LAST. This story inserts auto-merge between PR creation/URL storage and worktree removal.

4. **`core/config.py` `ScmConfig`**: After Story 9.1, has `auto_merge: bool = False` and `default_branch: str = ""`.

5. **`scm/__init__.py`**: Currently exports `generate_pr_body` from `scm/pr`. Does NOT export `open_pull_request` (it's imported directly in `engine/nodes.py`). Need to add `merge_pull_request`.

### Existing Code to Reuse — DO NOT REINVENT

- **`shutil.which("gh")`** — same pattern as `open_pull_request()` for gh CLI detection.
- **`asyncio.create_subprocess_exec()`** — same subprocess pattern as `open_pull_request()`.
- **`logger.warning()` structured events** — same logging pattern as the rest of `scm/pr.py`.
- **`commit_node` try/except pattern** — existing push and PR blocks use try/except with best-effort semantics. Auto-merge follows the same pattern.

### CRITICAL: PR Number Extraction

`open_pull_request()` returns the PR URL from `gh pr create` stdout, e.g., `"https://github.com/owner/repo/pull/42"`. The PR number is the last path segment: `pr_url.rstrip("/").rsplit("/", 1)[-1]`. Verify it's numeric before passing to `gh pr merge`.

### CRITICAL: Auto-Merge Placement in `commit_node`

The auto-merge call must be placed AFTER:
1. `commit_story()` — commit is done
2. `push_branch()` — branch is on remote
3. `open_pull_request()` — PR exists
4. PR URL stored in `run.yaml` — URL is persisted

And BEFORE:
5. `remove_worktree()` — worktree cleanup (worktree doesn't need to exist for merge)

This ensures the PR URL is persisted even if auto-merge fails, and the worktree is cleaned up regardless.

### CRITICAL: `open_pull_request` Default Branch Threading

Currently `commit_node` calls:
```python
pr_url = await open_pull_request(branch_name, story_slug, pr_body, project_root=project_root)
```

This story updates it to:
```python
pr_url = await open_pull_request(
    branch_name, story_slug, pr_body,
    project_root=project_root,
    default_branch=state.config.scm.default_branch,
)
```

This ensures PRs target the configured default branch, not just the auto-detected one.

### CRITICAL: Merge Strategy

Default strategy is `"squash"` which maps to `gh pr merge --squash`. This creates a single commit on the default branch per story. Combined with `--delete-branch`, the remote `arcwright-ai/<slug>` branch is cleaned up automatically.

Alternative strategies (`"merge"`, `"rebase"`) are supported via the `strategy` parameter but not exposed in config for MVP. The default `"squash"` aligns with typical code review workflows.

### Files Touched

| File | Changes |
|------|---------|
| `scm/pr.py` | New `merge_pull_request()` function, `__all__` update |
| `scm/__init__.py` | Add `merge_pull_request` to imports and `__all__` |
| `engine/nodes.py` | Call `merge_pull_request()` in `commit_node`, thread `default_branch` to `open_pull_request()` |
| `tests/test_scm/test_pr.py` | Unit tests for `merge_pull_request` |
| `tests/test_engine/test_nodes.py` | `commit_node` auto-merge tests |
