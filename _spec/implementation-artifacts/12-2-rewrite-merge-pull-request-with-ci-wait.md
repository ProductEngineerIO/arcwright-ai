# Story 12.2: Rewrite merge_pull_request() with CI Wait

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer with `auto_merge: true` and `merge_wait_timeout > 0`,
I want `merge_pull_request()` to queue auto-merge, wait for CI, and confirm the PR actually merged,
So that subsequent stories in an epic always build on verified, merged code.

## Acceptance Criteria (BDD)

### AC 1: Signature change and MergeOutcome return type

**Given** `scm/pr.py` `merge_pull_request()` function (L742–841)
**When** the signature is updated
**Then** the new signature is:
```python
async def merge_pull_request(
    pr_url: str,
    strategy: str = "squash",
    *,
    project_root: Path,
    wait_timeout: int = 0,
) -> MergeOutcome:
```
**And** the return type changes from `bool` to `MergeOutcome`
**And** existing callers using `wait_timeout=0` (default) see identical behavior — this is the only breaking change

### AC 2: Auto-merge queue with --auto flag (wait_timeout > 0)

**Given** `wait_timeout > 0`
**When** merge is initiated
**Then** Step A runs: `gh pr merge <number> <strategy_flag> --delete-branch --auto` to queue auto-merge
**And** stderr is captured — if `"auto-merge is not allowed"` is found, return `MergeOutcome.ERROR` with actionable log: _"Auto-merge is not enabled for this repository. Enable it in Settings → General → Allow auto-merge."_

### AC 3: CI wait via gh pr checks --watch (wait_timeout > 0)

**Given** Step A succeeded (auto-merge queued)
**When** CI wait begins
**Then** Step B runs: `gh pr checks <number> --watch --fail-fast` wrapped in `asyncio.wait_for(timeout=wait_timeout)`
**And** exit 0 → CI passed, proceed to Step C (verify merge)
**And** exit 1 → return `MergeOutcome.CI_FAILED`

### AC 4: Timeout handling with graceful subprocess termination

**Given** `gh pr checks --watch` is running and `asyncio.wait_for` raises `TimeoutError`
**When** timeout fires
**Then** `proc.terminate()` is called (SIGTERM), followed by `await proc.wait()` with 5s grace period
**And** if process is still alive after 5s, `proc.kill()` (SIGKILL) is used as fallback
**And** before returning TIMEOUT, a quick `gh pr view <number> --json state --jq .state` check confirms whether the PR actually merged (race window)
**And** if PR is already `"MERGED"` → return `MergeOutcome.MERGED` (not TIMEOUT)
**And** if PR is not merged → return `MergeOutcome.TIMEOUT`

### AC 5: Merge verification (Step C)

**Given** CI passed (Step B exit 0)
**When** merge verification runs
**Then** Step C verifies PR merged via `gh pr view <number> --json state --jq .state`
**And** retries up to 3 times with 5s sleep if not yet `MERGED` (race condition between CI pass and GitHub completing the merge)
**And** returns `MergeOutcome.MERGED` on success
**And** returns `MergeOutcome.ERROR` if still not merged after 3 retries

### AC 6: Backward compatible fire-and-forget (wait_timeout == 0)

**Given** `wait_timeout == 0` (default)
**When** merge is attempted
**Then** runs `gh pr merge <number> <strategy_flag> --delete-branch` (no `--auto`, immediate merge, same as current behavior)
**And** returns `MergeOutcome.MERGED` on success
**And** returns `MergeOutcome.ERROR` on failure

### AC 7: Guard clauses preserved

**Given** guard clause conditions
**When** `gh` not found → return `MergeOutcome.ERROR`
**And** invalid URL → return `MergeOutcome.ERROR`
**And** all outcomes logged via structured logging with `merge_outcome` field

### AC 8: Existing tests updated + new tests pass

**Given** the test suite
**When** tests are run
**Then** all existing `merge_pull_request` tests updated from `bool` assertions to `MergeOutcome` assertions
**And** 10 new unit tests added (listed in Tasks)
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

## Tasks / Subtasks

- [ ] Task 1: Update `merge_pull_request()` signature and return type (AC: #1)
  - [ ] 1.1: In `src/arcwright_ai/scm/pr.py` (~L742), change return type from `bool` to `MergeOutcome`. Add `wait_timeout: int = 0` keyword-only parameter after `project_root`.
  - [ ] 1.2: Update all internal `return True` to `return MergeOutcome.MERGED` and `return False` to `return MergeOutcome.ERROR` in the existing fire-and-forget code path.
  - [ ] 1.3: Update guard clauses: `gh` not found → `return MergeOutcome.ERROR`, invalid URL → `return MergeOutcome.ERROR`.

- [ ] Task 2: Implement CI-wait path when `wait_timeout > 0` (AC: #2, #3, #4, #5)
  - [ ] 2.1: Add a branch at the top of the merge logic: `if wait_timeout > 0:` → new CI-wait code path; `else:` → existing fire-and-forget path (with `bool` → `MergeOutcome` conversion from Task 1).
  - [ ] 2.2: **Step A — Queue auto-merge:** Run `gh pr merge <number> <strategy_flag> --delete-branch --auto` via `asyncio.create_subprocess_exec`. Capture both stdout and stderr. If stderr contains `"auto-merge is not allowed"`, log actionable message and return `MergeOutcome.ERROR`.
  - [ ] 2.3: **Step B — Wait for CI:** Run `gh pr checks <number> --watch --fail-fast` via `asyncio.create_subprocess_exec`. Wrap the `await proc.wait()` (or `proc.communicate()`) in `asyncio.wait_for(timeout=wait_timeout)`.
    - Exit 0 → proceed to Step C.
    - Exit 1 → return `MergeOutcome.CI_FAILED`.
  - [ ] 2.4: **Timeout handler:** On `asyncio.TimeoutError`:
    - Call `proc.terminate()` (SIGTERM).
    - `await asyncio.wait_for(proc.wait(), timeout=5)`; if TimeoutError again → `proc.kill()` then `await proc.wait()`.
    - Run `gh pr view <number> --json state --jq .state` to check if PR is already `MERGED`.
    - If merged → return `MergeOutcome.MERGED`.
    - If not merged → return `MergeOutcome.TIMEOUT`.
  - [ ] 2.5: **Step C — Verify merge:** Run `gh pr view <number> --json state --jq .state`. If `"MERGED"` → return `MergeOutcome.MERGED`. If not, retry up to 3 times with `await asyncio.sleep(5)` between attempts. After 3 retries still not merged → return `MergeOutcome.ERROR`.
  - [ ] 2.6: Add structured logging for every outcome using `logger.info("scm.merge.outcome", extra={"data": {"pr_url": pr_url, "outcome": outcome.value, "wait_timeout": wait_timeout, ...}})`.

- [ ] Task 3: Update existing tests — bool → MergeOutcome (AC: #8)
  - [ ] 3.1: In `tests/test_scm/test_pr.py` (~L891–1160), find all assertions that check `merge_pull_request` returns `True` and change to `MergeOutcome.MERGED`. Find all that check `False` and change to `MergeOutcome.ERROR`. All existing tests use default `wait_timeout=0`.
  - [ ] 3.2: These tests use `patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec)` pattern — this pattern is preserved.

- [ ] Task 4: Add new unit tests for CI-wait path (AC: #8)
  - [ ] 4.1: `test_merge_pr_auto_flag_when_wait_timeout_positive` — Mock subprocess to capture args; verify `--auto` flag present in `gh pr merge` args when `wait_timeout=300`.
  - [ ] 4.2: `test_merge_pr_checks_watch_called_after_auto` — Mock two sequential subprocess calls; verify first is `gh pr merge --auto`, second is `gh pr checks --watch --fail-fast`.
  - [ ] 4.3: `test_merge_pr_returns_merged_on_ci_pass` — Mock `gh pr merge --auto` (exit 0), `gh pr checks` (exit 0), `gh pr view` returns `"MERGED"`. Assert `MergeOutcome.MERGED`.
  - [ ] 4.4: `test_merge_pr_returns_ci_failed_on_check_failure` — Mock `gh pr merge --auto` (exit 0), `gh pr checks` (exit 1). Assert `MergeOutcome.CI_FAILED`.
  - [ ] 4.5: `test_merge_pr_returns_timeout_on_asyncio_timeout` — Mock `gh pr merge --auto` (exit 0), patch `asyncio.wait_for` to raise `TimeoutError`, mock `gh pr view` returns `"OPEN"`. Assert `MergeOutcome.TIMEOUT`. Verify `proc.terminate()` was called.
  - [ ] 4.6: `test_merge_pr_no_wait_when_timeout_zero` — `wait_timeout=0` → verify no `--auto` flag, no `gh pr checks` call, immediate merge.
  - [ ] 4.7: `test_merge_pr_returns_skipped_never` — Verify `merge_pull_request()` never returns `MergeOutcome.SKIPPED` (that value is only set by `commit_node`).
  - [ ] 4.8: `test_merge_pr_timeout_verify_actually_merged` — Mock `gh pr checks` to raise `TimeoutError`, mock `gh pr view --json state` to return `"MERGED"`. Assert `MergeOutcome.MERGED` (not TIMEOUT).
  - [ ] 4.9: `test_merge_pr_timeout_subprocess_sigterm` — Mock `gh pr checks` to hang; set `wait_timeout=2`. Assert `proc.terminate()` was called. Verify `proc.kill()` is NOT called if `proc.wait()` completes within 5s grace period.
  - [ ] 4.10: `test_merge_pr_auto_merge_not_allowed_stderr` — Mock `gh pr merge --auto` stderr to contain `"auto-merge is not allowed"`. Assert `MergeOutcome.ERROR` and verify log mentions Settings → General → Allow auto-merge.
  - [ ] 4.11: Run full suite: `uv run ruff check src/ tests/ && uv run mypy --strict src/ && uv run pytest` — zero failures, zero regressions

## Dev Notes

### Architecture Compliance

- **Package DAG (Mandatory):** This story modifies only `scm/pr.py` and `tests/test_scm/test_pr.py`. The `scm` package depends on `core` only. No new cross-package dependencies.
- **D10 (CI-Aware Merge Wait):** This is the core implementation of D10 — the two-phase merge approach (queue auto-merge → wait for CI → verify merge).
- **D7 (Single Gateway — Boundary 4):** All subprocess calls use `asyncio.create_subprocess_exec` directly (not the `git()` wrapper) because `gh` is the target, not `git`. This is consistent with the existing `merge_pull_request()` implementation.
- **Best-effort SCM pattern:** The existing pattern catches all exceptions and logs them. The new CI-wait path follows this — `MergeOutcome.ERROR` is returned on unexpected failures, never raised.
- **Async subprocess pattern:** Uses `asyncio.create_subprocess_exec` → `proc.communicate()` for simple calls, `proc.wait()` for the long-running `gh pr checks --watch`. Timeout wraps `proc.wait()` only.

### Key Implementation Detail: Subprocess Lifecycle

The `gh pr checks --watch --fail-fast` subprocess can block for minutes. Key considerations:
1. **`asyncio.wait_for` wraps `proc.communicate()`** — when timeout fires, the task is cancelled but the subprocess is NOT automatically killed. You must explicitly call `proc.terminate()`.
2. **SIGTERM before SIGKILL:** `proc.terminate()` sends SIGTERM. The `gh` CLI handles SIGTERM gracefully. Only use `proc.kill()` (SIGKILL) as a fallback if the process doesn't exit within 5 seconds.
3. **Race window on timeout:** CI might pass moments before the timeout fires. The `gh pr view --json state` check after timeout prevents false TIMEOUT results.

### Existing `merge_pull_request()` Structure (L742–841)

Current flow:
1. Check `gh` exists → `return False` (will become `MergeOutcome.ERROR`)
2. Extract PR number from URL → `return False` on failure
3. Build strategy flag from `_MERGE_STRATEGY_FLAGS` dict
4. Run `asyncio.create_subprocess_exec("gh", "pr", "merge", number, strategy_flag, "--delete-branch")`
5. `return proc.returncode == 0` (will become MERGED/ERROR)

The new CI-wait path inserts between steps 3 and 4 when `wait_timeout > 0`.

### Test Mocking Pattern

Existing tests mock `asyncio.create_subprocess_exec` at the module level:
```python
@patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec")
```
Each mock returns an `AsyncMock` with configurable `returncode`, `stdout`, `stderr` attributes. For the new tests requiring multiple sequential subprocess calls, use `side_effect` with a list of mock process objects.

### References

- [Source: _spec/implementation-artifacts/ci-aware-merge-wait.md#Task 2] — Task 2 implementation plan with full Step A/B/C detail
- [Source: _spec/planning-artifacts/architecture.md#D10] — CI-Aware Merge Wait architectural decision
- [Source: _spec/planning-artifacts/epics.md#Story 12.2] — Epic story definition with AC
- [Source: src/arcwright_ai/scm/pr.py#L742–841] — Current `merge_pull_request()` implementation
- [Source: src/arcwright_ai/scm/pr.py#L30–37] — `_MERGE_STRATEGY_FLAGS` dict
- [Source: src/arcwright_ai/scm/pr.py#L843–862] — `_extract_pr_number()` helper
- [Source: tests/test_scm/test_pr.py#L891–1160] — Existing merge tests (bool assertions, mock subprocess pattern)

### Previous Story Intelligence (Story 12.1)

- Story 12.1 creates `MergeOutcome` enum in `scm/pr.py` — this story uses it as the return type
- Story 12.1 adds `merge_wait_timeout` to `ScmConfig` — this story reads it (but only `commit_node` in Story 12.3 passes it)
- `MergeOutcome` is imported locally in `scm/pr.py` where it's defined — no cross-package import needed

### Files Touched

- `src/arcwright_ai/scm/pr.py` — Rewrite `merge_pull_request()`, update return type, add CI-wait path
- `tests/test_scm/test_pr.py` — Update existing tests (bool → MergeOutcome), add 10 new tests

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List
