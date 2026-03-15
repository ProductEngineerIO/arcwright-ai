# Story 9.3: Auto-Merge PR After Creation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running overnight dispatches,
I want PRs to auto-merge after creation when configured,
so that completed stories flow through to the default branch without manual intervention.

## Acceptance Criteria (BDD)

1. **Given** `scm/pr.py` module **When** `merge_pull_request(pr_url: str, strategy: str = "squash", *, project_root: Path) -> bool` is called **Then** it extracts the PR number from the `pr_url` returned by `open_pull_request()` **And** runs `gh pr merge <pr_number> --squash --delete-branch` to squash-merge and clean up the remote branch **And** returns `True` on success, `False` on merge failure (e.g., merge conflicts, required reviews pending).

2. **Given** `engine/nodes.py` `commit_node` **When** a PR is successfully created (`pr_url is not None`) and `state.config.scm.auto_merge is True` **Then** `commit_node` calls `merge_pull_request(pr_url, project_root=project_root)` after `open_pull_request()`.

3. **Given** `merge_pull_request()` returns `False` (merge failure) **When** `commit_node` processes the result **Then** merge failure is non-fatal — the PR remains open, merge failure is logged to provenance as a warning, and the story is still marked as `SUCCESS` (the code was committed and PR created; merge is best-effort).

4. **Given** `scm.auto_merge` is `False` (default) **When** `commit_node` runs **Then** `merge_pull_request()` is never called — existing behavior preserved.

5. **Given** `--delete-branch` flag is passed to `gh pr merge` **When** merge succeeds **Then** the remote `arcwright-ai/<story-slug>` branch is cleaned up after merge, reducing branch clutter.

6. **Given** an epic dispatch with multiple stories **When** auto-merge is enabled **Then** auto-merge happens per-story immediately after PR creation (not batched at the end), so subsequent stories can build on merged changes when combined with Story 9.2's `fetch_and_sync`.

7. **Given** `merge_pull_request()` succeeds **When** provenance is recorded **Then** the provenance entry records: merge attempt timestamp, success/failure, merge strategy, resulting merge commit SHA (when successful).

8. **Given** `merge_pull_request()` is called with a non-squash strategy **When** `strategy="merge"` or `strategy="rebase"` **Then** the `--squash` flag is replaced with the corresponding `--merge` or `--rebase` flag passed to `gh pr merge`. Default remains `"squash"`.

9. **Given** `merge_pull_request()` is called **When** `gh` CLI is not on PATH **Then** the function returns `False` immediately **And** logs `scm.pr.merge.skipped` with reason `"gh_not_found"`.

10. **Given** `merge_pull_request()` is called **When** the PR URL cannot be parsed for a PR number **Then** the function returns `False` **And** logs `scm.pr.merge.skipped` with reason `"invalid_pr_url"`.

11. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

12. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

14. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All existing tests continue to pass.

15. **Given** new unit tests in `tests/test_scm/test_pr.py` **When** the test suite runs **Then** tests cover:
    (a) `merge_pull_request` calls correct `gh pr merge <number> --squash --delete-branch` command;
    (b) `merge_pull_request` returns `True` on `gh` success (returncode 0);
    (c) `merge_pull_request` returns `False` on merge failure (returncode non-zero) without raising;
    (d) `merge_pull_request` extracts PR number correctly from various URL formats (e.g., `https://github.com/owner/repo/pull/42`);
    (e) `merge_pull_request` returns `False` when `gh` CLI is not found on PATH;
    (f) `merge_pull_request` passes `--merge` or `--rebase` when non-default strategy is given;
    (g) `merge_pull_request` logs `scm.pr.merge` structured event on success with merge commit SHA;
    (h) `merge_pull_request` logs `scm.pr.merge.failed` warning on failure;
    (i) `merge_pull_request` returns `False` on invalid PR URL (no `/pull/<number>`);
    (j) `merge_pull_request` returns `False` on subprocess exception without crashing.

16. **Given** new unit tests in `tests/test_engine/test_nodes.py` **When** the test suite runs **Then** tests cover:
    (a) `commit_node` calls `merge_pull_request` when `auto_merge` is `True` and `pr_url` is not `None`;
    (b) `commit_node` does NOT call `merge_pull_request` when `auto_merge` is `False`;
    (c) `commit_node` does NOT call `merge_pull_request` when `pr_url` is `None` (even if `auto_merge` is `True`);
    (d) `commit_node` records provenance entry with merge metadata on successful merge;
    (e) `commit_node` status remains `SUCCESS` when merge fails (non-fatal).

## Tasks / Subtasks

- [x] Task 1: Implement `merge_pull_request()` function in `scm/pr.py` (AC: #1, #5, #8, #9, #10)
  - [x] 1.1: Function signature: `async def merge_pull_request(pr_url: str, strategy: str = "squash", *, project_root: Path) -> bool`.
  - [x] 1.2: Check `shutil.which("gh")` — if `None`, log `scm.pr.merge.skipped` warning with `reason="gh_not_found"` and return `False`.
  - [x] 1.3: Extract PR number from `pr_url` using regex: `re.search(r"/pull/(\d+)$", pr_url)`. If parsing fails, log `scm.pr.merge.skipped` warning with `reason="invalid_pr_url"` and return `False`.
  - [x] 1.4: Map `strategy` to `gh` flag: `"squash"` → `"--squash"`, `"merge"` → `"--merge"`, `"rebase"` → `"--rebase"`. Default is `"--squash"`.
  - [x] 1.5: Run `asyncio.create_subprocess_exec("gh", "pr", "merge", pr_number, strategy_flag, "--delete-branch", cwd=str(project_root), stdout=PIPE, stderr=PIPE)`.
  - [x] 1.6: On success (returncode 0): parse stdout for merge commit SHA if present (e.g., `re.search(r"[0-9a-f]{7,40}", stdout)`), log `scm.pr.merge` info event with `{"pr_url": pr_url, "pr_number": pr_number, "strategy": strategy, "merge_sha": merge_sha}`, return `True`.
  - [x] 1.7: On failure (returncode != 0): log `scm.pr.merge.failed` warning with `{"pr_url": pr_url, "pr_number": pr_number, "stderr": stderr, "returncode": returncode}`, return `False`.
  - [x] 1.8: Catch any exception from subprocess execution → log `scm.pr.merge.failed` warning with `reason="subprocess_error"`, return `False`.
  - [x] 1.9: Google-style docstring with Args, Returns sections.

- [x] Task 2: Update `__all__` and package exports (AC: #1)
  - [x] 2.1: Add `"merge_pull_request"` to `scm/pr.py` `__all__`.
  - [x] 2.2: Add `merge_pull_request` to `scm/__init__.py` imports and `__all__`.

- [x] Task 3: Wire `merge_pull_request` into `commit_node` (AC: #2, #3, #4, #6, #7)
  - [x] 3.1: Add import for `merge_pull_request` from `scm/pr.py` in `engine/nodes.py` (line 35, alongside existing `_detect_default_branch`, `generate_pr_body`, `open_pull_request` imports).
  - [x] 3.2: After the existing `open_pull_request()` success block and PR URL persistence in `run.yaml`, add auto-merge logic gated on `state.config.scm.auto_merge`:
    ```python
    # Auto-merge PR when configured (Story 9.3)
    if pr_url is not None and state.config.scm.auto_merge:
        merge_succeeded = False
        try:
            merge_succeeded = await merge_pull_request(
                pr_url, project_root=project_root
            )
        except Exception as exc:
            logger.warning(
                "scm.pr.merge.error",
                extra={"data": {"story": story_slug, "error": str(exc)}},
            )
        # Record merge provenance (best-effort)
        try:
            checkpoint_dir = (
                state.project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / DIR_STORIES / story_slug
            )
            provenance_path = checkpoint_dir / VALIDATION_FILENAME
            entry = ProvenanceEntry(
                decision="Auto-merge PR after creation",
                alternatives=["manual merge", "skip merge"],
                rationale=(
                    f"Auto-merge {'succeeded' if merge_succeeded else 'failed'} "
                    f"for PR {pr_url} using squash strategy"
                ),
                ac_references=["FR39", "D7"],
                timestamp=datetime.now(tz=UTC).isoformat(),
            )
            await append_entry(provenance_path, entry)
        except Exception as prov_exc:
            logger.warning(
                "provenance.write_error",
                extra={"data": {"story": story_slug, "error": str(prov_exc)}},
            )
    ```
  - [x] 3.3: Record merge provenance entry via `append_entry()` after merge attempt. Decision: "Auto-merge PR after creation", rationale includes success/failure, PR URL, merge strategy. References: `["FR39", "D7"]`. Timestamp from `datetime.now(tz=UTC).isoformat()`. Follow the existing pattern from `budget_check_node` (lines ~350-380).
  - [x] 3.4: Merge failure does NOT change story status — `state.status` remains `SUCCESS`.
  - [x] 3.5: When `auto_merge` is `False` or `pr_url` is `None`, skip the merge block entirely — zero behavioral change to existing flow.
  - [x] 3.6: The `open_pull_request()` call already passes `default_branch=state.config.scm.default_branch` (confirmed in current code). Verify this is still the case and no additional change needed.

- [x] Task 4: Update autouse fixture in `tests/test_engine/test_nodes.py` (AC: #14)
  - [x] 4.1: In the `_mock_output_functions` autouse fixture (line ~71), add:
    ```python
    monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", AsyncMock(return_value=False))
    ```
    This ensures existing `commit_node` tests don't break — `merge_pull_request` is always stubbed, and since `auto_merge` defaults to `False` in `RunConfig`, the merge path is never triggered in existing tests.

- [x] Task 5: Create unit tests for `merge_pull_request` in `tests/test_scm/test_pr.py` (AC: #14, #15)
  - [x] 5.1: Test `test_merge_pull_request_calls_gh_merge_squash` — verify `gh pr merge <number> --squash --delete-branch` is called with correct args.
  - [x] 5.2: Test `test_merge_pull_request_returns_true_on_success` — returncode 0 → `True`.
  - [x] 5.3: Test `test_merge_pull_request_returns_false_on_failure` — returncode non-zero → `False`, no exception raised.
  - [x] 5.4: Test `test_merge_pull_request_extracts_pr_number_from_url` — parses `https://github.com/owner/repo/pull/42` → `"42"`.
  - [x] 5.5: Test `test_merge_pull_request_returns_false_gh_not_found` — `shutil.which("gh")` returns `None` → `False`.
  - [x] 5.6: Test `test_merge_pull_request_passes_merge_strategy` — strategy `"merge"` → `--merge` flag.
  - [x] 5.7: Test `test_merge_pull_request_passes_rebase_strategy` — strategy `"rebase"` → `--rebase` flag.
  - [x] 5.8: Test `test_merge_pull_request_logs_success_event` — on success, `scm.pr.merge` info is logged with merge metadata.
  - [x] 5.9: Test `test_merge_pull_request_logs_failure_warning` — on failure, `scm.pr.merge.failed` warning is logged.
  - [x] 5.10: Test `test_merge_pull_request_returns_false_on_invalid_url` — invalid PR URL (no `/pull/<number>`) → `False`.
  - [x] 5.11: Test `test_merge_pull_request_returns_false_on_subprocess_exception` — `asyncio.create_subprocess_exec` raises → `False`, no crash.

- [x] Task 6: Create unit tests for `commit_node` auto-merge integration in `tests/test_engine/test_nodes.py` (AC: #14, #16)
  - [x] 6.1: Test `test_commit_node_calls_merge_when_auto_merge_enabled` — `auto_merge=True` + `pr_url` set → `merge_pull_request` called with correct args.
  - [x] 6.2: Test `test_commit_node_skips_merge_when_auto_merge_disabled` — `auto_merge=False` → `merge_pull_request` NOT called.
  - [x] 6.3: Test `test_commit_node_skips_merge_when_pr_url_none` — `auto_merge=True` + `pr_url=None` → `merge_pull_request` NOT called.
  - [x] 6.4: Test `test_commit_node_records_merge_provenance` — verify `append_entry` called with merge metadata (ProvenanceEntry with "Auto-merge" in decision).
  - [x] 6.5: Test `test_commit_node_status_success_on_merge_failure` — merge returns `False`, story status remains `SUCCESS`.

- [x] Task 7: Run quality gates (AC: #11, #12, #13, #14)
  - [x] 7.1: `ruff check .` — zero violations against FULL repository.
  - [x] 7.2: `ruff format --check .` — zero formatting issues.
  - [x] 7.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 7.4: `pytest` — all tests pass (existing + new). 912 tests pass (883 baseline + 29 new).
  - [x] 7.5: Verify Google-style docstrings on all modified/new functions.

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: This story touches `scm/pr.py` (new function), `engine/nodes.py` (wiring), and `output/provenance.py` (provenance recording via existing `append_entry`). Valid paths: `engine → scm → core`, `engine → output → core`. No DAG violations.

**Decision 7 — Git Operations Strategy**: The architecture specifies: "Push + PR after validation. Optional auto-merge via `gh pr merge --squash` when `scm.auto_merge` is enabled." This story implements the `merge_pull_request()` function and wires it into `commit_node`.

**Decision 7 — No Force Operations**: The architecture mandates: "No force operations — no `--force`, no `reset --hard`, no rebase." Using `gh pr merge --squash --delete-branch` is permitted — it's a GitHub API operation, not a git force push. The `--delete-branch` flag only deletes the merged remote branch (standard post-merge cleanup).

**Best-Effort Pattern**: Consistent with `push_branch`, `open_pull_request`, and all SCM operations in `commit_node` — merge is best-effort. Failures are logged warnings, never halt the story. Story status remains `SUCCESS` regardless of merge outcome.

### Current State Analysis — What Already Exists

1. **`scm/pr.py`** (730 lines): Has `generate_pr_body()`, `open_pull_request()`, `_detect_default_branch()`. `open_pull_request()` returns `str | None` (the PR URL). This story adds `merge_pull_request()` which consumes that URL.

2. **`engine/nodes.py` `commit_node`** (lines ~1317-1510): Currently has this flow:
   ```
   commit_story() → push_branch() → generate_pr_body() → open_pull_request()
       → update_story_status(pr_url=...) → remove_worktree()
   ```
   This story inserts `merge_pull_request()` between the PR URL persistence and the worktree removal, gated on `state.config.scm.auto_merge`.

3. **`core/config.py` `ScmConfig`** (from Story 9.1): Already has `auto_merge: bool = False` at line 238. The field exists and is loaded from config. This story reads it in `commit_node` as `state.config.scm.auto_merge`.

4. **`scm/__init__.py`**: Exports from `branch.py` and `pr.py`. Currently exports `generate_pr_body` from `pr.py`. This story adds `merge_pull_request` to exports.

5. **`scm/pr.py` `__all__`**: Currently `["generate_pr_body", "open_pull_request"]`. Add `"merge_pull_request"`.

6. **Provenance recording pattern**: `budget_check_node` and `validate_node` both use `append_entry(provenance_path, ProvenanceEntry(...))`. Same pattern applies here for merge provenance.

7. **`open_pull_request()` call in `commit_node`** (line ~1442): Currently passes `default_branch=state.config.scm.default_branch`:
   ```python
   pr_url = await open_pull_request(
       branch_name,
       story_slug,
       pr_body,
       project_root=project_root,
       default_branch=state.config.scm.default_branch,
   )
   ```
   This already threads the config default branch. Verify no changes needed here.

8. **Test patterns in `test_pr.py`**: Tests use `monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", ...)` for `gh` CLI checks, `MagicMock` for subprocess proc objects, `AsyncMock` for `communicate()`, and `patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", ...)` for subprocess execution.

9. **Test patterns in `test_nodes.py`**: The `_mock_output_functions` autouse fixture patches all external I/O including SCM functions. Tests for `commit_node` use `monkeypatch.setattr("arcwright_ai.engine.nodes.<function>", AsyncMock(...))` to control individual function behavior.

10. **`RunConfig` default**: The `make_run_config()` helper in `test_nodes.py` creates a `RunConfig` with defaults — `ScmConfig` will have `auto_merge=False`. To test auto-merge in `commit_node`, tests need to build a `RunConfig` with `ScmConfig(auto_merge=True)`.

### Existing Code to Reuse — DO NOT REINVENT

- **`shutil.which("gh")`** — already used in `open_pull_request()` and `_detect_default_branch()` for `gh` CLI availability check. Use exact same pattern.
- **`asyncio.create_subprocess_exec()`** — already used in `open_pull_request()` for `gh pr create`. Use exact same subprocess pattern for `gh pr merge`.
- **`append_entry(path, ProvenanceEntry(...))`** from `output/provenance.py` — used by `budget_check_node` and `validate_node`. Use for merge provenance.
- **`ProvenanceEntry`** from `core/types.py` — fields: `decision`, `alternatives`, `rationale`, `ac_references`, `timestamp`. Use for merge result recording.
- **Logger pattern** — all SCM modules use `logger = logging.getLogger(__name__)` with structured `extra={"data": {...}}` events.
- **`re` module** — already imported in `scm/pr.py`. Use for PR number extraction.
- **`datetime.now(tz=UTC).isoformat()`** — already used in `commit_node` for timestamps. Use for provenance timestamp.

### CRITICAL: Auto-Merge Insertion Point in commit_node

The merge must happen AFTER `open_pull_request()` succeeds (returns non-None URL) and the PR URL is stored in run.yaml, and BEFORE `remove_worktree()`. The current `commit_node` flow:

```python
# 1. commit_story() → commit_hash
# 2. push_branch() → push_succeeded
# 3. generate_pr_body() → pr_body
# 4. open_pull_request() → pr_url
# 5. update_story_status(pr_url=pr_url) → persists URL
# --- INSERT merge_pull_request() + provenance HERE ---
# 6. state = state.model_copy(update={"pr_url": pr_url})
# 7. remove_worktree()
```

The auto-merge block slots between steps 5 and 6 (after URL is persisted, before state update and worktree removal). Actually, placement between step 5 and step 7 is fine — the exact position between the pr_url state copy and remove_worktree is immaterial since merge doesn't need the worktree.

### CRITICAL: merge_pull_request is Best-Effort

The function MUST NOT raise exceptions to the caller. All errors are caught internally, logged, and `False` is returned. The `commit_node` wrapper adds additional try/except as defense-in-depth, matching the pattern used for `push_branch`, `generate_pr_body`, and `open_pull_request`.

### CRITICAL: PR Number Extraction

`open_pull_request()` returns a URL like `"https://github.com/owner/repo/pull/42"`. Extract the number using `re.search(r"/pull/(\d+)$", pr_url)`. This is simpler and more reliable than parsing `gh` JSON output. Edge case: trailing slash — strip before matching.

### CRITICAL: Merge Strategy Flag Mapping

```python
_MERGE_STRATEGY_FLAGS: dict[str, str] = {
    "squash": "--squash",
    "merge": "--merge",
    "rebase": "--rebase",
}
```

Default is `"squash"` per architecture D7. Lookup with `.get(strategy, "--squash")` for safety.

### CRITICAL: Merge Commit SHA

When `gh pr merge --squash` succeeds, stdout may contain text like `"✓ Squashed and merged pull request #42"`. The merge commit SHA may or may not be present in stdout — it depends on `gh` version. Attempt to parse with `re.search(r"[0-9a-f]{7,40}", stdout)`. If parsing fails, record `"unknown"` in provenance — don't fail on this.

### CRITICAL: Autouse Fixture Update for test_nodes.py

The `_mock_output_functions` autouse fixture in `tests/test_engine/test_nodes.py` (lines 71-100) needs a default mock for `merge_pull_request` so existing commit_node tests don't break:
```python
monkeypatch.setattr("arcwright_ai.engine.nodes.merge_pull_request", AsyncMock(return_value=False))
```
This defaults to `False` (merge didn't happen) which preserves existing test behavior since `auto_merge` defaults to `False` in `RunConfig` and the merge path is gated on `auto_merge=True`.

### CRITICAL: RunConfig with auto_merge=True for Tests

To test auto-merge in `commit_node`, create a `RunConfig` with SCM auto-merge enabled:
```python
from arcwright_ai.core.config import ScmConfig

config = make_run_config()
# Override scm config to enable auto_merge
config_with_auto_merge = config.model_copy(
    update={"scm": ScmConfig(auto_merge=True)}
)
```

### Files Touched

| File | Changes |
|------|---------|
| `scm/pr.py` | New `merge_pull_request()` function, `__all__` update |
| `scm/__init__.py` | Add `merge_pull_request` to imports and `__all__` |
| `engine/nodes.py` | Import `merge_pull_request`, call it in `commit_node` when `auto_merge=True`, record provenance |
| `tests/test_scm/test_pr.py` | Unit tests for `merge_pull_request` (~11 tests) |
| `tests/test_engine/test_nodes.py` | `commit_node` auto-merge tests (~5 tests), autouse fixture update |

### Project Structure Notes

- All source files under `arcwright-ai/src/arcwright_ai/` — paths in tasks are relative to this root.
- Tests mirror source structure under `arcwright-ai/tests/`.
- No new files created — all changes are additions to existing files.
- `scm/pr.py` already imports `asyncio`, `logging`, `re`, `shutil` — no new imports needed for `merge_pull_request`.
- `engine/nodes.py` already imports `datetime`, `UTC`, `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`, `VALIDATION_FILENAME`, `ProvenanceEntry`, `append_entry` — all needed for provenance recording, no new imports beyond `merge_pull_request`.

### Previous Story Intelligence

**From Story 9.2 (Fetch & Sync — done):**
- `fetch_and_sync()` in `scm/branch.py` follows the same async pattern with structured logging and `ScmError` handling.
- The `preflight_node` wiring pattern (check config → call function → handle error) is a template for the `commit_node` merge wiring.
- Test patterns: `monkeypatch.setattr` for git mocks, `AsyncMock(return_value=...)` for controlled responses.
- The autouse fixture in `test_nodes.py` was updated in 9.2 to include `fetch_and_sync` and `_detect_default_branch` stubs — same pattern needed here for `merge_pull_request`.
- 883 unit tests at completion of Story 9.2 — this is the current baseline.
- Review follow-ups were addressed: ff-merge success logging, structured log test coverage, call-order assertions, diverged-local SHA assertions.

**From Story 9.1 (ScmConfig Enhancements — done):**
- `ScmConfig.auto_merge: bool = False` already exists in `core/config.py` at line 238.
- `ScmConfig.default_branch: str = ""` already exists in `core/config.py`.
- `_detect_default_branch()` accepts `default_branch_override` — established pattern for config-driven behavior.
- `open_pull_request()` accepts `default_branch` kwarg and forwards to `_detect_default_branch()`.
- The `commit_node` already reads `state.config.scm.default_branch` and passes it to `open_pull_request()`.
- The `commit_node` already reads `state.config.scm.remote` for push operations.

**From Story 6.7 (Push Branch & Open PR — done):**
- `push_branch()` and `open_pull_request()` are both best-effort in `commit_node`.
- `open_pull_request()` uses `asyncio.create_subprocess_exec` with `gh pr create` — exact same pattern for `gh pr merge`.
- Test pattern in `test_pr.py`: `MagicMock()` for proc objects with `.returncode` and `.communicate = AsyncMock(return_value=(...))`.
- Test pattern in `test_nodes.py`: `monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value="url"))`.

**From Git History (recent commits):**
- `dda020a` — feat(scm): add ff-merge success logging and update tests (Story 9.2 review fixes)
- `f835d34` — feat(scm): fetch and sync default branch before worktree creation (Story 9.2)
- `2c6d275` — feat: create story 9.1 — ScmConfig enhancements
- Pattern: commit messages use conventional commits format: `feat(scope): description`

### References

- [Source: _spec/planning-artifacts/architecture.md#L403-L428] — D7 Git Operations: "Push + PR after validation. Optional auto-merge via `gh pr merge --squash` when `scm.auto_merge` is enabled"
- [Source: _spec/planning-artifacts/epics.md#L1241-L1275] — Epic 9 Story 9.3 full specification with ACs and files touched
- [Source: src/arcwright_ai/scm/pr.py#L1-L26] — Module docstring, imports, `__all__`
- [Source: src/arcwright_ai/scm/pr.py#L602-L730] — `open_pull_request()` — reference implementation for `gh` CLI subprocess calls
- [Source: src/arcwright_ai/engine/nodes.py#L34-L35] — Import lines for `scm/pr.py` functions
- [Source: src/arcwright_ai/engine/nodes.py#L1317-L1510] — `commit_node` full implementation — insertion point for merge logic
- [Source: src/arcwright_ai/engine/nodes.py#L1430-L1450] — `open_pull_request()` call site in `commit_node` with `default_branch` kwarg
- [Source: src/arcwright_ai/core/config.py#L228-L238] — `ScmConfig` with `auto_merge: bool = False` and `default_branch: str = ""`
- [Source: src/arcwright_ai/core/types.py#L161-L178] — `ProvenanceEntry` model (decision, alternatives, rationale, ac_references, timestamp)
- [Source: src/arcwright_ai/output/provenance.py#L230-L251] — `append_entry()` function for provenance recording
- [Source: src/arcwright_ai/scm/__init__.py#L1-L32] — Package exports (add `merge_pull_request`)
- [Source: tests/test_scm/test_pr.py#L625-L882] — `open_pull_request` test patterns (subprocess mock, gh CLI mock)
- [Source: tests/test_engine/test_nodes.py#L71-L100] — Autouse fixture with SCM mocks (add `merge_pull_request` stub)
- [Source: tests/test_engine/test_nodes.py#L1951-L2140] — `commit_node` push+PR test patterns

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Implemented `merge_pull_request()` in `scm/pr.py` following exact same async subprocess pattern as `open_pull_request()`. Added `_MERGE_STRATEGY_FLAGS` dict for strategy→gh-flag mapping.
- Wired into `commit_node` in `engine/nodes.py`: auto-merge gated on `state.config.scm.auto_merge`, inserted between PR URL persistence and state copy. Provenance recorded via `append_entry()` with `ProvenanceEntry(decision="Auto-merge PR after creation", ac_references=["FR39", "D7"])`. Best-effort throughout — merge failure never changes story status.
- Updated `scm/__init__.py` to export `merge_pull_request` in imports and `__all__` (sorted).
- Added `merge_pull_request` mock to `_mock_output_functions` autouse fixture in `test_nodes.py` so existing tests remain unaffected.
- Added merge SHA lookup helper `get_pull_request_merge_sha()` in `scm/pr.py` to resolve merge commit OID via `gh pr view --json mergeCommit --jq .mergeCommit.oid`.
- Updated `commit_node` merge provenance rationale to include explicit metadata fields: merge attempt timestamp, success/failure status, merge strategy, PR URL, and merge commit SHA.
- Added 13 unit tests in `test_pr.py` covering all AC #15 sub-items plus merge-SHA helper behavior.
- Added 5 unit tests + helper `_make_run_config_with_auto_merge()` in `test_nodes.py` covering all AC #16 sub-items.
- Strengthened `commit_node` auto-merge tests to assert explicit strategy wiring and merge provenance metadata content.
- Quality gates: ruff ✅, ruff format ✅, mypy --strict ✅, pytest 912/912 ✅ (+29 new tests).
- Confirmed `open_pull_request()` already passes `default_branch=state.config.scm.default_branch` — no changes needed (3.6 verified).

### Change Log

- 2026-03-15: Story created by create-story workflow — comprehensive developer guide assembled from epics, architecture, prior story intelligence (9.1, 9.2, 6.7), and code-level source analysis.
- 2026-03-15: Story implemented by dev-story workflow — `merge_pull_request()` added to `scm/pr.py`, wired into `commit_node` in `engine/nodes.py`, exports updated in `scm/__init__.py`, 29 new tests added across `test_pr.py` and `test_nodes.py`. All quality gates pass.
- 2026-03-15: Code review fixes applied — merge provenance now records timestamp/status/strategy/merge SHA metadata, merge SHA helper added, Story 9.3 tests expanded, and review findings resolved.

### File List

- arcwright-ai/src/arcwright_ai/scm/pr.py
- arcwright-ai/src/arcwright_ai/scm/__init__.py
- arcwright-ai/src/arcwright_ai/engine/nodes.py
- arcwright-ai/tests/test_scm/test_pr.py
- arcwright-ai/tests/test_engine/test_nodes.py
- _spec/implementation-artifacts/9-3-auto-merge-pr-after-creation.md
- _spec/implementation-artifacts/sprint-status.yaml
