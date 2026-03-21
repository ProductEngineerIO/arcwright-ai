# Story 10.13: PR Creation Retry with Backoff for GitHub API Lag

Status: done

## Story

As a maintainer running Arcwright AI story execution,
I want `open_pull_request` to retry with exponential backoff when `gh pr create` fails due to GitHub API indexing lag after a push,
so that PRs are created automatically even when GitHub takes a few seconds to register the newly-pushed branch.

## Acceptance Criteria

1. **Given** `gh pr create` fails with a transient error (e.g. "No commits between") **When** retries are available **Then** the function waits with exponential backoff and retries the `gh pr create` command
2. **Given** `gh pr create` succeeds on a retry attempt **When** the PR URL is returned **Then** a `scm.pr.create` log event is emitted with the PR URL (identical to first-attempt success)
3. **Given** `gh pr create` fails on all retry attempts **When** the final attempt fails **Then** the function logs `scm.pr.create.skipped` with reason `gh_error` and `manual_pr_url`, and returns `None`
4. **Given** `gh pr create` fails with a permanent error (e.g. "already exists", auth failure) **When** the error is classified **Then** no retry is attempted and the function returns immediately
5. **And** a `scm.pr.create.retry` log event is emitted for each retry with `attempt`, `max_attempts`, `wait_seconds`, and `stderr`
6. **And** the retry constants (`_PR_RETRY_MAX`, `_PR_RETRY_BASE_SECONDS`) are module-level in `scm/pr.py`
7. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

## Tasks / Subtasks

- [x] Task 1 — Add transient error classifier (AC: #1, #4)
  - [x] 1.1 Create `_is_transient_pr_error(stderr: str) -> bool` function in `scm/pr.py`
  - [x] 1.2 Transient patterns: `"no commits between"`, `"can't be blank"`, `"must be a branch"`, `"not found"` (case-insensitive)
  - [x] 1.3 Permanent patterns (never retry): `"already exists"`, `"not a git repository"`, `"could not resolve"`, `"authentication"`, `"permission"`

- [x] Task 2 — Add retry constants (AC: #6)
  - [x] 2.1 Add `_PR_RETRY_MAX: int = 4` module-level constant
  - [x] 2.2 Add `_PR_RETRY_BASE_SECONDS: float = 2.0` module-level constant

- [x] Task 3 — Add retry loop to `open_pull_request()` (AC: #1, #2, #3, #5)
  - [x] 3.1 Wrap the `gh pr create` subprocess call in a retry loop
  - [x] 3.2 On non-zero returncode: check `_is_transient_pr_error(stderr)` — if permanent, return `None` immediately (existing behavior)
  - [x] 3.3 If transient and retries remaining: log `scm.pr.create.retry`, sleep with backoff, retry
  - [x] 3.4 Backoff formula: `wait = _PR_RETRY_BASE_SECONDS * (2 ** attempt)` → 2s, 4s, 8s, 16s
  - [x] 3.5 On success after retry: log `scm.pr.create` with PR URL (AC: #2 — identical to first-attempt success)
  - [x] 3.6 After all retries exhausted: log existing `scm.pr.create.skipped` with `gh_error` reason

- [x] Task 4 — Tests (AC: #7)
  - [x] 4.1 Test `_is_transient_pr_error()`: transient patterns return True
  - [x] 4.2 Test `_is_transient_pr_error()`: permanent patterns return False
  - [x] 4.3 Test retry succeeds on second attempt (mock subprocess to fail then succeed)
  - [x] 4.4 Test all retries exhausted returns None
  - [x] 4.5 Test permanent error skips retry entirely
  - [x] 4.6 Test `scm.pr.create.retry` log emitted per retry with correct fields
  - [x] 4.7 Test backoff timing (mock `asyncio.sleep`, verify called with 2, 4, 8, 16)

## Dev Notes

### Problem Context

Observed in run `20260320-213942-e61e46` (digital-anarchy, story 5-5-e2e-smoke-test-pass). After the agent successfully completed 2 attempts (74 min total), `push_branch()` pushed commit `5740d08f` to `origin/arcwright-ai/5-5-e2e-smoke-test-pass`. The push succeeded (diff: 6 files, +527/-61). However, `gh pr create` ran immediately after and got:

```
GraphQL: Head sha can't be blank, Base sha can't be blank,
No commits between develop and arcwright-ai/5-5-e2e-smoke-test-pass,
Head ref must be a branch, Base ref must be a branch (createPullRequest)
```

This is a GitHub API indexing lag — the branch exists on GitHub but the API hasn't registered it yet. A 2–5 second delay would have been sufficient.

### Scope — Minimal Change

This is a **surgical fix** to `open_pull_request()` only. Do NOT:
- Change `commit_node` — it already calls `open_pull_request()` with best-effort error handling
- Change `push_branch()` — the push itself succeeds; the lag is GitHub-side
- Add a delay between push and PR creation in `commit_node` — the retry belongs inside `open_pull_request()` where the failure is detected
- Add retry configuration to `LimitsConfig` — hardcoded constants are sufficient for this low-frequency operation

### Where to Add the Retry Loop

The retry wraps **only the subprocess call and return-code handling** inside `open_pull_request()` (lines 752–798 in `scm/pr.py`). The code before the subprocess (gh availability check, default branch detection, PR title derivation) runs once. The code after (exception handling) remains unchanged.

**Pseudocode:**
```python
for attempt in range(_PR_RETRY_MAX + 1):  # 0..4 = 5 total attempts (1 initial + 4 retries)
    proc = await asyncio.create_subprocess_exec("gh", "pr", "create", ...)
    stdout_bytes, stderr_bytes = await proc.communicate()
    stdout = stdout_bytes.decode(...)
    stderr = stderr_bytes.decode(...)

    if proc.returncode == 0:
        # Success — log and return PR URL
        ...
        return pr_url

    # "already exists" — not an error, skip (existing behavior)
    if "already exists" in stderr.lower() or "already exists" in stdout.lower():
        logger.warning("scm.pr.create.skipped", ...)
        return None

    # Permanent error — don't retry
    if not _is_transient_pr_error(stderr):
        logger.warning("scm.pr.create.skipped", ...)
        return None

    # Transient error — retry if budget allows
    if attempt < _PR_RETRY_MAX:
        wait = _PR_RETRY_BASE_SECONDS * (2 ** attempt)
        logger.info(
            "scm.pr.create.retry",
            extra={"data": {
                "story_slug": story_slug,
                "attempt": attempt + 1,
                "max_attempts": _PR_RETRY_MAX,
                "wait_seconds": wait,
                "stderr": stderr,
            }},
        )
        await asyncio.sleep(wait)
    else:
        # All retries exhausted
        logger.warning("scm.pr.create.skipped", ...)
        return None
```

### Existing Patterns to Follow

**Git lock retry pattern** (from `scm/git.py`):
```python
_GIT_LOCK_RETRIES = 3

for attempt in range(_GIT_LOCK_RETRIES + 1):
    proc = await asyncio.create_subprocess_exec(...)
    if _is_lock_error(stderr) and attempt < _GIT_LOCK_RETRIES:
        await asyncio.sleep(0.5 * (2 ** attempt))
        continue
```

The PR retry follows the same pattern but with:
- Different constants (4 retries, 2s base vs 3 retries, 0.5s base)
- Different error classifier (`_is_transient_pr_error` vs `_is_lock_error`)
- Same log-then-sleep-then-continue structure

**Async subprocess pattern** (already used in `open_pull_request()`):
```python
proc = await asyncio.create_subprocess_exec(
    "gh", "pr", "create", ...,
    cwd=str(project_root),
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
stdout_bytes, stderr_bytes = await proc.communicate()
```

### Transient vs Permanent Error Classification

**Transient** (GitHub API lag — branch not yet indexed):
- `"no commits between"` — HEAD and base resolve to same commit (branch not found)
- `"can't be blank"` — HEAD or base sha couldn't be resolved
- `"must be a branch"` — ref not recognized as a branch yet
- `"not found"` — branch ref lookup failed

**Permanent** (won't resolve with retries):
- `"already exists"` — PR already open (handled separately, pre-existing logic)
- `"not a git repository"` — wrong cwd
- `"could not resolve"` — DNS/network error
- `"authentication"` / `"permission"` — auth failure

The classifier uses `stderr.lower()` for case-insensitive matching. If stderr matches ANY transient pattern and NO permanent pattern, return `True`.

### Key Code Locations

| Component | File | Key Functions/Lines |
|-----------|------|---------------------|
| PR creation | `src/arcwright_ai/scm/pr.py` | `open_pull_request()` (line 700), subprocess at line 752 |
| commit_node caller | `src/arcwright_ai/engine/nodes.py` | PR call at line 1628 — **do not modify** |
| Git lock retry | `src/arcwright_ai/scm/git.py` | `_GIT_LOCK_RETRIES`, retry loop pattern |
| PR tests | `tests/test_scm/test_pr.py` | Existing tests to extend |

### Previous Story Intelligence

**Story 10.4** (commit node resilience): Established the best-effort pattern for PR creation. `open_pull_request()` returns `None` on failure; `commit_node` catches exceptions and continues. This story preserves that contract — retry is internal to `open_pull_request()`, invisible to callers.

**Story 10.6** (auto-merge success marked error): Fixed branch cleanup failure being misreported. Same principle applies here — PR creation failure after successful push shouldn't mark the run as failed.

### Test Approach

Mock `asyncio.create_subprocess_exec` to return configurable `Process` objects. Mock `asyncio.sleep` to avoid real delays and verify backoff values.

Existing test patterns in `tests/test_scm/test_pr.py` already mock subprocess for `gh pr create` — extend these with retry scenarios.

### References

- [Source: _spec/planning-artifacts/epics.md — Story 10.13]
- [Source: arcwright-ai/src/arcwright_ai/scm/pr.py — open_pull_request()]
- [Source: arcwright-ai/src/arcwright_ai/scm/git.py — git lock retry pattern]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — commit_node PR creation call]
- [Observed: digital-anarchy run 20260320-213942-e61e46 — PR creation race condition]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

- Root cause: `_detect_default_branch` also calls `asyncio.create_subprocess_exec` (for `gh repo view`) — patching the module-level `asyncio.create_subprocess_exec` in retry tests consumed mock `side_effect` items. Fixed by patching `_detect_default_branch` directly in the 6 new retry tests.

### Completion Notes List

- Added `_PR_RETRY_MAX: int = 4` and `_PR_RETRY_BASE_SECONDS: float = 2.0` module-level constants in `scm/pr.py`.
- Added `_is_transient_pr_error(stderr: str) -> bool` function — permanent patterns checked first (short-circuit), then transient patterns.
- Replaced the single-attempt `gh pr create` subprocess call in `open_pull_request()` with a `for attempt in range(_PR_RETRY_MAX + 1)` retry loop following the existing git-lock-retry pattern in `scm/git.py`.
- "already exists" fast-exit path preserved (pre-retry-classifier, unchanged behavior).
- Added `return None  # pragma: no cover` defensive guard after the loop for mypy `--strict` compliance.
- 9 new tests added: 2 parametrized unit tests for `_is_transient_pr_error` (14 cases total) + 6 integration-style tests for `open_pull_request` retry behavior. All 1175 suite tests pass.

### File List

- arcwright-ai/src/arcwright_ai/scm/pr.py
- arcwright-ai/tests/test_scm/test_pr.py

## Change Log

- 2026-03-20: Story 10.13 — Added exponential-backoff retry to `open_pull_request()` for GitHub API indexing lag. Added `_is_transient_pr_error`, `_PR_RETRY_MAX`, `_PR_RETRY_BASE_SECONDS`. 9 new tests; 1175/1175 suite pass.
