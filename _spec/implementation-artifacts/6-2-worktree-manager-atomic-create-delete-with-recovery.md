# Story 6.2: Worktree Manager — Atomic Create/Delete with Recovery

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer dispatching stories,
I want each story to execute in an isolated git worktree,
so that no story can corrupt the main branch or interfere with other stories.

## Acceptance Criteria (BDD)

1. **Given** `scm/worktree.py` module **When** the engine needs to create an execution environment for a story **Then** `create_worktree(story_slug: str, base_ref: str | None = None) → Path` creates worktree at `.arcwright-ai/worktrees/<story-slug>` with branch `arcwright-ai/<story-slug>` **And** returns the absolute `Path` to the worktree directory.

2. **Given** `scm/worktree.py` module **When** the engine needs to clean up after story execution **Then** `remove_worktree(story_slug: str) → None` removes the worktree **And** optionally deletes the associated branch.

3. **Given** a `create_worktree` call **When** `git worktree add` fails mid-operation (e.g., branch already exists, disk full, permission denied) **Then** cleanup restores consistent state — no partial worktree directories remain, no orphaned branches are created **And** `WorktreeError` is raised with a clear message describing the failure and the cleanup actions taken.

4. **Given** an existing worktree for the same `story_slug` **When** `create_worktree` is called **Then** `WorktreeError` is raised with a clear message indicating the worktree already exists **And** no `--force` flag is used, no implicit cleanup is performed per Decision 7.

5. **Given** a story executing within its worktree directory **When** the worktree path is used as the sandbox boundary **Then** the returned `Path` from `create_worktree` is the directory the agent executes in per NFR4.

6. **Given** a story that fails validation **When** the engine handles the failure **Then** the worktree is preserved (NOT cleaned up) for manual inspection **And** the worktree path is available in provenance/summary for developer reference.

7. **Given** `remove_worktree` is called for a `story_slug` whose worktree has already been removed **When** the operation executes **Then** it completes as a no-op (no error raised) per NFR19 idempotency requirement.

8. **Given** `remove_worktree` is called for a `story_slug` that never had a worktree **When** the operation executes **Then** it completes as a no-op (no error raised) per NFR19 idempotency requirement.

9. **Given** `create_worktree` with `base_ref=None` (default) **When** the worktree is created **Then** it uses `HEAD` as the base reference. **Given** `create_worktree` with an explicit `base_ref` (e.g., `"main"`, `"abc123"`) **When** the worktree is created **Then** the specified ref is used as the base.

10. **Given** `list_worktrees() → list[str]` **When** called **Then** it returns a list of story slugs for all currently active arcwright-managed worktrees (those under `.arcwright-ai/worktrees/`).

11. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

12. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

14. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

15. **Given** new tests in `tests/test_scm/test_worktree.py` **When** the test suite runs **Then** unit tests cover:
    (a) `create_worktree` returns correct `Path` under `.arcwright-ai/worktrees/<story-slug>`;
    (b) `create_worktree` invokes `git worktree add` with correct args including branch name and base ref;
    (c) `create_worktree` with `base_ref=None` defaults to `HEAD`;
    (d) `create_worktree` with explicit `base_ref` passes it to `git worktree add`;
    (e) `create_worktree` raises `WorktreeError` when worktree already exists (directory already present);
    (f) `create_worktree` atomic recovery: `git worktree add` fails → partial directory cleaned up, no orphan branch;
    (g) `remove_worktree` invokes `git worktree remove` with correct path;
    (h) `remove_worktree` is idempotent — removing an already-removed worktree is a no-op;
    (i) `remove_worktree` is idempotent — removing a never-created worktree is a no-op;
    (j) `list_worktrees` returns correct story slugs from `git worktree list` output;
    (k) `list_worktrees` returns empty list when no arcwright worktrees exist;
    (l) Structured log events emitted for create, remove, and error operations;
    (m) All git calls go through `scm.git.git()` — no direct subprocess calls in `worktree.py`.

16. **Given** integration tests marked `@pytest.mark.slow` **When** the integration test suite runs **Then** tests cover:
    (a) Create worktree with real git — verify directory exists, branch exists, files isolated from main;
    (b) Remove worktree with real git — verify directory removed, worktree list no longer shows it;
    (c) Full lifecycle: create → verify isolation → remove → verify cleanup;
    (d) Idempotent remove — remove twice, second is no-op.

## Tasks / Subtasks

- [x] Task 1: Implement `create_worktree` function (AC: #1, #3, #4, #5, #9)
  - [x] 1.1: Function signature: `async def create_worktree(story_slug: str, base_ref: str | None = None, *, project_root: Path) -> Path`.
  - [x] 1.2: Compute worktree path: `project_root / DIR_ARCWRIGHT / DIR_WORKTREES / story_slug` using constants from `core/constants.py`.
  - [x] 1.3: Check if worktree directory already exists — if so, raise `WorktreeError(f"Worktree already exists for '{story_slug}'", details={"path": str(worktree_path), "story_slug": story_slug})`.
  - [x] 1.4: Ensure parent directory `.arcwright-ai/worktrees/` exists (`worktree_path.parent.mkdir(parents=True, exist_ok=True)`).
  - [x] 1.5: Compute branch name: `BRANCH_PREFIX + story_slug` (e.g., `arcwright-ai/<story-slug>`).
  - [x] 1.6: Compute base ref: use `base_ref` if provided, otherwise `"HEAD"`.
  - [x] 1.7: Call `await git("worktree", "add", str(worktree_path), "-b", branch_name, resolved_base_ref, cwd=project_root)`.
  - [x] 1.8: Wrap git call in try/except `ScmError` — on failure, run `_cleanup_partial_worktree(worktree_path, branch_name, project_root)` then re-raise as `WorktreeError`.
  - [x] 1.9: Log success as `git.worktree.create` structured event with story_slug, worktree_path, branch_name, base_ref in data dict.
  - [x] 1.10: Return `worktree_path`.
  - [x] 1.11: Google-style docstring with Args, Returns, Raises.

- [x] Task 2: Implement `_cleanup_partial_worktree` helper (AC: #3)
  - [x] 2.1: Signature: `async def _cleanup_partial_worktree(worktree_path: Path, branch_name: str, project_root: Path) -> None`.
  - [x] 2.2: Try `await git("worktree", "remove", "--force", str(worktree_path), cwd=project_root)` — catch `ScmError` silently (worktree may not exist in git's tracking if add failed early).
  - [x] 2.3: If worktree directory still exists on disk, remove it: `shutil.rmtree(str(worktree_path), ignore_errors=True)`.
  - [x] 2.4: Try `await git("branch", "-D", branch_name, cwd=project_root)` — catch `ScmError` silently (branch may not have been created).
  - [x] 2.5: Log cleanup actions as `git.worktree.cleanup` event.
  - [x] 2.6: This function must NEVER raise — all errors are caught and logged. Its job is best-effort cleanup.

- [x] Task 3: Implement `remove_worktree` function (AC: #2, #7, #8)
  - [x] 3.1: Function signature: `async def remove_worktree(story_slug: str, *, project_root: Path) -> None`.
  - [x] 3.2: Compute worktree path: `project_root / DIR_ARCWRIGHT / DIR_WORKTREES / story_slug`.
  - [x] 3.3: Check if worktree directory exists — if not, log `git.worktree.remove` with `"already_absent": True` and return (no-op for idempotency).
  - [x] 3.4: Call `await git("worktree", "remove", str(worktree_path), cwd=project_root)`.
  - [x] 3.5: Catch `ScmError` — if worktree was already removed by git (race condition), treat as success. Otherwise re-raise as `WorktreeError`.
  - [x] 3.6: Log success as `git.worktree.remove` structured event.
  - [x] 3.7: Google-style docstring with Args, Raises.

- [x] Task 4: Implement `list_worktrees` function (AC: #10)
  - [x] 4.1: Function signature: `async def list_worktrees(*, project_root: Path) -> list[str]`.
  - [x] 4.2: Call `await git("worktree", "list", "--porcelain", cwd=project_root)`.
  - [x] 4.3: Parse output — each worktree block has `worktree <path>` line. Filter for paths under `.arcwright-ai/worktrees/`.
  - [x] 4.4: Extract story slug from path (the directory name under `worktrees/`).
  - [x] 4.5: Return sorted list of story slugs.
  - [x] 4.6: Google-style docstring with Args, Returns.

- [x] Task 5: Add structured logging (AC: #15l)
  - [x] 5.1: Create `logger = logging.getLogger(__name__)` (yields `arcwright_ai.scm.worktree`).
  - [x] 5.2: Log `create_worktree` success: `logger.info("git.worktree.create", extra={"data": {"story_slug": ..., "worktree_path": ..., "branch": ..., "base_ref": ...}})`.
  - [x] 5.3: Log `remove_worktree` success: `logger.info("git.worktree.remove", extra={"data": {"story_slug": ..., "worktree_path": ...}})`.
  - [x] 5.4: Log `remove_worktree` no-op: `logger.info("git.worktree.remove", extra={"data": {"story_slug": ..., "already_absent": True}})`.
  - [x] 5.5: Log cleanup actions: `logger.warning("git.worktree.cleanup", extra={"data": {"story_slug": ..., "worktree_path": ..., "branch": ...}})`.
  - [x] 5.6: Log errors with full context in data dict.

- [x] Task 6: Update `__all__` exports (AC: #1, #2, #10)
  - [x] 6.1: Update `scm/worktree.py` `__all__` to `["create_worktree", "remove_worktree", "list_worktrees"]`.
  - [x] 6.2: Update `scm/__init__.py` `__all__` to include `"create_worktree"`, `"remove_worktree"`, `"list_worktrees"`. Add re-exports: `from arcwright_ai.scm.worktree import create_worktree, remove_worktree, list_worktrees`.

- [x] Task 7: Create unit tests in `tests/test_scm/test_worktree.py` (AC: #14, #15)
  - [x] 7.1: Test `test_create_worktree_returns_correct_path` — Mock `git()`, call `create_worktree("my-story", project_root=tmp_path)`, verify returned path is `tmp_path / ".arcwright-ai" / "worktrees" / "my-story"`. (AC: #15a)
  - [x] 7.2: Test `test_create_worktree_invokes_git_with_correct_args` — Mock `git()`, call `create_worktree`, inspect mock call args: `("worktree", "add", str(expected_path), "-b", "arcwright/my-story", "HEAD")`. (AC: #15b)
  - [x] 7.3: Test `test_create_worktree_defaults_to_head` — Mock `git()`, call `create_worktree("s", project_root=...)` without base_ref. Verify "HEAD" in git call args. (AC: #15c)
  - [x] 7.4: Test `test_create_worktree_uses_explicit_base_ref` — Mock `git()`, call `create_worktree("s", base_ref="main", project_root=...)`. Verify "main" in git call args, NOT "HEAD". (AC: #15d)
  - [x] 7.5: Test `test_create_worktree_raises_worktree_error_when_exists` — Create the worktree directory on disk beforehand. Call `create_worktree`. Verify `WorktreeError` raised with "already exists" in message. `git()` should NOT be called. (AC: #15e)
  - [x] 7.6: Test `test_create_worktree_atomic_cleanup_on_failure` — Mock `git()` to raise `ScmError` on `worktree add` call. Verify cleanup is attempted (mock tracks cleanup calls). Verify `WorktreeError` is raised (not `ScmError`). (AC: #15f)
  - [x] 7.7: Test `test_remove_worktree_invokes_git_correctly` — Create worktree dir, mock `git()`. Call `remove_worktree`. Verify `git("worktree", "remove", ...)` called. (AC: #15g)
  - [x] 7.8: Test `test_remove_worktree_idempotent_already_removed` — Do NOT create worktree dir. Call `remove_worktree`. Verify no exception raised, `git()` NOT called (early return). (AC: #15h)
  - [x] 7.9: Test `test_remove_worktree_idempotent_never_created` — Do NOT create worktree dir. Call `remove_worktree`. Verify no exception raised. (AC: #15i)
  - [x] 7.10: Test `test_list_worktrees_returns_story_slugs` — Mock `git("worktree", "list", "--porcelain")` to return porcelain output with arcwright worktree paths. Verify extracted slugs match. (AC: #15j)
  - [x] 7.11: Test `test_list_worktrees_empty_when_no_arcwright_worktrees` — Mock `git("worktree", "list", "--porcelain")` to return only the main worktree. Verify empty list. (AC: #15k)
  - [x] 7.12: Test `test_create_worktree_logs_structured_event` — Mock `git()`, use `caplog`, verify `git.worktree.create` log emitted with data dict. (AC: #15l)
  - [x] 7.13: Test `test_remove_worktree_logs_structured_event` — Create dir, mock `git()`, use `caplog`, verify `git.worktree.remove` log emitted. (AC: #15l)
  - [x] 7.14: All test functions are `async def` with `@pytest.mark.asyncio` decorator.

- [x] Task 8: Create integration tests in `tests/test_scm/test_worktree_integration.py` (AC: #16)
  - [x] 8.1: All tests marked `@pytest.mark.slow` and `@pytest.mark.asyncio`.
  - [x] 8.2: Fixture `git_repo(tmp_path)` — creates a real git repo with `git init`, initial commit, returns path.
  - [x] 8.3: Test `test_create_worktree_real_git` — Create worktree in real repo. Verify directory exists, branch exists (`git branch --list`), file changes in worktree don't appear in main. (AC: #16a)
  - [x] 8.4: Test `test_remove_worktree_real_git` — Create then remove worktree. Verify directory gone, worktree not in `git worktree list`. (AC: #16b)
  - [x] 8.5: Test `test_worktree_full_lifecycle` — Create → write file in worktree → verify isolated from main → remove → verify cleanup. (AC: #16c)
  - [x] 8.6: Test `test_remove_worktree_idempotent_real_git` — Create, remove, remove again. Second remove is no-op. (AC: #16d)

- [x] Task 9: Run quality gates (AC: #11, #12, #13, #14)
  - [x] 9.1: `ruff check .` — zero violations against FULL repository.
  - [x] 9.2: `ruff format --check .` — zero formatting issues.
  - [x] 9.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 9.4: `pytest` — all tests pass (existing + new), excluding `@pytest.mark.slow` unless real git available.
  - [x] 9.5: Verify Google-style docstrings on all public functions.
  - [x] 9.6: Verify `git diff --name-only` matches Dev Agent Record file list.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 6.2 adds code ONLY to `scm/worktree.py` and `scm/__init__.py`. The worktree module imports from `core/` only (`core/exceptions.py` for `WorktreeError`, `core/constants.py` for directory/branch constants) and from `scm/git.py` for the `git()` wrapper. This is the valid dependency: `scm → core` + internal `scm` imports. No DAG violations.

**Decision 7 — Git Operations Strategy**: Worktree lifecycle is explicitly specified:
1. `git worktree add .arcwright-ai/worktrees/<story-slug> -b arcwright/<story-slug> <base-ref>`
2. Agent executes in worktree directory (sandbox boundary)
3. Validation passes → `git add` + `git commit` (inside worktree) → `git worktree remove`
4. Validation fails → worktree preserved for inspection, logged in provenance
5. Halt/budget-exceeded → all active worktrees preserved, run marked incomplete

**Key D7 conventions**: No force operations (no `--force`, no `reset --hard`, no rebase). Existing branch → error out. Push after successful validation via `push_branch()`. All git commands run with `cwd=worktree_path` except worktree add/remove (project root). Cleanup is always user-initiated (never automatic). [Source: architecture.md — Decision 7]

**Architectural Constraint 4 — Worktree Isolation as Security Model**: "Git worktrees are not a convenience — they are the **primary isolation and safety boundary**." Worktree operations must be atomic and recoverable — if `git worktree add` fails mid-operation, cleanup logic must restore consistent state. This is a founding architectural decision. [Source: architecture.md — Constraint 4]

**Decision 8 — Structured Logging**: The `git.worktree.create` and `git.worktree.remove` event types are listed in the D8 event type taxonomy. Log events MUST use structured `extra={"data": {...}}` format. [Source: architecture.md — Decision 8]

**Decision 6 — Error Taxonomy**: `WorktreeError(ScmError)` is the exception for worktree create/cleanup failures. It inherits `message: str` and `details: dict[str, Any] | None` from `ArcwrightError`. [Source: architecture.md — Decision 6]

**NFR4 — Worktree Isolation**: "Worktree isolation prevents any story execution from corrupting the main branch or other stories' worktrees." Each story executes within its worktree directory — worktree path is the sandbox boundary.

**NFR19 — Idempotency**: "Resume, cleanup, init, and all re-runnable operations must produce identical state on repeated execution." `remove_worktree` for an already-removed or never-created worktree must be a no-op.

**Boundary 4 — Application ↔ File System**: "All git operations go through `scm/git.py` — no subprocess calls from other packages." The `worktree.py` module calls `git()` from `scm/git.py` — never uses `subprocess` directly.

### Current State Analysis — What Already Exists

1. **`scm/worktree.py`** — Stub file with docstring `"SCM worktree — Atomic worktree create/delete with recovery."` and empty `__all__`. Implementation goes here.

2. **`scm/__init__.py`** — Package init with `GitResult` and `git` in `__all__`. Has placeholder comments for `create_worktree` and `remove_worktree`. This story adds the worktree functions to the public API.

3. **`scm/git.py`** — FULLY IMPLEMENTED in Story 6.1. Provides:
   - `GitResult(ArcwrightModel)` — frozen Pydantic model with `stdout`, `stderr`, `returncode`, `success` property.
   - `async def git(*args: str, cwd: Path | None = None) -> GitResult` — sole gateway for all git subprocess calls.
   - Raises `ScmError` on non-zero exit with error classification (lock contention with retry, permission denied, not-a-repo).
   - USE THIS — call `git()` for all git operations. Do NOT use `asyncio.create_subprocess_exec` directly.

4. **`WorktreeError`** in `core/exceptions.py` — Already defined as `ScmError` subclass: `"Raised when git worktree add or git worktree remove fails. The branch name should be included in details when available."` Has `message: str` and `details: dict[str, Any] | None` from `ArcwrightError` base. USE THIS — do NOT create a new exception.

5. **`core/constants.py`** — Already defines:
   - `DIR_ARCWRIGHT = ".arcwright-ai"`
   - `DIR_WORKTREES = "worktrees"`
   - `BRANCH_PREFIX = "arcwright/"`
   - `WORKTREE_DIR_TEMPLATE = ".arcwright-ai/worktrees/{story_slug}"`
   USE THESE constants — do NOT hardcode strings.

6. **`tests/test_scm/`** — Directory exists with `__init__.py`, `.gitkeep`, and `test_git.py` (11 unit tests from story 6.1). Create `test_worktree.py` and `test_worktree_integration.py` here.

7. **`tests/conftest.py`** — Has `tmp_project` fixture that scaffolds `.arcwright-ai/` and `_spec/` directories. Use for tests that need project directory structure.

### Existing Code to Reuse — DO NOT REINVENT

- **`git()`** from `scm/git.py` — CALL for all git operations. Do NOT use subprocess directly.
- **`WorktreeError`** from `core/exceptions.py` — RAISE for worktree-specific failures. `ScmError` for git-level failures is handled by `git()` function internally.
- **`DIR_ARCWRIGHT`**, **`DIR_WORKTREES`**, **`BRANCH_PREFIX`** from `core/constants.py` — USE for all path and branch name construction.
- **`logging.getLogger(__name__)`** pattern — REUSE from `scm/git.py`.

### CRITICAL: The `git()` Function Already Handles Error Classification

The `git()` function in `scm/git.py` raises `ScmError` on non-zero exit codes with classified error messages (lock contention, permission denied, not-a-repo). When calling `git()` in `worktree.py`:
- Catch `ScmError` — re-raise as `WorktreeError` with worktree-specific context added.
- Do NOT duplicate error classification logic.
- The `ScmError.details` dict from the original error should be preserved or merged into the `WorktreeError.details`.

### CRITICAL: Atomic Cleanup Strategy

When `git worktree add` fails mid-operation, there are two possible partial states:
1. **Branch was created but worktree directory was not fully populated** — need to delete the branch + remove any partial directory.
2. **Worktree directory was partially created** — need to `git worktree remove --force` it + clean up the directory on disk.

The cleanup helper must handle BOTH states. Cleanup is **best-effort** — silently catch errors during cleanup (log them, but don't raise). The original error should be re-raised as `WorktreeError` after cleanup completes.

The `--force` flag is used ONLY in `_cleanup_partial_worktree` (cleanup of a failed operation), NOT in normal `create_worktree` or `remove_worktree`. This is consistent with D7's "no force operations" rule — force is only for emergency recovery from partial failure.

### CRITICAL: `remove_worktree` Idempotency Implementation

Idempotency is achieved by checking if the worktree directory exists BEFORE calling `git worktree remove`:
- If directory does NOT exist → log as no-op, return immediately.
- If directory exists → call `git worktree remove` → if it fails because worktree is already removed from git's tracking (but directory exists as leftover), fall back to directory removal.

Do NOT rely solely on `git worktree list` to check existence — the directory might exist without being tracked by git (partial state), or the worktree might be tracked but directory already removed.

### CRITICAL: `list_worktrees` Parsing Strategy

`git worktree list --porcelain` outputs blocks like:
```
worktree /path/to/main
HEAD abc123
branch refs/heads/main

worktree /path/to/.arcwright-ai/worktrees/my-story
HEAD def456
branch refs/heads/arcwright/my-story

```

Parse line by line. For lines starting with `worktree `, extract the path. Check if path contains `/.arcwright-ai/worktrees/`. If so, extract the directory name as the story slug.

### CRITICAL: `shutil.rmtree` for Directory Cleanup

Use `shutil.rmtree(str(path), ignore_errors=True)` for removing partial worktree directories in cleanup. Import `shutil` at module level. This is a sync operation — it's acceptable here because it's only used in error recovery paths and the directory is small.

### CRITICAL: Do NOT Create Worktree Parent Directory Using `git`

The `.arcwright-ai/worktrees/` parent directory must exist before `git worktree add` is called. Use `worktree_path.parent.mkdir(parents=True, exist_ok=True)` to ensure it exists. This is a filesystem operation, not a git operation.

### Mocking Strategy for Unit Tests

Mock `scm.git.git` at the callsite in `worktree.py`. Since `worktree.py` imports `git` from `scm.git`:

```python
from arcwright_ai.scm.git import git
```

The mock should be:
```python
monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)
```

Where `mock_git` is an `AsyncMock`. Configure side effects per call to simulate different git operations (`worktree add`, `worktree remove`, `worktree list`, `branch -D`, etc.).

**For tests that need to distinguish between multiple git calls** (e.g., `create_worktree` calls `git("worktree", "add", ...)` then on failure calls `git("worktree", "remove", ...)`), use `side_effect` as a function or list of return values on the `AsyncMock`.

### Integration Tests with Real Git

Integration tests use `tmp_path` to create real git repos:
```python
@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    """Create a real git repo with initial commit for integration testing."""
    await git("init", cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=tmp_path)
    await git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# Test")
    await git("add", ".", cwd=tmp_path)
    await git("commit", "-m", "Initial commit", cwd=tmp_path)
    # Create .arcwright-ai/worktrees directory
    (tmp_path / ".arcwright-ai" / "worktrees").mkdir(parents=True)
    return tmp_path
```

Mark all integration tests with `@pytest.mark.slow` — they are excluded from the default test run. Run with `pytest -m slow` to include them.

### Relationship to Other Stories in Epic 6

- **Story 6.1 (done):** Foundation — the `git()` wrapper this story calls for all operations.
- **Story 6.2 (this):** Worktree lifecycle — `create_worktree`, `remove_worktree`, `list_worktrees`. Foundation for stories 6.5 and 6.6.
- **Story 6.3:** `scm/branch.py` — `commit_story` calls `git("add", ".")` + `git("commit", ...)` inside worktree. Separate from worktree lifecycle.
- **Story 6.4:** `scm/pr.py` — reads provenance, generates PR body. No direct worktree interaction.
- **Story 6.5:** `cli/clean.py` — calls `list_worktrees()` and `remove_worktree()` from this story.
- **Story 6.6:** Engine node integration — calls `create_worktree` in preflight node, `remove_worktree` in commit node.

This story depends on **Story 6.1** (done). Stories **6.5 and 6.6** depend on this story.

### Testing Patterns from Story 6.1

- **Mock at callsite**: `monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)` — NOT `monkeypatch.setattr(git_module, "git", mock)`.
- **Use `pytest.mark.asyncio`**: All test functions must be async since `create_worktree()`, `remove_worktree()`, `list_worktrees()` are async.
- **Use `caplog`**: For log verification, use `caplog` fixture with `logging.DEBUG` level capture on `"arcwright_ai.scm.worktree"`.
- **Test naming**: `test_<function_name>_<scenario>`, e.g., `test_create_worktree_returns_correct_path`.
- **Assertion style**: Plain `assert` + `pytest.raises(WorktreeError, match="...")`.
- **`tmp_path` for filesystem**: All tests that check directory existence use `tmp_path` — never touch the real filesystem.
- **`AsyncMock` for `git()`**: The `git()` function is async, so mock must be `AsyncMock` from `unittest.mock`.

### CRITICAL: Monkeypatch Strategy (Learned from Story 6.1)

Story 6.1's debug log notes: "pytest's dotted-string resolver treats the module name as a package path" for some patterns. For worktree.py tests, use:
```python
monkeypatch.setattr("arcwright_ai.scm.worktree.git", mock_git)
```
This works because `worktree.py` does `from arcwright_ai.scm.git import git` — it creates a local name binding. Test the monkeypatch approach early in development to confirm it works.

**Alternative if dotted-string fails**: Import the module and setattr on it directly:
```python
import arcwright_ai.scm.worktree as worktree_module
monkeypatch.setattr(worktree_module, "git", mock_git)
```

### Project Structure Notes

Files created/modified by this story:
```
src/arcwright_ai/scm/worktree.py       # MODIFIED: implement create_worktree, remove_worktree, list_worktrees, _cleanup_partial_worktree
src/arcwright_ai/scm/__init__.py        # MODIFIED: add create_worktree, remove_worktree, list_worktrees to __all__ + re-exports
tests/test_scm/test_worktree.py         # CREATED: unit tests for worktree functions
tests/test_scm/test_worktree_integration.py  # CREATED: integration tests with real git (@pytest.mark.slow)
```

No other files should be modified. This story adds to the `scm` package only.

### References

- [Architecture Decision 7: Git Operations Strategy](../../_spec/planning-artifacts/architecture.md#decision-7-git-operations-strategy)
- [Architecture Constraint 4: Worktree Isolation as Security Model](../../_spec/planning-artifacts/architecture.md#first-class-architectural-constraints)
- [Architecture Decision 8: Logging & Observability](../../_spec/planning-artifacts/architecture.md#decision-8-logging--observability)
- [Architecture Decision 6: Error Handling Taxonomy](../../_spec/planning-artifacts/architecture.md#decision-6-error-handling-taxonomy)
- [Architecture: Package Dependency DAG](../../_spec/planning-artifacts/architecture.md#package-dependency-dag-mandatory)
- [Architecture: Testing Patterns](../../_spec/planning-artifacts/architecture.md#testing-patterns)
- [Architecture: Structured Logging Patterns](../../_spec/planning-artifacts/architecture.md#structured-logging-patterns)
- [Architecture: Boundary 4 — Application ↔ File System](../../_spec/planning-artifacts/architecture.md#architectural-boundaries)
- [Architecture: Data Flow — Preflight Node](../../_spec/planning-artifacts/architecture.md#data-flow)
- [Epics: Story 6.2](../../_spec/planning-artifacts/epics.md#story-62-worktree-manager--atomic-createdelete-with-recovery)
- [Previous Story 6.1: Git Subprocess Wrapper](../../_spec/implementation-artifacts/6-1-git-subprocess-wrapper-safe-shell-out-foundation.md)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- Integration tests initially failed because `git worktree remove` rejects worktrees with untracked files (no `--force` in production code per D7). Fixed by committing any written files in the worktree before calling `remove_worktree` in integration tests, matching real-world usage.
- Used `contextlib.suppress(ScmError)` in `_cleanup_partial_worktree` instead of `try/except/pass` to satisfy `ruff SIM105`.
- Sorted `__all__` alphabetically in both `worktree.py` and `scm/__init__.py` to satisfy `ruff RUF022`.

### Completion Notes List

- Implemented `create_worktree`, `remove_worktree`, `list_worktrees`, and `_cleanup_partial_worktree` in `src/arcwright_ai/scm/worktree.py`.
- All functions are `async`, use `git()` from `scm/git.py` exclusively (no direct subprocess), and raise `WorktreeError` on failure.
- Atomic recovery: `_cleanup_partial_worktree` silently handles both partial-directory and orphan-branch states using `contextlib.suppress`.
- `remove_worktree` achieves idempotency by checking directory existence before invoking git.
- `list_worktrees` parses `git worktree list --porcelain` output, filtering for `.arcwright-ai/worktrees/` paths.
- Updated `scm/__init__.py` to re-export all three public symbols.
- 15 unit tests (all passing, green) covering all AC #15 sub-items.
- 4 integration tests marked `@pytest.mark.slow` covering all AC #16 sub-items.
- Zero ruff violations, zero mypy --strict errors.

## Senior Developer Review (AI)

### Reviewer

Ed

### Date

2026-03-07

### Outcome

Changes Requested (addressed in this review pass)

### Findings

1. **HIGH** — AC #2 gap: `remove_worktree` did not support optional deletion of associated branch.
2. **HIGH** — AC #3 gap: `WorktreeError` on failed create did not include cleanup actions taken.
3. **MEDIUM** — AC #15l gap: missing explicit structured error events for create/remove failure paths.
4. **MEDIUM** — Portability gap: `list_worktrees` used POSIX-only path marker matching.

### Fixes Applied During Review

- Added `delete_branch: bool = False` support to `remove_worktree()` and branch delete behavior via `git("branch", "-D", ...)` when requested.
- Refactored `_cleanup_partial_worktree()` to return concrete cleanup actions and included them in both structured logs and raised `WorktreeError` details/message.
- Added structured error log events: `git.worktree.create.error` and `git.worktree.remove.error`.
- Updated `list_worktrees()` parsing to use `Path(...).parts` segment matching for robust path handling.
- Added unit tests for optional branch deletion and cleanup-action-rich create failure message/details.

### Validation Evidence

- `ruff check src/arcwright_ai/scm/worktree.py tests/test_scm/test_worktree.py` ✅
- `.venv/bin/python -m mypy --strict src/ tests/test_scm/test_worktree.py` ✅
- `pytest tests/test_scm/test_worktree.py tests/test_scm/test_worktree_integration.py -q` ✅ (19 passed)

### Change Log

- 2026-03-07: Implemented Story 6.2 — `create_worktree`, `remove_worktree`, `list_worktrees`, atomic cleanup, structured logging, unit tests (×13), integration tests (×4). Zero lint/type errors.
- 2026-03-07: Senior Developer Review (AI) remediation — added optional branch deletion, cleanup-action propagation in create failures, structured error events, cross-platform worktree listing, and 2 additional unit tests.

### File List

- src/arcwright_ai/scm/worktree.py
- src/arcwright_ai/scm/__init__.py
- tests/test_scm/test_worktree.py
- tests/test_scm/test_worktree_integration.py
- _spec/implementation-artifacts/6-2-worktree-manager-atomic-create-delete-with-recovery.md
- _spec/implementation-artifacts/sprint-status.yaml
