# Story 4.3: Run Summary & Halt Report Generation

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator who has just completed (or been interrupted during) a run,
I want a comprehensive summary of what happened and actionable next steps,
so that I can quickly understand results and know exactly how to continue.

## Acceptance Criteria (BDD)

1. **Given** `output/summary.py` module **When** the summary generator is implemented **Then** it exposes the following async public functions:
   - `async write_success_summary(project_root: Path, run_id: str) -> Path` that reads `run.yaml` via `get_run_status()`, computes metrics, and writes `summary.md` to `.arcwright-ai/runs/<run-id>/summary.md`.
   - `async write_halt_report(project_root: Path, run_id: str, *, halted_story: str, halt_reason: str, validation_history: list[dict[str, Any]], last_agent_output: str, suggested_fix: str) -> Path` that writes a structured halt report as `summary.md` in the same run directory.
   - `async write_timeout_summary(project_root: Path, run_id: str) -> Path` that writes a timeout-specific summary as `summary.md`.
   All three functions return the `Path` to the written `summary.md` file. All functions import types from `core/` and `output/run_manager` only — zero engine dependency enforced. The module's dependency surface is: `core/constants`, `core/exceptions`, `core/io`, `output/run_manager`.

2. **Given** a completed run where all stories passed validation **When** `write_success_summary()` is called **Then** the generated `summary.md` contains:
   - `# Run Summary: <run-id>` heading
   - `## Overview` section with: run ID, status (`completed`), start time (from `run.yaml`), total stories count, completed stories count, total duration placeholder (`"N/A"` — computed by caller when wired in Story 4.4)
   - `## Stories Completed` section listing each story as `- [x] <story-slug> (status: <status>)` with started_at and completed_at timestamps if available
   - `## Cost Summary` section with budget data from `run.yaml`: invocation count, total tokens, estimated cost.  Display `"N/A"` for any budget field that is `0` or `"0"` (indicating tracking was not active)
   - `## Provenance References` section with a bullet list pointing to each story's artifacts directory: `- .arcwright-ai/runs/<run-id>/stories/<story-slug>/`
   - `## Next Steps` section with: "All stories completed successfully. Review provenance artifacts for decision audit trail."
   The file uses only markdown headings, lists, and prose — no custom formats or binary data per NFR17.

3. **Given** a halted run where a story failed validation after maximum retries **When** `write_halt_report()` is called **Then** the generated `summary.md` contains the 4 required diagnostic fields per NFR18:
   - **(1) Which story failed**: `## Halted Story` section with the story slug, epic ID (parsed from slug), and halt reason
   - **(2) What validation criteria failed**: `## Validation Failures` section extracted from the `validation_history` parameter — each attempt listed with outcome and failure details
   - **(3) Retry history with feedback**: `## Retry History` section as a markdown table `| Attempt | Outcome | Feedback |` showing all validation attempts from `validation_history`, with feedback truncated to 200 chars per row if longer
   - **(4) Suggested manual fix**: `## Suggested Fix` section containing the `suggested_fix` parameter text and the exact resume command: `arcwright-ai dispatch --epic EPIC-<N> --resume`
   Additionally, the halt report includes `## Last Agent Output` with the `last_agent_output` parameter, truncated to the last 2000 characters and wrapped in a fenced code block. If the full output exceeds 2000 chars, a truncation notice is prepended. Content exceeding 2000 characters uses a collapsible `<details>` block.

4. **Given** a run that exceeded its time budget **When** `write_timeout_summary()` is called **Then** the generated `summary.md` includes:
   - `# Run Summary: <run-id>` heading with status `timed_out`
   - `## Overview` section showing the timeout status and stories completed before timeout
   - `## Stories Completed` section listing stories that finished (same format as success summary)
   - `## Stories Remaining` section listing stories that were still queued/in-progress when timeout occurred
   - `## Cost Summary` section with budget data at time of timeout
   - `## Next Steps` section with the resume command: `arcwright-ai dispatch --epic EPIC-<N> --resume`

5. **Given** any of the three write functions **When** `summary.md` already exists at the target path **Then** the function overwrites the existing file — summaries are idempotent per NFR19. The last write wins. No append behavior.

6. **Given** any of the three write functions **When** the run ID cannot be found (no `run.yaml`) **Then** the function raises `RunError` with message `"Run not found: {run_id}"` and details `{"path": str(expected_path)}`. This is propagated from `get_run_status()` — summary functions do NOT catch and swallow `RunError`.

7. **Given** the epic ID needs to be derived from a story slug **When** constructing the resume command **Then** the `_extract_epic_from_slug(slug: str) -> str` private helper parses the first number from the slug (e.g., `"4-3-run-summary"` → `"4"`). If the slug doesn't match the expected `N-N-...` pattern, the resume command uses `"<EPIC>"` as a placeholder.

8. **Given** the `output/__init__.py` module **When** this story is complete **Then** `__all__` is updated to include (alphabetically sorted with existing exports): `["RunStatus", "RunStatusValue", "RunSummary", "StoryStatusEntry", "append_entry", "create_run", "generate_run_id", "get_run_status", "list_runs", "render_validation_row", "update_run_status", "update_story_status", "write_entries", "write_halt_report", "write_success_summary", "write_timeout_summary"]`. Corresponding imports are added from `output.summary`.

9. **Given** new unit tests in `tests/test_output/test_summary.py` **When** the test suite runs **Then** tests cover:
   (a) `write_success_summary()` generates correct markdown with all required sections (Overview, Stories Completed, Cost Summary, Provenance References, Next Steps);
   (b) `write_success_summary()` stories listed with correct status and timestamps;
   (c) `write_success_summary()` budget fields of `0`/`"0"` displayed as `"N/A"`;
   (d) `write_halt_report()` includes all 4 NFR18 diagnostic fields (halted story, validation failures, retry history, suggested fix);
   (e) `write_halt_report()` retry history table formatted correctly with truncated feedback;
   (f) `write_halt_report()` last agent output truncated to 2000 chars with notice;
   (g) `write_halt_report()` short agent output rendered without truncation;
   (h) `write_halt_report()` resume command contains correct epic number parsed from slug;
   (i) `write_timeout_summary()` includes stories completed and stories remaining sections;
   (j) `write_timeout_summary()` resume command present in Next Steps;
   (k) All three functions overwrite existing `summary.md` (idempotency);
   (l) All three functions raise `RunError` when run ID not found;
   (m) `_extract_epic_from_slug()` correctly parses epic number from various slug formats;
   (n) `_extract_epic_from_slug()` returns `"<EPIC>"` for unparseable slugs;
   (o) Write functions create parent directories if they don't exist (via `write_text_async`);
   (p) Success summary with multiple stories (3+) renders all correctly;
   (q) Halt report with empty `validation_history` still has the table header.

10. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

11. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

12. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

13. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 411 existing tests continue to pass unmodified.

## Tasks / Subtasks

- [x] Task 1: Implement private helpers in `output/summary.py` (AC: #1, #7)
  - [x] 1.1: Replace existing stub with proper module. Add module docstring, `from __future__ import annotations`, and imports:
    ```python
    from __future__ import annotations

    import re
    from typing import TYPE_CHECKING, Any

    from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, SUMMARY_FILENAME
    from arcwright_ai.core.io import write_text_async
    from arcwright_ai.output.run_manager import RunStatusValue, get_run_status

    if TYPE_CHECKING:
        from pathlib import Path
    ```
  - [x] 1.2: Implement `_extract_epic_from_slug(slug: str) -> str` — uses `re.match(r"^(\d+)-", slug)` to parse epic number; returns `"<EPIC>"` on parse failure
  - [x] 1.3: Implement `_summary_path(project_root: Path, run_id: str) -> Path` — returns `project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id / SUMMARY_FILENAME`
  - [x] 1.4: Implement `_format_budget_field(value: Any) -> str` — returns `"N/A"` if value is `0`, `"0"`, `None`, or empty string; otherwise `str(value)`
  - [x] 1.5: Implement `_truncate_output(text: str, max_chars: int = 2000) -> tuple[str, bool]` — returns `(truncated_text, was_truncated)`. If text exceeds `max_chars`, returns last `max_chars` characters with `was_truncated=True`

- [x] Task 2: Implement `write_success_summary()` async function (AC: #1, #2, #5, #6)
  - [x] 2.1: Function signature: `async def write_success_summary(project_root: Path, run_id: str) -> Path`
  - [x] 2.2: Call `await get_run_status(project_root, run_id)` to read run.yaml — let `RunError` propagate on failure
  - [x] 2.3: Build markdown sections in order:
    - `# Run Summary: {run_id}` heading
    - `## Overview` — run_id, status, start_time, total stories, completed stories, duration placeholder "N/A"
    - `## Stories Completed` — iterate `run_status.stories`, render each as `- [x] {slug} (status: {status})` with timestamps if available. Use `- [ ]` for non-completed stories
    - `## Cost Summary` — budget fields from `run_status.budget` using `_format_budget_field()` for each: invocation_count, total_tokens, estimated_cost
    - `## Provenance References` — bullet list of story artifact directories
    - `## Next Steps` — success message
  - [x] 2.4: Join all lines, write via `await write_text_async(path, content)` — `write_text_async` creates parent dirs
  - [x] 2.5: Return the `Path` to `summary.md`

- [x] Task 3: Implement `write_halt_report()` async function (AC: #1, #3, #5, #6, #7)
  - [x] 3.1: Function signature: `async def write_halt_report(project_root: Path, run_id: str, *, halted_story: str, halt_reason: str, validation_history: list[dict[str, Any]], last_agent_output: str, suggested_fix: str) -> Path`
  - [x] 3.2: Call `await get_run_status(project_root, run_id)` to read run.yaml
  - [x] 3.3: Build `## Halted Story` section — halted_story slug, epic ID via `_extract_epic_from_slug()`, halt reason, run_id
  - [x] 3.4: Build `## Validation Failures` section — iterate `validation_history`, render each attempt's outcome and failing criteria. Each dict expected to have keys: `attempt` (int), `outcome` (str), `failures` (str)
  - [x] 3.5: Build `## Retry History` table — `| Attempt | Outcome | Feedback |` with separator row. Truncate feedback to 200 chars with `...` suffix if longer. If `validation_history` is empty, show header with `| — | — | — |` row
  - [x] 3.6: Build `## Last Agent Output` section — use `_truncate_output()` and wrap in fenced code block. If truncated, prepend `*... truncated ({total_length} chars total) ...*`
  - [x] 3.7: Build `## Suggested Fix` section — `suggested_fix` text + exact resume command: `arcwright-ai dispatch --epic EPIC-{epic_num} --resume`
  - [x] 3.8: Build `## Run Context` section — stories completed and remaining from run_status, budget at halt time
  - [x] 3.9: Write via `write_text_async()`, return path

- [x] Task 4: Implement `write_timeout_summary()` async function (AC: #1, #4, #5, #6)
  - [x] 4.1: Function signature: `async def write_timeout_summary(project_root: Path, run_id: str) -> Path`
  - [x] 4.2: Call `await get_run_status(project_root, run_id)` to read run.yaml
  - [x] 4.3: Build `# Run Summary: {run_id}` heading with `timed_out` status
  - [x] 4.4: Build `## Overview` section — same structure as success but with timed_out status
  - [x] 4.5: Build `## Stories Completed` — only stories with success/done status
  - [x] 4.6: Build `## Stories Remaining` — stories still queued/running/retry at timeout time
  - [x] 4.7: Build `## Cost Summary` — budget data at timeout time
  - [x] 4.8: Build `## Next Steps` — resume command using first remaining story's epic
  - [x] 4.9: Write via `write_text_async()`, return path

- [x] Task 5: Update `output/__init__.py` exports (AC: #8)
  - [x] 5.1: Add imports from `output.summary`: `write_halt_report`, `write_success_summary`, `write_timeout_summary`
  - [x] 5.2: Update `__all__` to alphabetically sorted list including all new public symbols plus existing ones: `["RunStatus", "RunStatusValue", "RunSummary", "StoryStatusEntry", "append_entry", "create_run", "generate_run_id", "get_run_status", "list_runs", "render_validation_row", "update_run_status", "update_story_status", "write_entries", "write_halt_report", "write_success_summary", "write_timeout_summary"]`

- [x] Task 6: Update `output/summary.py` module `__all__` (AC: #1)
  - [x] 6.1: Set `__all__: list[str] = ["write_halt_report", "write_success_summary", "write_timeout_summary"]`

- [x] Task 7: Create unit tests in `tests/test_output/test_summary.py` (AC: #9)
  - [x] 7.1: Create test file with imports:
    ```python
    from __future__ import annotations

    from pathlib import Path
    from typing import Any
    from unittest.mock import AsyncMock, patch

    import pytest

    from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, SUMMARY_FILENAME
    from arcwright_ai.core.exceptions import RunError
    from arcwright_ai.output.run_manager import RunStatus, RunStatusValue, StoryStatusEntry
    from arcwright_ai.output.summary import (
        _extract_epic_from_slug,
        write_halt_report,
        write_success_summary,
        write_timeout_summary,
    )
    ```
  - [x] 7.2: Create `_create_test_run_status()` helper fixture that returns a `RunStatus` with configurable story entries
  - [x] 7.3: Create helper to set up a run directory with `run.yaml` for integration-style tests — use `tmp_path` and `create_run()` from `run_manager`
  - [x] 7.4: Test `write_success_summary()` generates all required sections (AC: #9a)
  - [x] 7.5: Test `write_success_summary()` stories listed with correct status/timestamps (AC: #9b)
  - [x] 7.6: Test `write_success_summary()` zero budget fields display as "N/A" (AC: #9c)
  - [x] 7.7: Test `write_halt_report()` all 4 NFR18 diagnostic fields present (AC: #9d)
  - [x] 7.8: Test `write_halt_report()` retry history table formatting with truncated feedback (AC: #9e)
  - [x] 7.9: Test `write_halt_report()` long agent output truncation (AC: #9f)
  - [x] 7.10: Test `write_halt_report()` short agent output no truncation (AC: #9g)
  - [x] 7.11: Test `write_halt_report()` resume command with correct epic number (AC: #9h)
  - [x] 7.12: Test `write_timeout_summary()` stories completed and remaining sections (AC: #9i)
  - [x] 7.13: Test `write_timeout_summary()` resume command present (AC: #9j)
  - [x] 7.14: Test all three functions overwrite existing summary.md (AC: #9k)
  - [x] 7.15: Test all three functions raise RunError on missing run (AC: #9l)
  - [x] 7.16: Test `_extract_epic_from_slug()` valid slugs (AC: #9m)
  - [x] 7.17: Test `_extract_epic_from_slug()` unparseable slugs return `"<EPIC>"` (AC: #9n)
  - [x] 7.18: Test success summary with multiple stories (3+) (AC: #9p)
  - [x] 7.19: Test halt report with empty validation_history (AC: #9q)
  - [x] 7.20: All tests use `tmp_path` fixture, `@pytest.mark.asyncio` decorators

- [x] Task 8: Run quality gates (AC: #10, #11, #12, #13)
  - [x] 8.1: `ruff check .` — zero violations against FULL repository
  - [x] 8.2: `ruff format --check .` — zero formatting issues
  - [x] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 8.4: `pytest` — all tests pass (411 existing + 27 new = 438 total)
  - [x] 8.5: Verify Google-style docstrings on all public functions

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Fixed resume placeholder formatting for unparseable slugs: resume command now uses `<EPIC>` (not `EPIC-<EPIC>`). [arcwright-ai/src/arcwright_ai/output/summary.py](arcwright-ai/src/arcwright_ai/output/summary.py)
- [x] [AI-Review][MEDIUM] Escaped markdown table control characters in retry history feedback/outcome fields to preserve table rendering. [arcwright-ai/src/arcwright_ai/output/summary.py](arcwright-ai/src/arcwright_ai/output/summary.py)
- [x] [AI-Review][MEDIUM] Eliminated async-generator cleanup warning by explicitly closing the invocation stream in all paths. [arcwright-ai/src/arcwright_ai/agent/invoker.py](arcwright-ai/src/arcwright_ai/agent/invoker.py)
- [x] [AI-Review][MEDIUM] Updated Dev Agent Record file list to include all files changed during review follow-up fixes. [_spec/implementation-artifacts/4-3-run-summary-and-halt-report-generation.md](_spec/implementation-artifacts/4-3-run-summary-and-halt-report-generation.md)

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `output → core` only. The `output/summary.py` module must NEVER import from `engine/`, `agent/`, `validation/`, `context/`, `scm/`, or `cli/`. It MAY import from `output/run_manager.py` (same package, read-only consumer of `get_run_status()`). It uses `write_text_async` from `core/io`, constants from `core/constants`, and `RunError` from `core/exceptions`. That's the entire dependency surface.

**D5 — Run Directory Schema**: Summary files are written to `.arcwright-ai/runs/<run-id>/summary.md`. The constant `SUMMARY_FILENAME = "summary.md"` already exists in `core/constants.py`. The `HALT_REPORT_FILENAME = "halt-report.md"` constant also exists but this story writes halt reports as `summary.md` (every run gets exactly one summary file) — the separate `halt-report.md` is the per-story halt report produced by `engine/nodes.py::_generate_halt_report()`. Do NOT confuse the two: this module generates the **run-level** summary, not the **story-level** halt report.

**D5 — Write Policy**: Summary files are transition checkpoints written at run completion. The summary module is a standalone writer — no other module should write `summary.md`. Story 4.4 will call the summary functions from the `run_complete` conditional edge in the LangGraph graph.

**Existing `_generate_halt_report()` in `engine/nodes.py`**: This function produces per-story halt reports for escalated stories (FR11). It uses `StoryState`, `PipelineResult`, `PipelineOutcome` — engine types. Story 4.3's halt report is fundamentally different: it's the **run-level** halt summary. The two functions have different inputs, different output locations, and different purposes. Do NOT merge or replace the existing function. Do NOT import engine types.

**NFR16 — Every Run Gets a Summary**: Every run (success, halt, timeout) must produce a `summary.md`. This is enforced architecturally by providing three separate write functions that Story 4.4 will call from the appropriate graph edges. The summary module itself does not enforce "always write" — that's the responsibility of the caller (engine integration in Story 4.4).

**NFR17 — Human-Readable Markdown**: All output uses standard markdown: headings, lists, tables, fenced code blocks. No custom formats, no binary data, no machine-only sections. The goal is that an operator can read the summary in any markdown viewer (GitHub, VS Code, terminal `cat`) and understand the run outcome immediately.

**NFR18 — Halt Report Diagnostic Fields**: The 4 required fields are:
1. **Which story failed** — story slug + epic ID
2. **What validation criteria failed** — from validation_history parameter
3. **Retry history with feedback** — markdown table of all attempts
4. **Suggested manual fix** — from suggested_fix parameter + resume command

These fields are provided as parameters to `write_halt_report()` by the caller (Story 4.4). The summary module renders them — it does not compute them from run state. The computation happens in the engine node that detects the halt condition.

**FR32 — Run Summary Contents**: "Story completion status, validation results, cost, and provenance references." The success summary covers all of these. The provenance references section points to artifact directories rather than listing individual decisions — keeping the summary concise.

**FR33 — Halt Reports**: "Structured halt reports as markdown files when execution stops due to failure, cost, or timeout." This story implements all three: halt (validation failure or agent error), cost budget exhaustion, and timeout. The `halt_reason` parameter distinguishes these cases.

### API Design Rationale — Three Functions vs. One

Three separate functions (`write_success_summary`, `write_halt_report`, `write_timeout_summary`) instead of one `write_summary(outcome: str, ...)` because:
1. **Different parameter signatures** — halt reports need `validation_history`, `last_agent_output`, `suggested_fix`; success summaries don't
2. **Type safety** — each function's signature documents exactly what data is needed for that outcome
3. **No conditional parameter optionality** — avoids `Optional` parameters that are "required when outcome is halt but ignored otherwise"
4. **Consistent with Story 4.4 wiring** — the three graph edge conditions (success, halt, timeout) each call the corresponding function directly

### Existing Code to Reuse — DO NOT REINVENT

- **`get_run_status()`** from `output/run_manager.py` — returns `RunStatus` model with `run_id`, `status`, `start_time`, `config_snapshot`, `budget`, `stories` (dict[str, StoryStatusEntry]), `last_completed_story`. Use this to read run state; do NOT read `run.yaml` directly.
- **`RunStatusValue`** from `output/run_manager.py` — StrEnum with `QUEUED`, `RUNNING`, `COMPLETED`, `HALTED`, `TIMED_OUT`.
- **`StoryStatusEntry`** from `output/run_manager.py` — has `status` (str), `retry_count` (int), `started_at` (str | None), `completed_at` (str | None). Uses `extra="ignore"` for forward compat.
- **`RunStatus`** from `output/run_manager.py` — has `budget` typed as `dict[str, Any]` (not `BudgetState`). Budget keys: `invocation_count`, `total_tokens`, `estimated_cost`, `max_invocations`, `max_cost`. Cost fields are serialized as strings.
- **`write_text_async()`** from `core/io.py` — async text file write. Parent directories must exist (caller responsibility — but note `save_yaml` creates parent dirs, while `write_text_async` does not; use `Path.parent.mkdir(parents=True, exist_ok=True)` via `asyncio.to_thread()` before writing).
- **Constants**: `DIR_ARCWRIGHT = ".arcwright-ai"`, `DIR_RUNS = "runs"`, `DIR_STORIES = "stories"`, `SUMMARY_FILENAME = "summary.md"`.
- **`RunError`** from `core/exceptions.py` — carries `message` and optional `details` dict.

### `write_text_async` Does NOT Create Parent Dirs

Unlike `save_yaml()` which calls `path.parent.mkdir(parents=True, exist_ok=True)` internally, `write_text_async()` just calls `path.write_text()`. The summary functions must ensure the run directory exists before writing. Since `get_run_status()` succeeds (meaning `run.yaml` exists), the directory already exists. But be defensive — add a `mkdir` call wrapped in `asyncio.to_thread()` before writing.

### Relationship to Other Stories in Epic 4

- **Story 4.1 (done)**: Created `output/provenance.py` — standalone provenance recording
- **Story 4.2 (done)**: Created `output/run_manager.py` — run directory lifecycle and `run.yaml` management. Provides `get_run_status()` consumed by this story.
- **Story 4.3 (this)**: Creates `output/summary.py` — run summary and halt report generation. Standalone module, no engine dependency.
- **Story 4.4**: Wires Stories 4.1, 4.2, 4.3 into the LangGraph engine nodes. Will call `write_success_summary()`, `write_halt_report()`, `write_timeout_summary()` from graph edge callbacks. That is where "every run produces a summary" (NFR16) is enforced.

### Testing Patterns

- Use `tmp_path` fixture for all file I/O tests — never write to real project directories.
- Use `@pytest.mark.asyncio` for all async test functions.
- For testing against real `run.yaml`, use `create_run()` from `run_manager` to set up test data in `tmp_path`, then call summary functions against the same `tmp_path` as `project_root`.
- For testing `write_halt_report()`, provide realistic `validation_history` dicts with keys `attempt`, `outcome`, `failures`.
- Use `Path.read_text()` to read back the written `summary.md` and assert against expected content patterns.
- Test idempotency by calling the write function twice and verifying the second call overwrites (file content matches second invocation's expected output).
- Test `RunError` propagation by using a `tmp_path` with no run directory — `get_run_status()` will raise `RunError`.

### Known Pitfalls from Epics 1-3

1. **`__all__` ordering must be alphabetical** — ruff enforces this. Exports in `output/__init__.py` and `output/summary.py` must be sorted.
2. **No aspirational exports** — only export symbols that actually exist and are implemented. Do NOT pre-export planned Story 4.4 symbols.
3. **`from __future__ import annotations`** at the top of every module — required for `X | None` union syntax.
4. **`frozen=True`** on `ArcwrightModel` — model instances are immutable. When reading `RunStatus`, access fields directly; do not try to modify.
5. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just `ruff check src/arcwright_ai/output/`), and failures in ANY file must be reported honestly. Do not self-report "zero violations" if violations exist anywhere.
6. **File list in Dev Agent Record must match actual git changes** — verify against `git status` before claiming completion. This was a 7/11 systemic pattern across Epics 2-3.
7. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.
8. **Use `asyncio.to_thread()` for synchronous operations in async functions** — `Path.mkdir()`, `Path.exists()` are synchronous; wrap in `asyncio.to_thread()` if called from async functions.
9. **`RunStatus.budget` is `dict[str, Any]`** not a typed model — cost fields (`estimated_cost`, `max_cost`) are serialized as strings in YAML. When displaying, treat them as strings: `_format_budget_field(budget.get("estimated_cost", "0"))`.
10. **Off-by-one in retry/attempt counts** — Story 3.4 had a retry count off-by-one bug. When rendering retry history tables, `attempt` numbers should come from the `validation_history` dicts, not computed from index.
11. **`ConfigError` → `RunError` domain boundary** — if `get_run_status()` raises `RunError`, let it propagate. Do NOT catch and convert to a different exception type.
12. **Structured log event payloads must include ALL fields documented in ACs** — not directly applicable to this story (no structured log events), but relevant context for Story 4.4.

### Project Structure Notes

The `output/` package layout after this story:

```
src/arcwright_ai/output/
├── __init__.py          # Updated: exports summary symbols + existing provenance/run_manager exports
├── provenance.py        # UNCHANGED: Story 4.1 implementation
├── run_manager.py       # UNCHANGED: Story 4.2 implementation
└── summary.py           # UPDATED: Run summary and halt report generation (was empty stub)
```

Test structure:

```
tests/test_output/
├── __init__.py          # EXISTS: Empty
├── test_provenance.py   # EXISTS: 16 tests from Story 4.1
├── test_run_manager.py  # EXISTS: 23 tests from Story 4.2
└── test_summary.py      # NEW: ~20 summary unit tests
```

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema]
- [Source: _spec/planning-artifacts/architecture.md — Decision 6: Error Handling Taxonomy]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/architecture.md — Async Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Python Code Style Patterns]
- [Source: _spec/planning-artifacts/epics.md — Epic 4, Story 4.3]
- [Source: _spec/planning-artifacts/prd.md — FR32 (run summary), FR33 (halt reports)]
- [Source: _spec/planning-artifacts/prd.md — NFR16 (every run produces summary), NFR17 (human-readable markdown), NFR18 (halt report 4 diagnostic fields)]
- [Source: _spec/implementation-artifacts/epic-3-retro-2026-03-04.md — Action Items and Patterns]
- [Source: _spec/implementation-artifacts/4-1-provenance-recorder-decision-logging-during-execution.md — Provenance module patterns]
- [Source: _spec/implementation-artifacts/4-2-run-manager-run-directory-lifecycle-and-state-tracking.md — RunStatus API, testing patterns, pitfalls]
- [Source: src/arcwright_ai/core/constants.py — SUMMARY_FILENAME, HALT_REPORT_FILENAME, DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES]
- [Source: src/arcwright_ai/core/io.py — write_text_async (does NOT create parent dirs)]
- [Source: src/arcwright_ai/core/exceptions.py — RunError]
- [Source: src/arcwright_ai/output/__init__.py — current exports]
- [Source: src/arcwright_ai/output/summary.py — current empty stub]
- [Source: src/arcwright_ai/output/run_manager.py — get_run_status, RunStatus, RunStatusValue, StoryStatusEntry]
- [Source: src/arcwright_ai/engine/nodes.py — _generate_halt_report() (story-level, NOT to be confused with run-level)]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

No blocking issues encountered. Minor ruff auto-fix applied for 4 f-strings without placeholders (F541).

### Completion Notes List

- Implemented `output/summary.py` with 5 private helpers and 3 async public functions (`write_success_summary`, `write_halt_report`, `write_timeout_summary`)
- All functions read `run.yaml` via `get_run_status()` — zero direct YAML reads, zero engine imports
- Halt report renders all 4 NFR18 diagnostic fields: halted story, validation failures, retry history table (feedback truncated to 200 chars), suggested fix + resume command
- `write_halt_report` wraps last agent output >2000 chars in a `<details>` collapsible block with truncation notice
- `write_timeout_summary` derives resume epic from first remaining story slug via `_extract_epic_from_slug`
- All three functions ensure parent directory exists before writing via `asyncio.to_thread(Path.mkdir, ...)`
- Updated `output/__init__.py` with 3 new imports and alphabetically sorted `__all__` list
- Created 27 unit tests covering all 17 AC sub-bullets (9a–9q) plus extra path/idempotency tests
- Quality gates: ruff 0 violations, ruff format 0 issues, mypy --strict 0 errors, 438/438 tests pass

### File List

- `src/arcwright_ai/output/summary.py`
- `src/arcwright_ai/output/__init__.py`
- `tests/test_output/test_summary.py`
- `src/arcwright_ai/agent/invoker.py`
- `_spec/implementation-artifacts/4-3-run-summary-and-halt-report-generation.md`
- `_spec/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-03-04: Story 4.3 created with comprehensive context — ready for dev.
- 2026-03-04: Story 4.3 implemented — `output/summary.py` complete with 3 public async functions and 5 private helpers; 27 new unit tests; all quality gates pass.
- 2026-03-04: Senior Developer Review (AI) completed — 1 HIGH and 3 MEDIUM issues identified; status moved to `in-progress`; review follow-ups added.
- 2026-03-04: Review follow-ups fixed — placeholder formatting corrected, retry table escaping added, async stream cleanup warning resolved, and artifacts updated; status moved back to `review`.

## Senior Developer Review (AI)

### Reviewer

Ed (AI Senior Developer Review)

### Date

2026-03-04

### Outcome

Changes Requested

### Summary

- Verified quality gates: `ruff check .`, `mypy --strict src/`, and full `pytest` all pass.
- Identified one AC-level defect in resume placeholder formatting and additional medium-severity quality/documentation gaps.
- Story remains not-ready for `done` until HIGH and MEDIUM findings are resolved.

### Findings

1. **HIGH** — Resume placeholder formatting violates AC #7 fallback behavior on unparseable slugs (`EPIC-<EPIC>` generated).
  - Evidence: [`arcwright-ai/src/arcwright_ai/output/summary.py:309`](arcwright-ai/src/arcwright_ai/output/summary.py#L309), [`arcwright-ai/src/arcwright_ai/output/summary.py:437`](arcwright-ai/src/arcwright_ai/output/summary.py#L437)

2. **MEDIUM** — Retry-history markdown row writer does not sanitize feedback content, so `|`/newline characters can break report readability.
  - Evidence: [`arcwright-ai/src/arcwright_ai/output/summary.py:269`](arcwright-ai/src/arcwright_ai/output/summary.py#L269)

3. **MEDIUM** — Async warning surfaced in full-suite run (`MockSDKClient.query` coroutine not awaited), indicating resource handling debt.
  - Evidence: full `pytest -q` run output; related test at [`arcwright-ai/tests/test_agent/test_invoker.py:228`](arcwright-ai/tests/test_agent/test_invoker.py#L228)

4. **MEDIUM** — Dev Agent Record File List does not fully match actual modified tracked files.
  - Evidence: [`_spec/implementation-artifacts/4-3-run-summary-and-halt-report-generation.md:341`](_spec/implementation-artifacts/4-3-run-summary-and-halt-report-generation.md#L341), [`_spec/implementation-artifacts/sprint-status.yaml:75`](_spec/implementation-artifacts/sprint-status.yaml#L75)
