# Story 10.14: Quality Gate — Project-Type Auto-Detection

Status: done

## Story

As a maintainer running Arcwright AI against a non-Python project,
I want the Quality Gate to detect the target project's language via manifest files before executing any toolchain,
so that the gate does not spuriously fail (or block story execution) when the worktree contains a Node.js, Go, or other non-Python project.

## Acceptance Criteria

1. **Given** a worktree whose root (or one level deep) contains `pyproject.toml` **When** `run_quality_gate` is called **Then** `detect_project_dir` returns `project_type="python"` and the `project_dir` pointing to the directory containing `pyproject.toml` — identical behavior to the current hardcoded path
2. **Given** a worktree whose root (or one level deep) contains `package.json` but no `pyproject.toml` **When** `run_quality_gate` is called **Then** the gate is skipped, `QualityGateResult.passed=True`, and `QualityFeedback.skipped_reason` contains a message indicating the project type is `"node"` and the gate is not yet implemented for that type
3. **Given** a worktree whose root (or one level deep) contains `go.mod` but no `pyproject.toml` or `package.json` **When** `run_quality_gate` is called **Then** the gate is skipped, `QualityGateResult.passed=True`, and `QualityFeedback.skipped_reason` contains a message indicating the project type is `"go"` and the gate is not yet implemented for that type
4. **Given** a worktree with no recognized manifest file at root or one level deep **When** `run_quality_gate` is called **Then** the gate is skipped, `QualityGateResult.passed=True`, and `QualityFeedback.skipped_reason` contains a message indicating the project type is unknown
5. **Given** a worktree root contains both `pyproject.toml` and `package.json` **When** `detect_project_dir` runs **Then** `pyproject.toml` wins — `project_type="python"` is returned (Python takes priority in polyglot repos)
6. **Given** `detect_project_dir` finds a manifest one level deep (e.g. `worktree_path/arcwright-ai/pyproject.toml`) **When** `run_quality_gate` resolves the `project_dir` **Then** it uses `worktree_path/arcwright-ai` as `cwd` for all subprocess calls — preserving the existing nested-layout behavior
7. **Given** the gate is skipped (non-Python or unknown) **When** the `pipeline.py` receives `QualityGateResult.passed=True` **Then** the pipeline returns `PipelineOutcome.PASS` — skipping is treated as a gate pass, not a failure
8. **And** a `quality_gate.project_type_detected` log event is emitted by `detect_project_dir` with fields `project_type` and `project_dir`
9. **And** a `quality_gate.skipped` log event is emitted when the gate is bypassed with fields `project_type` and `reason`
10. **And** `detect_project_dir` is exported in `quality_gate.__all__`
11. **And** `QualityFeedback.skipped_reason: str | None = None` is added as a new optional field — `None` means the gate ran normally
12. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

## Tasks / Subtasks

- [x] Task 1 — Add `skipped_reason` field to `QualityFeedback` (AC: #2, #3, #4, #11)
  - [x] 1.1 Add `skipped_reason: str | None = None` to `QualityFeedback` model in `quality_gate.py`
  - [x] 1.2 Update docstring to describe the field

- [x] Task 2 — Implement `detect_project_dir` (AC: #1, #2, #3, #4, #5, #6, #8)
  - [x] 2.1 Define `_MANIFEST_PRIORITY: list[tuple[str, str]]` — ordered list of `(filename, project_type)`: `[("pyproject.toml", "python"), ("package.json", "node"), ("go.mod", "go")]`
  - [x] 2.2 Implement `detect_project_dir(worktree_path: Path) -> tuple[str | None, Path]`
    - Search at depth 0 (`worktree_path / filename`) first, then depth 1 (`worktree_path / subdir / filename` for each immediate subdirectory), in `_MANIFEST_PRIORITY` order
    - Return `(project_type, parent_of_manifest)` on first match
    - Return `(None, worktree_path)` if no manifest found
  - [x] 2.3 Emit `quality_gate.project_type_detected` log event with `project_type` and `project_dir` fields
  - [x] 2.4 Add `detect_project_dir` to `__all__`

- [x] Task 3 — Wire `detect_project_dir` into `run_quality_gate` (AC: #1, #2, #3, #4, #6, #7, #9)
  - [x] 3.1 Replace `project_dir = worktree_path / "arcwright-ai"` with `project_type, project_dir = detect_project_dir(worktree_path)`
  - [x] 3.2 Add early-return skip path: if `project_type != "python"`, emit `quality_gate.skipped` log event, return `QualityGateResult(passed=True, feedback=QualityFeedback(passed=True, skipped_reason=<message>))`
  - [x] 3.3 Skip message format: `"Quality Gate skipped: project type '{project_type or 'unknown'}' is not yet supported. Gate will pass automatically."` — informative but not alarming

- [x] Task 4 — Tests (AC: #12)
  - [x] 4.1 `detect_project_dir`: `pyproject.toml` at worktree root → returns `("python", worktree_path)`
  - [x] 4.2 `detect_project_dir`: `pyproject.toml` one level deep → returns `("python", worktree_path / subdir)`
  - [x] 4.3 `detect_project_dir`: `package.json` at root, no `pyproject.toml` → returns `("node", worktree_path)`
  - [x] 4.4 `detect_project_dir`: `go.mod` at root, no higher-priority manifests → returns `("go", worktree_path)`
  - [x] 4.5 `detect_project_dir`: no manifest at any depth → returns `(None, worktree_path)`
  - [x] 4.6 `detect_project_dir`: both `pyproject.toml` and `package.json` at root → returns `("python", worktree_path)` (priority)
  - [x] 4.7 `detect_project_dir`: `package.json` at root and `pyproject.toml` one level deep → returns `("python", worktree_path / subdir)` (python still wins via priority ordering, not depth)
  - [x] 4.8 `run_quality_gate` with node project: returns `QualityGateResult(passed=True)` with `skipped_reason` set, no subprocesses launched
  - [x] 4.9 `run_quality_gate` with unknown project: returns `QualityGateResult(passed=True)` with `skipped_reason` set
  - [x] 4.10 `run_quality_gate` with python project at root (no `arcwright-ai/` subdirectory): subprocesses invoked with `cwd=worktree_path` (not `worktree_path / "arcwright-ai"`)
  - [x] 4.11 `QualityFeedback` serialization: `skipped_reason=None` serializes cleanly (no extra field noise), `skipped_reason="..."` round-trips correctly

## Dev Notes

### Problem Context

`run_quality_gate` in `validation/quality_gate.py` has two hardcoded Python assumptions:

1. **`project_dir = worktree_path / "arcwright-ai"`** — bakes in the arcwright-ai self-hosted nested layout. Any project that doesn't have an `arcwright-ai/` subdirectory will fail all subprocess calls because the `cwd` directory doesn't exist.

2. **Always runs `ruff`, `mypy --strict`, `pytest`** — these tools are Python-specific. A Node.js or Go project will receive `FileNotFoundError` from the subprocess launcher for every tool, returning `passed=False` on all, causing `FAIL_QUALITY` for every story — effectively blocking execution.

Since `worktree_path` is already optional (`worktree_path: Path | None = None` in `run_validation_pipeline`), the gate is architecturally opt-in. But once provided, the current code fails hard for non-Python targets.

### Detection Strategy

`detect_project_dir` searches for manifest files in priority order, checking depth 0 before depth 1. The two-depth search handles both flat layouts (`worktree_path/pyproject.toml`) and arcwright-ai's own nested layout (`worktree_path/arcwright-ai/pyproject.toml`). Deeper nesting (depth 2+) is not searched — it would risk false positives from vendored or example code.

**Search order** (first match wins):
```
1. worktree_path/pyproject.toml          → ("python", worktree_path)
2. worktree_path/package.json            → ("node",   worktree_path)
3. worktree_path/go.mod                  → ("go",     worktree_path)
4. worktree_path/*/pyproject.toml        → ("python", worktree_path/<subdir>)
5. worktree_path/*/package.json          → ("node",   worktree_path/<subdir>)
6. worktree_path/*/go.mod                → ("go",     worktree_path/<subdir>)
7. (nothing found)                       → (None,     worktree_path)
```

Priority across types (`pyproject.toml` > `package.json` > `go.mod`) takes precedence over depth. This means if `pyproject.toml` exists one level deep but `package.json` is at root, Python still wins. This is intentional — it prevents a stray `package.json` (e.g., a tooling config at repo root) from masking a Python project in a subdirectory.

### Skip Semantics

Non-Python and unknown projects return `QualityGateResult(passed=True)`. This is a **deliberate pass-through**, not a silent skip. The reasons:

- The gate is a quality assurance layer for Python tooling; it has no authority over other languages.
- Returning `FAIL_QUALITY` for a Node project would be incorrect behavior, not a legitimate quality failure.
- `skipped_reason` is surfaced in `QualityFeedback` so that `pipeline.py` logs it and it appears in provenance, preserving full observability.

The `validate_node` in `engine/nodes.py` does not need to change — it routes on `PipelineOutcome`, and a pass-with-skip produces `PASS` identical to a pass-with-fixes.

### Depth-1 Subdirectory Enumeration

Depth-1 search must only inspect immediate subdirectories, not files at depth 0 again. Use:
```python
for child in worktree_path.iterdir():
    if child.is_dir():
        candidate = child / filename
        if candidate.is_file():
            return (project_type, child)
```

Do not recurse deeper — `iterdir()` is non-recursive and bounded.

### What Is NOT Changed

- `_run_auto_fix`, `_run_checks`, `_run_subprocess` — unchanged; they receive `cwd` as a parameter.
- `run_validation_pipeline` in `pipeline.py` — unchanged; it already passes `worktree_path` through.
- `validate_node`, `agent_dispatch_node` in `engine/nodes.py` — unchanged.
- No new config fields — auto-detection is sufficient; a configurable override is deferred.
- Node.js and Go toolchain execution — deferred; the skip path provides the correct structure for future implementation.

### Key Code Locations

| Component | File | Relevant Symbol |
|---|---|---|
| Quality Gate | `src/arcwright_ai/validation/quality_gate.py` | `run_quality_gate`, `QualityFeedback` |
| Pipeline | `src/arcwright_ai/validation/pipeline.py` | `run_validation_pipeline` — no changes required |
| Tests | `tests/test_validation/test_quality_gate.py` | Add new test class `TestDetectProjectDir` and extend `TestRunQualityGate` |

### References

- [Source: arcwright-ai/src/arcwright_ai/validation/quality_gate.py] — `run_quality_gate` lines 376–449; hardcoded `project_dir = worktree_path / "arcwright-ai"` is the primary target
- [Source: arcwright-ai/src/arcwright_ai/validation/quality_gate.py] — `QualityFeedback` model; add `skipped_reason` field alongside existing `auto_fix_summary` and `tool_results`
- [Source: arcwright-ai/tests/test_validation/test_quality_gate.py] — existing test structure; new tests extend the same file

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Added `skipped_reason: str | None = None` to `QualityFeedback`; updated docstring with full field description.
- Implemented `detect_project_dir(worktree_path: Path) -> tuple[str | None, Path]` with `_MANIFEST_PRIORITY` priority ordering and two-depth search (depth 0 before depth 1, but priority type always wins over depth).
- Replaced hardcoded `project_dir = worktree_path / "arcwright-ai"` in `run_quality_gate` with `detect_project_dir`; non-Python and unknown projects return early with `QualityGateResult(passed=True)` and `skipped_reason` populated; `quality_gate.skipped` log event emitted.
- Added `detect_project_dir` to `__all__` (ruff auto-sorted alphabetically).
- Updated module docstring to describe auto-detection behaviour.
- All 37 quality gate tests pass; full suite of 1187 passes; `ruff check`, `ruff format --check`, and `mypy --strict` all clean.
- The 5 existing `run_quality_gate` tests that relied on the hardcoded worktree subdir path were updated to mock `detect_project_dir` via a new `mock_detect_python_project` fixture, preserving their original intent.

### Review Reconciliation (2026-03-21)

- Code-review was executed in a branch with concurrent documentation updates outside Story 10.14 (`10-13` artifact and sprint tracking file), which created temporary git-vs-story noise.
- Story 10.14 implementation evidence is confined to the quality gate source/tests listed below and validated by passing targeted suites:
  - `tests/test_validation/test_quality_gate.py` (37 passed)
  - `tests/test_validation/test_pipeline.py -k "quality_gate or FAIL_QUALITY or no_worktree_path"` (3 passed)
- Transparency follow-up applied: this story artifact is now included in File List and reconciliation is recorded in Change Log.

### File List

- arcwright-ai/src/arcwright_ai/validation/quality_gate.py
- arcwright-ai/tests/test_validation/test_quality_gate.py
- _spec/implementation-artifacts/10-14-quality-gate-project-type-auto-detection.md

## Change Log

- 2026-03-21: Story 10.14 implemented — Quality Gate project-type auto-detection. Added `detect_project_dir` with `_MANIFEST_PRIORITY` (python/node/go), wired into `run_quality_gate` with skip path for non-Python projects. Added `skipped_reason` field to `QualityFeedback`. 12 new tests added (4.1–4.11); 5 existing tests updated to mock detection.
- 2026-03-21: Code review reconciliation — documented concurrent-branch git context, added explicit verification test outcomes, and updated File List for review-trace completeness.

## Status

done
