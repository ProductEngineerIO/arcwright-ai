# Story 6.3: Branch Manager & Commit Strategy

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer reviewing overnight results,
I want clean git branches per story with structured commit messages,
so that the git history is organized and traceable back to the run that produced it.

## Acceptance Criteria (BDD)

1. **Given** `scm/branch.py` module **When** a story is dispatched and completes validation **Then** branch naming follows convention: `arcwright-ai/<story-slug>` — namespaced, predictable, greppable per D7.

2. **Given** `scm/branch.py` module **When** `create_branch(story_slug: str, base_ref: str | None = None, *, project_root: Path) -> str` is called **Then** a new branch named `arcwright-ai/<story-slug>` is created at the specified base ref (defaulting to `HEAD`) **And** the branch name is returned **And** if the branch already exists, `BranchError` is raised (no force operations per D7).

3. **Given** `scm/branch.py` module **When** a story completes validation and needs to commit **Then** `commit_story(story_slug: str, story_title: str, story_path: str, run_id: str, *, worktree_path: Path) -> str` stages all changes with `git add .` and commits with message format `[arcwright-ai] <story-title>\n\nStory: <story-file-path>\nRun: <run-id>` using `COMMIT_MESSAGE_TEMPLATE` from `core/constants.py` **And** the commit hash is returned.

4. **Given** `commit_story` is called **When** there are no staged changes (nothing to commit) **Then** a `BranchError` is raised with a clear message indicating no changes were found (not silently ignored).

5. **Given** `scm/branch.py` module **When** `branch_exists(branch_name: str, *, project_root: Path) -> bool` is called **Then** it returns `True` if the branch exists locally, `False` otherwise **And** no exception is raised for non-existent branches.

6. **Given** `scm/branch.py` module **When** `list_branches(*, project_root: Path) -> list[str]` is called **Then** it returns a sorted list of all arcwright-namespaced branches (matching `arcwright-ai/*` pattern) **And** returns an empty list when no arcwright branches exist.

7. **Given** `scm/branch.py` module **When** `delete_branch(branch_name: str, *, project_root: Path, force: bool = False) -> None` is called **Then** it deletes the branch using `git branch -d` (safe delete, only if fully merged) by default **And** if `force=True`, uses `git branch -D` (force delete regardless of merge status) **And** if the branch does not exist, the call is a no-op (idempotent per NFR19).

8. **Given** all git operations in `scm/branch.py` **When** any function is called **Then** no push is performed — all operations are local only per D7 **And** no `--force`, `reset --hard`, or rebase commands are used per D7.

9. **Given** all git operations in `scm/branch.py` **When** any function is called **Then** all operations are compatible with git 2.25+ per NFR14 (no features introduced after git 2.25, which is Ubuntu 20.04 floor).

10. **Given** all git operations in `scm/branch.py` **When** git commands are executed **Then** all calls go through `scm.git.git()` — no direct subprocess calls per Boundary 4.

11. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

12. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

14. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

15. **Given** new tests in `tests/test_scm/test_branch.py` **When** the test suite runs **Then** unit tests cover:
    (a) `create_branch` creates branch with correct name format `arcwright-ai/<story-slug>`;
    (b) `create_branch` invokes `git("branch", branch_name, base_ref, cwd=project_root)` with correct args;
    (c) `create_branch` with `base_ref=None` defaults to `HEAD`;
    (d) `create_branch` with explicit `base_ref` passes it to `git branch`;
    (e) `create_branch` raises `BranchError` when branch already exists;
    (f) `commit_story` invokes `git("add", ".", cwd=worktree_path)` then `git("commit", "-m", message, cwd=worktree_path)`;
    (g) `commit_story` uses `COMMIT_MESSAGE_TEMPLATE` with correct interpolation of story_title, story_path, run_id;
    (h) `commit_story` returns the commit hash from `git rev-parse HEAD`;
    (i) `commit_story` raises `BranchError` when nothing to commit (git commit fails with "nothing to commit");
    (j) `branch_exists` returns `True` for existing branch;
    (k) `branch_exists` returns `False` for non-existent branch (catches `ScmError`);
    (l) `list_branches` returns sorted list of arcwright branch names;
    (m) `list_branches` returns empty list when no arcwright branches exist;
    (n) `delete_branch` invokes `git("branch", "-d", branch_name)` by default;
    (o) `delete_branch` invokes `git("branch", "-D", branch_name)` when `force=True`;
    (p) `delete_branch` is idempotent — deleting non-existent branch is a no-op;
    (q) Structured log events emitted for create, commit, delete, and error operations;
    (r) All git calls go through `scm.git.git()` — no direct subprocess calls in `branch.py`.

16. **Given** integration tests marked `@pytest.mark.slow` **When** the integration test suite runs **Then** tests cover:
    (a) Create branch with real git — verify branch exists in `git branch --list`;
    (b) Create branch that already exists — verify `BranchError` raised;
    (c) Commit story with real git — verify commit in log with correct message format;
    (d) Commit story with no changes — verify `BranchError` raised;
    (e) `branch_exists` returns correct values for existing and non-existing branches;
    (f) `list_branches` returns correct arcwright branches from real repo;
    (g) Delete branch with real git — verify branch no longer in `git branch --list`;
    (h) Delete non-existent branch — verify no error (idempotent).

## Tasks / Subtasks

- [x] Task 1: Implement `branch_exists` function (AC: #5, #9, #10)
  - [x] 1.1: Function signature: `async def branch_exists(branch_name: str, *, project_root: Path) -> bool`.
  - [x] 1.2: Call `await git("rev-parse", "--verify", f"refs/heads/{branch_name}", cwd=project_root)`.
  - [x] 1.3: Return `True` on success, `False` on `ScmError` (branch does not exist).
  - [x] 1.4: Google-style docstring with Args, Returns.

- [x] Task 2: Implement `create_branch` function (AC: #1, #2, #8, #9, #10)
  - [x] 2.1: Function signature: `async def create_branch(story_slug: str, base_ref: str | None = None, *, project_root: Path) -> str`.
  - [x] 2.2: Compute branch name: `BRANCH_PREFIX + story_slug` (e.g., `arcwright-ai/<story-slug>`).
  - [x] 2.3: Compute base ref: use `base_ref` if provided, otherwise `"HEAD"`.
  - [x] 2.4: Check if branch already exists via `branch_exists()` — if so, raise `BranchError(f"Branch '{branch_name}' already exists for story '{story_slug}'", details={"branch": branch_name, "story_slug": story_slug})`.
  - [x] 2.5: Call `await git("branch", branch_name, resolved_base_ref, cwd=project_root)`.
  - [x] 2.6: Catch `ScmError` — re-raise as `BranchError` with branch-specific context.
  - [x] 2.7: Log success as `git.branch.create` structured event with story_slug, branch_name, base_ref.
  - [x] 2.8: Return `branch_name`.
  - [x] 2.9: Google-style docstring with Args, Returns, Raises.

- [x] Task 3: Implement `commit_story` function (AC: #3, #4, #8, #9, #10)
  - [x] 3.1: Function signature: `async def commit_story(story_slug: str, story_title: str, story_path: str, run_id: str, *, worktree_path: Path) -> str`.
  - [x] 3.2: Call `await git("add", ".", cwd=worktree_path)` to stage all changes.
  - [x] 3.3: Build commit message using `COMMIT_MESSAGE_TEMPLATE.format(story_title=story_title, story_path=story_path, run_id=run_id)` from `core/constants.py`.
  - [x] 3.4: Call `await git("commit", "-m", message, cwd=worktree_path)`.
  - [x] 3.5: Catch `ScmError` on commit — if stderr contains "nothing to commit" or "nothing added to commit", raise `BranchError("No changes to commit for story '{story_slug}'", details={"story_slug": story_slug, "worktree_path": str(worktree_path)})`. (Implemented via pre-commit `git status --porcelain` check — git routes this message to stdout not stderr in git 2.25+; status check is more reliable.)
  - [x] 3.6: Catch other `ScmError` on commit — re-raise as `BranchError` with commit-specific context.
  - [x] 3.7: Call `await git("rev-parse", "HEAD", cwd=worktree_path)` to get the commit hash.
  - [x] 3.8: Log success as `git.commit` structured event with story_slug, commit_hash, worktree_path, run_id.
  - [x] 3.9: Return the commit hash (stripped).
  - [x] 3.10: Google-style docstring with Args, Returns, Raises.

- [x] Task 4: Implement `list_branches` function (AC: #6, #9, #10)
  - [x] 4.1: Function signature: `async def list_branches(*, project_root: Path) -> list[str]`.
  - [x] 4.2: Call `await git("branch", "--list", f"{BRANCH_PREFIX}*", cwd=project_root)`.
  - [x] 4.3: Parse output — each line is a branch name. Strip leading `* ` (current branch marker) and whitespace.
  - [x] 4.4: Filter for non-empty lines.
  - [x] 4.5: Return sorted list of branch names.
  - [x] 4.6: Google-style docstring with Args, Returns.

- [x] Task 5: Implement `delete_branch` function (AC: #7, #8, #9, #10)
  - [x] 5.1: Function signature: `async def delete_branch(branch_name: str, *, project_root: Path, force: bool = False) -> None`.
  - [x] 5.2: Check if branch exists via `branch_exists()` — if not, log as no-op and return (idempotent).
  - [x] 5.3: Choose flag: `"-D"` if `force=True`, `"-d"` otherwise.
  - [x] 5.4: Call `await git("branch", flag, branch_name, cwd=project_root)`.
  - [x] 5.5: Catch `ScmError` — re-raise as `BranchError` with context (e.g., "branch not fully merged" for `-d` failures).
  - [x] 5.6: Log success as `git.branch.delete` structured event with branch_name, force.
  - [x] 5.7: Google-style docstring with Args, Raises.

- [x] Task 6: Add structured logging (AC: #15q)
  - [x] 6.1: Create `logger = logging.getLogger(__name__)` (yields `arcwright_ai.scm.branch`).
  - [x] 6.2: Log `create_branch` success: `logger.info("git.branch.create", extra={"data": {"story_slug": ..., "branch": ..., "base_ref": ...}})`.
  - [x] 6.3: Log `commit_story` success: `logger.info("git.commit", extra={"data": {"story_slug": ..., "commit_hash": ..., "worktree_path": ..., "run_id": ...}})`.
  - [x] 6.4: Log `delete_branch` success: `logger.info("git.branch.delete", extra={"data": {"branch": ..., "force": ...}})`.
  - [x] 6.5: Log `delete_branch` no-op: `logger.info("git.branch.delete", extra={"data": {"branch": ..., "already_absent": True}})`.
  - [x] 6.6: Log errors with full context in data dict.

- [x] Task 7: Update `__all__` exports (AC: #2, #3, #5, #6, #7)
  - [x] 7.1: Update `scm/branch.py` `__all__` to `["branch_exists", "commit_story", "create_branch", "delete_branch", "list_branches"]`.
  - [x] 7.2: Update `scm/__init__.py` `__all__` to include `"branch_exists"`, `"commit_story"`, `"create_branch"`, `"delete_branch"`, `"list_branches"`. Add re-exports: `from arcwright_ai.scm.branch import branch_exists, commit_story, create_branch, delete_branch, list_branches`.

- [x] Task 8: Create unit tests in `tests/test_scm/test_branch.py` (AC: #14, #15)
  - [x] 8.1: Test `test_create_branch_returns_correct_name`
  - [x] 8.2: Test `test_create_branch_invokes_git_with_correct_args`
  - [x] 8.3: Test `test_create_branch_defaults_to_head`
  - [x] 8.4: Test `test_create_branch_uses_explicit_base_ref`
  - [x] 8.5: Test `test_create_branch_raises_branch_error_when_exists`
  - [x] 8.6: Test `test_commit_story_invokes_git_add_and_commit`
  - [x] 8.7: Test `test_commit_story_uses_commit_message_template`
  - [x] 8.8: Test `test_commit_story_returns_commit_hash`
  - [x] 8.9: Test `test_commit_story_raises_branch_error_on_nothing_to_commit`
  - [x] 8.10: Test `test_branch_exists_returns_true`
  - [x] 8.11: Test `test_branch_exists_returns_false`
  - [x] 8.12: Test `test_list_branches_returns_sorted_list`
  - [x] 8.13: Test `test_list_branches_returns_empty_when_none`
  - [x] 8.14: Test `test_delete_branch_invokes_git_with_d_flag`
  - [x] 8.15: Test `test_delete_branch_invokes_git_with_D_flag_when_force`
  - [x] 8.16: Test `test_delete_branch_idempotent_nonexistent`
  - [x] 8.17: Test `test_create_branch_logs_structured_event`
  - [x] 8.18: Test `test_commit_story_logs_structured_event`
  - [x] 8.19: All test functions are `async def` with `@pytest.mark.asyncio` decorator.

- [x] Task 9: Create integration tests in `tests/test_scm/test_branch_integration.py` (AC: #16)
  - [x] 9.1: All tests marked `@pytest.mark.slow` and `@pytest.mark.asyncio`.
  - [x] 9.2: `git_repo(tmp_path)` fixture — creates a real git repo with `git init`, initial commit, returns path.
  - [x] 9.3: Test `test_create_branch_real_git`
  - [x] 9.4: Test `test_create_branch_existing_raises_error`
  - [x] 9.5: Test `test_commit_story_real_git`
  - [x] 9.6: Test `test_commit_story_no_changes_raises_error`
  - [x] 9.7: Test `test_branch_exists_real_git`
  - [x] 9.8: Test `test_list_branches_real_git`
  - [x] 9.9: Test `test_delete_branch_real_git`
  - [x] 9.10: Test `test_delete_branch_idempotent_real_git`

- [x] Task 10: Run quality gates (AC: #11, #12, #13, #14)
  - [x] 10.1: `ruff check .` — zero violations against FULL repository.
  - [x] 10.2: `ruff format --check .` — zero formatting issues.
  - [x] 10.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 10.4: `pytest` — all tests pass (629 non-slow + 8 integration = 637 total).
  - [x] 10.5: Verify Google-style docstrings on all public functions.
  - [x] 10.6: Verify `git diff --name-only` matches Dev Agent Record file list.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 6.3 adds code ONLY to `scm/branch.py` and `scm/__init__.py`. The branch module imports from `core/` only (`core/exceptions.py` for `BranchError`, `core/constants.py` for `BRANCH_PREFIX` and `COMMIT_MESSAGE_TEMPLATE`) and from `scm/git.py` for the `git()` wrapper. This is the valid dependency: `scm → core` + internal `scm` imports. No DAG violations.

**Decision 7 — Git Operations Strategy**: Branch naming and commit conventions are explicitly specified:
- Branch naming: `arcwright-ai/<story-slug>` — namespaced, predictable, greppable
- Commit message: `[arcwright-ai] <story-title>\n\nStory: <story-file-path>\nRun: <run-id>`
- No force operations — no `--force`, no `reset --hard`, no rebase. Existing branch → error out
- Push after successful validation — `push_branch()` pushes to remote with merge-ours reconciliation
- All git commands run with `cwd=worktree_path` for commit operations (inside worktree), `cwd=project_root` for branch operations
[Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Decision 7]

**Decision 8 — Structured Logging**: The `git.commit` and `git.branch.create` event types are listed in the D8 event type taxonomy. Log events MUST use structured `extra={"data": {...}}` format. [Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Decision 8]

**Decision 6 — Error Taxonomy**: `BranchError(ScmError)` is the exception for branch-specific failures (branch already exists, checkout failures). It inherits `message: str` and `details: dict[str, Any] | None` from `ArcwrightError`. [Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Decision 6]

**NFR14 — Git 2.25+ Compatibility**: All git commands used must be available in git 2.25 (Ubuntu 20.04 baseline). The commands used in this story (`git branch`, `git add`, `git commit`, `git rev-parse`) are all available in git 2.25+. No newer features required.

**NFR19 — Idempotency**: `delete_branch` for a non-existent branch must be a no-op.

**Boundary 4 — Application ↔ File System**: All git operations go through `scm/git.py` — no subprocess calls from other packages. The `branch.py` module calls `git()` from `scm/git.py` — never uses `subprocess` directly.

### Current State Analysis — What Already Exists

1. **`scm/branch.py`** — Stub file with docstring `"SCM branch — Branch management and commit strategy."` and empty `__all__`. Implementation goes here.

2. **`scm/__init__.py`** — Package init with `GitResult`, `git`, `create_worktree`, `remove_worktree`, `list_worktrees` in `__all__`. This story adds the branch functions to the public API.

3. **`scm/git.py`** — FULLY IMPLEMENTED in Story 6.1. Provides:
   - `GitResult(ArcwrightModel)` — frozen Pydantic model with `stdout`, `stderr`, `returncode`, `success` property.
   - `async def git(*args: str, cwd: Path | None = None) -> GitResult` — sole gateway for all git subprocess calls.
   - Raises `ScmError` on non-zero exit with error classification (lock contention with retry, permission denied, not-a-repo).
   - USE THIS — call `git()` for all git operations. Do NOT use `asyncio.create_subprocess_exec` directly.

4. **`scm/worktree.py`** — FULLY IMPLEMENTED in Story 6.2. Provides:
   - `create_worktree(story_slug, base_ref, *, project_root) → Path` — creates worktree AND branch (`git worktree add -b arcwright/<slug>`).
   - `remove_worktree(story_slug, *, project_root, delete_branch=False) → None` — removes worktree with optional branch deletion.
   - `list_worktrees(*, project_root) → list[str]` — lists active arcwright worktrees.
   - Note: `create_worktree` already creates branches as part of `git worktree add -b`. Story 6.3's `create_branch` is a STANDALONE branch creation for use outside the worktree workflow.

5. **`BranchError`** in `core/exceptions.py` — Already defined as `ScmError` subclass: `"Raised when a branch already exists or checkout fails."` Has `message: str` and `details: dict[str, Any] | None` from `ArcwrightError` base. USE THIS — do NOT create a new exception.

6. **`core/constants.py`** — Already defines:
   - `BRANCH_PREFIX = "arcwright-ai/"`
   - `COMMIT_MESSAGE_TEMPLATE = "[arcwright-ai] {story_title}\n\nStory: {story_path}\nRun: {run_id}"`
   USE THESE constants — do NOT hardcode strings.

7. **`tests/test_scm/`** — Directory exists with `__init__.py`, `.gitkeep`, `test_git.py` (from 6.1), `test_worktree.py` and `test_worktree_integration.py` (from 6.2). Create `test_branch.py` and `test_branch_integration.py` here.

8. **`tests/conftest.py`** — Has `tmp_project` fixture that scaffolds `.arcwright-ai/` and `_spec/` directories. Use for tests that need project directory structure.

### Existing Code to Reuse — DO NOT REINVENT

- **`git()`** from `scm/git.py` — CALL for all git operations. Do NOT use subprocess directly.
- **`BranchError`** from `core/exceptions.py` — RAISE for branch-specific failures. `ScmError` for git-level failures is handled by `git()` function internally.
- **`BRANCH_PREFIX`** from `core/constants.py` — USE for all branch name construction.
- **`COMMIT_MESSAGE_TEMPLATE`** from `core/constants.py` — USE for commit message formatting.
- **`logging.getLogger(__name__)`** pattern — REUSE from `scm/git.py` and `scm/worktree.py`.

### CRITICAL: Relationship Between `create_worktree` and `create_branch`

`create_worktree` in `worktree.py` already creates branches via `git worktree add -b arcwright-ai/<slug>`. The `create_branch` function in `branch.py` is a STANDALONE branch creation utility. In the normal engine flow:
1. `create_worktree()` creates both the worktree AND the branch (Story 6.2)
2. `commit_story()` stages and commits changes inside the worktree (this story)
3. `remove_worktree()` removes the worktree (Story 6.2)

`create_branch()` is used in scenarios outside the worktree flow, such as cleanup, testing, or future non-worktree execution modes. Do NOT call `create_branch` during the normal worktree-based execution flow — the worktree creation already handles branch creation.

### CRITICAL: `commit_story` Runs INSIDE the Worktree

The `commit_story` function operates with `cwd=worktree_path`. This means:
- `git add .` stages files in the worktree's working directory only
- `git commit` creates a commit on the worktree's branch (automatically `arcwright-ai/<story-slug>`)
- The `.arcwright-ai/` directory at the project root is NOT in scope of the worktree's `git add .`
- No files from the main working tree are affected

### CRITICAL: Detecting "Nothing to Commit"

When `git commit` is called with no staged changes, git exits with non-zero status and stderr contains "nothing to commit" or "nothing added to commit". The `git()` wrapper will raise `ScmError`. Detect this pattern in the stderr and raise `BranchError` with a clear message instead. Example stderr patterns:
- `"nothing to commit, working tree clean"`
- `"nothing to commit (create/copy files and use \"git add\" to track)"`
- `"nothing added to commit but untracked files present"`

### CRITICAL: `branch_exists` Uses `refs/heads/` Prefix

When checking if a branch exists with `git rev-parse --verify`, use `refs/heads/<branch_name>` to ensure only local branches are matched (not remote tracking branches or tags). Example:
```python
await git("rev-parse", "--verify", f"refs/heads/{branch_name}", cwd=project_root)
```

### CRITICAL: `list_branches` Output Parsing

`git branch --list "arcwright-ai/*"` outputs lines like:
```
  arcwright-ai/story-1
* arcwright-ai/story-2
  arcwright-ai/story-3
```

The current branch is marked with `* `. Strip the leading `  ` or `* ` from each line. Filter out empty lines.

### CRITICAL: `delete_branch` Safe vs Force Delete

- `-d` (safe): Only deletes if the branch is fully merged into its upstream or HEAD. Fails with "not fully merged" for unmerged branches.
- `-D` (force): Deletes regardless of merge status.

The `force=False` default ensures safety. The `force=True` option is needed by Story 6.5's cleanup command (`arcwright clean --all` removes ALL arcwright branches including unmerged).

### Mocking Strategy for Unit Tests

Mock `scm.git.git` at the callsite in `branch.py`. Since `branch.py` imports `git` from `scm.git`:

```python
from arcwright_ai.scm.git import git
```

The mock should be:
```python
monkeypatch.setattr("arcwright_ai.scm.branch.git", mock_git)
```

Where `mock_git` is an `AsyncMock`. Configure side effects per call to simulate different git operations.

For `branch_exists` calls within `create_branch` and `delete_branch`, you may need to either:
1. Mock `branch_exists` directly: `monkeypatch.setattr("arcwright_ai.scm.branch.branch_exists", mock_branch_exists)`
2. Or configure the `git` mock to handle `rev-parse --verify` calls appropriately.

Option 1 is cleaner for unit tests since it isolates the function under test.

### Integration Tests with Real Git

Integration tests use `tmp_path` to create real git repos. Reuse or mirror the `git_repo` fixture pattern from `test_worktree_integration.py`:

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
    (tmp_path / ".arcwright-ai" / "worktrees").mkdir(parents=True)
    return tmp_path
```

For `commit_story` integration tests, create a worktree first (using `create_worktree`), then write a file in the worktree, then call `commit_story`. Verify the commit exists in `git log --oneline`.

Mark all integration tests with `@pytest.mark.slow`.

### Relationship to Other Stories in Epic 6

- **Story 6.1 (done):** Foundation — the `git()` wrapper this story calls for all operations.
- **Story 6.2 (done):** Worktree lifecycle — `create_worktree`, `remove_worktree`, `list_worktrees`. Worktree creation already creates branches via `git worktree add -b`.
- **Story 6.3 (this):** Branch manager — `create_branch`, `commit_story`, `branch_exists`, `list_branches`, `delete_branch`. Standalone branch operations + commit strategy inside worktrees.
- **Story 6.4:** `scm/pr.py` — PR body generator. Reads provenance, generates PR body. No direct branch interaction; consumes `commit_story` output (commit hash) indirectly.
- **Story 6.5:** `cli/clean.py` — cleanup command. Calls `list_branches()` and `delete_branch()` from this story for branch cleanup.
- **Story 6.6:** Engine node integration — `commit` node calls `commit_story()` from this story after validation passes, then `remove_worktree()` from 6.2.

### Project Structure Notes

- Implementation file: `src/arcwright_ai/scm/branch.py` (currently a stub)
- Package exports updated: `src/arcwright_ai/scm/__init__.py`
- Unit tests: `tests/test_scm/test_branch.py` (new file)
- Integration tests: `tests/test_scm/test_branch_integration.py` (new file)
- No new files in `core/` — all constants and exceptions already exist

### References

- [Source: architecture.md — Decision 7 (Git Operations Strategy)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Decision 6 (Error Handling Taxonomy)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Decision 8 (Logging & Observability)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Package Dependency DAG](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Implementation Patterns](../../_spec/planning-artifacts/architecture.md)
- [Source: epics.md — Epic 6 Story 6.3](../../_spec/planning-artifacts/epics.md)
- [Source: story 6-1](6-1-git-subprocess-wrapper-safe-shell-out-foundation.md) — git() wrapper foundation
- [Source: story 6-2](6-2-worktree-manager-atomic-create-delete-with-recovery.md) — worktree manager patterns and code conventions

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- `commit_story` initially detected "nothing to commit" by checking `ScmError.message` and `details["stderr"]`. However, in git 2.25+ the message goes to **stdout** (not stderr). Fixed by inserting a `git status --porcelain` pre-check after `git add .` — raises `BranchError` immediately if output is empty.

### Completion Notes List

- Implemented all 5 public functions in `scm/branch.py`: `branch_exists`, `create_branch`, `commit_story`, `list_branches`, `delete_branch`.
- All functions use `scm.git.git()` exclusively — no direct subprocess calls.
- `BRANCH_PREFIX` and `COMMIT_MESSAGE_TEMPLATE` constants used from `core/constants.py`.
- `BranchError` from `core/exceptions.py` used for all branch-specific failures.
- Structured logging via `logger.info(event_name, extra={"data": {...}})` on all success paths and no-ops.
- `delete_branch` is idempotent: pre-checks with `branch_exists()`, no-op logs when branch absent.
- `create_branch` guards against duplicate branches via `branch_exists()` pre-check.
- 18 unit tests (all async, all passing) + 8 integration tests with real git (all passing).
- All quality gates passed: ruff check, ruff format, mypy --strict, 629 non-slow + 8 slow tests.
- Post-review remediation applied: added structured `logger.error` events with full context for create/commit/delete failure paths and no-change commit errors.
- Post-review remediation applied: `branch_exists` now returns `False` only for branch-missing cases and re-raises non-not-found SCM failures.
- Post-review remediation applied: added unit test coverage for non-not-found `branch_exists` error propagation.

### File List

- `arcwright-ai/src/arcwright_ai/scm/branch.py`
- `arcwright-ai/src/arcwright_ai/scm/__init__.py`
- `arcwright-ai/tests/test_scm/test_branch.py`
- `arcwright-ai/tests/test_scm/test_branch_integration.py`
- `_spec/implementation-artifacts/sprint-status.yaml`

## Senior Developer Review (AI)

### Review Date

- 2026-03-07

### Outcome

- Changes Requested findings resolved.
- HIGH/MEDIUM findings fixed in code and story documentation.
- Verified with targeted gates:
  - `pytest tests/test_scm/test_branch.py -q`
  - `pytest tests/test_scm/test_branch_integration.py -q -m slow`
  - `ruff check src/arcwright_ai/scm/branch.py tests/test_scm/test_branch.py tests/test_scm/test_branch_integration.py`
  - `.venv/bin/python -m mypy --strict src/arcwright_ai/scm/branch.py`

## Change Log

- 2026-03-07: Story 6.3 implemented — `scm/branch.py` fully implemented with `branch_exists`, `create_branch`, `commit_story`, `list_branches`, `delete_branch`; `scm/__init__.py` updated with re-exports; 18 unit tests + 8 integration tests added; all quality gates passed.
- 2026-03-07: Code review fixes applied — added structured error logging on branch/commit failure paths, tightened `branch_exists` error handling to avoid masking non-not-found SCM failures, added unit test for propagation behavior, synced story status and sprint status to done.
