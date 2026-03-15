# Story 7.3: Cost Display in CLI Status & Run Summary

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer monitoring run progress or reviewing completed runs,
I want cost information displayed clearly in status and summary outputs,
so that I can make informed decisions about dispatching and budget allocation.

## Acceptance Criteria (BDD)

1. **Given** cost data accumulated in `BudgetState` and persisted in `run.yaml` **When** the developer runs `arcwright-ai status` **Then** the cost section includes: total tokens (input + output, comma-formatted), estimated cost (formatted as `"$X.XX"`), per-story breakdown (table with slug, tokens, cost, invocations), and budget remaining (percentage and absolute amount). The budget remaining shows "unlimited" when `max_cost == 0` and "unlimited" when `max_invocations == 0`.

2. **Given** a completed or halted run **When** the run summary (`summary.md`) is generated via `write_success_summary`, `write_halt_report`, or `write_timeout_summary` **Then** the Cost Summary section includes: total cost (formatted `"$X.XX"`), per-story costs (markdown table with slug, tokens_input, tokens_output, cost, invocations), retry overhead (cost spent on retries vs first-pass — calculated from per-story `invocations > 1`), and budget utilization percentage (or "unlimited" when `max_cost == 0`).

3. **Given** any cost or token value **When** displayed to the user (CLI or summary) **Then** cost is formatted human-readable: `"$1.17"` not `"0.00117 USD"` or `"1.17"`, tokens are comma-separated: `"12,450 tokens"` not `"12450"`, zero cost displays as `"$0.00"`, zero tokens displays as `"0 tokens"`.

4. **Given** a run is in progress **When** `arcwright-ai status` is called **Then** the status shows live cost from the current `run.yaml` budget section, including any per-story data accumulated so far.

5. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

6. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

7. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

8. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 762 existing tests continue to pass.

9. **Given** new and updated tests **When** the test suite runs **Then** tests cover:
    (a) `format_cost` returns `"$1.17"` for `Decimal("1.17")`, `"$0.00"` for zero, `"$0.01"` for `Decimal("0.005")` (rounding);
    (b) `format_tokens` returns `"12,450"` for 12450, `"0"` for 0, `"1,000,000"` for 1000000;
    (c) `format_budget_remaining` returns percentage and absolute, returns `"unlimited"` for zero ceiling;
    (d) CLI status output includes `"$"` prefix in cost display;
    (e) CLI status output includes per-story breakdown table when `per_story` is non-empty;
    (f) CLI status output hides per-story table when `per_story` is empty;
    (g) `write_success_summary` cost section includes per-story markdown table;
    (h) `write_success_summary` cost section includes retry overhead line;
    (i) `write_halt_report` Run Context section includes formatted cost values (not raw);
    (j) `write_timeout_summary` cost section includes formatted values;
    (k) Budget remaining shows correct percentage (e.g., `"73% ($7.30 of $10.00)"`) when max_cost is set;
    (l) Retry overhead calculation: story with 3 invocations at $0.50 each → first-pass $0.50, retries $1.00, retry overhead 200%;
    (m) Existing status tests still pass with updated output format;
    (n) Existing summary tests still pass with updated output format.

## Boundary Conditions

- **Boundary 1 (Empty per_story):** When `per_story` is `{}` (no stories dispatched yet), CLI status and summaries must not crash — display `"No per-story data yet"` or skip the table. Both the dict being missing from `run.yaml` (old runs) and being present but empty must be handled.
- **Boundary 2 (Zero max_cost/max_invocations):** When budget ceilings are `0` (unlimited), display `"unlimited"` in the budget remaining field, not a divide-by-zero error or negative percentage.
- **Boundary 3 (Decimal precision):** Cost formatting must handle high-precision Decimal values gracefully. `Decimal("0.123456789")` should display as `"$0.12"` (2 decimal places). All formatting uses `Decimal` quantization to `0.01`, never `float` rounding.
- **Boundary 4 (Backwards compatibility):** Old `run.yaml` files without `per_story`, `total_tokens_input`, or `total_tokens_output` in the budget dict must render without error — use `.get()` with defaults.
- **Boundary 5 (String cost values):** `run.yaml` serializes `estimated_cost` and `max_cost` as strings (via `_serialize_budget`). The formatting functions must handle both `Decimal` and `str` input types, parsing strings to `Decimal` before formatting.
- **Boundary 6 (Very large values):** Token counts in the millions (e.g., 5,000,000) must comma-format correctly. Cost values above $100 should format correctly (e.g., `"$123.45"`).

## Tasks / Subtasks

- [x] Task 1: Create cost formatting utility functions (AC: #3)
  - [x] 1.1: In `output/summary.py`, add `format_cost(value: Decimal | str | int | float | None) -> str`
  - [x] 1.2: In `output/summary.py`, add `format_tokens(value: int | str | None) -> str`
  - [x] 1.3: In `output/summary.py`, add `format_budget_remaining(current: Decimal | str, ceiling: Decimal | str) -> str`
  - [x] 1.4: In `output/summary.py`, add `format_retry_overhead(per_story: dict[str, Any]) -> str`
  - [x] 1.5: Add Google-style docstrings to all four functions.

- [x] Task 2: Enhance CLI status cost display (AC: #1, #3, #4)
  - [x] 2.1: In `cli/status.py`, import `format_cost`, `format_tokens`, `format_budget_remaining` from `output/summary.py`.
  - [x] 2.2: Update cost section output to show formatted tokens with input/output split.
  - [x] 2.3: Update cost value to show `"  Est. Cost:   $X.XX"` using `format_cost`.
  - [x] 2.4: Add budget remaining line using `format_budget_remaining`.
  - [x] 2.5: Add per-story breakdown table when `per_story` is non-empty.
  - [x] 2.6: If `per_story` is empty or missing from budget dict, skip the per-story table entirely.

- [x] Task 3: Enhance run summary cost section in `write_success_summary` (AC: #2, #3)
  - [x] 3.1: Replace the existing Cost Summary section with enhanced version.
  - [x] 3.2: Add formatted total cost line using `format_cost`.
  - [x] 3.3: Add formatted total tokens lines using `format_tokens`.
  - [x] 3.4: Add formatted invocations count.
  - [x] 3.5: Add budget utilization line using `format_budget_remaining`.
  - [x] 3.6: Add per-story cost markdown table.
  - [x] 3.7: Add retry overhead line using `format_retry_overhead`.

- [x] Task 4: Enhance halt report cost section in `write_halt_report` (AC: #2, #3)
  - [x] 4.1: Update the Run Context section to use formatted cost values.
  - [x] 4.2: Replace raw invocation count with formatted string.
  - [x] 4.3: Replace raw tokens with `format_tokens`.
  - [x] 4.4: Replace raw cost with `format_cost`.
  - [x] 4.5: Add budget remaining display to halt report Run Context section.

- [x] Task 5: Enhance timeout summary cost section in `write_timeout_summary` (AC: #2, #3)
  - [x] 5.1: Update the Cost Summary section to use the same formatted output as `write_success_summary`.

- [x] Task 6: Update existing tests for new output format (AC: #8, #9m, #9n)
  - [x] 6.1: Update `test_status_budget_cost_display` to expect `"$"` prefix and comma-formatted tokens.
  - [x] 6.2: Update `test_status_budget_zero_values_display_na` → renamed to `test_status_budget_zero_values_display_formatted`, expects `"$0.00"`.
  - [x] 6.3: Update `test_write_success_summary_zero_budget_shows_na` → renamed to `test_write_success_summary_zero_budget_shows_formatted_zeros`, expects `"$0.00"`.
  - [x] 6.4: Halt report tests — no existing tests checked specific cost values; new tests added instead.
  - [x] 6.5: All 762 existing tests verified to still pass (792 total including new).

- [x] Task 7: Create new unit tests (AC: #9a-#9l)
  - [x] 7.1: In `tests/test_output/test_cost_formatting.py`, add tests for `format_cost`.
  - [x] 7.2: Add tests for `format_tokens`.
  - [x] 7.3: Add tests for `format_budget_remaining`.
  - [x] 7.4: Add tests for `format_retry_overhead`.
  - [x] 7.5: Add `test_status_per_story_breakdown_displayed` to `test_status.py`.
  - [x] 7.6: Add `test_status_per_story_empty_no_table` to `test_status.py`.
  - [x] 7.7: Add `test_write_success_summary_per_story_table` to `test_summary.py`.
  - [x] 7.8: Add `test_write_success_summary_retry_overhead` to `test_summary.py`.

- [x] Task 8: Verify all quality gates (AC: #5, #6, #7, #8)
  - [x] 8.1: Run `ruff check .` — zero violations.
  - [x] 8.2: Run `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 8.3: Verify all docstrings are Google-style.
  - [x] 8.4: Run full test suite — 792 tests pass (762 existing + 30 new).

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Implement AC #1 unlimited budget semantics for invocation ceiling in CLI/summaries. Budget remaining now treats `max_invocations == 0` as unlimited in status/summaries.
- [x] [AI-Review][HIGH] Align halted-run output with AC #2 cost section requirements (per-story costs + retry overhead in halted summary flow). `write_halt_report` now includes a full Cost Summary section.
- [x] [AI-Review][MEDIUM] Remove float conversion in `format_cost` to satisfy Decimal-only formatting requirement in Boundary 3 (`never float rounding`).
- [x] [AI-Review][MEDIUM] Update Dev Agent Record → File List to include all modified files.

## Dev Notes

### Existing Code Landscape

- **`_format_cost_value`** in `cli/status.py` (line 610) is the current cost formatting helper. It returns `"N/A"` for zero/empty values and `str(value)` for everything else. This story replaces its usage with proper `"$X.XX"` formatting. The function itself can remain for backward compat but its callers in `_status_async` will switch to the new formatters.

- **`_format_budget_field`** in `output/summary.py` (line 66) is the summary-side equivalent — returns `"N/A"` for zero/empty, else `str(value)`. Same replacement needed for all its call sites in `write_success_summary`, `write_halt_report`, and `write_timeout_summary`.

- **`_status_async`** in `cli/status.py` (line 690) is the async implementation of the status command. It currently reads budget dict and displays raw values with three lines (Invocations, Tokens, Est. Cost). This story expands it to include input/output token split, `$` formatting, per-story table, and budget remaining.

- **`write_success_summary`** in `output/summary.py` (line 168) builds `summary.md` for successful runs. Its Cost Summary section (line 239) currently shows 3 bullet points (Invocations, Total Tokens, Estimated Cost) using `_format_budget_field`. This story enhances with per-story table, retry overhead, budget utilization.

- **`write_halt_report`** in `output/summary.py` (line 290) builds `summary.md` for halted runs. Its Run Context section (around line 456) uses `_format_budget_field` for 3 cost lines. Needs same formatting enhancement.

- **`write_timeout_summary`** in `output/summary.py` (line 508) builds `summary.md` for timed-out runs. Its Cost Summary section uses same pattern. Needs same formatting enhancement.

- **`_serialize_budget`** in `output/run_manager.py` (line 204) converts `BudgetState` → YAML-safe dict, converting `Decimal` → `str`. The budget dict in `run.yaml` therefore has `estimated_cost` and `max_cost` as strings, and `per_story` entries with `cost` as strings. The new formatting functions must handle `str` inputs (parse to `Decimal` before formatting).

- **`RunStatus.budget`** is `dict[str, Any]` — not a typed model. Budget fields are accessed via `.get()` with defaults. The `per_story` value (when present) is `dict[str, dict[str, Any]]` where inner dicts have keys `tokens_input`, `tokens_output`, `cost` (str), `invocations` (int).

- **`BudgetState`** in `core/types.py` (line 123) has `total_tokens`, `total_tokens_input`, `total_tokens_output`, `estimated_cost`, `max_invocations`, `max_cost`, `per_story`, `invocation_count`. All from Story 7.1.

- **`StoryCost`** in `core/types.py` (line 103) has `tokens_input`, `tokens_output`, `cost` (Decimal), `invocations` (int). From Story 7.1.

### Architecture Compliance Notes

- **FR24 (Cost visibility):** Developer can view cost summary as part of run status output. This story fulfills the "formatted, human-readable" aspect.
- **FR31 (Run status):** Developer can check current or last run status via CLI, including completion state and cost summary. This story enhances the cost summary portion.
- **D8 (CLI output convention):** All CLI output goes to stderr via `typer.echo(..., err=True)`. Must be preserved.
- **Boundary 1 (CLI ↔ Engine):** CLI never imports engine internals. CLI can import from `output/` — this is the allowed dependency direction. The new formatting functions live in `output/summary.py` and are imported by `cli/status.py`.
- **Module DAG:** `output/summary.py` NEVER imports from `engine/`, `agent/`, `validation/`, `context/`, `scm/`, or `cli/`. Its full dependency surface is `core/constants`, `core/exceptions`, `core/io`, `output/run_manager`. New formatting functions need only `Decimal` from stdlib.

### Formatting Specification

Cost formatting uses Python's `Decimal.quantize` for exact 2-decimal-place output:
```python
from decimal import Decimal, ROUND_HALF_UP

def format_cost(value: Decimal | str | int | float | None) -> str:
    if value is None:
        return "$0.00"
    d = Decimal(str(value))
    quantized = d.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${quantized:,}"
```

Token formatting uses Python's built-in comma separator:
```python
def format_tokens(value: int | str | None) -> str:
    if value is None:
        return "0"
    return f"{int(value):,}"
```

### Previous Story Intelligence

**From Story 7.2 (Budget Check Node):**
- `AgentBudgetError` is raised from the dispatch layer (not from `budget_check_node` directly) to preserve `finalize_node` execution.
- `_derive_halt_reason` now detects budget breaches by checking `_is_budget_exceeded(state.budget)`.
- `_derive_suggested_fix` includes budget consumption breakdown for budget-exceeded halts — the halt report already has *some* budget info in the suggested fix text. This story standardizes the formatting.
- The `finalize_node` passes budget details through `write_halt_report` — the `suggested_fix` string may contain raw budget numbers that could benefit from the new formatting.

**From Story 7.1 (BudgetState Model):**
- `StoryCost` is frozen; accumulation uses `model_copy(update={...})`.
- `per_story` is a `dict[str, StoryCost]` in `BudgetState`, serialized to `dict[str, dict]` in `run.yaml`.
- `_serialize_budget` converts `Decimal` → `str` for YAML safety.
- Cost calculation: `(tokens_input / 1_000_000) * pricing.input_rate + (tokens_output / 1_000_000) * pricing.output_rate`.
- `ModelPricing` defaults: `input_rate=Decimal("15.00")`, `output_rate=Decimal("75.00")` per 1M tokens.

**From Story 5.5 (Run Status Command):**
- Status command pattern: `_status_async` reads `RunStatus` via `get_run_status`, categorizes stories, formats output to stderr.
- Budget dict is accessed via `.get()` with defaults — no typed access.
- Current test `test_status_budget_cost_display` puts `invocation_count=5`, `total_tokens=50000`, `estimated_cost="1.50"` in budget dict and asserts they appear in stderr output. Will need updating for new format.

### Existing Test Coverage (Affected)

Tests in `tests/test_cli/test_status.py` that assert on cost output:
- `test_status_budget_cost_display` (line 217) — asserts `"5"` in invocations, `"50000"` in tokens, `"1.50"` in cost. Must update for `"$1.50"` and `"50,000"`.
- `test_status_budget_zero_values_display_na` (line 244) — asserts `"N/A"` for zero values. Must update for `"$0.00"` and `"0"`.

Tests in `tests/test_output/test_summary.py` that assert on cost output:
- `test_write_success_summary_zero_budget_shows_na` (line 196) — asserts `"N/A"` appears in summary for zero budget. Must update for `"$0.00"`.
- `test_write_success_summary_required_sections` (line 152) — asserts `"## Cost Summary"` heading exists. Should still pass.
- Halt report tests check `"Cost at Halt"` text — field label may change to formatted values.

### Project Structure Notes

- All source code under `arcwright-ai/src/arcwright_ai/`
- CLI status: `cli/status.py`
- Summary generation: `output/summary.py`
- Run manager: `output/run_manager.py`
- Core types: `core/types.py` (BudgetState, StoryCost)
- CLI tests: `tests/test_cli/test_status.py`
- Summary tests: `tests/test_output/test_summary.py`
- All output to stderr per D8 convention

### References

- [Source: _spec/planning-artifacts/epics.md — Story 7.3 definition, lines 988-1004]
- [Source: _spec/planning-artifacts/architecture.md — FR24: Cost ceiling enforcement, line 870]
- [Source: _spec/planning-artifacts/architecture.md — FR31: Run status via run_manager, line 877]
- [Source: _spec/planning-artifacts/architecture.md — FR33: Run summary via summary.py, line 879]
- [Source: _spec/planning-artifacts/architecture.md — Subsystem 9: Run State Manager, line 57]
- [Source: _spec/planning-artifacts/architecture.md — Subsystem 10: CLI Surface, line 58]
- [Source: _spec/planning-artifacts/architecture.md — Boundary 1: CLI ↔ Engine, line 897]
- [Source: _spec/planning-artifacts/architecture.md — output/ package description, line 253]
- [Source: arcwright-ai/src/arcwright_ai/cli/status.py — _format_cost_value, line 610]
- [Source: arcwright-ai/src/arcwright_ai/cli/status.py — _status_async, line 690]
- [Source: arcwright-ai/src/arcwright_ai/output/summary.py — _format_budget_field, line 66]
- [Source: arcwright-ai/src/arcwright_ai/output/summary.py — write_success_summary, line 168]
- [Source: arcwright-ai/src/arcwright_ai/output/summary.py — write_halt_report, line 290]
- [Source: arcwright-ai/src/arcwright_ai/output/summary.py — write_timeout_summary, line 508]
- [Source: arcwright-ai/src/arcwright_ai/output/run_manager.py — _serialize_budget, line 204]
- [Source: arcwright-ai/src/arcwright_ai/output/run_manager.py — RunStatus model, line 108]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — BudgetState, line 123]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — StoryCost, line 103]
- [Source: _spec/implementation-artifacts/7-1-budgetstate-model-and-cost-accumulation.md — Previous story]
- [Source: _spec/implementation-artifacts/7-2-budget-check-node-dual-ceiling-enforcement.md — Previous story]
- [Source: _spec/implementation-artifacts/5-5-run-status-command-live-and-historical-run-visibility.md — Status command story]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Added 4 public formatting functions to `output/summary.py`: `format_cost`, `format_tokens`, `format_budget_remaining`, `format_retry_overhead`. All added to `__all__`.
- `format_cost` uses `Decimal.quantize(ROUND_HALF_UP)` for precision; displays `$X.XX` with comma thousands separator for large values.
- `format_tokens` returns comma-separated integer string; handles None, str, and int inputs.
- `format_budget_remaining` returns `"unlimited"` when ceiling==0, else `"X% ($Y.YY of $Z.ZZ)"` with remaining amount and percentage.
- `format_retry_overhead` computes first-pass cost (cost/invocations per story) vs total; returns `"$0.00 (no retries)"` or `"$X.XX (Y% overhead)"`.
- Enhanced `_status_async` in `cli/status.py`: imports new formatters, displays formatted cost/tokens/remaining, adds per-story breakdown table when `per_story` non-empty.
- Enhanced `write_success_summary` in `output/summary.py`: new Cost Summary section with total cost, tokens (with input/output split), invocations, budget utilization, per-story markdown table, and retry overhead.
- Enhanced `write_halt_report` Run Context section: formatted `format_tokens` and `format_cost` values, added Budget Remaining line.
- Enhanced `write_timeout_summary` Cost Summary section: same enhanced format as `write_success_summary`.
- Updated 3 existing tests that asserted on old `"N/A"` / unformatted values.
- Created `tests/test_output/test_cost_formatting.py` with 25 new tests for all 4 formatting functions.
- Added 5 new tests to existing test files (2 in `test_status.py`, 3 in `test_summary.py`).
- All 792 tests pass (762 original + 30 new). `ruff check .` — 0 violations. `mypy --strict src/` — 0 errors.
- Addressed code review follow-ups: invocation-ceiling unlimited semantics implemented, halted summary cost section expanded (table + retry overhead), and `format_cost` now formats directly from `Decimal` (no float conversion).
- Added 4 additional tests for review fixes (status unlimited display, formatter invocation-unlimited behavior, and halted summary coverage). Full suite now: 796 tests pass.

### File List

- arcwright-ai/src/arcwright_ai/output/summary.py
- arcwright-ai/src/arcwright_ai/cli/status.py
- arcwright-ai/tests/test_output/test_cost_formatting.py
- arcwright-ai/tests/test_cli/test_status.py
- arcwright-ai/tests/test_output/test_summary.py
- _spec/implementation-artifacts/sprint-status.yaml

## Change Log

- 2026-03-11: Story 7.3 implemented — added `format_cost`, `format_tokens`, `format_budget_remaining`, `format_retry_overhead` to `output/summary.py`; enhanced CLI status cost display with `$`-formatting, comma-formatted tokens, budget remaining, and per-story table; enhanced `write_success_summary`, `write_halt_report`, `write_timeout_summary` with formatted cost sections; updated 3 existing tests; added 30 new tests. Ruff: 0 violations. Mypy: 0 errors. Tests: 792/792 pass.
- 2026-03-11: Senior Developer code review completed (AI). Findings: 2 HIGH, 2 MEDIUM. Added Review Follow-ups (AI), set status to `in-progress`, and synced sprint tracking status.
- 2026-03-11: Implemented all AI review follow-ups; updated `format_budget_remaining` for invocation-unlimited semantics, expanded halted-run Cost Summary, removed float conversion from `format_cost`, added follow-up tests, and re-validated gates. Ruff: 0 violations. Mypy strict: 0 errors. Tests: 796/796 pass.

## Senior Developer Review (AI)

Reviewer: Ed (AI)
Date: 2026-03-11
Outcome: Approved (Post-Fix)

### Summary

- Story reviewed against Acceptance Criteria, checked tasks, and actual git changes.
- Git/story documentation discrepancy found (1 file changed but not listed in File List).
- Quality gates re-run during review: `ruff check .` passed, `.venv/bin/python -m mypy --strict src/arcwright_ai/output/summary.py src/arcwright_ai/cli/status.py` passed, full tests passed (`792 passed`).

### Findings

#### HIGH

1. **AC #1 unlimited budget behavior is incomplete**
  - AC requires budget remaining to show `"unlimited"` when `max_cost == 0` and when `max_invocations == 0`.
  - Current implementation computes remaining from `estimated_cost/max_cost` only and ignores invocation ceiling semantics.
  - Evidence: `status.py` uses `format_budget_remaining(..., max_cost)` only; summary/halt/timeout do the same.

2. **AC #2 halted-run cost section requirements not fully met**
  - AC #2 requires cost summary details (including per-story costs table and retry overhead) for summary generation paths including halted runs.
  - `write_halt_report` includes only top-level run context cost lines and does not include per-story table or retry overhead.
  - Evidence: `write_halt_report` Run Context section lacks per-story cost table and retry-overhead line.

#### MEDIUM

3. **Boundary 3 Decimal-only formatting contract is violated in `format_cost` implementation detail**
  - Boundary states formatting should use Decimal quantization and never float rounding.
  - `format_cost` quantizes with Decimal but then converts to float for output formatting (`f"${float(quantized):,.2f}"`), which reintroduces float representation risk.

4. **Dev Agent File List is incomplete vs actual git changes**
  - `_spec/implementation-artifacts/sprint-status.yaml` is modified in git but missing from story File List.
  - This is a transparency/documentation issue for review traceability.
