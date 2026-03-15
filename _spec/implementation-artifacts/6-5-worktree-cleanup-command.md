# Story 6.5: Worktree Cleanup Command

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer managing disk space after multiple runs,
I want a cleanup command that removes stale worktrees and branches,
so that completed run artifacts don't accumulate indefinitely.

## Acceptance Criteria (BDD)

1. **Given** `cli/clean.py` implementing the `arcwright-ai clean` command **When** the developer runs `arcwright-ai clean` (no flags) **Then** completed worktrees (whose branches are fully merged into HEAD) are removed **And** merged arcwright-namespaced branches are deleted using safe deletion (`git branch -d`).

2. **Given** the developer runs `arcwright-ai clean --all` **When** any arcwright-managed worktrees or branches exist **Then** ALL arcwright-namespaced worktrees are removed regardless of merge status **And** ALL arcwright-namespaced branches are force-deleted (`git branch -D`) including failed/stale.

3. **Given** cleanup is always user-initiated per D7 **When** any dispatch, commit, or engine operation completes **Then** no automatic cleanup occurs — no lazy cleanup on dispatch, no post-merge hooks in MVP.

4. **Given** all cleanup operations **When** cleaning an already-clean state (no worktrees, no arcwright branches) **Then** the operation is a no-op and reports "Nothing to clean" per NFR19 **And** running cleanup twice in succession produces the same result (idempotent).

5. **Given** cleanup completes **When** one or more items were removed **Then** stdout reports what was cleaned: e.g., "Removed 3 worktrees, deleted 3 branches" **And** when nothing was cleaned: "Nothing to clean".

6. **Given** cleanup runs **When** no network is available **Then** cleanup succeeds because all operations are local git commands (NFR20).

7. **Given** integration tests with real git **When** the test suite runs **Then** tests cover: create worktrees → run default cleanup (only merged removed) → verify removal → run cleanup again (verify idempotent no-op) **And** create worktrees → run `--all` cleanup → verify all removed including unmerged.

8. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

9. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

10. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

11. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 657 existing tests continue to pass.

12. **Given** partial cleanup failure (e.g., one worktree removal fails) **When** the clean command is running **Then** remaining items are still cleaned (best-effort, not all-or-nothing) **And** warnings are logged for each skipped item **And** the command still reports the partial results.

## Tasks / Subtasks

- [x] Task 1: Create `cli/clean.py` with `_list_merged_branches` helper (AC: #1, #2)
  - [x] 1.1: Create module `src/arcwright_ai/cli/clean.py` with module docstring following existing CLI module patterns.
  - [x] 1.2: Implement `async def _list_merged_branches(*, project_root: Path) -> set[str]` — calls `git("branch", "--merged", cwd=project_root)`, parses output, returns only branches starting with `BRANCH_PREFIX` ("arcwright/").
  - [x] 1.3: Add `logger = logging.getLogger(__name__)` (yields `arcwright_ai.cli.clean`).
  - [x] 1.4: Define `__all__: list[str] = ["clean_command"]`.

- [x] Task 2: Implement `_clean_default` async function (AC: #1, #4, #5, #12)
  - [x] 2.1: `async def _clean_default(project_root: Path) -> tuple[int, int]` — returns `(worktrees_removed, branches_deleted)`.
  - [x] 2.2: Call `_list_merged_branches(project_root=project_root)` to get the set of merged arcwright branch names.
  - [x] 2.3: Call `list_worktrees(project_root=project_root)` to get all active worktree slugs.
  - [x] 2.4: For each worktree slug whose branch (`arcwright-ai/<slug>`) is in the merged set: call `remove_worktree(slug, project_root=project_root)` (without `delete_branch=True`). Catch `WorktreeError`, log warning, skip to next. Increment `worktrees_removed` on success.
  - [x] 2.5: After worktree removal pass, call `list_branches(project_root=project_root)` to get remaining arcwright branches.
  - [x] 2.6: For each branch in the merged set: call `delete_branch(branch_name, project_root=project_root, force=False)`. Catch `BranchError`, log warning, skip. Increment `branches_deleted` on success.
  - [x] 2.7: Log completion as `clean.default` structured event with worktrees_removed, branches_deleted.

- [x] Task 3: Implement `_clean_all` async function (AC: #2, #4, #5, #12)
  - [x] 3.1: `async def _clean_all(project_root: Path) -> tuple[int, int]` — returns `(worktrees_removed, branches_deleted)`.
  - [x] 3.2: Call `list_worktrees(project_root=project_root)`, remove each with `remove_worktree(slug, project_root=project_root)` (no `delete_branch=True` — handle branches in a separate pass for accurate counting). Catch `WorktreeError`, log warning, skip.
  - [x] 3.3: After worktree removal, call `list_branches(project_root=project_root)` to get remaining arcwright branches.
  - [x] 3.4: For each branch: call `delete_branch(branch_name, project_root=project_root, force=True)`. Catch `BranchError`, log warning, skip. Increment `branches_deleted` on success.
  - [x] 3.5: Log completion as `clean.all` structured event.

- [x] Task 4: Implement `clean_command` Typer function (AC: #1, #2, #3, #4, #5, #6)
  - [x] 4.1: `def clean_command(all_: Annotated[bool, typer.Option("--all", help="...")] = False, project_root: Annotated[Path | None, typer.Option("--project-root", ...)] = None) -> None`.
  - [x] 4.2: Resolve `project_root` to `Path.cwd()` when `None`.
  - [x] 4.3: Wrap async call with `asyncio.run()` — call `_clean_all` if `all_` else `_clean_default`.
  - [x] 4.4: Catch `ScmError` at boundary → `typer.echo(f"Error: {exc.message}", err=True)` + `raise typer.Exit(code=EXIT_SCM)`.
  - [x] 4.5: Report results: "Nothing to clean" when both counts are 0; otherwise "Removed N worktree(s), deleted M branch(es)".
  - [x] 4.6: Google-style docstring with parameter descriptions.

- [x] Task 5: Register `clean` command in `cli/app.py` (AC: #1)
  - [x] 5.1: Add `from arcwright_ai.cli.clean import clean_command` import.
  - [x] 5.2: Add `app.command(name="clean")(clean_command)` registration.

- [x] Task 6: Create unit tests in `tests/test_cli/test_clean.py` (AC: #1, #2, #4, #5, #11, #12)
  - [x] 6.1: Test `test_clean_default_removes_merged_worktrees_and_branches` — mock `_list_merged_branches` returning one merged branch, mock `list_worktrees` returning matching slug, verify `remove_worktree` and `delete_branch(force=False)` called.
  - [x] 6.2: Test `test_clean_default_skips_unmerged_worktrees` — mock `_list_merged_branches` returning empty set, mock `list_worktrees` returning slug, verify `remove_worktree` NOT called.
  - [x] 6.3: Test `test_clean_default_cleans_orphaned_merged_branches` — branches exist but no worktrees, verify `delete_branch(force=False)` called for merged branches.
  - [x] 6.4: Test `test_clean_all_removes_all_worktrees_and_branches` — mock `list_worktrees` and `list_branches`, verify `remove_worktree` and `delete_branch(force=True)` called for all.
  - [x] 6.5: Test `test_clean_nothing_to_clean` — empty worktrees and branches, verify output "Nothing to clean".
  - [x] 6.6: Test `test_clean_idempotent_second_run_is_noop` — first clean removes items, second clean finds nothing → "Nothing to clean".
  - [x] 6.7: Test `test_clean_partial_failure_continues` — mock `remove_worktree` to raise `WorktreeError` on first slug but succeed on second, verify second is still cleaned and partial result reported.
  - [x] 6.8: Test `test_clean_reports_correct_counts` — verify output string format matches "Removed N worktree(s), deleted M branch(es)".
  - [x] 6.9: Test `test_clean_scm_error_exits_with_code_4` — mock to raise `ScmError`, verify `typer.Exit(code=4)`.
  - [x] 6.10: Test `test_clean_default_logs_structured_events` — verify `clean.default` log event emitted with counts.
  - [x] 6.11: Test `test_clean_all_logs_structured_events` — verify `clean.all` log event emitted.
  - [x] 6.12: All test functions use `@pytest.mark.asyncio` for async tests OR typer `CliRunner` for integration-style CLI tests.

- [x] Task 7: Create integration tests in `tests/test_scm/test_clean_integration.py` (AC: #7, #11)
  - [x] 7.1: Reuse `git_repo` fixture pattern from `test_worktree_integration.py` — real git init, initial commit, `.arcwright-ai/worktrees/` directory.
  - [x] 7.2: Test `test_clean_default_removes_merged_worktree_integration` — create worktree, merge its branch into main, run `_clean_default`, verify worktree directory gone and branch deleted.
  - [x] 7.3: Test `test_clean_default_preserves_unmerged_worktree_integration` — create worktree with unmerged changes, run `_clean_default`, verify worktree and branch still exist.
  - [x] 7.4: Test `test_clean_all_removes_everything_integration` — create multiple worktrees (some merged, some not), run `_clean_all`, verify all worktrees and branches removed.
  - [x] 7.5: Test `test_clean_idempotent_integration` — run cleanup, then run cleanup again, verify no errors and "Nothing to clean" equivalent (zero counts returned).
  - [x] 7.6: Mark all with `@pytest.mark.slow` and `@pytest.mark.asyncio`.

- [x] Task 8: Run quality gates (AC: #8, #9, #10, #11)
  - [x] 8.1: `ruff check .` — zero violations against FULL repository.
  - [x] 8.2: `ruff format --check .` — zero formatting issues.
  - [x] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 8.4: `pytest` — all tests pass (657 existing + 19 new clean tests = 676 total).
  - [x] 8.5: Verify Google-style docstrings on all public functions.
  - [x] 8.6: Verify `git diff --name-only` and untracked files; reconcile Dev Agent Record file list.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 6.5 adds a new CLI module `cli/clean.py` that imports from `scm/` (for `list_worktrees`, `remove_worktree`, `list_branches`, `delete_branch`) and `scm/git.py` (for the `git` wrapper to query merged branches). This is valid: `cli → scm → core`. No DAG violations. The `cli/clean.py` module does NOT import from `engine/`, `output/`, `agent/`, or `context/`. [Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Package Dependency DAG]

**Decision 7 — Git Operations Strategy**: Cleanup is always user-initiated. No automatic cleanup on dispatch, no post-merge hooks in MVP. The `arcwright clean` command has two modes: default (merged-only) and `--all` (force remove everything). All git operations go through the `scm/git.py` wrapper — `cli/clean.py` never calls subprocess directly. [Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Decision 7]

**Decision 6 — Error Handling**: `ScmError` is the parent exception for all SCM failures. `WorktreeError(ScmError)` for worktree removal failures, `BranchError(ScmError)` for branch deletion failures. CLI layer catches `ScmError` → maps to exit code 4 (`EXIT_SCM`). Individual worktree/branch failures during cleanup are caught as warnings (best-effort, not all-or-nothing). [Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Decision 6]

**Decision 8 — Logging & Observability**: Structured logging with `logger = logging.getLogger(__name__)` and `extra={"data": {...}}` event format. Event types for this story: `clean.default` (success summary), `clean.all` (success summary), `clean.worktree.skip` (warning when worktree removal fails), `clean.branch.skip` (warning when branch deletion fails). [Source: [architecture.md](../../_spec/planning-artifacts/architecture.md) — Decision 8]

**NFR19 — Idempotency**: Cleanup must produce identical state on repeated execution. `remove_worktree` is already idempotent (no-op when directory absent). `delete_branch` is already idempotent (no-op when branch absent). `_list_merged_branches` returns empty set when no arcwright branches exist. Running `arcwright clean` twice → first pass cleans, second pass finds nothing → "Nothing to clean".

**NFR20 — Offline Operation**: All git operations are local. No push, no remote queries, no network required. `git branch --merged`, `git worktree list`, `git worktree remove`, `git branch -d/-D` are all local operations.

### Determining "Completed" for Default Mode

Default mode removes "completed worktrees + merged branches". The definition of "completed" is: **the worktree's corresponding branch is fully merged into HEAD**. This is determined by:

1. Query `git branch --merged` (returns branches merged into current HEAD)
2. Filter for arcwright-namespaced branches (`arcwright-ai/*`)
3. Any worktree whose branch appears in this set is "completed"

This approach works because:
- When Story 6.6 integrates SCM with engine nodes, the commit node will commit changes inside the worktree, then the worktree may or may not be removed depending on the engine flow
- A merged branch means the story's work has been incorporated into the main line
- An unmerged branch means the story's work is still isolated — cleanup should preserve it in default mode

### Key Implementation Decisions

1. **Separate worktree removal and branch deletion passes**: Remove worktrees first (via `remove_worktree` without `delete_branch=True`), then delete branches in a second pass. This ensures accurate counting and avoids the `contextlib.suppress(ScmError)` in `remove_worktree`'s `delete_branch=True` path that silently swallows errors.

2. **Branch deletion must happen AFTER worktree removal**: Git refuses to delete a branch that is checked out in a worktree. Worktree removal frees the branch for deletion.

3. **Default mode uses `force=False` for `delete_branch`**: This maps to `git branch -d`, which only succeeds for fully merged branches. If a branch appears in `git branch --merged` but deletion still fails (race condition), the error is caught and logged as a warning.

4. **`--all` mode uses `force=True` for `delete_branch`**: This maps to `git branch -D`, which deletes regardless of merge status.

5. **`_list_merged_branches` uses `git branch --merged` directly**: This is called via the `git()` wrapper, not via `list_branches()`. The `list_branches()` function in `branch.py` lists all arcwright branches but does not filter by merge status. A new private helper in `cli/clean.py` is needed.

### Existing Code to Reuse — DO NOT REINVENT

- **`list_worktrees(project_root=)`** from `scm/worktree.py` — returns sorted list of story slugs for active arcwright worktrees. Already implemented in Story 6.2. [Source: scm/worktree.py]
- **`remove_worktree(story_slug, project_root=, delete_branch=False)`** from `scm/worktree.py` — idempotent removal. Already implemented in Story 6.2. [Source: scm/worktree.py]
- **`list_branches(project_root=)`** from `scm/branch.py` — returns sorted list of all `arcwright-ai/*` branch names. Already implemented in Story 6.3. [Source: scm/branch.py]
- **`delete_branch(branch_name, project_root=, force=False)`** from `scm/branch.py` — idempotent deletion, `force=False` uses `-d` (merged-only), `force=True` uses `-D`. Already implemented in Story 6.3. [Source: scm/branch.py]
- **`git(*args, cwd=)`** from `scm/git.py` — the single gateway for all git subprocess calls. Already implemented in Story 6.1. [Source: scm/git.py]
- **`BRANCH_PREFIX`** from `core/constants.py` — `"arcwright-ai/"`. [Source: core/constants.py]
- **`EXIT_SCM`** from `core/constants.py` — exit code `4`. [Source: core/constants.py]
- **`EXIT_SUCCESS`** from `core/constants.py` — exit code `0`. [Source: core/constants.py]
- **`ScmError`, `WorktreeError`, `BranchError`** from `core/exceptions.py`. [Source: core/exceptions.py]

### CRITICAL: CLI Command Registration Pattern

Follow the exact pattern used by existing commands in `cli/app.py`:

```python
from arcwright_ai.cli.clean import clean_command
app.command(name="clean")(clean_command)
```

The command function uses Typer annotations for arguments:
```python
def clean_command(
    all_: Annotated[bool, typer.Option("--all", help="...")] = False,
    project_root: Annotated[Path | None, typer.Option("--project-root", ...)] = None,
) -> None:
```

Note: `all_` (not `all`) because `all` is a Python builtin. Typer maps `all_` to the `--all` CLI flag via the `typer.Option("--all", ...)` annotation.

### CRITICAL: Async Wrapping Pattern

The `clean_command` Typer function is synchronous (Typer does not natively support async). Async operations are wrapped with `asyncio.run()`:

```python
def clean_command(...) -> None:
    resolved_root = project_root or Path.cwd()
    try:
        worktrees_removed, branches_deleted = asyncio.run(
            _clean_all(resolved_root) if all_ else _clean_default(resolved_root)
        )
    except ScmError as exc:
        typer.echo(f"Error: {exc.message}", err=True)
        raise typer.Exit(code=EXIT_SCM) from exc
```

This matches the pattern used in `cli/dispatch.py` where `asyncio.run()` wraps the async engine pipeline.

### CRITICAL: `git branch --merged` Output Format

Output of `git branch --merged` uses the same format as `git branch`:
```
* main
  arcwright/story-a
  arcwright/story-b
  feature/unrelated
```

- Leading `* ` marks the current branch
- Leading `  ` for other branches
- Parse by stripping `* ` and whitespace, then filter by `BRANCH_PREFIX`

### CRITICAL: Worktree Must Be Removed Before Branch Deletion

Git will refuse to delete a branch that is checked out in a worktree:
```
error: Cannot delete branch 'arcwright/my-story' checked out at '/path/to/worktree'
```

The implementation MUST remove the worktree first, then delete the branch. This is why the two-pass approach (remove worktrees → delete branches) is architecturally necessary.

### Mocking Strategy for Unit Tests

For unit tests in `tests/test_cli/test_clean.py`, mock the SCM functions at their callsite in `cli/clean.py`:

```python
monkeypatch.setattr("arcwright_ai.cli.clean.list_worktrees", mock_list_worktrees)
monkeypatch.setattr("arcwright_ai.cli.clean.remove_worktree", mock_remove_worktree)
monkeypatch.setattr("arcwright_ai.cli.clean.list_branches", mock_list_branches)
monkeypatch.setattr("arcwright_ai.cli.clean.delete_branch", mock_delete_branch)
monkeypatch.setattr("arcwright_ai.cli.clean.git", mock_git)
```

For `_list_merged_branches`, it calls `git()` directly, so mock `git` at `arcwright_ai.cli.clean.git`.

For the CLI entry point test, use Typer's `CliRunner`:
```python
from typer.testing import CliRunner
from arcwright_ai.cli.app import app

runner = CliRunner()
result = runner.invoke(app, ["clean"])
assert result.exit_code == 0
assert "Nothing to clean" in result.output
```

### Integration Test Fixtures

Reuse the `git_repo` fixture pattern from `test_worktree_integration.py`:

```python
@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    await git("init", cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=tmp_path)
    await git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# Test")
    await git("add", ".", cwd=tmp_path)
    await git("commit", "-m", "Initial commit", cwd=tmp_path)
    (tmp_path / DIR_ARCWRIGHT / DIR_WORKTREES).mkdir(parents=True)
    return tmp_path
```

To create a "merged" worktree for testing:
1. Create worktree + branch
2. Write a file in worktree, add + commit
3. Switch to main, merge the arcwright branch (`git merge arcwright-ai/<slug>`)
4. Now `git branch --merged` will include `arcwright-ai/<slug>`
5. Run cleanup — should remove worktree + delete branch

To create an "unmerged" worktree:
1. Create worktree + branch
2. Write a file in worktree, add + commit (but don't merge into main)
3. Now `git branch --merged` will NOT include `arcwright-ai/<slug>`
4. Default cleanup should SKIP it; `--all` cleanup should REMOVE it

### Relationship to Other Stories in Epic 6

- **Story 6.1 (done):** Foundation — the `git()` wrapper. Used by `_list_merged_branches`.
- **Story 6.2 (done):** Worktree lifecycle — `create_worktree`, `remove_worktree`, `list_worktrees`. Core dependencies for cleanup.
- **Story 6.3 (done):** Branch manager — `list_branches`, `delete_branch`, `branch_exists`. Core dependencies for cleanup.
- **Story 6.4 (done):** PR body generator. No interaction with this story.
- **Story 6.5 (this):** Cleanup command. Consumes APIs from 6.1, 6.2, 6.3.
- **Story 6.6 (next):** Engine node integration. Will wire SCM operations into the LangGraph pipeline. May call cleanup indirectly but per D7, cleanup is NEVER automatic.

### Previous Story Intelligence (6-4)

From Story 6-4 (PR Body Generator with Provenance Embedding):
- All async functions follow `async def` pattern with `@pytest.mark.asyncio` test decorators
- Logging uses `logger = logging.getLogger(__name__)` with `extra={"data": {...}}` structured events
- `monkeypatch.setattr()` used for mocking — mock at the callsite, not the source module
- `ScmError` and `BranchError` carry `details` dicts for structured error context
- Integration tests use real git repos via `git_repo(tmp_path)` fixture
- Quality gates: `ruff check .`, `ruff format --check .`, `mypy --strict src/`, `pytest` all pass at 657 tests
- B904 ruff error pattern: when re-raising exceptions, use `raise XError(...) from exc`
- Google-style docstrings required on all public functions with Args, Returns, Raises sections

### Git Operations Compatibility

- All commands compatible with Git 2.25+ per NFR14
- `git branch --merged` available since Git 1.7.10 — well within requirement
- `git worktree list --porcelain` available since Git 2.7 — well within requirement
- `git worktree remove` available since Git 2.17 — well within requirement

### Project Structure Notes

- **New file**: `src/arcwright_ai/cli/clean.py` — cleanup command implementation
- **Modified file**: `src/arcwright_ai/cli/app.py` — register `clean` command
- **New file**: `tests/test_cli/test_clean.py` — unit tests
- **New file**: `tests/test_scm/test_clean_integration.py` — integration tests with real git
- No new files in `core/` — all constants, exceptions, and utilities already exist
- No changes to `scm/` package — all needed functions are already exported

### References

- [Source: architecture.md — Decision 7 (Git Operations Strategy)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Decision 6 (Error Handling Taxonomy)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Decision 8 (Logging & Observability)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Package Dependency DAG](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Worktree Isolation as Security Model](../../_spec/planning-artifacts/architecture.md)
- [Source: epics.md — Epic 6 Story 6.5](../../_spec/planning-artifacts/epics.md)
- [Source: epics.md — FR7, NFR19, NFR20](../../_spec/planning-artifacts/epics.md)
- [Source: story 6-4](6-4-pr-body-generator-with-provenance-embedding.md) — PR body generator patterns and conventions
- [Source: scm/worktree.py](../../arcwright-ai/src/arcwright_ai/scm/worktree.py) — worktree lifecycle operations
- [Source: scm/branch.py](../../arcwright-ai/src/arcwright_ai/scm/branch.py) — branch management operations
- [Source: scm/git.py](../../arcwright-ai/src/arcwright_ai/scm/git.py) — git subprocess wrapper
- [Source: core/constants.py](../../arcwright-ai/src/arcwright_ai/core/constants.py) — path and exit code constants
- [Source: core/exceptions.py](../../arcwright-ai/src/arcwright_ai/core/exceptions.py) — exception hierarchy
- [Source: cli/app.py](../../arcwright-ai/src/arcwright_ai/cli/app.py) — command registration pattern
- [Source: test_worktree_integration.py](../../arcwright-ai/tests/test_scm/test_worktree_integration.py) — integration test fixture pattern

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Discovered `git branch --merged` uses `+` prefix (not two spaces) for branches checked out in linked worktrees. Fixed `_list_merged_branches` to `lstrip("*+ ")` instead of `lstrip("* ")`. Without this fix all integration tests for default-mode cleanup failed with `worktrees == 0`.

### Completion Notes List

- Implemented `src/arcwright_ai/cli/clean.py` with `_list_merged_branches`, `_clean_default`, `_clean_all`, and `clean_command` following all task specifications.
- Registered `clean` command first in `cli/app.py` command list.
- Wrote 15 unit tests in `tests/test_cli/test_clean.py` covering all ACs; includes a dedicated test for the `+` prefix worktree branch detection.
- Wrote 4 integration tests in `tests/test_scm/test_clean_integration.py` with real git repos covering merged/unmerged/all/idempotent scenarios.
- All 676 tests pass (657 pre-existing + 19 new). Zero ruff, ruff-format, or mypy --strict violations.
- Key implementation decision: `_list_merged_branches` must strip `*`, `+`, and spaces from `git branch --merged` output — the `+` prefix marks branches checked out in linked worktrees (standard git behavior since 2.5.0).

### File List

- `src/arcwright_ai/cli/clean.py` (new)
- `src/arcwright_ai/cli/app.py` (modified)
- `tests/test_cli/test_clean.py` (new)
- `tests/test_scm/test_clean_integration.py` (new)

## Change Log

- 2026-03-08: Implemented Story 6.5 — `arcwright-ai clean` command with default (merged-only) and `--all` (force) modes. 19 new tests added. All quality gates pass.
- 2026-03-08: Senior Developer Review (AI) completed. Resolved findings and promoted status to done.

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted code review workflow)

### Date

2026-03-08

### Outcome

Approved

### Findings

1. **MEDIUM**: `tests/test_scm/test_clean_integration.py` referenced private module functions (`_clean_default`, `_clean_all`), which triggered private-usage diagnostics and reduced API-boundary clarity.
  - **Fix applied**: Added public wrappers `clean_default` and `clean_all` in `src/arcwright_ai/cli/clean.py`, exported via `__all__`, and updated integration tests to use public APIs.

2. **LOW**: Story completion claims required full quality-gate evidence.
  - **Verification completed**: `ruff check .`, `ruff format --check .`, `.venv/bin/python -m mypy --strict src/`, and `pytest -q` all pass.

3. **LOW**: Git/story transparency needed explicit review-time reconciliation.
  - **Fix applied**: Review record and status synchronization updated in story + sprint tracker.

### Validation Evidence

- `pytest -q tests/test_cli/test_clean.py tests/test_scm/test_clean_integration.py` → 19 passed
- `ruff check src/arcwright_ai/cli/clean.py tests/test_cli/test_clean.py tests/test_scm/test_clean_integration.py` → passed
- `.venv/bin/python -m mypy --strict src/arcwright_ai/cli/clean.py` → passed
- `ruff check .` and `ruff format --check .` → passed
- `.venv/bin/python -m mypy --strict src/` → passed
- `pytest -q` → 676 passed
