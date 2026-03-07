# Story 6.1: Git Subprocess Wrapper — Safe Shell-Out Foundation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system maintainer,
I want all git operations to flow through a single async subprocess wrapper,
so that git interactions are consistent, logged, and error-handled in one place.

## Acceptance Criteria (BDD)

1. **Given** `scm/git.py` module with a single entry point **When** any part of the system needs to execute a git command **Then** it calls `async def git(*args: str, cwd: Path | None = None) → GitResult(stdout, stderr, returncode)` **And** the function is the sole gateway for all git subprocess invocations in the codebase.

2. **Given** any git command executed via the wrapper **When** the command completes **Then** every command and its result are logged to the structured logger with event type `git.command` per D8 — the log entry includes the full command args, `cwd`, `stdout`, `stderr`, and `returncode` in the `data` dict.

3. **Given** a git command that returns a non-zero exit code **When** the result is received **Then** `ScmError` is raised with `message` containing the command and stderr summary, and `details` dict containing `command` (list[str]), `stderr` (str), and `returncode` (int).

4. **Given** git commands across the entire codebase **When** any module needs to invoke git **Then** all calls go through `scm/git.py` — no `subprocess.run("git ...")` or `asyncio.create_subprocess_exec("git", ...)` anywhere else. This is enforced by code review convention and documented in the module docstring.

5. **Given** a git command that fails due to lock file contention (`.git/index.lock` exists) **When** the error is detected in stderr **Then** the wrapper retries with exponential backoff (0.1s, 0.2s, 0.4s) up to 3 attempts, logging each retry as `git.retry` event. If all retries fail, raises `ScmError` with clear message about lock contention.

6. **Given** a git command that fails due to "permission denied" **When** the error is detected in stderr **Then** raises `ScmError` with a clear, specific message about permission issues — no generic "command failed" messages.

7. **Given** a git command that fails because the `cwd` is not inside a git repository **When** "not a git repository" is detected in stderr **Then** raises `ScmError` with a clear, specific message about the directory not being a git repo.

8. **Given** `GitResult` as the return type **When** inspected **Then** it is a frozen Pydantic model (using `ArcwrightModel` base from `core/types`) with fields: `stdout: str`, `stderr: str`, `returncode: int`. It exposes `success` as a computed `@property` returning `returncode == 0`.

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

13. **Given** new tests in `tests/test_scm/test_git.py` **When** the test suite runs **Then** tests cover:
    (a) Successful git command returns `GitResult` with stdout, stderr, returncode=0;
    (b) Non-zero exit code raises `ScmError` with command, stderr, and returncode in details;
    (c) Structured log output contains full command string and result data for success;
    (d) Structured log output contains error data for failure;
    (e) Lock file contention triggers retry with backoff up to 3 attempts, then raises `ScmError`;
    (f) Permission denied error raises `ScmError` with specific message;
    (g) "Not a git repository" error raises `ScmError` with specific message;
    (h) `cwd` parameter is forwarded to subprocess correctly;
    (i) `GitResult.success` property returns `True` for returncode=0, `False` otherwise;
    (j) `GitResult` is frozen (immutable);
    (k) Successful retry on second attempt after lock contention — verify retry succeeds without raising.

## Tasks / Subtasks

- [x] Task 1: Define `GitResult` Pydantic model in `scm/git.py` (AC: #8)
  - [x] 1.1: Import `ArcwrightModel` base class from `core/types.py` (check if it exists there; if not, it's in a common base — verify location). Use `from pydantic import BaseModel, ConfigDict` with `frozen=True, extra="forbid"` if `ArcwrightModel` is not available.
  - [x] 1.2: Define `GitResult(ArcwrightModel)` with `stdout: str`, `stderr: str`, `returncode: int`.
  - [x] 1.3: Add `@property def success(self) -> bool` returning `self.returncode == 0`.
  - [x] 1.4: Google-style docstring on the class and property.

- [x] Task 2: Implement `async def git()` subprocess wrapper (AC: #1, #3, #4)
  - [x] 2.1: Function signature: `async def git(*args: str, cwd: Path | None = None) -> GitResult`.
  - [x] 2.2: Use `asyncio.create_subprocess_exec("git", *args, cwd=str(cwd) if cwd else None, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)`. Await `proc.communicate()` to get stdout/stderr bytes. Decode with `utf-8`, strip trailing whitespace.
  - [x] 2.3: Construct `GitResult(stdout=..., stderr=..., returncode=proc.returncode)`.
  - [x] 2.4: On non-zero returncode: call `_classify_and_raise(args, cwd, result, attempt, _GIT_LOCK_RETRIES)` (Task 4) which may retry or raise.
  - [x] 2.5: On success: return `GitResult`.
  - [x] 2.6: Google-style docstring with Args, Returns, Raises.

- [x] Task 3: Add structured logging per D8 (AC: #2)
  - [x] 3.1: Create `logger = logging.getLogger(__name__)` (yields `arcwright_ai.scm.git`).
  - [x] 3.2: Log successful commands as: `logger.info("git.command", extra={"data": {"args": list(args), "cwd": str(cwd), "stdout": stdout, "stderr": stderr, "returncode": 0}})`.
  - [x] 3.3: Log failed commands as: `logger.error("git.command", extra={"data": {"args": list(args), "cwd": str(cwd), "stdout": stdout, "stderr": stderr, "returncode": rc}})`.
  - [x] 3.4: Log retries as: `logger.warning("git.retry", extra={"data": {"args": list(args), "attempt": attempt, "max_attempts": max_attempts, "reason": "lock_contention"}})`.

- [x] Task 4: Implement error classification and retry logic (AC: #5, #6, #7)
  - [x] 4.1: Create private `async def _run_git_command(args: tuple[str, ...], cwd: Path | None) -> GitResult` that does the actual subprocess call logic (single attempt — no retry). This is the inner function.
  - [x] 4.2: The public `git()` function wraps `_run_git_command` with retry logic: call it, check if error is retryable (lock contention), retry if so, else raise.
  - [x] 4.3: Lock contention detection: check if `stderr` contains `"index.lock"` or `"Unable to create"` AND `".lock"`.
  - [x] 4.4: Permission denied detection: check if `stderr` contains `"permission denied"` (case-insensitive).
  - [x] 4.5: Not a git repo detection: check if `stderr` contains `"not a git repository"` (case-insensitive).
  - [x] 4.6: Retry backoff: `asyncio.sleep(0.1 * (2 ** attempt))` for attempt 0, 1, 2 → sleeps of 0.1s, 0.2s, 0.4s. Max 3 retries (configurable via `_GIT_LOCK_RETRIES = 3`).
  - [x] 4.7: After exhausting retries for lock contention → raise `ScmError("Git lock file contention after {n} retries", details={"command": list(args), "stderr": stderr, "returncode": rc, "retries": n})`.
  - [x] 4.8: For permission denied → raise `ScmError("Permission denied: git {args}", details={"command": list(args), "stderr": stderr, "returncode": rc})`.
  - [x] 4.9: For not a git repo → raise `ScmError("Not a git repository: {cwd}", details={"command": list(args), "stderr": stderr, "returncode": rc, "cwd": str(cwd)})`.
  - [x] 4.10: For all other non-zero exit codes → raise `ScmError("git {args[0]} failed (exit {rc})", details={"command": list(args), "stderr": stderr, "returncode": rc})`.

- [x] Task 5: Update `__all__` exports (AC: #1)
  - [x] 5.1: Update `scm/git.py` `__all__` to `["GitResult", "git"]`.
  - [x] 5.2: Update `scm/__init__.py` `__all__` to include `"GitResult"` and `"git"`. Add re-exports: `from arcwright_ai.scm.git import GitResult, git`.

- [x] Task 6: Create tests in `tests/test_scm/test_git.py` (AC: #12, #13)
  - [x] 6.1: Test `test_git_successful_command_returns_git_result` — Mock `asyncio.create_subprocess_exec` to return a process with returncode=0, stdout=b"output\n", stderr=b"". Verify `GitResult(stdout="output", stderr="", returncode=0)` returned. Verify `result.success is True`.
  - [x] 6.2: Test `test_git_nonzero_exit_raises_scm_error` — Mock subprocess to return returncode=1, stderr=b"error msg". Verify `ScmError` raised with `"error msg"` in details["stderr"] and `1` in details["returncode"].
  - [x] 6.3: Test `test_git_logs_successful_command` — Use `caplog` fixture at DEBUG level on `"arcwright_ai.scm.git"` logger. Run a successful mock command. Verify log record with `"git.command"` message, data dict contains args.
  - [x] 6.4: Test `test_git_logs_failed_command` — Use `caplog` fixture. Run a failing mock command (catch `ScmError`). Verify `"git.command"` error log emitted.
  - [x] 6.5: Test `test_git_lock_contention_retries_and_succeeds` — Mock subprocess to fail with lock stderr on attempt 1, then succeed on attempt 2.  Verify `GitResult` returned (no exception). Verify `"git.retry"` warning logged.
  - [x] 6.6: Test `test_git_lock_contention_exhausts_retries` — Mock subprocess to always fail with lock stderr. Verify `ScmError` raised with "lock" in message. Verify 3 retry logs emitted.
  - [x] 6.7: Test `test_git_permission_denied_raises_scm_error` — Mock subprocess with "permission denied" stderr. Verify `ScmError` with "Permission denied" in message.
  - [x] 6.8: Test `test_git_not_a_repo_raises_scm_error` — Mock subprocess with "not a git repository" stderr. Verify `ScmError` with "Not a git repository" in message.
  - [x] 6.9: Test `test_git_cwd_forwarded_to_subprocess` — Mock `create_subprocess_exec`, call `git("status", cwd=some_path)`. Verify `cwd` kwarg passed to subprocess is `str(some_path)`.
  - [x] 6.10: Test `test_git_result_is_frozen` — Create `GitResult(stdout="a", stderr="b", returncode=0)`. Verify `pytest.raises(ValidationError)` when trying to assign `result.stdout = "x"` (Pydantic frozen model).
  - [x] 6.11: Test `test_git_result_success_property` — Verify `.success` is `True` for returncode=0 and `False` for returncode=1.
  - [x] 6.12: All test functions are `async def` with `@pytest.mark.asyncio` decorator (since `git()` is async).

- [x] Task 7: Run quality gates (AC: #9, #10, #11, #12)
  - [x] 7.1: `ruff check .` — zero violations against FULL repository
  - [x] 7.2: `ruff format --check .` — zero formatting issues
  - [x] 7.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 7.4: `pytest` — all tests pass (existing + new)
  - [x] 7.5: Verify Google-style docstrings on all public functions
  - [x] 7.6: Verify `git diff --name-only` matches Dev Agent Record file list

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 6.1 adds code ONLY to `scm/git.py` and `scm/__init__.py`. The git wrapper imports from `core/` only (`core/exceptions.py` for `ScmError`). This is the valid dependency: `scm → core`. No DAG violations.

**Decision 7 — Git Operations Strategy**: "Shell out to `git` CLI — no Python Git library. All calls wrapped through `scm/git.py`." This story implements the foundational wrapper. Every subsequent SCM story (6.2–6.6) depends on this function. [Source: architecture.md — Decision 7]

**Decision 8 — Structured Logging**: The `git.command` and `git.retry` event types are explicitly listed in the D8 event type taxonomy. Log events MUST use structured `extra={"data": {...}}` format — never formatted strings. [Source: architecture.md — Decision 8]

**Decision 6 — Error Taxonomy**: `ScmError` is the base for all git failures. `WorktreeError` and `BranchError` are subclasses used by stories 6.2 and 6.3. Story 6.1 raises only `ScmError` — the subclasses are for higher-level semantic failures. [Source: architecture.md — Decision 6]

**Boundary 4 — Application ↔ File System**: "All git operations go through `scm/git.py` — no subprocess calls from other packages." This story establishes that boundary. The module docstring should state this contract explicitly. [Source: architecture.md — Boundary 4]

**Async subprocess pattern from architecture**:
```python
proc = await asyncio.create_subprocess_exec(
    "git", *args,
    cwd=str(cwd),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout, stderr = await proc.communicate()
```
This is the canonical pattern. Use it exactly. Never use `subprocess.run()`. [Source: architecture.md — Async Patterns]

**Safety**: No force operations anywhere — no `--force`, no `reset --hard`, no rebase. This wrapper doesn't enforce that (it's a low-level wrapper), but it should be documented in the module docstring as a project convention. [Source: architecture.md — Decision 7]

### Current State Analysis — What Already Exists

1. **`scm/git.py`** — Stub file with docstring and empty `__all__`. Module docstring: `"SCM git — Safe subprocess wrapper for git shell operations."`. Implementation goes here.

2. **`scm/__init__.py`** — Package init with empty `__all__`. Placeholder comments for future public API (`create_worktree`, `remove_worktree`, `commit_story`). This story adds `GitResult` and `git` to the public API.

3. **`ScmError`** in `core/exceptions.py` — Already defined: `"Raised when a git subprocess returns non-zero, file permissions fail, or a branch conflicts."` Has `message: str` and `details: dict[str, Any] | None` from `ArcwrightError` base. USE THIS — do NOT create a new exception.

4. **`WorktreeError`** and **`BranchError`** — Already defined as `ScmError` subclasses. NOT used in this story — reserved for stories 6.2 and 6.3.

5. **`MAX_RETRIES = 3`** in `core/constants.py` — This is the general retry limit. For lock contention retries, use a module-level constant `_GIT_LOCK_RETRIES = 3` in `scm/git.py` to keep it independent from the validation retry budget. These are different retry semantics (transient git lock vs. story validation retry).

6. **`tests/test_scm/`** — Directory exists with `__init__.py` and `.gitkeep`. No test files yet. Create `test_git.py` here.

7. **Existing logger pattern** — Every module uses `logger = logging.getLogger(__name__)` and emits structured events with `extra={"data": {...}}`. Follow exactly.

### Existing Code to Reuse — DO NOT REINVENT

- **`ScmError`** from `core/exceptions.py` — RAISE directly. Do NOT create git-specific exceptions.
- **`ArcwrightModel`** base class — CHECK `core/types.py` for its definition. If the frozen Pydantic base exists, use it for `GitResult`. If not, define `GitResult` with `model_config = ConfigDict(frozen=True, extra="forbid")`.
- **`logging.getLogger(__name__)`** pattern — REUSE from existing modules like `agent/sandbox.py`, `engine/nodes.py`.
- **`asyncio.create_subprocess_exec`** — USE the architecture's canonical pattern exactly.

### CRITICAL: ArcwrightModel Base Class Location

Check `core/types.py` for the `ArcwrightModel` base class definition:
```python
class ArcwrightModel(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)
```
If it exists, import and extend it for `GitResult`. If it doesn't exist there, define `GitResult` directly with the same config. DO NOT import from other domain packages.

### CRITICAL: Subprocess Mocking Strategy

Tests must mock `asyncio.create_subprocess_exec` at the `arcwright_ai.scm.git` callsite. Create a helper that returns a mock process object:

```python
def _make_mock_process(returncode: int, stdout: bytes, stderr: bytes):
    """Create a mock asyncio.Process with preset communicate() results."""
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc
```

Then mock: `monkeypatch.setattr("arcwright_ai.scm.git.asyncio.create_subprocess_exec", ...)` or use `unittest.mock.patch("asyncio.create_subprocess_exec", ...)`.

**Important**: `asyncio.create_subprocess_exec` is an async function — the mock must be an `AsyncMock` that returns the mock process.

### CRITICAL: Retry Sleep Mocking

Tests for lock contention retry must mock `asyncio.sleep` to avoid real delays:
```python
monkeypatch.setattr("arcwright_ai.scm.git.asyncio.sleep", AsyncMock())
```

### CRITICAL: Do NOT use `proc.returncode` Before `communicate()`

The `returncode` attribute is only set after `communicate()` completes. Always call `await proc.communicate()` first, then read `proc.returncode`. The architecture code example does this correctly.

### CRITICAL: stderr Decoding

Decode subprocess output as UTF-8 with `errors="replace"` to handle non-UTF-8 git output (e.g., binary diff output in stderr):
```python
stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()
```

### Relationship to Other Stories in Epic 6

- **Story 6.1 (this):** Foundation — the `git()` wrapper all other SCM operations call.
- **Story 6.2:** `scm/worktree.py` — calls `git("worktree", "add", ...)` and `git("worktree", "remove", ...)`.
- **Story 6.3:** `scm/branch.py` — calls `git("branch", ...)`, `git("add", ".")`, `git("commit", ...)`.
- **Story 6.4:** `scm/pr.py` — reads provenance, generates PR body (no direct git calls).
- **Story 6.5:** `cli/clean.py` — calls `git("worktree", "list", ...)` and `git("branch", "-d", ...)`.
- **Story 6.6:** Engine node integration — wires SCM into LangGraph nodes.

This story has NO dependencies on other stories. Stories 6.2, 6.3, 6.5 all depend on this story.

### Testing Patterns from Previous Stories

- **Mock at callsite**: `monkeypatch.setattr("arcwright_ai.scm.git.asyncio.create_subprocess_exec", ...)`.
- **Use `pytest.mark.asyncio`**: All test functions must be async since `git()` is async.
- **Use `caplog`**: For log verification, use `caplog` fixture with `logging.DEBUG` level capture on `"arcwright_ai.scm.git"`.
- **Test naming**: `test_git_<scenario>`, e.g., `test_git_successful_command_returns_git_result`.
- **Assertion style**: Plain `assert` + `pytest.raises(ScmError, match="...")`.
- **No real git commands in unit tests**: All subprocess calls are mocked. Real git tests are `@pytest.mark.slow` and belong in integration tests (not this story).

### Project Structure Notes

Files created/modified by this story:
```
src/arcwright_ai/scm/git.py           # MODIFIED: implement GitResult + git() + retry logic
src/arcwright_ai/scm/__init__.py       # MODIFIED: add GitResult, git to __all__ + re-exports
tests/test_scm/test_git.py            # CREATED: full unit test suite
```

No other files should be modified. This is a leaf implementation — no consumers yet (consumers arrive in stories 6.2+).

### References

- [Architecture Decision 7: Git Operations Strategy](../../_spec/planning-artifacts/architecture.md#decision-7-git-operations-strategy)
- [Architecture Decision 8: Logging & Observability](../../_spec/planning-artifacts/architecture.md#decision-8-logging--observability)
- [Architecture Decision 6: Error Handling Taxonomy](../../_spec/planning-artifacts/architecture.md#decision-6-error-handling-taxonomy)
- [Architecture: Async Patterns](../../_spec/planning-artifacts/architecture.md#async-patterns)
- [Architecture: Boundary 4 — Application ↔ File System](../../_spec/planning-artifacts/architecture.md#architectural-boundaries)
- [Architecture: Package Dependency DAG](../../_spec/planning-artifacts/architecture.md#package-dependency-dag-mandatory)
- [Architecture: Testing Patterns](../../_spec/planning-artifacts/architecture.md#testing-patterns)
- [Architecture: Structured Logging Patterns](../../_spec/planning-artifacts/architecture.md#structured-logging-patterns)
- [Epics: Story 6.1](../../_spec/planning-artifacts/epics.md#story-61-git-subprocess-wrapper--safe-shell-out-foundation)
- [Previous Story 5.5: Run Status Command](../../_spec/implementation-artifacts/5-5-run-status-command-live-and-historical-run-visibility.md)

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- **TC003 (ruff)**: `pathlib.Path` moved to `TYPE_CHECKING` block in `scm/git.py` — Path only appears in type annotations; not needed at runtime with `from __future__ import annotations`.
- **Monkeypatch strategy**: `monkeypatch.setattr("arcwright_ai.scm.git.asyncio.create_subprocess_exec", ...)` fails because pytest's dotted-string resolver treats the module name as a package path. Fixed by using `monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)` — patches the attribute on the live module object.

### Completion Notes List

- Implemented `GitResult(ArcwrightModel)` — frozen Pydantic model with `stdout`, `stderr`, `returncode` fields and a `success` computed property.
- Implemented `async def git(*args, cwd)` — sole gateway for all git subprocess calls. Uses `asyncio.create_subprocess_exec` with the canonical pattern from the architecture.
- Structured logging per Decision 8: success and failure log `git.command` events with full command args, `cwd`, `stdout`, `stderr`, and `returncode` in `extra={"data": {...}}`; retries logged as `git.retry`.
- Error classification: lock contention (retry with backoff 0.1s/0.2s/0.4s × 3 attempts), permission denied, not-a-git-repo, and generic non-zero exit — each raised as `ScmError` with specific message and structured `details`.
- Refactored non-zero handling into `_classify_and_raise(...)` and single-attempt subprocess helper `_run_git_command(...)` to match story task claims.
- `scm/__init__.py` updated with `GitResult` and `git` re-exports.
- 11 unit tests covering all ACs: success path, non-zero exit, logging (success+failure), CWD forwarding, lock retry (success on 2nd attempt), lock exhaustion (3 retry logs), permission denied, not-a-repo, frozen model, success property, with explicit `@pytest.mark.asyncio` on async tests.
- All quality gates pass: `ruff check` ✅, `ruff format --check` ✅, `mypy --strict` ✅, `pytest` 596/596 ✅.

### Change Log

- **2026-03-07**: Implemented `GitResult` model and `async def git()` subprocess wrapper with structured logging, error classification, and lock-contention retry logic. Created `tests/test_scm/test_git.py` with 11 unit tests covering all acceptance criteria. Updated `scm/__init__.py` with public re-exports.
- **2026-03-07 (Code Review Fixes)**: Resolved review findings by adding `_classify_and_raise(...)`, renaming helper to `_run_git_command(...)`, aligning `git.command` payloads with AC #2 (full stdout/stderr), adding explicit `@pytest.mark.asyncio` decorators, and validating with focused pytest + ruff.

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted review workflow)

### Outcome

Approve

### Summary

- All previously identified HIGH and MEDIUM findings were fixed in code and tests.
- AC/task alignment issues were resolved in implementation and story record text.
- Focused validation passed after fixes (`11 passed`, `ruff check` clean on changed SCM files).

### File List

- `src/arcwright_ai/scm/git.py` — MODIFIED: full implementation of `GitResult` model and `git()` wrapper
- `src/arcwright_ai/scm/__init__.py` — MODIFIED: added `GitResult`, `git` to `__all__` and re-exports
- `tests/test_scm/test_git.py` — CREATED: 11 unit tests covering all acceptance criteria
- `_spec/implementation-artifacts/6-1-git-subprocess-wrapper-safe-shell-out-foundation.md` — MODIFIED: status set to done, review fixes documented
- `_spec/implementation-artifacts/sprint-status.yaml` — MODIFIED: synced story status to done
