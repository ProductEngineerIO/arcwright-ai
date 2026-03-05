# Story 4.2: Run Manager — Run Directory Lifecycle & State Tracking

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator managing multiple runs,
I want each run to have a unique directory with structured state tracking,
so that I can see the status of any run at a glance and resume interrupted runs.

## Acceptance Criteria (BDD)

1. **Given** `output/run_manager.py` module **When** the run manager is implemented **Then** it exposes the following async public functions:
   - `generate_run_id() -> RunId` (sync — no I/O, just datetime + uuid) that produces a run ID in format `YYYYMMDD-HHMMSS-<short-uuid>` (e.g., `20260302-143022-a1b2c3`) where `<short-uuid>` is the first 6 hexadecimal characters of a `uuid4()`. The datetime component uses `RUN_ID_DATETIME_FORMAT` from `core/constants.py` and is generated in UTC.
   - `async create_run(project_root: Path, run_id: RunId, config: RunConfig, story_slugs: list[str]) -> Path` that creates the run directory and initial `run.yaml`.
   - `async update_run_status(project_root: Path, run_id: str, *, status: RunStatusValue | None = None, last_completed_story: str | None = None, budget: BudgetState | None = None) -> None` that updates fields in `run.yaml`.
   - `async update_story_status(project_root: Path, run_id: str, story_slug: str, *, status: str, started_at: str | None = None, completed_at: str | None = None, retry_count: int | None = None) -> None` that updates a specific story's entry in `run.yaml`.
   - `async get_run_status(project_root: Path, run_id: str) -> RunStatus` that reads `run.yaml` and returns a typed model.
   - `async list_runs(project_root: Path) -> list[RunSummary]` that scans the runs directory and returns lightweight summaries sorted by start_time descending (most recent first).
   All functions import types from `core/` packages only. Zero engine dependency enforced.

2. **Given** a call to `create_run(project_root, run_id, config, story_slugs)` **When** the run is created **Then** it creates the directory structure `.arcwright-ai/runs/<run-id>/` under `project_root` (creating parent dirs if needed), and creates `stories/` subdirectory within the run directory. It writes `run.yaml` at `.arcwright-ai/runs/<run-id>/run.yaml` containing the following YAML structure:
   ```yaml
   run_id: "20260302-143022-a1b2c3"
   start_time: "2026-03-02T14:30:22+00:00"  # ISO 8601 with timezone
   status: "queued"
   config_snapshot:
     model_version: "claude-opus-4-5"
     tokens_per_story: 200000
     cost_per_run: 10.0
     retry_budget: 3
     timeout_per_story: 300
     methodology_type: "bmad"
     artifacts_path: "_spec"
     branch_template: "arcwright/{story_slug}"
   budget:
     invocation_count: 0
     total_tokens: 0
     estimated_cost: "0"
     max_invocations: 0
     max_cost: "0"
   stories:
     "2-1-state-models":
       status: "queued"
       retry_count: 0
       started_at: null
       completed_at: null
     "2-2-context-injector":
       status: "queued"
       retry_count: 0
       started_at: null
       completed_at: null
   last_completed_story: null
   ```
   The `config_snapshot` is a flat dict extracted from the `RunConfig` model containing the operationally-relevant fields (model version, limits, methodology, SCM). It does NOT include the API key (security: NFR6). The `budget` section serializes `BudgetState` via `model_dump()` with `Decimal` fields converted to strings for YAML-safe serialization. The `stories` section maps each slug from `story_slugs` to an initial `StoryStatusEntry`. The function returns the `Path` to the created run directory.

3. **Given** an existing `run.yaml` **When** `update_run_status()` is called with one or more keyword arguments **Then** it reads the existing `run.yaml` via `load_yaml()` wrapped in `asyncio.to_thread()`, applies only the provided non-`None` fields (partial update — unspecified fields are not modified), and writes back via `save_yaml()` wrapped in `asyncio.to_thread()`. Specifically:
   - If `status` is provided: updates the top-level `status` field with the `RunStatusValue` value.
   - If `last_completed_story` is provided: updates the `last_completed_story` field.
   - If `budget` is provided: replaces the `budget` section with the serialized `BudgetState` (using `model_dump()` with Decimal-to-string conversion).
   - If `run.yaml` does not exist at the expected path, raises `RunError` with message `"run.yaml not found for run {run_id}"` and details `{"path": str(expected_path)}`.

4. **Given** an existing `run.yaml` with a `stories` section **When** `update_story_status()` is called **Then** it reads `run.yaml`, locates the story entry by `story_slug` key in the `stories` dict, applies only the provided non-`None` fields (`status`, `started_at`, `completed_at`, `retry_count`), and writes back. If the `story_slug` key does not exist in `stories`, it creates a new entry with the provided values and defaults for unspecified fields (`retry_count: 0`, `started_at: null`, `completed_at: null`). If `run.yaml` does not exist, raises `RunError`.

5. **Given** `run.yaml` exists for the specified `run_id` **When** `get_run_status()` is called **Then** it reads `run.yaml` via `asyncio.to_thread(load_yaml, path)`, validates the content, and returns a `RunStatus` model with all fields populated. If `run.yaml` does not exist, raises `RunError` with message `"Run not found: {run_id}"`. If `run.yaml` is malformed or missing required fields, raises `RunError` with descriptive message.

6. **Given** the `.arcwright-ai/runs/` directory exists **When** `list_runs()` is called **Then** it scans all subdirectories of `.arcwright-ai/runs/`, reads `run.yaml` from each that contains one, constructs `RunSummary` models (lightweight: `run_id`, `status`, `start_time`, `story_count`, `completed_count`), and returns them sorted by `start_time` descending (most recent first). If the runs directory does not exist or is empty, returns an empty list (not an error). Subdirectories that lack `run.yaml` are silently skipped (logged at debug level).

7. **Given** the models defined in `output/run_manager.py` **When** the implementation is complete **Then** the module defines the following Pydantic models:
   - `RunStatusValue(StrEnum)` with values: `queued`, `running`, `completed`, `halted`, `timed_out`.
   - `StoryStatusEntry(ArcwrightModel)` with fields: `status` (str), `retry_count` (int, default 0), `started_at` (str | None, default None), `completed_at` (str | None, default None).
   - `RunStatus(ArcwrightModel)` with fields: `run_id` (str), `status` (RunStatusValue), `start_time` (str), `config_snapshot` (dict[str, Any]), `budget` (dict[str, Any]), `stories` (dict[str, StoryStatusEntry]), `last_completed_story` (str | None, default None).
   - `RunSummary(ArcwrightModel)` with fields: `run_id` (str), `status` (RunStatusValue), `start_time` (str), `story_count` (int), `completed_count` (int).
   All models use `ArcwrightModel` conventions (frozen=True, extra="forbid"). `StoryStatusEntry` uses `extra="ignore"` instead of `extra="forbid"` for forward compatibility (future stories may add fields).

8. **Given** the `output/__init__.py` module **When** this story is complete **Then** `__all__` is updated to export (alphabetically sorted): `["RunStatus", "RunStatusValue", "RunSummary", "StoryStatusEntry", "append_entry", "create_run", "generate_run_id", "get_run_status", "list_runs", "render_validation_row", "update_run_status", "update_story_status", "write_entries"]`. Corresponding imports are added from `output.run_manager`.

9. **Given** new unit tests in `tests/test_output/test_run_manager.py` **When** the test suite runs **Then** tests cover:
   (a) `generate_run_id()` produces a string matching pattern `^\d{8}-\d{6}-[0-9a-f]{6}$` and two sequential calls produce different IDs;
   (b) `create_run()` creates the directory structure with `run.yaml` and `stories/` subdir;
   (c) `create_run()` produces valid `run.yaml` content with all required keys and correct initial values;
   (d) `create_run()` config_snapshot does NOT contain the API key (NFR6);
   (e) `create_run()` Decimal fields in budget are serialized as strings in YAML;
   (f) `update_run_status()` partial update — only specified fields change, others preserved;
   (g) `update_run_status()` with `budget` replacement — full budget section updated;
   (h) `update_run_status()` on missing `run.yaml` raises `RunError`;
   (i) `update_story_status()` updates existing story entry correctly;
   (j) `update_story_status()` creates new story entry if slug not found;
   (k) `update_story_status()` on missing `run.yaml` raises `RunError`;
   (l) `get_run_status()` returns correct typed `RunStatus` model;
   (m) `get_run_status()` on missing run raises `RunError`;
   (n) `list_runs()` returns summaries sorted by start_time descending;
   (o) `list_runs()` on empty/missing runs directory returns empty list;
   (p) `list_runs()` skips subdirectories without `run.yaml`;
   (q) `update_story_status()` partial update — only specified fields change, others (e.g., `retry_count`) preserved;
   (r) `update_run_status()` with `RunStatusValue.HALTED` — status correctly persisted and readable.

10. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

11. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

12. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

13. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 388 existing tests continue to pass unmodified.

## Tasks / Subtasks

- [x] Task 1: Implement models and `generate_run_id()` in `output/run_manager.py` (AC: #1, #7)
  - [x] 1.1: Add module docstring, `from __future__ import annotations`, and imports:
    ```python
    import asyncio
    import uuid
    from datetime import datetime, timezone
    from enum import StrEnum
    from typing import TYPE_CHECKING, Any

    from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, RUN_ID_DATETIME_FORMAT, RUN_METADATA_FILENAME
    from arcwright_ai.core.exceptions import RunError
    from arcwright_ai.core.io import load_yaml, save_yaml
    from arcwright_ai.core.types import ArcwrightModel, RunId

    if TYPE_CHECKING:
        from pathlib import Path
        from arcwright_ai.core.config import RunConfig
        from arcwright_ai.core.types import BudgetState
    ```
  - [x] 1.2: Define `RunStatusValue(StrEnum)` with values: `QUEUED = "queued"`, `RUNNING = "running"`, `COMPLETED = "completed"`, `HALTED = "halted"`, `TIMED_OUT = "timed_out"`
  - [x] 1.3: Define `StoryStatusEntry(ArcwrightModel)` with `model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)` and fields: `status` (str), `retry_count` (int, default 0), `started_at` (str | None, default None), `completed_at` (str | None, default None)
  - [x] 1.4: Define `RunStatus(ArcwrightModel)` with fields: `run_id` (str), `status` (RunStatusValue), `start_time` (str), `config_snapshot` (dict[str, Any]), `budget` (dict[str, Any]), `stories` (dict[str, StoryStatusEntry]), `last_completed_story` (str | None, default None)
  - [x] 1.5: Define `RunSummary(ArcwrightModel)` with fields: `run_id` (str), `status` (RunStatusValue), `start_time` (str), `story_count` (int), `completed_count` (int)
  - [x] 1.6: Implement `generate_run_id() -> RunId` — sync function, `datetime.now(tz=timezone.utc).strftime(RUN_ID_DATETIME_FORMAT)` + `-` + `uuid.uuid4().hex[:6]`

- [x] Task 2: Implement `_build_config_snapshot()` and `_serialize_budget()` private helpers (AC: #2)
  - [x] 2.1: `_build_config_snapshot(config: RunConfig) -> dict[str, Any]` — extracts flat dict of operationally-relevant config fields. Explicitly EXCLUDES `api.claude_api_key` per NFR6. Fields: `model_version`, `tokens_per_story`, `cost_per_run`, `retry_budget`, `timeout_per_story`, `methodology_type`, `artifacts_path`, `branch_template`
  - [x] 2.2: `_serialize_budget(budget: BudgetState) -> dict[str, Any]` — calls `budget.model_dump()` and converts any `Decimal` values to `str` for YAML-safe serialization (PyYAML's `safe_dump` cannot handle `Decimal`)
  - [x] 2.3: `_run_dir(project_root: Path, run_id: str) -> Path` — helper returning `project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id`
  - [x] 2.4: `_run_yaml_path(project_root: Path, run_id: str) -> Path` — helper returning `_run_dir(...) / RUN_METADATA_FILENAME`

- [x] Task 3: Implement `create_run()` async function (AC: #1, #2)
  - [x] 3.1: Function signature: `async def create_run(project_root: Path, run_id: RunId, config: RunConfig, story_slugs: list[str]) -> Path`
  - [x] 3.2: Create run directory: `run_dir / DIR_STORIES` with `mkdir(parents=True, exist_ok=True)` wrapped in `asyncio.to_thread()`
  - [x] 3.3: Build initial `run.yaml` data dict:
    ```python
    data = {
        "run_id": str(run_id),
        "start_time": datetime.now(tz=timezone.utc).isoformat(),
        "status": RunStatusValue.QUEUED.value,
        "config_snapshot": _build_config_snapshot(config),
        "budget": _serialize_budget(BudgetState()),
        "stories": {
            slug: {"status": "queued", "retry_count": 0, "started_at": None, "completed_at": None}
            for slug in story_slugs
        },
        "last_completed_story": None,
    }
    ```
  - [x] 3.4: Write via `await asyncio.to_thread(save_yaml, run_yaml_path, data)`
  - [x] 3.5: Return `run_dir` Path

- [x] Task 4: Implement `update_run_status()` async function (AC: #3)
  - [x] 4.1: Function signature: `async def update_run_status(project_root: Path, run_id: str, *, status: RunStatusValue | None = None, last_completed_story: str | None = None, budget: BudgetState | None = None) -> None`
  - [x] 4.2: Read existing `run.yaml` via `await asyncio.to_thread(load_yaml, path)` — if path doesn't exist, raise `RunError`
  - [x] 4.3: Apply only non-`None` updates:
    - `status` → set `data["status"] = status.value`
    - `last_completed_story` → set `data["last_completed_story"] = last_completed_story`
    - `budget` → set `data["budget"] = _serialize_budget(budget)`
  - [x] 4.4: Write back via `await asyncio.to_thread(save_yaml, path, data)`
  - [x] 4.5: Wrap the `load_yaml` call in try/except for `OSError` and `ConfigError` — convert to `RunError`

- [x] Task 5: Implement `update_story_status()` async function (AC: #4)
  - [x] 5.1: Function signature: `async def update_story_status(project_root: Path, run_id: str, story_slug: str, *, status: str, started_at: str | None = None, completed_at: str | None = None, retry_count: int | None = None) -> None`
  - [x] 5.2: Read existing `run.yaml` — raise `RunError` if missing
  - [x] 5.3: Locate or create story entry in `data["stories"]`:
    - If `story_slug` exists: update only non-`None` fields
    - If `story_slug` doesn't exist: create new entry with provided values and defaults
  - [x] 5.4: Apply field updates carefully — `status` is always set (required param), others only if non-None
  - [x] 5.5: Write back via `save_yaml`

- [x] Task 6: Implement `get_run_status()` async function (AC: #5)
  - [x] 6.1: Function signature: `async def get_run_status(project_root: Path, run_id: str) -> RunStatus`
  - [x] 6.2: Read `run.yaml` — raise `RunError("Run not found: {run_id}")` if missing
  - [x] 6.3: Parse `stories` dict — construct `StoryStatusEntry` for each entry using `model_validate()`
  - [x] 6.4: Construct and return `RunStatus.model_validate(...)` from loaded data
  - [x] 6.5: Catch `pydantic.ValidationError` and wrap in `RunError` with descriptive message

- [x] Task 7: Implement `list_runs()` async function (AC: #6)
  - [x] 7.1: Function signature: `async def list_runs(project_root: Path) -> list[RunSummary]`
  - [x] 7.2: Compute runs dir: `project_root / DIR_ARCWRIGHT / DIR_RUNS`
  - [x] 7.3: If runs dir doesn't exist → return `[]`
  - [x] 7.4: Iterate subdirectories via `await asyncio.to_thread(lambda: sorted(runs_dir.iterdir()))`, filter to directories only
  - [x] 7.5: For each subdir: check for `run.yaml`, load it, safely parse status and story counts
  - [x] 7.6: Compute `completed_count` by counting stories where status is "success" or TaskState.SUCCESS value
  - [x] 7.7: Build `RunSummary` for each valid run
  - [x] 7.8: Sort by `start_time` descending, return list
  - [x] 7.9: Silently skip (log at debug level) subdirectories that lack `run.yaml` or have malformed content

- [x] Task 8: Update `output/__init__.py` exports (AC: #8)
  - [x] 8.1: Update `__all__` to alphabetically sorted list including all new public symbols: `RunStatus`, `RunStatusValue`, `RunSummary`, `StoryStatusEntry`, `create_run`, `generate_run_id`, `get_run_status`, `list_runs`, `update_run_status`, `update_story_status` plus existing provenance exports
  - [x] 8.2: Add imports from `output.run_manager`

- [x] Task 9: Create unit tests in `tests/test_output/test_run_manager.py` (AC: #9)
  - [x] 9.1: Test `generate_run_id()` pattern match `^\d{8}-\d{6}-[0-9a-f]{6}$` and uniqueness
  - [x] 9.2: Test `create_run()` directory structure (run dir, stories subdir, run.yaml exists)
  - [x] 9.3: Test `create_run()` run.yaml content — all required keys, correct initial values, stories populated
  - [x] 9.4: Test `create_run()` config_snapshot excludes API key (NFR6)
  - [x] 9.5: Test `create_run()` Decimal budget fields serialized as strings
  - [x] 9.6: Test `update_run_status()` partial update — change status only, verify other fields unchanged
  - [x] 9.7: Test `update_run_status()` budget replacement — full budget section updated
  - [x] 9.8: Test `update_run_status()` on missing run.yaml → RunError
  - [x] 9.9: Test `update_story_status()` updates existing story entry
  - [x] 9.10: Test `update_story_status()` creates new story entry
  - [x] 9.11: Test `update_story_status()` on missing run.yaml → RunError
  - [x] 9.12: Test `update_story_status()` partial update — only specified fields change
  - [x] 9.13: Test `get_run_status()` returns correct RunStatus model
  - [x] 9.14: Test `get_run_status()` on missing run → RunError
  - [x] 9.15: Test `list_runs()` returns sorted summaries (most recent first)
  - [x] 9.16: Test `list_runs()` on empty/missing runs dir → empty list
  - [x] 9.17: Test `list_runs()` skips directories without run.yaml
  - [x] 9.18: Test `update_run_status()` with `RunStatusValue.HALTED` persists correctly
  - [x] 9.19: All tests use `tmp_path` fixture, `@pytest.mark.asyncio` decorators

- [x] Task 10: Run quality gates (AC: #10, #11, #12, #13)
  - [x] 10.1: `ruff check .` — zero violations against FULL repository
  - [x] 10.2: `ruff format --check .` — zero formatting issues
  - [x] 10.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 10.4: `pytest` — all tests pass (388 existing + 23 new = 411 total)
  - [x] 10.5: Verify Google-style docstrings on all public functions and models

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `output → core` only. The `output/run_manager.py` module must NEVER import from `engine/`, `agent/`, `validation/`, `context/`, `scm/`, or `cli/`. It uses `RunConfig` from `core/config.py`, `BudgetState`/`RunId`/`ArcwrightModel` from `core/types.py`, `RunError` from `core/exceptions.py`, `load_yaml`/`save_yaml` from `core/io.py`, and constants from `core/constants.py`. That's the entire dependency surface.

**D5 — Run Directory Schema**: Run ID format `YYYYMMDD-HHMMSS-<short-uuid>` (e.g., `20260302-143022-a1b2c3`). Run directory at `.arcwright-ai/runs/<run-id>/`. Contains `run.yaml` (metadata), `stories/` (per-story artifacts), `log.jsonl` (structured log). The `run.yaml` file is the run's persistent state — updated at every state transition.

**D5 — Write Policy**: LangGraph state is the authority during graph execution. Run directory files are transition checkpoints. The run_manager module is the single writer for `run.yaml` — no other module should read/write `run.yaml` directly. Currently, `engine/nodes.py` writes `context-bundle.md`, `agent-output.md`, and `validation.md` directly to the run directory — Story 4.4 will wire those writes through the run_manager/provenance APIs.

**Architecture Boundary 4**: All `.arcwright-ai/` writes should go through `output/run_manager.py`. This story establishes the `run.yaml` management API that Story 4.4 will wire into the engine nodes. The existing direct writes in `engine/nodes.py` (checkpoint files) are NOT modified by this story — that migration belongs to Story 4.4.

**NFR2 — Progress Recovery**: The `last_completed_story` field in `run.yaml` is the resume pointer. Story 5.3 (Resume Controller) will read this field to determine where to restart. The run_manager must keep this field accurate at every story completion.

**NFR6 — API Key Security**: The `config_snapshot` in `run.yaml` must NEVER contain the API key. The `_build_config_snapshot()` helper explicitly extracts only operational fields, excluding `api.claude_api_key`.

**NFR8 — State Integrity**: `run.yaml` updates use read-modify-write cycles through `load_yaml`/`save_yaml`. These are synchronous on the file system level (no partial writes since `save_yaml` uses `Path.write_text` which is atomic on most filesystems for small files). Wrapped in `asyncio.to_thread()` for async compatibility.

**NFR19 — Idempotency**: `create_run()` uses `mkdir(parents=True, exist_ok=True)` — re-running with the same ID is safe. `update_story_status()` creating a new entry for an unknown slug is additive, not destructive.

### Existing Code to Reuse — DO NOT REINVENT

- **`RunId`** already exists in `core/types.py` as a `NewType("RunId", str)`. Use it directly for the return type of `generate_run_id()`.
- **`BudgetState`** already exists in `core/types.py` as a frozen `ArcwrightModel` with fields: `invocation_count` (int), `total_tokens` (int), `estimated_cost` (Decimal), `max_invocations` (int), `max_cost` (Decimal). Serialize via `model_dump()`.
- **`RunConfig`** (from `core/config.py`) contains sub-models: `api` (ApiConfig with `claude_api_key`), `model` (ModelConfig with `version`), `limits` (LimitsConfig with `tokens_per_story`, `cost_per_run`, `retry_budget`, `timeout_per_story`), `methodology` (MethodologyConfig with `artifacts_path`, `type`), `scm` (ScmConfig with `branch_template`), `reproducibility` (ReproducibilityConfig).
- **`load_yaml()`** and **`save_yaml()`** in `core/io.py` — synchronous functions. `load_yaml` returns `dict[str, Any]`, raises `ConfigError`. `save_yaml` creates parent dirs and writes with `safe_dump`. For async: wrap in `asyncio.to_thread()`.
- **`RunError`** from `core/exceptions.py` — carries `message` and optional `details` dict.
- **`ArcwrightModel`** from `core/types.py` — base with `frozen=True`, `extra="forbid"`, `str_strip_whitespace=True`.
- **Constants from `core/constants.py`**: `DIR_ARCWRIGHT = ".arcwright-ai"`, `DIR_RUNS = "runs"`, `DIR_STORIES = "stories"`, `RUN_METADATA_FILENAME = "run.yaml"`, `RUN_ID_DATETIME_FORMAT = "%Y%m%d-%H%M%S"`.
- **`TaskState`** in `core/lifecycle.py` — the `SUCCESS = "success"` value is used when counting completed stories in `list_runs()`.

### Relationship to Other Stories in Epic 4

- **Story 4.1 (done)**: Created `output/provenance.py` — standalone provenance recording module
- **Story 4.2 (this)**: Creates `output/run_manager.py` — run directory lifecycle and `run.yaml` management
- **Story 4.3**: Creates `output/summary.py` — run summary and halt report generation. Will consume `get_run_status()` from this story to gather data for summaries.
- **Story 4.4**: Wires Stories 4.1, 4.2, 4.3 into the LangGraph engine nodes. Will call `create_run()`, `update_run_status()`, `update_story_status()` from within graph nodes. That is where the existing direct checkpoint writes in `engine/nodes.py` get complemented with run.yaml state tracking.

### YAML Serialization Pitfall — Decimal Handling

`BudgetState` uses `Decimal` for `estimated_cost` and `max_cost`. PyYAML's `safe_dump` cannot serialize `Decimal` objects — it will raise a `RepresenterError`. The `_serialize_budget()` helper MUST convert `Decimal` values to `str` before passing to `save_yaml()`. Example:

```python
def _serialize_budget(budget: BudgetState) -> dict[str, Any]:
    data = budget.model_dump()
    for key in ("estimated_cost", "max_cost"):
        if isinstance(data.get(key), Decimal):
            data[key] = str(data[key])
    return data
```

When reading back via `get_run_status()`, the budget dict will have string values for cost fields. This is acceptable — `RunStatus.budget` is typed as `dict[str, Any]`. Story 7.1 may later introduce a richer typed budget model for display.

### `load_yaml` Error Handling

`load_yaml()` raises `ConfigError` on file read failures and YAML parse errors. The run_manager should catch `ConfigError` and `OSError` when loading `run.yaml` and re-raise as `RunError` to maintain the correct exception domain. The error hierarchy boundary is important: `ConfigError` is for config files, `RunError` is for run directory state.

### Testing Patterns

- Use `tmp_path` fixture for all file I/O tests — never write to real project directories
- Use `@pytest.mark.asyncio` for all async test functions
- Create helper fixtures for common setups (e.g., `_create_test_run()` that calls `create_run()` with test data)
- For `RunConfig` in tests: construct with `ApiConfig(claude_api_key="test-key-123")` wrapped in `RunConfig(api=ApiConfig(...))` — the API key must be present in the model but must NOT appear in run.yaml
- Test both happy path and error paths (missing files, malformed YAML)
- Use `re.match()` for pattern-based assertions on run ID format
- Use `freezegun` or manual datetime injection if deterministic timestamps are needed — but for most tests, verifying the format (ISO 8601) is sufficient without pinning exact values

### Project Structure Notes

The `output/` package layout after this story:

```
src/arcwright_ai/output/
├── __init__.py          # Updated: exports run_manager symbols + existing provenance exports
├── provenance.py        # UNCHANGED: Story 4.1 implementation
├── run_manager.py       # NEW: Run directory lifecycle + state tracking
└── summary.py           # UNCHANGED: Still empty stub (Story 4.3)
```

Test structure:

```
tests/test_output/
├── __init__.py          # EXISTS: Empty
├── .gitkeep             # EXISTS: Can be removed after adding test_run_manager.py
├── test_provenance.py   # EXISTS: 16 tests from Story 4.1
└── test_run_manager.py  # NEW: ~19 run manager unit tests
```

### Known Pitfalls from Epics 1-3

1. **`__all__` ordering must be alphabetical** — ruff enforces this. Exports in `output/__init__.py` must be sorted.
2. **No aspirational exports** — only export symbols that actually exist and are implemented. Do NOT pre-export planned Story 4.3 symbols.
3. **`from __future__ import annotations`** at the top of every module — required for `X | None` union syntax.
4. **`frozen=True`** on `ArcwrightModel` — model instances are immutable. Use `model_copy(update={...})` for mutations if needed. For run.yaml read-modify-write, work with raw dicts from `load_yaml()`.
5. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just `ruff check src/arcwright_ai/output/`), and failures in ANY file must be reported honestly. Do not self-report "zero violations" if violations exist anywhere.
6. **Off-by-one in state mutation sequences** — when counting completed stories or tracking retry counts, verify expected values at each point explicitly. Pre-increment vs post-increment matters.
7. **Structured log event payloads must include ALL fields documented in ACs** — not directly applicable to this story (no structured log events emitted from run_manager), but relevant for Story 4.4 integration.
8. **Use `asyncio.to_thread()` for synchronous operations in async functions** — `load_yaml()`, `save_yaml()`, `path.mkdir()`, `path.exists()`, `path.iterdir()` are all synchronous — wrap each in `asyncio.to_thread()`.
9. **File list in Dev Agent Record must match actual git changes** — verify against `git status` before claiming completion.
10. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
11. **Decimal serialization for YAML** — PyYAML `safe_dump` cannot handle `Decimal`. Always convert to `str` before saving.
12. **`ConfigError` → `RunError` domain boundary** — `load_yaml()` raises `ConfigError` but run_manager should present `RunError` to callers. Catch and re-raise with appropriate message.

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy]
- [Source: _spec/planning-artifacts/architecture.md — Decision 8: Logging & Observability]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/architecture.md — Async Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Python Code Style Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Boundary 4: Application ↔ File System]
- [Source: _spec/planning-artifacts/epics.md — Epic 4, Story 4.2]
- [Source: _spec/planning-artifacts/prd.md — FR31, FR32, FR33]
- [Source: _spec/planning-artifacts/prd.md — NFR2, NFR6, NFR8, NFR16, NFR19]
- [Source: _spec/implementation-artifacts/epic-3-retro-2026-03-04.md — Action Items]
- [Source: _spec/implementation-artifacts/4-1-provenance-recorder-decision-logging-during-execution.md — Patterns established]
- [Source: src/arcwright_ai/core/types.py — BudgetState, RunId, ArcwrightModel]
- [Source: src/arcwright_ai/core/constants.py — DIR_RUNS, RUN_METADATA_FILENAME, RUN_ID_DATETIME_FORMAT, DIR_STORIES]
- [Source: src/arcwright_ai/core/io.py — load_yaml, save_yaml]
- [Source: src/arcwright_ai/core/exceptions.py — RunError]
- [Source: src/arcwright_ai/core/config.py — RunConfig, ApiConfig, LimitsConfig, etc.]
- [Source: src/arcwright_ai/output/__init__.py — current exports]
- [Source: src/arcwright_ai/output/run_manager.py — current empty stub]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

No blocking issues encountered.

### Completion Notes List

- Implemented `output/run_manager.py` from scratch: `RunStatusValue`, `StoryStatusEntry`, `RunStatus`, `RunSummary` models plus 6 public async functions (`generate_run_id`, `create_run`, `update_run_status`, `update_story_status`, `get_run_status`, `list_runs`) and 4 private helpers.
- `_serialize_budget()` converts Decimal fields to `str` before `safe_dump` — YAML-safe per pitfall #11.
- `_load_run_yaml()` private helper centralises `ConfigError`→`RunError` domain translation (pitfall #12).
- All async functions wrap synchronous I/O in `asyncio.to_thread()` per NFR8/pitfall #8.
- `_build_config_snapshot()` explicitly excludes `api.claude_api_key` per NFR6.
- `create_run()` lazily imports `BudgetState` inside the function body to stay TYPE_CHECKING-friendly for the `BudgetState` default budget.
- ruff auto-fixed 5 issues: import sort (#I001) and 2× `timezone.utc` → `datetime.UTC` alias (#UP017).
- 23 new tests added covering all 18 AC#9 scenarios (a–r) plus 5 bonus correctness tests.
- All 411 tests pass; zero ruff violations; zero mypy --strict errors.
- Code review follow-up fixes applied: removed remaining synchronous filesystem checks from async paths and aligned completed-count semantics in `list_runs()` with TaskState success value handling.

### File List

- src/arcwright_ai/output/run_manager.py
- src/arcwright_ai/output/__init__.py
- tests/test_output/test_run_manager.py
- _spec/implementation-artifacts/4-2-run-manager-run-directory-lifecycle-and-state-tracking.md
- _spec/implementation-artifacts/sprint-status.yaml

## Senior Developer Review (AI)

### Reviewer

Ed

### Date

2026-03-04

### Outcome

Approve

### Summary

Adversarial review completed against ACs, task checklist, and git reality. Three medium findings were identified and resolved in-session.

### Findings and Resolutions

- [x] [MEDIUM] Async filesystem checks remained in async paths (`path.exists()` / `is_dir()` / `yaml_path.exists()`), risking event-loop blocking under high run counts. Fixed by moving these checks behind `asyncio.to_thread()` in `get_run_status()` and `list_runs()`.
- [x] [MEDIUM] `list_runs()` completed-count logic only matched literal `"success"`, while task guidance required compatibility with TaskState success semantics. Fixed by explicitly handling `TaskState.SUCCESS.value` in the completed-count predicate.
- [x] [MEDIUM] Story File List was out of sync with actual modified files (`sprint-status.yaml` and this story file). Fixed by reconciling the File List with git state.

## Change Log

- 2026-03-04: Implemented Story 4.2 — `output/run_manager.py` run directory lifecycle and state tracking. Added `RunStatusValue`, `StoryStatusEntry`, `RunStatus`, `RunSummary` models; `generate_run_id`, `create_run`, `update_run_status`, `update_story_status`, `get_run_status`, `list_runs` public functions. Updated `output/__init__.py` exports. Added 23 unit tests in `tests/test_output/test_run_manager.py`. All 411 tests pass; zero ruff/mypy violations.
- 2026-03-04: Senior code review completed. Resolved 3 medium findings (async path checks, completed-count semantics alignment, and story/git file-list reconciliation). Story approved and moved to done.
