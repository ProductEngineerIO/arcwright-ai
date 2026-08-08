# Story 10.17: Historical Cost Estimation in Dispatch Confirmation

Status: done

## Story

As a developer using Arcwright AI for overnight epic dispatch,
I want the pre-dispatch confirmation to show a real estimated cost range derived from past runs,
so that I can make informed decisions before committing to an overnight run instead of seeing a useless `$?.?? - $?.??` placeholder.

## Acceptance Criteria

1. **Given** at least one past run exists with per-story cost data **When** `dispatch --epic` shows the confirmation prompt **Then** the estimated cost range line reads `Estimated cost range: $X.XX - $Y.YY (based on N stories across M runs)` where the range is `min_per_story × story_count` to `max_per_story × story_count`, N is the total number of historical per-story cost samples used, and M is the number of distinct runs those samples came from.
2. **Given** no past runs exist, or all past runs contain only zero-cost stories (i.e., failed before any agent invocation) **When** the confirmation prompt is shown **Then** the line reads `Estimated cost range: $?.?? - $?.?? (no historical data available)` — unchanged from the current placeholder.
3. **Given** past runs exist **When** computing the range **Then** only the most recent 10 completed runs are considered (sorted by run directory name, which is already time-ordered by the `YYYYMMDD-HHMMSS-` prefix).
4. **Given** a story in a past run has `cost == "0"` or `cost == "0.0"` (failed before agent invocation) **When** building the cost sample set **Then** that story's cost is excluded from the min/max computation.
5. **Given** `_show_dispatch_confirmation` is called **When** the runs directory does not exist, or any individual `run.yaml` fails to parse **Then** those runs are silently skipped and execution continues — the fallback `$?.?? - $?.??` is shown if no valid samples remain.
6. **Given** cost values stored in `run.yaml` are strings (e.g. `"0.1234"`) **When** computing min/max **Then** they are correctly parsed as `Decimal` for precision-safe arithmetic.
7. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1 — Add `_estimate_cost_range()` helper in `dispatch.py` (AC: #1, #2, #3, #4, #5, #6)
  - [x] 1.0 Add missing imports to `dispatch.py`: extend the `from arcwright_ai.core.constants import (...)` block with `DIR_RUNS` and `RUN_METADATA_FILENAME`; add `from arcwright_ai.core.io import load_yaml` below the existing `from arcwright_ai.core.config import ...` line. Verify first with `grep "load_yaml\|DIR_RUNS\|RUN_METADATA" cli/dispatch.py` — skip any that are already present.
  - [x] 1.1 Add `_estimate_cost_range(project_root: Path, story_count: int) -> tuple[Decimal, Decimal, int, int] | None` as a private synchronous helper in `cli/dispatch.py`, placed above `_show_dispatch_confirmation`; return `None` if `story_count == 0`
  - [x] 1.2 Resolve runs directory: `project_root / DIR_ARCWRIGHT / DIR_RUNS`; return `None` immediately if it does not exist
  - [x] 1.3 List all subdirectories, sort them (ascending by name — run IDs are already time-ordered), take the last 10 (i.e. `subdirs[-10:]`)
  - [x] 1.4 For each run subdir, load `run.yaml` via `load_yaml(subdir / RUN_METADATA_FILENAME)`; skip silently on `ConfigError` or `OSError`
  - [x] 1.5 From each loaded run, navigate `raw.get("budget", {}).get("per_story", {})`; for each story entry extract `entry.get("cost", "0")`; convert to `Decimal` inside a `try/except (ValueError, InvalidOperation)`; skip the entry on conversion failure or if the value is `<= Decimal("0")`
  - [x] 1.6 Initialize `samples: list[Decimal] = []` and `runs_with_data: int = 0` before the loop. For each run subdir, collect its valid per-story costs into a local `run_samples` list; if `run_samples` is non-empty after processing that run, extend `samples` with `run_samples` and increment `runs_with_data` by 1
  - [x] 1.7 If the accumulated sample list is empty, return `None`
  - [x] 1.8 Return `(min(samples) * story_count, max(samples) * story_count, len(samples), runs_with_data)` — the projected low and high total cost for this dispatch, plus sample and run counts for formatting

- [x] Task 2 — Update `_show_dispatch_confirmation` to use the estimate (AC: #1, #2)
  - [x] 2.1 Add `project_root: Path` parameter to `_show_dispatch_confirmation` signature (keyword-only after `config`)
  - [x] 2.2 Call `_estimate_cost_range(project_root, story_count)` inside `_show_dispatch_confirmation` (before the budget ceilings echo block is fine)
  - [x] 2.3 If the helper returns `None`, keep the existing fallback line: `"\n   Estimated cost range: $?.?? - $?.?? (no historical data available)"`
  - [x] 2.4 If the helper returns a 4-tuple, unpack as `low, high, sample_count, runs_with_data = result`; format the line as: `f"\n   Estimated cost range: ${low:.2f} - ${high:.2f} (based on {sample_count} stories across {runs_with_data} runs)"`
  - [x] 2.5 Update the call site at line ~632 (inside `_dispatch_epic_async`): add `project_root=project_root` to the `_show_dispatch_confirmation(...)` call

- [x] Task 3 — Tests (AC: #7)
  - [x] 3.1 Unit test: runs dir does not exist → `_estimate_cost_range` returns `None`
  - [x] 3.2 Unit test: runs dir exists but all runs have zero-cost stories → returns `None`
  - [x] 3.3 Unit test: single run with one story (cost `"0.5000"`) and `story_count=3` → returns `(Decimal("1.50"), Decimal("1.50"), 1, 1)`
  - [x] 3.4 Unit test: two runs with costs `["0.50", "1.20"]` and `story_count=2` → returns `(Decimal("1.00"), Decimal("2.40"), 2, 2)`
  - [x] 3.5 Unit test: more than 10 run dirs → only the last 10 are scanned (oldest is excluded)
  - [x] 3.6 Unit test: a `run.yaml` that fails to parse is silently skipped; valid runs still contribute
  - [x] 3.7 Unit test: `_show_dispatch_confirmation` displays the formatted range string when data is available
  - [x] 3.8 Unit test: `_show_dispatch_confirmation` displays the `$?.??` fallback when no data

## Dev Notes

### Problem Context

`_show_dispatch_confirmation` in `cli/dispatch.py` has contained a hardcoded placeholder since it was written:

```python
typer.echo(
    "\n   Estimated cost range: $?.?? - $?.?? (no historical data available)",
    err=True,
)
```

The data to replace this has always been available: every completed run writes per-story cost to `run.yaml` under `budget.per_story[story_slug]["cost"]`. This story wires the two together.

### Data Source: `run.yaml` Budget Section

```yaml
# .arcwright-ai/runs/20260808-120000-a7f3/run.yaml
budget:
  estimated_cost: "2.4512"
  max_cost: "25.0"
  per_story:
    10-15-run-cost-in-pr-body:
      cost: "1.1834"
      cost_by_role:
        generate: "1.0200"
        review: "0.1634"
      tokens_input: 48200
      tokens_output: 3100
    10-16-mark-story-done-in-sprint-status-before-pr-creation:
      cost: "1.2678"
      cost_by_role: ...
```

`cost` fields are serialized as strings (see `_serialize_budget` in `run_manager.py` — PyYAML cannot handle `Decimal` objects directly).

### Helper Return Type

Return type: `tuple[Decimal, Decimal, int, int] | None` — `(low_total, high_total, sample_count, runs_with_data)`. The last two ints let `_show_dispatch_confirmation` format the count details without doing any computation itself. Return `None` on no data or when `story_count == 0`.

### Implementation Location

All changes are in `arcwright-ai/src/arcwright_ai/cli/dispatch.py`:

```
_estimate_cost_range(project_root, story_count)   ← new private helper
_show_dispatch_confirmation(...)                   ← add project_root param, call helper
_dispatch_epic_async(...)                          ← update call site to pass project_root
```

### Current Call Site (line ~632)

```python
# Before:
_show_dispatch_confirmation(epic_spec, stories, config, skip_confirm=skip_confirm)

# After:
_show_dispatch_confirmation(epic_spec, stories, config, project_root=project_root, skip_confirm=skip_confirm)
```

`project_root` is already resolved earlier in `_dispatch_epic_async` (via `_discover_project_root()`).

### Required Imports (dispatch.py additions)

```python
from decimal import Decimal  # already imported — check before adding
from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, RUN_METADATA_FILENAME  # check existing imports
from arcwright_ai.core.io import load_yaml  # likely not yet imported in dispatch.py — add if missing
```

Verify with `grep -n "^from\|^import" cli/dispatch.py` before adding.

### Synchronous I/O is Intentional

`_show_dispatch_confirmation` is a synchronous function called from within `_dispatch_epic_async`. Keeping `_estimate_cost_range` synchronous is correct — making it async would require `_show_dispatch_confirmation` to become async too, adding unnecessary complexity for a brief pre-dispatch UX step. Reading at most 10 small YAML files is imperceptible in practice. Do NOT refactor to use `asyncio.to_thread` or the async `list_runs()`/`get_run_status()` from `run_manager.py` — those are async and would break the synchronous call chain.

### Edge Cases

- Run dirs with no `budget` key (very old format): `raw.get("budget", {})` returns `{}` → no samples contributed → no crash
- Story entries where `cost` key is missing: `entry.get("cost", "0")` → treated as 0 → filtered out
- `Decimal` conversion of malformed string: wrap in try/except, skip that entry
- `story_count == 0`: multiply by 0 would produce `(0, 0)` — guard: return `None` if `story_count == 0`

### Test File

All Task 3 tests go in `arcwright-ai/tests/test_cli/test_dispatch.py` (existing file, 37 tests). Add a new section `# _estimate_cost_range tests` and `# _show_dispatch_confirmation cost range tests` to group them.

### References

- [Source: arcwright-ai/src/arcwright_ai/cli/dispatch.py#_show_dispatch_confirmation] — target function, current placeholder at line ~384
- [Source: arcwright-ai/src/arcwright_ai/output/run_manager.py#_serialize_budget] — confirms cost fields are string-serialized Decimals
- [Source: arcwright-ai/src/arcwright_ai/output/run_manager.py#list_runs] — reference pattern for scanning run dirs synchronously vs async (use sync equivalent here)
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py] — `DIR_ARCWRIGHT`, `DIR_RUNS`, `RUN_METADATA_FILENAME`
- [Source: arcwright-ai/src/arcwright_ai/core/io.py#load_yaml] — synchronous YAML loader

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.5 (GitHub Copilot)

### Debug Log References

- `ruff check` — all checks passed (repo-wide)
- `mypy --strict src/arcwright_ai` — no issues found (44 source files)
- `pytest tests/test_cli/test_dispatch.py` — 45 passed (37 existing + 8 new)
- `pytest` (full suite) — 1225 passed, 4 pre-existing failures in `tests/test_core/test_config.py` unrelated to this story (default model version mismatch from a local override; verified present on `main` before this story's changes via `git stash`)

### Completion Notes List

- Added `_estimate_cost_range(project_root, story_count)` in `cli/dispatch.py`: scans the last 10 run directories under `.arcwright-ai/runs/`, loads each `run.yaml` via `load_yaml`, extracts positive per-story `cost` values from `budget.per_story`, and returns `(low_total, high_total, sample_count, runs_with_data)` or `None` when no usable samples exist (or `story_count == 0`).
- `_show_dispatch_confirmation` now takes a keyword-only `project_root: Path` parameter and calls `_estimate_cost_range` to render either the real estimated range (`$X.XX - $Y.YY (based on N stories across M runs)`) or the original `$?.?? - $?.?? (no historical data available)` fallback.
- Updated the single call site in `_dispatch_epic_async` to pass `project_root=project_root`.
- Added 8 new unit tests covering: missing runs dir, all-zero-cost runs, single/multi-run min-max projection, the 10-run cap (oldest run excluded), silent skip of unparseable `run.yaml`, and both display branches of `_show_dispatch_confirmation`.
- Sprint status updated: `10-17-historical-cost-estimation-in-dispatch-confirmation` → `review`.
- **Code review (2026-08-08):** No CRITICAL/HIGH/MEDIUM findings — File List matched `git diff` exactly, all 7 ACs verified against implementation, all 8 unit tests confirmed genuine (re-ran `ruff check`, `mypy --strict`, and the full `pytest` suite independently: 1225 passed, same 4 pre-existing unrelated failures in `test_config.py`). Fixed 2 LOW findings: (1) guarded `_estimate_cost_range` against non-mapping `per_story` entries with an `isinstance(entry, dict)` check to avoid a possible `AttributeError` on corrupted `run.yaml` data; (2) removed the redundant `OSError` clause from the `except` around `load_yaml(...)` since `load_yaml` already wraps `OSError` into `ConfigError`. Added `test_estimate_cost_range_skips_non_mapping_story_entries` (46 tests total in `test_dispatch.py`, up from 45).

### File List

- `arcwright-ai/src/arcwright_ai/cli/dispatch.py`
- `arcwright-ai/tests/test_cli/test_dispatch.py`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/implementation-artifacts/10-17-historical-cost-estimation-in-dispatch-confirmation.md`

### Change Log

- 2026-08-08: Implemented `_estimate_cost_range()` helper and wired it into `_show_dispatch_confirmation`; 8 new tests added (Story 10.17)
