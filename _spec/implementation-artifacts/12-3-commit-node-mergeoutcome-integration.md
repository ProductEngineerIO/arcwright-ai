# Story 12.3: commit_node MergeOutcome Integration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the engine's commit_node,
I want to pass the configured `merge_wait_timeout` to `merge_pull_request()` and record the structured `MergeOutcome` on story state,
So that merge results flow correctly into provenance records and are available for the dispatch loop to inspect.

## Acceptance Criteria (BDD)

### AC 1: Pass merge_wait_timeout from config to merge_pull_request()

**Given** `engine/nodes.py` `commit_node` auto-merge block (~L1508–1555)
**When** `auto_merge` is `True` and `merge_pull_request()` is called
**Then** `merge_pull_request()` is called with `wait_timeout=state.config.scm.merge_wait_timeout`
**And** the existing `strategy="squash"` and `project_root=project_root` arguments are preserved

### AC 2: Replace bool logic with MergeOutcome switch

**Given** `commit_node` receives a `MergeOutcome` from `merge_pull_request()`
**When** the outcome is processed
**Then** the existing `merge_succeeded: bool` conditional is replaced with `MergeOutcome` switch logic:
  - `MERGED` → call `get_pull_request_merge_sha()`, fetch merge SHA, record provenance as success
  - `CI_FAILED` / `TIMEOUT` / `ERROR` → skip `get_pull_request_merge_sha()` (no merge SHA to fetch), record provenance with failure details, set `merge_sha = "not_merged"`
**And** the `MergeOutcome` value is used directly as `outcome.value` in the provenance `rationale` string (replacing the old `'success' if merge_succeeded else 'failed'` pattern)

### AC 3: Set merge_outcome on StoryState

**Given** the commit_node has completed SCM operations
**When** state is returned
**Then** `state.merge_outcome = merge_outcome.value` is set (string, e.g. `"merged"`, `"ci_failed"`)
**And** when `auto_merge` is `False`, `state.merge_outcome = MergeOutcome.SKIPPED.value` (i.e. `"skipped"`)
**And** when `auto_merge` is `True` but PR creation failed (`pr_url is None`), `state.merge_outcome = MergeOutcome.ERROR.value`

### AC 4: Provenance recording updated

**Given** the `ProvenanceEntry` for auto-merge (~L1538–1556)
**When** provenance is recorded
**Then** the `rationale` field reflects the `MergeOutcome` value:
  - `status=merged; strategy=squash; merge_sha=<sha>` on MERGED
  - `status=ci_failed; strategy=squash; merge_sha=not_merged` on CI_FAILED
  - `status=timeout; strategy=squash; merge_sha=not_merged` on TIMEOUT
  - `status=error; strategy=squash; merge_sha=not_merged` on ERROR
**And** the `decision` field remains `"Auto-merge PR after creation"`

### AC 5: Backward compatibility when wait_timeout=0

**Given** `merge_wait_timeout=0` (default)
**When** auto-merge runs
**Then** behavior is identical to current code — `merge_pull_request()` returns `MergeOutcome.MERGED` or `MergeOutcome.ERROR` (fire-and-forget), provenance records accordingly
**And** `state.merge_outcome` is set to the outcome value

### AC 6: Unit tests

**Given** the test suite
**When** tests are run
**Then** tests verify:
  - `test_commit_node_sets_merge_outcome_merged` — auto-merge succeeds → `state.merge_outcome == "merged"`
  - `test_commit_node_sets_merge_outcome_ci_failed` — CI fails → `state.merge_outcome == "ci_failed"`
  - `test_commit_node_sets_merge_outcome_skipped` — auto-merge disabled → `state.merge_outcome == "skipped"`
  - `test_commit_node_passes_wait_timeout_from_config` — verifies `merge_wait_timeout` from config flows through to `merge_pull_request()` call
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

## Tasks / Subtasks

- [x] Task 1: Import `MergeOutcome` in `nodes.py` (AC: #2)
  - [x] 1.1: In `src/arcwright_ai/engine/nodes.py`, update the import from `arcwright_ai.scm.pr` (~L42–44) to include `MergeOutcome`:
    ```python
    from arcwright_ai.scm.pr import (
        MergeOutcome,
        _detect_default_branch,
        generate_pr_body,
        get_pull_request_merge_sha,
        merge_pull_request,
        open_pull_request,
    )
    ```
  - [x] 1.2: Verify import is valid per package DAG: `engine → scm` is a valid edge. `nodes.py` already imports from `scm.pr` so this adds no new dependency.

- [x] Task 2: Update auto-merge block with `wait_timeout` and `MergeOutcome` (AC: #1, #2, #3, #4, #5)
  - [x] 2.1: In `commit_node()` auto-merge block (~L1508), pass `wait_timeout` to `merge_pull_request()`:
    ```python
    merge_outcome = await merge_pull_request(
        pr_url,
        strategy=merge_strategy,
        project_root=project_root,
        wait_timeout=state.config.scm.merge_wait_timeout,
    )
    ```
    Change local variable name from `merge_succeeded` to `merge_outcome` (type becomes `MergeOutcome`, not `bool`).

  - [x] 2.2: Replace the `if merge_succeeded:` conditional (~L1532) with a `MergeOutcome` check:
    ```python
    if merge_outcome == MergeOutcome.MERGED:
        try:
            merge_sha = await get_pull_request_merge_sha(pr_url, project_root=project_root) or "unknown"
        except Exception as exc:
            logger.warning(...)
    else:
        merge_sha = "not_merged"
    ```

  - [x] 2.3: Update provenance `rationale` string (~L1548) to use `merge_outcome.value` instead of the old ternary:
    ```python
    rationale=(
        f"merge_attempted_at={merge_attempted_at}; "
        f"status={merge_outcome.value}; "
        f"strategy={merge_strategy}; "
        f"pr_url={pr_url}; "
        f"merge_sha={merge_sha}"
    ),
    ```

  - [x] 2.4: Set `state.merge_outcome` after the auto-merge block completes. Place this INSIDE the `if pr_url is not None and state.config.scm.auto_merge:` block:
    ```python
    state.merge_outcome = merge_outcome.value
    ```
    This must be set regardless of which `MergeOutcome` value was returned.

- [x] Task 3: Handle auto_merge=False and PR creation failure (AC: #3)
  - [x] 3.1: When `state.config.scm.auto_merge` is `False` (the `else` branch of the auto-merge conditional), set:
    ```python
    state.merge_outcome = MergeOutcome.SKIPPED.value
    ```
    Import `MergeOutcome` is already available from Task 1.

  - [x] 3.2: When `pr_url is None` and `auto_merge` is True (PR creation failed), set:
    ```python
    state.merge_outcome = MergeOutcome.ERROR.value
    ```
    This handles the case where `open_pull_request()` returned `None`.

  - [x] 3.3: Ensure `state.merge_outcome` is set on ALL code paths through `commit_node()` that reach the auto-merge section. When `commit_hash is None` (no changes committed), `state.merge_outcome` remains `None` (the story had nothing to merge).

- [x] Task 4: Update exception handler for merge call (AC: #2)
  - [x] 4.1: The existing `try/except` around `merge_pull_request()` (~L1518) catches `Exception`. Update the except block to set `merge_outcome = MergeOutcome.ERROR` (instead of `merge_succeeded = False`).
  - [x] 4.2: Ensure `state.merge_outcome = merge_outcome.value` is still set after the except block (the variable must be defined on both the try and except paths).

- [x] Task 5: Unit tests (AC: #6)
  - [x] 5.1: In `tests/test_engine/test_nodes.py`, add `test_commit_node_sets_merge_outcome_merged`:
    - Mock `merge_pull_request` to return `MergeOutcome.MERGED`
    - Mock `get_pull_request_merge_sha` to return a SHA
    - Set `config.scm.auto_merge=True`
    - Assert `result.merge_outcome == "merged"`

  - [x] 5.2: Add `test_commit_node_sets_merge_outcome_ci_failed`:
    - Mock `merge_pull_request` to return `MergeOutcome.CI_FAILED`
    - Set `config.scm.auto_merge=True`
    - Assert `result.merge_outcome == "ci_failed"`
    - Assert `get_pull_request_merge_sha` was NOT called

  - [x] 5.3: Add `test_commit_node_sets_merge_outcome_skipped`:
    - Set `config.scm.auto_merge=False`
    - Assert `result.merge_outcome == "skipped"`
    - Assert `merge_pull_request` was NOT called

  - [x] 5.4: Add `test_commit_node_passes_wait_timeout_from_config`:
    - Set `config.scm.merge_wait_timeout=1200`
    - Set `config.scm.auto_merge=True`
    - Mock `merge_pull_request` → capture `wait_timeout` kwarg
    - Assert `merge_pull_request` was called with `wait_timeout=1200`

  - [x] 5.5: Run full suite: `uv run ruff check src/ tests/ && uv run mypy --strict src/ && uv run pytest` — zero failures, zero regressions

## Dev Notes

### Architecture Compliance

- **Package DAG (Mandatory):** `engine → scm → core` is a valid dependency chain. `nodes.py` already imports from `scm.pr` (L42–44: `merge_pull_request`, `open_pull_request`, `get_pull_request_merge_sha`, `generate_pr_body`, `_detect_default_branch`). Adding `MergeOutcome` to that import introduces no new package edge.
- **D10 (CI-Aware Merge Wait):** This story connects the D10 subsystem: wires the config timeout through to the merge function and records the structured outcome on state.
- **D11 (Agent SCM Guardrails):** The existing `base_ref` resolution and `commit_story()` call (added in Story 10.4) are preserved — this story only modifies the auto-merge block that runs AFTER the commit/push sequence.
- **Best-effort SCM pattern:** All merge operations remain wrapped in try/except. Failure sets `MergeOutcome.ERROR` on state but does not change the story's SUCCESS status. The halt decision is made by the dispatch loop (Story 12.4), not commit_node.
- **Provenance recording:** The existing `ProvenanceEntry` structure is preserved. Only the `rationale` string changes from boolean status to `MergeOutcome.value` string.

### Exact Code Locations

The auto-merge block in `commit_node()` spans approximately L1508–1555 in `nodes.py`:

```python
# Current code (to be replaced):
if pr_url is not None and state.config.scm.auto_merge:
    merge_attempted_at = datetime.now(tz=UTC).isoformat()
    merge_strategy = "squash"
    merge_succeeded = False           # ← becomes merge_outcome
    merge_sha = "not_merged"
    try:
        merge_succeeded = await merge_pull_request(
            pr_url,
            strategy=merge_strategy,
            project_root=project_root,  # ← add wait_timeout=...
        )
    except Exception as exc:
        logger.warning(...)

    if merge_succeeded:               # ← becomes if merge_outcome == MergeOutcome.MERGED:
        try:
            merge_sha = await get_pull_request_merge_sha(...)
        except Exception as exc:
            ...

    merge_entry = ProvenanceEntry(
        decision="Auto-merge PR after creation",
        ...
        rationale=(               # ← update status= to use merge_outcome.value
            f"... status={'success' if merge_succeeded else 'failed'}; ..."
        ),
        ...
    )
```

### Existing Test Patterns (test_nodes.py)

commit_node tests (~L1817–1920) use these mocking patterns:
- `@patch("arcwright_ai.engine.nodes.commit_story")` → mock commit
- `@patch("arcwright_ai.engine.nodes.remove_worktree")` → mock cleanup
- `@patch("arcwright_ai.engine.nodes._detect_default_branch")` → mock branch detection
- `@patch("arcwright_ai.engine.nodes.git")` → mock git commands
- `@patch("arcwright_ai.engine.nodes.merge_pull_request")` → mock merge (add this for new tests)
- `@patch("arcwright_ai.engine.nodes.open_pull_request")` → mock PR creation (add this for new tests)

State construction in tests follows `StoryState(story_id=..., epic_id=..., run_id=..., story_path=..., project_root=..., config=RunConfig(...))` pattern.

### Previous Story Intelligence (Story 12.2)

- Story 12.2 changes `merge_pull_request()` return type from `bool` → `MergeOutcome`. This story relies on that return type change.
- Story 12.2 adds `wait_timeout` parameter. This story passes `state.config.scm.merge_wait_timeout` to it.
- The `MergeOutcome.SKIPPED` value is ONLY set in this story (commit_node), never returned by `merge_pull_request()` itself.

### Files Touched

- `src/arcwright_ai/engine/nodes.py` — Update auto-merge block: import `MergeOutcome`, pass `wait_timeout`, switch on outcome, set `state.merge_outcome`
- `tests/test_engine/test_nodes.py` — 4 new/updated commit_node tests

### References

- [Source: _spec/implementation-artifacts/ci-aware-merge-wait.md#Task 3] — Task 3 implementation plan
- [Source: _spec/planning-artifacts/architecture.md#D10] — CI-Aware Merge Wait architectural decision
- [Source: _spec/planning-artifacts/epics.md#Story 12.3] — Epic story definition with AC
- [Source: src/arcwright_ai/engine/nodes.py#L1508–1555] — Current auto-merge block in commit_node
- [Source: src/arcwright_ai/engine/nodes.py#L42–44] — Current scm.pr imports
- [Source: tests/test_engine/test_nodes.py#L1817–1920] — Existing commit_node tests

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

N/A

### Completion Notes List

- `MergeOutcome` was already imported in `nodes.py` from Story 12.2's prior work — Task 1 was already satisfied.
- Added `wait_timeout=state.config.scm.merge_wait_timeout` to `merge_pull_request()` call (AC #1, #5).
- Updated provenance `rationale` to use `merge_outcome.value` replacing the old `'success'/'failed'` ternary (AC #4).
- Set `state.merge_outcome = merge_outcome.value` inside the auto-merge block (AC #3).
- Added `elif commit_hash is not None and state.config.scm.auto_merge:` branch → `MergeOutcome.ERROR.value` when PR creation failed (AC #3).
- Added `elif commit_hash is not None:` branch → `MergeOutcome.SKIPPED.value` when `auto_merge=False` (AC #3).
- All paths respect AC #3 note: when `commit_hash is None`, `state.merge_outcome` remains `None`.
- Fixed existing `test_commit_node_records_merge_provenance` to assert `status=merged` (was `status=success`) to match new rationale format.
- Added 4 new tests: `test_commit_node_sets_merge_outcome_merged`, `test_commit_node_sets_merge_outcome_ci_failed`, `test_commit_node_sets_merge_outcome_skipped`, `test_commit_node_passes_wait_timeout_from_config`.
- All 956 tests pass; `ruff check` and `mypy --strict src/` clean.

### File List

- arcwright-ai/src/arcwright_ai/engine/nodes.py
- arcwright-ai/tests/test_engine/test_nodes.py
- _spec/implementation-artifacts/12-3-commit-node-mergeoutcome-integration.md
- _spec/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-03-17: Implemented Story 12.3 — pass `merge_wait_timeout` to `merge_pull_request()`, replace bool logic with `MergeOutcome` switch, set `state.merge_outcome` on all SCM code paths, add 4 unit tests. (Dev: Claude Sonnet 4.6)
- 2026-03-17: Senior Developer Review (AI) completed. ACs validated against implementation and focused tests; story approved and moved to done. (Reviewer: Ed)

## Senior Developer Review (AI)

Date: 2026-03-17
Reviewer: Ed
Outcome: Approved

### Scope Reviewed

- Story file acceptance criteria and completed tasks
- Implementation changes in `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- Test changes in `arcwright-ai/tests/test_engine/test_nodes.py`
- Git delta cross-check against Dev Agent Record File List

### Findings

- No HIGH issues found.
- No MEDIUM issues found.
- No LOW issues found.

### AC Validation Summary

- AC1: Implemented. `commit_node()` passes `wait_timeout=state.config.scm.merge_wait_timeout` to `merge_pull_request()`.
- AC2: Implemented. Merge handling uses `MergeOutcome`; merge SHA lookup occurs only for `MergeOutcome.MERGED`.
- AC3: Implemented. `state.merge_outcome` set for merged path, auto-merge disabled path (`skipped`), and PR creation failure path (`error`); remains `None` when no commit exists.
- AC4: Implemented. Provenance rationale now records `status={merge_outcome.value}` and expected merge SHA semantics.
- AC5: Implemented by wiring. `merge_wait_timeout` is forwarded directly; behavior at zero remains delegated to `merge_pull_request()`.
- AC6: Implemented. Story-specific merge outcome and timeout tests are present and passing.

### Verification Run

- Command: `uv run pytest tests/test_engine/test_nodes.py -k "merge_outcome or wait_timeout or records_merge_provenance or status_success_on_merge_failure"`
- Result: 6 passed, 0 failed
