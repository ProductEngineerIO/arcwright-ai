# Story 10.16: Mark Story Done in Sprint-Status Before PR Creation

Status: done

## Story

As a developer using Arcwright AI for overnight dispatch,
I want the BMAD sprint-status.yaml to be updated to `done` automatically when a story's PR is created,
so that sprint tracking reflects actual completion without requiring manual updates after each run.

## Acceptance Criteria

1. **Given** `commit_node` is about to call `open_pull_request()` **When** `push_succeeded` is `True` and a PR is about to be created **Then** `sprint-status.yaml` is updated: `development_status[story_slug]` is set to `"done"` and `last_updated` is set to the current date (YYYY-MM-DD).
2. **Given** the sprint-status update runs **When** the YAML file has YAML comment blocks (section headers, status definitions) **Then** all comments, blank lines, and unrelated fields are preserved — only the matching `story_slug` status value and `last_updated` date are changed.
3. **Given** the sprint-status file does not exist at the expected path **When** the update runs **Then** the failure is logged as a warning at level `scm.sprint_status.not_found` and execution continues normally — PR creation is unaffected.
4. **Given** any I/O or parsing error occurs during the sprint-status update **When** the error is caught **Then** it is logged as a warning at level `scm.sprint_status.update_error` and `commit_node` continues without re-raising — PR creation is unaffected.
5. **Given** the sprint-status file exists but `story_slug` is not found in `development_status` **When** the update runs **Then** the file is left unchanged, a debug log is emitted (`scm.sprint_status.key_not_found`), and execution continues normally.
6. **Given** `commit_node` is NOT creating a PR (e.g. push failed, no commit hash) **When** execution proceeds **Then** no sprint-status update is attempted.
7. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1 — Implement `_update_sprint_status_done()` helper in `engine/nodes.py` (AC: #1, #2, #3, #4, #5)
  - [x] 1.1 Add `_update_sprint_status_done(story_slug, project_root, artifacts_path)` as an `async` helper function in `engine/nodes.py`
  - [x] 1.2 Resolve sprint-status path: `project_root / artifacts_path / "implementation-artifacts" / "sprint-status.yaml"`
  - [x] 1.3 If file does not exist: log `scm.sprint_status.not_found` at WARNING and return
  - [x] 1.4 Read file content as text (via `asyncio.to_thread(path.read_text, encoding="utf-8")`)
  - [x] 1.5 Use `re.sub` with `MULTILINE` flag to update `development_status[story_slug]` — pattern: `r'(?m)^(\s+{slug}:\s*)\S+'` → replacement: `r'\g<1>done'` (where `{slug}` is `re.escape(story_slug)`)
  - [x] 1.6 Use `re.sub` with `MULTILINE` flag to update `last_updated` — pattern: `r'(?m)^(last_updated:\s*)\S+'` → replacement: `r'\g<1>{date}'` (where `{date}` is `date.today().isoformat()`)
  - [x] 1.7 If neither regex matched (story key not found in file text), log `scm.sprint_status.key_not_found` at DEBUG and return without writing
  - [x] 1.8 Write updated content back via `asyncio.to_thread(path.write_text, updated, encoding="utf-8")`
  - [x] 1.9 Log `scm.sprint_status.updated` at INFO with `story_slug` and `path` in structured extra data
  - [x] 1.10 Wrap the entire function body in try/except and re-raise nothing — log any exception as WARNING `scm.sprint_status.update_error` with `story`, `error` in extra data

- [x] Task 2 — Call site in `commit_node` (AC: #1, #6)
  - [x] 2.1 In `commit_node`, locate the block that calls `open_pull_request()` (currently inside `if push_succeeded:` → `try:` → before `pr_url = await open_pull_request(...)`)
  - [x] 2.2 Immediately before the `generate_pr_body` / `open_pull_request` call, add a best-effort call to `await _update_sprint_status_done(story_slug, project_root, state.config.methodology.artifacts_path)` — no try/except needed at the call site since the helper is internally safe
  - [x] 2.3 Confirm the call is inside the `if push_succeeded:` guard so it only runs when a PR is actually being attempted (AC: #6)

- [x] Task 3 — Tests (AC: #7)
  - [x] 3.1 Unit test: `_update_sprint_status_done()` with a real sprint-status.yaml fixture → target story status changed to `done`, `last_updated` updated, all comments preserved
  - [x] 3.2 Unit test: file does not exist → warning logged, no exception raised
  - [x] 3.3 Unit test: story_slug not in file → debug log, file unchanged
  - [x] 3.4 Unit test: story already `done` → idempotent, file written with same `done` value and updated `last_updated`
  - [x] 3.5 Unit test: story status is `ready-for-dev` → correctly replaced with `done`
  - [x] 3.6 Unit test: I/O error (mock `path.write_text` to raise `OSError`) → warning logged, no exception propagated
  - [x] 3.7 Integration: verify `commit_node` calls `_update_sprint_status_done` when `push_succeeded=True`

## Dev Notes

### Problem Context

After an overnight Arcwright AI dispatch run, sprint-status.yaml still shows all completed stories as `in-progress` (or `ready-for-dev`). The human must manually update the YAML for every story. With 5+ stories per run this is friction that defeats the "wake up to completed work" promise.

The PR creation point is the right trigger because it is the definitive signal that the story's implementation is committed, validated, and ready for merge — semantically equivalent to `done` from Arcwright's perspective. Stories that fail validation never reach PR creation, so their status correctly remains unchanged.

### Implementation Location

All new code lives in `engine/nodes.py`:
- A private helper `_update_sprint_status_done()` near the other private helpers (e.g. `_derive_story_title`, `_escalate_after_scm_failure`)
- One `await` call in `commit_node`, inside the `if push_succeeded:` block, immediately before `generate_pr_body()`

### Sprint-Status File Path

```python
# Resolved inside _update_sprint_status_done():
sprint_status_path = project_root / artifacts_path / "implementation-artifacts" / "sprint-status.yaml"
# Example for this project:
# /path/to/project / "_spec" / "implementation-artifacts" / "sprint-status.yaml"
```

`artifacts_path` comes from `state.config.methodology.artifacts_path` (default `"_spec"`).

### Why Text-Based Regex (not YAML load/dump)

PyYAML (`yaml.safe_load` + `yaml.dump`) is already used in the codebase (`core/io.py`). However, `yaml.dump` **does not preserve comments**. The sprint-status.yaml contains meaningful comment blocks (status definitions, section headers like `# Epic 1: Project Foundation`) that must survive the update.

Using `re.sub` on the raw text file content preserves comments exactly. The patterns are narrow and unambiguous:

```python
import re
from datetime import date

# Update story status (matches "  10-15-run-cost-in-pr-body: done" or any non-whitespace status)
updated = re.sub(
    rf'(?m)^(\s+{re.escape(story_slug)}:\s*)\S+',
    r'\g<1>done',
    content,
)

# Update last_updated date
updated = re.sub(
    r'(?m)^(last_updated:\s*)\S+',
    rf'\g<1>{date.today().isoformat()}',
    updated,
)
```

The `(?m)` flag anchors `^` to line beginnings, ensuring uniqueness. No false positives are possible because story slugs are unique keys in the file.

### Sprint-Status YAML Structure (Reference)

```yaml
last_updated: 2026-08-08

development_status:
  # Epic 10: Ad-Hoc Improvements & Housekeeping
  epic-10: in-progress
  10-15-run-cost-in-pr-body: done
  10-16-mark-story-done-in-sprint-status-before-pr-creation: in-progress  ← target
```

After update:
```yaml
last_updated: 2026-08-08  ← updated to today

development_status:
  # Epic 10: Ad-Hoc Improvements & Housekeeping
  epic-10: in-progress
  10-15-run-cost-in-pr-body: done
  10-16-mark-story-done-in-sprint-status-before-pr-creation: done  ← updated
```

### Structured Log Events

| Event key | Level | When |
|-----------|-------|------|
| `scm.sprint_status.updated` | INFO | Successful update |
| `scm.sprint_status.not_found` | WARNING | File does not exist |
| `scm.sprint_status.key_not_found` | DEBUG | story_slug missing from file |
| `scm.sprint_status.update_error` | WARNING | Any unexpected exception |

Extra data fields: `{"story": story_slug, "path": str(sprint_status_path)}`

### Call Site in `commit_node` (Current Code)

Current flow (abbreviated):
```python
if push_succeeded:
    # ... extract_agent_decisions (best-effort) ...

    # Generate PR body and open PR (AC: #3, #4)
    try:
        pr_body = await generate_pr_body(...)
        pr_url = await open_pull_request(...)
    except Exception as exc:
        logger.warning("scm.pr.error", ...)
```

After this story:
```python
if push_succeeded:
    # ... extract_agent_decisions (best-effort) ...

    # Mark story done in sprint-status before PR creation (AC: #1, best-effort)
    await _update_sprint_status_done(
        story_slug, project_root, state.config.methodology.artifacts_path
    )

    # Generate PR body and open PR (AC: #3, #4)
    try:
        pr_body = await generate_pr_body(...)
        pr_url = await open_pull_request(...)
    except Exception as exc:
        logger.warning("scm.pr.error", ...)
```

### Key Files

| File | Change |
|------|--------|
| `arcwright-ai/src/arcwright_ai/engine/nodes.py` | Add `_update_sprint_status_done()` helper; add call site in `commit_node` |
| `arcwright-ai/tests/test_engine/test_commit_node.py` | New tests for sprint-status update behavior (or create if not exists) |

### Imports Required (nodes.py additions)

```python
from datetime import date  # stdlib — likely already imported as `datetime`; check first
import re                  # stdlib — likely already imported; check first
```

Verify with `grep -n "^import re\|^from datetime" engine/nodes.py` before adding imports.

### References

- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py] — `commit_node` function, `push_succeeded` guard, `open_pull_request` call site
- [Source: arcwright-ai/src/arcwright_ai/core/config.py] — `MethodologyConfig.artifacts_path` field
- [Source: _spec/implementation-artifacts/sprint-status.yaml] — File format, comment structure, key naming conventions
- [Source: arcwright-ai/src/arcwright_ai/core/io.py] — PyYAML patterns (load_yaml/save_yaml) — not used here due to comment-preservation requirement
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py#_derive_story_title] — Pattern for private helper functions in nodes.py
- [Source: _spec/implementation-artifacts/10-15-run-cost-in-pr-body.md] — Previous story, best-effort call pattern in commit_node

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Added `date` to the `from datetime import` line in `nodes.py` (was `UTC, datetime`).
- Added `_update_sprint_status_done(story_slug, project_root, artifacts_path)` private async helper in `engine/nodes.py`, placed after `_derive_story_title` and before `preflight_node`. Uses `re.search` to detect presence of slug before writing (correctly idempotent for already-done stories). Uses existing `write_text_async` for writing (matches codebase pattern). Entire body wrapped in try/except; never raises.
- Call site added in `commit_node` inside the `if push_succeeded:` guard, immediately before the `generate_pr_body` / `open_pull_request` block.
- 7 tests added in `tests/test_engine/test_commit_node.py` (6 unit + 1 integration). All pass. Zero regressions (1216 total pass).
- `ruff check` and `mypy --strict` both clean.

### File List

- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/tests/test_engine/test_commit_node.py`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/implementation-artifacts/10-16-mark-story-done-in-sprint-status-before-pr-creation.md`

### Change Log

- 2026-08-08: Implemented `_update_sprint_status_done()` helper and call site in `commit_node`; 7 new tests added (Story 10.16)
- 2026-08-08: Code review — added negative integration test `test_commit_node_does_not_update_sprint_status_when_push_failed` to cover AC #6 (push_succeeded=False → no sprint-status update); 8/8 tests pass
