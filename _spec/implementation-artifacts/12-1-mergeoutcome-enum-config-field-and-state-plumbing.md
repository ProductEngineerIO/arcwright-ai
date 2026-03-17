# Story 12.1: MergeOutcome Enum, Config Field & State Plumbing

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer configuring Arcwright AI for CI-aware epic dispatch,
I want a `merge_wait_timeout` config field and a `MergeOutcome` enum,
So that the merge subsystem can report structured outcomes and the dispatch loop can make halt decisions.

## Acceptance Criteria (BDD)

### AC 1: merge_wait_timeout field on ScmConfig

**Given** `core/config.py` `ScmConfig` Pydantic model (L245–264)
**When** `merge_wait_timeout` is added
**Then** `ScmConfig` gains `merge_wait_timeout: int = 0` — seconds to wait for CI after auto-merge; `0` = fire-and-forget (backward compatible default)
**And** the field follows the existing frozen Pydantic pattern: `ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)`
**And** `_KNOWN_SECTION_FIELDS["scm"]` auto-includes `merge_wait_timeout` via `frozenset(ScmConfig.model_fields.keys())` (no manual update needed)
**And** existing config round-trip tests still pass (new field has a default)

### AC 2: Footgun warning for auto_merge + timeout=0

**Given** config is loaded with `auto_merge=True` and `merge_wait_timeout=0`
**When** config validation runs
**Then** a structured log warning is emitted: _"auto_merge is enabled but merge_wait_timeout is 0 — CI checks will not be waited for. Set merge_wait_timeout to enable chain integrity."_
**And** the warning uses `logger.warning("config.scm.merge_wait_no_ci_wait", extra={"data": {...}})` following existing structured logging conventions

### AC 3: MergeOutcome StrEnum

**Given** `scm/pr.py` module
**When** `MergeOutcome` is defined
**Then** `MergeOutcome` is a `StrEnum` with values: `MERGED = "merged"`, `SKIPPED = "skipped"`, `CI_FAILED = "ci_failed"`, `TIMEOUT = "timeout"`, `ERROR = "error"`
**And** `MergeOutcome` is exported from `scm/__init__.py`

### AC 4: StoryState.merge_outcome field

**Given** `engine/state.py` `StoryState` model
**When** `merge_outcome` field is added
**Then** `StoryState` gains `merge_outcome: str | None = None`
**And** the field is `str | None` (not `MergeOutcome`) to avoid cross-package import from `scm` into `engine/state.py` — the dispatch loop compares string values

### AC 5: Config template update

**Given** `cli/status.py` `_DEFAULT_CONFIG_YAML` (L53–96)
**When** the template is updated
**Then** the scm section includes a commented-out `merge_wait_timeout` line:
```yaml
  # merge_wait_timeout: 0        # seconds to wait for CI after auto-merge (0 = fire-and-forget)
  #                              # recommended: 1200 (20 min) when auto_merge is true
```

### AC 6: Unit tests

**Given** the test suite
**When** tests are run
**Then** tests verify: (1) `merge_wait_timeout` defaults to 0, (2) config loads with explicit timeout value, (3) footgun warning is logged when `auto_merge=True` + `timeout=0`, (4) `MergeOutcome` enum values match expected strings, (5) `StoryState` accepts `merge_outcome` field
**And** `ruff check .` and `mypy --strict src/` pass with zero issues

## Tasks / Subtasks

- [x] Task 1: Add `merge_wait_timeout` to `ScmConfig` (AC: #1)
  - [x] 1.1: In `src/arcwright_ai/core/config.py`, add `merge_wait_timeout: int = 0` field to `ScmConfig` class (after `auto_merge` field, ~L260). No docstring needed — field name is self-documenting. The field follows the same `frozen=True` pattern as all other ScmConfig fields.
  - [x] 1.2: Verify `_KNOWN_SECTION_FIELDS["scm"]` (L298–310) is derived from `frozenset(ScmConfig.model_fields.keys())` — no manual update required since the mapping auto-derives from model fields.

- [x] Task 2: Add footgun warning for `auto_merge=True` + `merge_wait_timeout=0` (AC: #2)
  - [x] 2.1: In `src/arcwright_ai/core/config.py`, locate `load_config()` or the `ScmConfig` validator/post-init. Add a `model_validator(mode="after")` on `ScmConfig` (or add the check in the existing config loading path) that emits: `logger.warning("config.scm.merge_wait_no_ci_wait", extra={"data": {"auto_merge": True, "merge_wait_timeout": 0}})` when `self.auto_merge is True and self.merge_wait_timeout == 0`.
  - [x] 2.2: **Alternative approach** (preferred if `ScmConfig` is frozen and validators aren't idiomatic): Add the warning in `load_config()` after the `ScmConfig` is constructed. Check `config.scm.auto_merge and config.scm.merge_wait_timeout == 0` and log the warning there. This avoids side effects in the Pydantic model itself.

- [x] Task 3: Add `MergeOutcome` StrEnum (AC: #3)
  - [x] 3.1: In `src/arcwright_ai/scm/pr.py`, add near the top of the file (after existing imports, before `_MERGE_STRATEGY_FLAGS` constant at ~L30):
    ```python
    from enum import StrEnum

    class MergeOutcome(StrEnum):
        MERGED = "merged"
        SKIPPED = "skipped"
        CI_FAILED = "ci_failed"
        TIMEOUT = "timeout"
        ERROR = "error"
    ```
  - [x] 3.2: In `src/arcwright_ai/scm/__init__.py`, add `MergeOutcome` to imports from `arcwright_ai.scm.pr` and add it to `__all__`. The existing pattern imports `generate_pr_body`, `get_pull_request_merge_sha`, `merge_pull_request` from `pr.py` — add `MergeOutcome` to that same import line.

- [x] Task 4: Add `merge_outcome` field to `StoryState` (AC: #4)
  - [x] 4.1: In `src/arcwright_ai/engine/state.py`, add `merge_outcome: str | None = None` to `StoryState` class. Place it after `pr_url: str | None = None` (~L63) for logical grouping. The type is `str | None` (not `MergeOutcome`) to preserve the `engine → core` package DAG — `engine/state.py` must not import from `scm`.
  - [x] 4.2: Update the `StoryState` docstring to document the new field: `merge_outcome: Structured merge result from commit_node. Read by dispatch loop to decide epic continuation. None until commit_node runs.`

- [x] Task 5: Update `_DEFAULT_CONFIG_YAML` template (AC: #5)
  - [x] 5.1: In `src/arcwright_ai/cli/status.py`, in the `_DEFAULT_CONFIG_YAML` string (L53–96), add to the scm section after the `auto_merge` comment (~L93):
    ```yaml
      # merge_wait_timeout: 0        # seconds to wait for CI after auto-merge (0 = fire-and-forget)
      #                              # recommended: 1200 (20 min) when auto_merge is true
    ```

- [x] Task 6: Unit tests (AC: #6)
  - [x] 6.1: In `tests/test_core/test_config.py`, add test: `ScmConfig` with default `merge_wait_timeout` → value is `0`
  - [x] 6.2: In `tests/test_core/test_config.py`, add test: `ScmConfig` with explicit `merge_wait_timeout=1200` → value is `1200`
  - [x] 6.3: In `tests/test_core/test_config.py`, add test: footgun warning logged when `auto_merge=True` and `merge_wait_timeout=0` (use `caplog` to capture structured log)
  - [x] 6.4: In `tests/test_scm/test_pr.py`, add test: `MergeOutcome` enum values match `{"merged", "skipped", "ci_failed", "timeout", "error"}`
  - [x] 6.5: In `tests/test_engine/test_state.py` (or `test_nodes.py`), add test: `StoryState` accepts `merge_outcome="merged"` and `merge_outcome=None`
  - [x] 6.6: Run full suite: `uv run ruff check src/ tests/ && uv run mypy --strict src/ && uv run pytest` — zero failures, zero regressions

## Dev Notes

### Architecture Compliance

- **Package DAG (Mandatory):** `core` is the foundation package. `scm` depends on `core`. `engine` depends on `core`. Changes span `core/config.py` (config field), `scm/pr.py` (enum), and `engine/state.py` (state field). These are independent leaves — no circular imports.
- **D10 (CI-Aware Merge Wait):** This story creates the data structures that D10 depends on. The `MergeOutcome` enum and `merge_wait_timeout` config field are the foundation for the CI-wait rewrite in Story 12.2.
- **D7 (No Force Operations):** No git operations in this story — purely data model additions.
- **Frozen Pydantic pattern:** `ScmConfig` uses `ConfigDict(frozen=True)`. The new `merge_wait_timeout` field is immutable after construction, consistent with all other config fields.
- **StoryState is mutable:** `StoryState` uses `ConfigDict(frozen=False, extra="forbid")`. The new `merge_outcome` field is set by `commit_node` during graph traversal.

### Exact Code Locations

| Change | File | Line | Detail |
|--------|------|------|--------|
| `merge_wait_timeout` field | `src/arcwright_ai/core/config.py` | ~L260 (after `auto_merge`) | `merge_wait_timeout: int = 0` |
| Footgun warning | `src/arcwright_ai/core/config.py` | In `load_config()` | Check `scm.auto_merge and scm.merge_wait_timeout == 0` |
| `MergeOutcome` enum | `src/arcwright_ai/scm/pr.py` | ~L28 (before `_MERGE_STRATEGY_FLAGS`) | `StrEnum` with 5 values |
| `__init__.py` export | `src/arcwright_ai/scm/__init__.py` | ~L10 | Add `MergeOutcome` to imports and `__all__` |
| `merge_outcome` field | `src/arcwright_ai/engine/state.py` | ~L63 (after `pr_url`) | `merge_outcome: str \| None = None` |
| Config template | `src/arcwright_ai/cli/status.py` | ~L93 | Add commented YAML line |

### Existing Test Patterns

- **Config tests:** `tests/test_core/test_config.py` — uses `ScmConfig(...)` constructor directly, asserts field defaults
- **Structured log tests:** Use `caplog.at_level(logging.WARNING)` and check `caplog.records` for event names
- **State tests:** Construct `StoryState(...)` with required fields and check optional field defaults

### Files Touched

- `src/arcwright_ai/core/config.py` — `ScmConfig.merge_wait_timeout` field + footgun warning
- `src/arcwright_ai/scm/pr.py` — `MergeOutcome` StrEnum definition
- `src/arcwright_ai/scm/__init__.py` — Export `MergeOutcome`
- `src/arcwright_ai/engine/state.py` — `StoryState.merge_outcome` field
- `src/arcwright_ai/cli/status.py` — Config template update
- `tests/test_core/test_config.py` — Config field + warning tests
- `tests/test_scm/test_pr.py` — `MergeOutcome` enum tests
- `tests/test_engine/test_state.py` (or `test_nodes.py`) — StoryState field test

### References

- [Source: _spec/implementation-artifacts/ci-aware-merge-wait.md#Task 1] — Task 1 implementation plan
- [Source: _spec/planning-artifacts/architecture.md#D10] — CI-Aware Merge Wait architectural decision
- [Source: _spec/planning-artifacts/epics.md#Story 12.1] — Epic story definition with AC
- [Source: src/arcwright_ai/core/config.py#ScmConfig] — Current ScmConfig class (L245–264)
- [Source: src/arcwright_ai/engine/state.py#StoryState] — Current StoryState class (L20–68)
- [Source: src/arcwright_ai/scm/pr.py#L30] — Location for MergeOutcome enum
- [Source: src/arcwright_ai/scm/__init__.py] — Current exports list

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

None required — all tasks implemented cleanly on first attempt.

### Completion Notes List

- ✅ Task 1: Added `merge_wait_timeout: int = 0` to `ScmConfig` after `auto_merge`. Field is immutable (frozen=True). `_KNOWN_SECTION_FIELDS["scm"]` auto-derives from model fields — no manual update needed.
- ✅ Task 2: Added `logging` import and module-level `logger` to `config.py`. Footgun warning added in `load_config()` after `RunConfig.model_validate()` — preferred approach (Task 2.2) to avoid side effects in frozen Pydantic model.
- ✅ Task 3: Added `MergeOutcome(StrEnum)` to `scm/pr.py` with 5 values (MERGED, SKIPPED, CI_FAILED, TIMEOUT, ERROR). Added `from enum import StrEnum` import. Exported from `scm/__init__.py`.
- ✅ Task 4: Added `merge_outcome: str | None = None` to `StoryState` after `pr_url`. Type is `str | None` (not `MergeOutcome`) to preserve `engine → core` DAG. Docstring updated.
- ✅ Task 5: Updated `_DEFAULT_CONFIG_YAML` in `cli/status.py` with commented `merge_wait_timeout` line and recommendation comment.
- ✅ Task 6: 9 new unit tests added across 3 test files. All 48 config tests, 164 scm+engine tests pass. `ruff check` clean. `mypy --strict` clean on all changed files.

### File List

- arcwright-ai/src/arcwright_ai/core/config.py
- arcwright-ai/src/arcwright_ai/scm/pr.py
- arcwright-ai/src/arcwright_ai/scm/__init__.py
- arcwright-ai/src/arcwright_ai/engine/state.py
- arcwright-ai/src/arcwright_ai/cli/status.py
- arcwright-ai/tests/test_core/test_config.py
- arcwright-ai/tests/test_scm/test_pr.py
- arcwright-ai/tests/test_engine/test_state.py

## Change Log

- 2026-03-17: Story 12.1 implemented — `ScmConfig.merge_wait_timeout` field, footgun warning, `MergeOutcome` StrEnum, `StoryState.merge_outcome` field, config template update, 9 new unit tests. All ACs satisfied.
- 2026-03-17: Code review completed with no high/medium/low findings; lint, mypy strict, targeted tests, and full pytest suite passed.
