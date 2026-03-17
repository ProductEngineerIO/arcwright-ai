---
title: 'CI-Aware Merge Wait for Epic Chain Integrity'
slug: 'ci-aware-merge-wait'
created: '2026-03-16'
status: 'approved'
stepsCompleted: [1, 2, 3]
tech_stack: ['python', 'asyncio', 'gh-cli']
files_to_modify:
  - 'src/arcwright_ai/scm/pr.py'
  - 'src/arcwright_ai/scm/__init__.py'
  - 'src/arcwright_ai/core/config.py'
  - 'src/arcwright_ai/cli/status.py'
  - 'src/arcwright_ai/cli/dispatch.py'
  - 'src/arcwright_ai/engine/nodes.py'
  - 'src/arcwright_ai/engine/state.py'
  - 'tests/test_scm/test_pr.py'
  - 'tests/test_engine/test_nodes.py'
code_patterns:
  - 'frozen-pydantic-config'
  - 'async-subprocess-exec'
  - 'best-effort-non-fatal-scm'
  - 'structured-logging'
test_patterns:
  - 'monkeypatch-subprocess'
  - 'AsyncMock'
  - 'caplog-structured-events'
---

# Tech-Spec: CI-Aware Merge Wait for Epic Chain Integrity

**Created:** 2026-03-16

## Overview

### Problem Statement

When `auto_merge: true` is configured and an epic dispatches multiple sequential stories, the current `merge_pull_request()` function calls `gh pr merge --squash --delete-branch` immediately after PR creation. This is fire-and-forget — it either merges instantly (no branch protection) or fails silently (CI checks required).

The result is a broken chain: Story N+1's `fetch_and_sync()` doesn't see Story N's code because it hasn't been CI-verified and merged yet. Stories build on stale base refs, producing incorrect output or merge conflicts.

### Solution

Replace the fire-and-forget `gh pr merge` call with a two-phase approach:

1. **Enable auto-merge**: `gh pr merge <number> --squash --delete-branch --auto` — queues the PR to merge automatically once all required status checks pass
2. **Wait for CI**: `gh pr checks <number> --watch --fail-fast` — blocks until CI finishes (exit 0 = pass, exit 1 = fail, exit 8 = pending/timeout)
3. **Confirm merge**: After CI passes, verify the PR actually merged via `gh pr view --json state`
4. **Halt on failure**: If CI fails or timeout is reached, the merge wait returns a failure status. The `commit_node` records this and the story is still marked SUCCESS (code was committed and PR created), but the **epic dispatch loop** halts — preventing subsequent stories from building on stale code.

A new `merge_wait_timeout` config field (default `0` — fire-and-forget, backward compatible) controls the maximum blocking time. Setting it to a positive value (recommended: `1200` = 20 minutes) enables the CI-wait loop.

> **Footgun warning**: `auto_merge: true` + `merge_wait_timeout: 0` enables auto-merge but does NOT wait for CI. The epic loop will proceed immediately, defeating chain integrity. When `auto_merge: true` and `merge_wait_timeout: 0`, the code logs a prominent warning: _"auto_merge is enabled but merge_wait_timeout is 0 — CI checks will not be waited for. Set merge_wait_timeout to enable chain integrity."_

### Scope

**In Scope:**
- New `merge_wait_timeout: int` field on `ScmConfig`
- Rewrite `merge_pull_request()` to use `--auto` + `gh pr checks --watch --fail-fast`
- New `MergeOutcome` enum for structured merge result reporting
- Updated `commit_node` to interpret merge outcome and signal halt when CI fails
- Epic dispatch loop update to halt on `CI_FAILED` / `TIMEOUT` merge outcomes
- Config template update with commented-out `merge_wait_timeout`
- Unit tests for all new code paths

**Out of Scope:**
- Changes to the `--resume` mechanism
- D1 CI-chain GitHub Actions workflows
- Speculative execution / branch-tip worktrees
- Merge queue support (`gh pr merge --merge-queue`)

## Context for Development

### Codebase Patterns

- **Frozen Pydantic models**: `ScmConfig` uses `ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)`. New fields follow the same pattern.
- **Auto-derived known keys**: `_KNOWN_SECTION_FIELDS["scm"]` is `frozenset(ScmConfig.model_fields.keys())` — adding a field auto-updates it.
- **Async subprocess**: `merge_pull_request()` uses `asyncio.create_subprocess_exec` directly (not the `git()` wrapper) because it calls `gh`, not `git`.
- **Best-effort SCM**: All SCM operations in `commit_node` are wrapped in try/except and logged as warnings. Merge failure is non-fatal to the story.
- **Structured logging**: All log events use `logger.info/warning` with `extra={"data": {...}}` for structured context.
- **Provenance recording**: Merge outcomes are recorded via `ProvenanceEntry` appended to the story's validation file.

### Files to Reference

| File | Purpose |
| ---- | ------- |
| `src/arcwright_ai/scm/pr.py` (L740–942) | Current `merge_pull_request()`, `_extract_pr_number()`, `get_pull_request_merge_sha()` |
| `src/arcwright_ai/core/config.py` (L220–241) | `ScmConfig` class definition |
| `src/arcwright_ai/engine/nodes.py` (L1507–1570) | `commit_node` auto-merge block |
| `src/arcwright_ai/cli/status.py` (L93–98) | `_DEFAULT_CONFIG_YAML` scm section |
| `tests/test_scm/test_pr.py` (L891–1160) | Existing `merge_pull_request` unit tests |
| `src/arcwright_ai/scm/__init__.py` | Public exports — add `MergeOutcome` |
| `src/arcwright_ai/cli/dispatch.py` (L620–930) | `_dispatch_epic_async()` story loop — add merge outcome check |

### Technical Decisions

1. **`gh pr checks --watch --fail-fast` over manual poll loop**: The `gh` CLI has built-in watch mode with configurable interval. Using it avoids reimplementing poll logic. `--fail-fast` exits immediately on the first check failure, minimizing wait time on known failures. The `--watch` flag blocks until all checks complete — exactly what we need.

2. **Exit code semantics**: `gh pr checks --watch` returns exit `0` on all-pass, `1` on any failure, `8` on still-pending. We use `asyncio.wait_for()` with `merge_wait_timeout` to enforce the time bound — if the subprocess is still running when timeout hits, we send `SIGTERM` (with a 5s grace period before `SIGKILL`) and treat it as a timeout halt. Before returning TIMEOUT, a quick `gh pr view` check confirms the PR didn't actually just merge (race window).

3. **`--auto` flag instead of immediate merge**: `gh pr merge --auto` queues the PR for auto-merge once checks pass. This is the correct GitHub-native approach. If checks never pass, the PR stays open with auto-merge queued.

4. **`merge_wait_timeout: 0` = backward compatible fire-and-forget**: When timeout is `0`, skip the `gh pr checks --watch` step entirely — just call `gh pr merge --auto` (or immediate merge if no branch protection) and move on. This preserves the current behavior exactly.

5. **Halt mechanism — merge_failed flag on StoryState**: The `commit_node` sets a `merge_failed: bool` field on `StoryState`. The dispatch loop in `dispatch.py` already checks `exit_code != EXIT_SUCCESS` after each story. We don't need to change the dispatch loop — instead, the `commit_node` returns `state.status = TaskState.SUCCESS` (the code is valid) but sets `merge_failed = True`. The dispatch loop then checks this flag and halts with a clear message. **Actually, simpler**: We use the existing `state.status` — the story is SUCCESS but we set an `epic_halt_requested: bool` flag that the dispatch loop reads.

   **Simplest approach**: The `commit_node` returns the state as-is (SUCCESS). The dispatch loop already calls `graph.ainvoke(initial_state)` and checks the result. We add a `merge_outcome` field to `StoryState` that the dispatch loop inspects after SUCCESS to decide whether to continue the epic loop. This keeps the graph nodes clean and pushes the "halt epic" decision to the orchestrator where it belongs.

6. **Three possible merge outcomes**:
   - `MERGED` — CI passed, PR merged, chain intact → continue epic
   - `MERGE_SKIPPED` — `auto_merge` is false or `merge_wait_timeout` is 0 → continue epic (fire-and-forget)
   - `MERGE_FAILED` — CI failed or timeout → halt epic, PR stays open with `--auto` queued

## Implementation Plan

### Tasks

#### Task 1: Add `MergeOutcome` enum and `merge_wait_timeout` config field

**Files:** `src/arcwright_ai/core/config.py`, `src/arcwright_ai/engine/state.py`

1.1. Add `merge_wait_timeout: int = 0` to `ScmConfig`. Docstring: seconds to wait for CI checks after enabling auto-merge. `0` = fire-and-forget (backward compatible default). **Log a warning at config load time if `auto_merge=True` and `merge_wait_timeout=0`**: this combination enables auto-merge without waiting, which defeats chain integrity in multi-story epics.

1.2. Add `MergeOutcome` StrEnum to `src/arcwright_ai/scm/pr.py`:
```python
class MergeOutcome(StrEnum):
    MERGED = "merged"           # CI passed, PR merged
    SKIPPED = "skipped"         # auto_merge off or timeout=0
    CI_FAILED = "ci_failed"     # CI checks failed
    TIMEOUT = "timeout"         # CI checks didn't complete within timeout
    ERROR = "error"             # gh CLI error (missing, network, etc.)
```

1.3. Add `merge_outcome: str | None = None` field to `StoryState` in `engine/state.py`. This is read by the dispatch loop after graph completion.

1.4. Export `MergeOutcome` from `src/arcwright_ai/scm/__init__.py` so that `dispatch.py` and `nodes.py` can import the enum directly (`from arcwright_ai.scm import MergeOutcome`) instead of comparing bare string literals.

#### Task 2: Rewrite `merge_pull_request()` to use `--auto` + CI wait

**File:** `src/arcwright_ai/scm/pr.py`

2.1. Change `merge_pull_request()` signature:
```python
async def merge_pull_request(
    pr_url: str,
    strategy: str = "squash",
    *,
    project_root: Path,
    wait_timeout: int = 0,
) -> MergeOutcome:
```
Return type changes from `bool` to `MergeOutcome`.

2.2. When `wait_timeout > 0`:
- Step A: Run `gh pr merge <number> <strategy_flag> --delete-branch --auto` to queue auto-merge. **Capture stderr** — if it contains `"auto-merge is not allowed"`, return `MergeOutcome.ERROR` with a log message: _"Auto-merge is not enabled for this repository. Enable it in Settings → General → Allow auto-merge."_
- Step B: Run `gh pr checks <number> --watch --fail-fast` wrapped in `asyncio.wait_for(timeout=wait_timeout)`
  - Exit 0 → CI passed. Proceed to Step C.
  - Exit 1 → CI failed. Return `MergeOutcome.CI_FAILED`.
  - `asyncio.TimeoutError` → **Subprocess termination**: call `proc.terminate()`, then `await proc.wait()` with a 5-second grace period. If the process is still alive after 5s, call `proc.kill()`. Do NOT use `proc.kill()` immediately — `SIGTERM` gives `gh` a chance to clean up. **Before returning TIMEOUT**, run a quick `gh pr view <number> --json state --jq .state` check — if the PR is already `"MERGED"` (CI passed moments before timeout fired), return `MergeOutcome.MERGED` instead of `MergeOutcome.TIMEOUT`. Otherwise return `MergeOutcome.TIMEOUT`.
- Step C: Verify PR merged via `gh pr view <number> --json state --jq .state`. If `"MERGED"` → return `MergeOutcome.MERGED`. If not merged yet (race condition — CI passed but merge hasn't completed), retry `gh pr view` up to 3 times with 5s sleep. If still not merged → return `MergeOutcome.ERROR`.

2.3. When `wait_timeout == 0` (backward compatible):
- Run `gh pr merge <number> <strategy_flag> --delete-branch` (no `--auto`, immediate merge attempt, same as current behavior)
- Return `MergeOutcome.MERGED` on success, `MergeOutcome.ERROR` on failure

2.4. Guard clauses unchanged: `gh` not found → `MergeOutcome.ERROR`, invalid URL → `MergeOutcome.ERROR`.

2.5. All outcomes are logged via structured logging with `merge_outcome` field.

#### Task 3: Update `commit_node` to pass timeout and set merge outcome

**File:** `src/arcwright_ai/engine/nodes.py`

3.1. In the auto-merge block, pass `wait_timeout=state.config.scm.merge_wait_timeout`:
```python
merge_outcome = await merge_pull_request(
    pr_url,
    strategy=merge_strategy,
    project_root=project_root,
    wait_timeout=state.config.scm.merge_wait_timeout,
)
```

3.2. Replace the `merge_succeeded: bool` logic with `MergeOutcome` handling. **Blast radius detail** — the existing code has:
- A `merge_succeeded` boolean conditional that gates the `get_pull_request_merge_sha()` call
- A provenance recording block that uses the boolean

Both must be updated to switch on `MergeOutcome`:
- `MERGED` → call `get_pull_request_merge_sha()`, fetch merge SHA, record provenance as success
- `SKIPPED` → skip `get_pull_request_merge_sha()` entirely, record provenance noting skip
- `CI_FAILED` / `TIMEOUT` / `ERROR` → skip `get_pull_request_merge_sha()`, record provenance with failure details. **Do not call `get_pull_request_merge_sha()` on failure** — the PR hasn't merged so there is no merge SHA to fetch.

3.3. Set `state.merge_outcome = merge_outcome.value` on the returned state.

3.4. When `auto_merge` is `False`, set `state.merge_outcome = MergeOutcome.SKIPPED.value`.

#### Task 4: Update dispatch loop to halt on merge failure

**File:** `src/arcwright_ai/cli/dispatch.py`

4.1. After `graph.ainvoke()` returns and the story status is SUCCESS, check `result.merge_outcome`:
```python
if result.merge_outcome in ("ci_failed", "timeout"):
    logger.warning("dispatch.epic.halt.merge_failed", ...)
    # Halt the epic — don't start next story
    break
```

4.2. Log a clear message: "Epic halted: Story {slug} PR merge failed (CI {outcome}). Fix the PR and run `arcwright dispatch --resume` to continue."

#### Task 5: Update config template

**File:** `src/arcwright_ai/cli/status.py`

5.1. Add `merge_wait_timeout` to the `_DEFAULT_CONFIG_YAML` scm section:
```yaml
scm:
  branch_template: "arcwright-ai/{story_slug}"
  # default_branch: ""          # empty = auto-detect
  # auto_merge: false            # set true for unattended overnight dispatch
  # merge_wait_timeout: 0        # seconds to wait for CI after auto-merge (0 = fire-and-forget)
  #                              # recommended: 1200 (20 min) when auto_merge is true
```

#### Task 6: Unit tests

**Files:** `tests/test_scm/test_pr.py`, `tests/test_engine/test_nodes.py`

6.1. **test_pr.py** — New tests for `merge_pull_request()`:
- `test_merge_pr_auto_flag_when_wait_timeout_positive` — verifies `--auto` flag in subprocess args when `wait_timeout > 0`
- `test_merge_pr_checks_watch_called_after_auto` — verifies `gh pr checks --watch --fail-fast` is called after `gh pr merge --auto`
- `test_merge_pr_returns_merged_on_ci_pass` — CI passes (exit 0), PR state is MERGED → returns `MergeOutcome.MERGED`
- `test_merge_pr_returns_ci_failed_on_check_failure` — CI fails (exit 1) → returns `MergeOutcome.CI_FAILED`
- `test_merge_pr_returns_timeout_on_asyncio_timeout` — `asyncio.wait_for` raises `TimeoutError` → returns `MergeOutcome.TIMEOUT`
- `test_merge_pr_no_wait_when_timeout_zero` — `wait_timeout=0` → no `--auto`, no `gh pr checks`, immediate merge (backward compat)
- `test_merge_pr_returns_skipped_never` — `MergeOutcome.SKIPPED` is only set by `commit_node`, never by `merge_pull_request()`
- `test_merge_pr_timeout_verify_actually_merged` — Mock `gh pr checks` to raise `TimeoutError`, but mock `gh pr view --json state` to return `"MERGED"` → asserts `MergeOutcome.MERGED` (not TIMEOUT)
- `test_merge_pr_timeout_subprocess_sigterm` — Timing simulation: mock `gh pr checks` to hang indefinitely, set `wait_timeout=2`, assert `proc.terminate()` is called (not `proc.kill()`), assert total elapsed time is ~2s (±tolerance)
- `test_merge_pr_auto_merge_not_allowed_stderr` — Mock `gh pr merge --auto` to fail with stderr containing `"auto-merge is not allowed"` → asserts `MergeOutcome.ERROR` and log message mentions repo settings

6.2. **test_pr.py** — Update existing tests:
- All existing `merge_pull_request` tests that assert `True`/`False` returns must be updated to assert `MergeOutcome` enum values instead. These all use `wait_timeout=0` (default), so behavior is preserved — only the return type changes.

6.3. **test_nodes.py** — New/updated tests for `commit_node`:
- `test_commit_node_sets_merge_outcome_merged` — auto-merge succeeds → `state.merge_outcome == "merged"`
- `test_commit_node_sets_merge_outcome_ci_failed` — CI fails → `state.merge_outcome == "ci_failed"`
- `test_commit_node_sets_merge_outcome_skipped` — auto-merge disabled → `state.merge_outcome == "skipped"`
- `test_commit_node_passes_wait_timeout_from_config` — verifies `merge_wait_timeout` from config flows through

6.4. **test_dispatch.py** (if exists) or inline in test_nodes:
- `test_dispatch_halts_on_ci_failed_merge_outcome` — verify epic loop breaks

### Acceptance Criteria

1. **Given** `scm.auto_merge: true` and `scm.merge_wait_timeout: 1200` **When** a story's PR is created **Then** `merge_pull_request()` calls `gh pr merge --auto` followed by `gh pr checks --watch --fail-fast` **And** blocks until CI completes or timeout is reached.

2. **Given** CI passes within the timeout **When** `gh pr checks` exits with code 0 **Then** `merge_pull_request()` verifies the PR merged and returns `MergeOutcome.MERGED` **And** the next story in the epic proceeds with `fetch_and_sync` finding the merged code.

3. **Given** CI fails **When** `gh pr checks` exits with code 1 **Then** `merge_pull_request()` returns `MergeOutcome.CI_FAILED` **And** the PR stays open with auto-merge queued **And** the epic dispatch loop halts after this story **And** a clear log message tells the developer to fix the PR and `--resume`.

4. **Given** CI doesn't complete within `merge_wait_timeout` seconds **When** the timeout fires **Then** the `gh pr checks` subprocess is killed **And** `merge_pull_request()` returns `MergeOutcome.TIMEOUT` **And** the epic dispatch loop halts **And** the PR stays open with auto-merge still queued (it will eventually merge if CI later passes).

5. **Given** `scm.merge_wait_timeout: 0` (default) **When** auto-merge is enabled **Then** `merge_pull_request()` uses the current fire-and-forget behavior (no `--auto`, immediate `gh pr merge`) **And** returns `MergeOutcome.MERGED` on success or `MergeOutcome.ERROR` on failure **And** the epic loop does NOT halt on failure (backward compatible, best-effort).

6. **Given** `scm.auto_merge: false` **When** `commit_node` runs **Then** `merge_pull_request()` is never called **And** `state.merge_outcome` is set to `"skipped"` **And** the epic loop continues.

7. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

8. **Given** story implementation is complete **When** `mypy --strict src/` is run **Then** zero errors.

9. **Given** existing tests **When** story is complete **Then** all existing tests pass (return type change from `bool` to `MergeOutcome` is the only breaking change — all existing test assertions updated).

## Additional Context

### Dependencies

- `gh` CLI >= 2.x (already a project dependency for PR creation)
- `asyncio.wait_for` (stdlib)
- No new package dependencies

### Testing Strategy

- **Unit tests**: Mock `asyncio.create_subprocess_exec` to control `gh` CLI behavior. Mock exit codes 0, 1, 8. Mock `asyncio.TimeoutError` for timeout path.
- **No integration test with real CI**: Real CI testing requires a GitHub repo with branch protection. This is tested manually or in actual epic dispatch runs. The existing `test_scm_integration.py` tests verify the git chain; gh CLI operations remain unit-tested with mocks.

### Notes

- **Backward compatibility**: `merge_wait_timeout: 0` (default) preserves exact current behavior. Existing users see no change.
- **Future: Option D1**: The `MergeOutcome` enum and `merge_outcome` field on `StoryState` lay groundwork for D1 (CI-chain workflows). A GitHub Actions workflow could read the merge outcome from state and trigger the next story.
- **`--auto` + branch protection**: Requires the GitHub repo to have "Allow auto-merge" enabled in Settings → General. If not enabled, `gh pr merge --auto` fails with stderr `"auto-merge is not allowed"` — parsed and returned as `MergeOutcome.ERROR` with an actionable log message.
- **`--auto` persistence after check failure**: Confirmed via GitHub docs — when CI fails, the auto-merge queue is **NOT** cancelled. The PR stays open with auto-merge still queued. When the developer pushes a fix, CI re-runs, and if checks pass, GitHub auto-merges the PR automatically. Auto-merge is only removed when: (a) an unauthorized contributor pushes to the head branch, (b) the base branch changes, or (c) someone manually calls `gh pr merge --disable-auto`. This is the **desired behavior** for our epic halt scenario: the developer fixes the PR, CI re-runs, auto-merge completes, and then `--resume` picks up the epic from where it left off with the merged code in place.
- **Required reviewers**: If branch protection requires human review, `gh pr checks --watch` will block until reviews are provided and CI passes. The timeout is the safety valve — after `merge_wait_timeout` seconds, the epic halts. This is the correct behavior: fully unattended execution is incompatible with required human reviewers.
