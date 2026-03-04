# Story 4.1: Provenance Recorder — Decision Logging During Execution

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator reviewing completed work,
I want every AI decision recorded with timestamp, alternatives considered, and rationale,
so that I can audit why the AI made specific choices and build trust in the system.

## Acceptance Criteria (BDD)

1. **Given** `output/provenance.py` module **When** the provenance recorder is implemented **Then** it exposes two async public functions: `append_entry(path: Path, entry: ProvenanceEntry) -> None` which appends a single entry to an existing provenance markdown file (creating it if it doesn't exist), and `write_entries(path: Path, entries: list[ProvenanceEntry]) -> None` which writes a complete provenance markdown file from scratch with all provided entries. Both functions import `ProvenanceEntry` from `arcwright_ai.core.types` (the model already exists — do NOT redefine it). Both functions are async, using `read_text_async` and `write_text_async` from `core/io` for file I/O. Neither function imports anything from `engine/` — zero engine dependency enforced.

2. **Given** a `ProvenanceEntry` with all fields populated (`timestamp`, `decision`, `alternatives`, `rationale`, `ac_references`) **When** `write_entries()` renders it to markdown **Then** the output file begins with `# Provenance: {story_slug}` heading (story_slug extracted from the file path's parent directory name), followed by three mandatory sections in order: `## Agent Decisions`, `## Validation History`, `## Context Provided`. The `## Agent Decisions` section contains each entry as a subsection with format: `### Decision: {entry.decision}` followed by `- **Timestamp**: {entry.timestamp}`, `- **Alternatives**: {comma-separated entry.alternatives or "None considered"}`, `- **Rationale**: {entry.rationale}`, `- **References**: {comma-separated entry.ac_references or "None"}`.

3. **Given** the `## Validation History` section **When** `write_entries()` renders it **Then** it outputs a markdown table with columns `| Attempt | Result | Feedback |` and separator row `|---------|--------|----------|`. When no validation data is provided (entries only, no validation results), the section contains the table header with a single row `| — | — | — |` indicating no validation has occurred yet. A separate helper function `render_validation_row(attempt: int, result: str, feedback: str) -> str` is provided for Story 4.4 to use when wiring validation results into provenance.

4. **Given** the `## Context Provided` section **When** `write_entries()` renders it **Then** it lists all unique `ac_references` from all entries as a deduplicated bullet list: `- {ref}` per reference, sorted alphabetically. If no references exist across any entry, the section contains `- No context references recorded`.

5. **Given** a `ProvenanceEntry` where `rationale` exceeds 500 characters **When** it is rendered to markdown **Then** the rationale is wrapped in a collapsible `<details>` block: `<details><summary>Rationale (click to expand)</summary>\n\n{rationale}\n\n</details>`. Rationale of 500 characters or fewer is rendered inline. Similarly, if `alternatives` has more than 5 items, the alternatives list is wrapped in a `<details>` block.

6. **Given** an existing provenance file at `path` with content **When** `append_entry()` is called with a new entry **Then** the function reads the existing file via `read_text_async()`, locates the `## Agent Decisions` section, inserts the new decision subsection at the end of that section (before `## Validation History`), and writes the updated content back via `write_text_async()`. If the file does not exist, `append_entry()` creates a new file with the single entry using the same format as `write_entries()`.

7. **Given** the provenance file path contract from D3↔D5 **When** provenance files are written **Then** the expected path is `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md` — matching the constant `VALIDATION_FILENAME` from `core/constants.py`. The provenance module does NOT construct this path itself — callers (Story 4.4) pass the fully resolved `Path`. The module only reads/writes to the `Path` it receives.

8. **Given** the `output/__init__.py` module **When** this story is complete **Then** `__all__` is updated to export: `["append_entry", "write_entries", "render_validation_row"]`. Imports are added from `output.provenance`.

9. **Given** new unit tests in `tests/test_output/test_provenance.py` **When** the test suite runs **Then** tests cover: (a) `write_entries()` with a single entry produces correct markdown with all three sections and heading; (b) `write_entries()` with multiple entries (3+) renders all decisions in order; (c) `append_entry()` to a non-existent file creates a new valid provenance file; (d) `append_entry()` to an existing file correctly inserts the new decision before `## Validation History`; (e) long rationale (>500 chars) wrapped in `<details>` block; (f) short rationale (<=500 chars) rendered inline; (g) many alternatives (>5) wrapped in `<details>` block; (h) few alternatives (<=5) rendered inline as comma-separated; (i) empty alternatives list renders as "None considered"; (j) empty ac_references renders as "None" in decision and "No context references recorded" in Context Provided section; (k) `render_validation_row()` returns correctly formatted table row; (l) deduplication and alphabetical sorting of ac_references in Context Provided section; (m) story_slug extraction from path parent directory name.

10. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

11. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

12. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

13. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 372 existing tests continue to pass unmodified. The existing `_serialize_validation_checkpoint()` in `engine/nodes.py` is NOT modified or replaced by this story — that migration happens in Story 4.4.

## Tasks / Subtasks

- [x] Task 1: Implement provenance rendering helpers in `output/provenance.py` (AC: #2, #3, #4, #5)
  - [x] 1.1: Add imports:
    ```python
    import asyncio
    from pathlib import Path
    
    from arcwright_ai.core.io import read_text_async, write_text_async
    from arcwright_ai.core.types import ProvenanceEntry
    ```
  - [x] 1.2: Implement `_render_decision_section(entry: ProvenanceEntry) -> str` private function that renders a single decision subsection:
    - Format heading as `### Decision: {entry.decision}`
    - Render `- **Timestamp**: {entry.timestamp}`
    - Render alternatives: if len > 5 wrap in `<details>`, else comma-join or "None considered"
    - Render rationale: if len > 500 wrap in `<details>`, else inline
    - Render `- **References**: {comma-join entry.ac_references or "None"}`
  - [x] 1.3: Implement `render_validation_row(attempt: int, result: str, feedback: str) -> str` public function returning a markdown table row: `| {attempt} | {result} | {feedback} |`
  - [x] 1.4: Implement `_render_validation_history(rows: list[str] | None = None) -> str` private function:
    - Outputs `## Validation History\n\n| Attempt | Result | Feedback |\n|---------|--------|----------|`
    - If `rows` is None or empty, appends `| — | — | — |`
    - Else appends each row string
  - [x] 1.5: Implement `_render_context_provided(entries: list[ProvenanceEntry]) -> str` private function:
    - Collects all `ac_references` from all entries, deduplicates, sorts alphabetically
    - If empty: `- No context references recorded`
    - Else: one `- {ref}` bullet per reference
  - [x] 1.6: Implement `_extract_story_slug(path: Path) -> str` private helper that returns the parent directory name from the path (e.g., for `.arcwright-ai/runs/.../stories/2-1-foo/validation.md` returns `"2-1-foo"`)

- [x] Task 2: Implement `write_entries()` async function (AC: #1, #2, #7)
  - [x] 2.1: Function signature: `async def write_entries(path: Path, entries: list[ProvenanceEntry]) -> None`
  - [x] 2.2: Build full markdown document:
    ```
    # Provenance: {story_slug}
    
    ## Agent Decisions
    
    {each _render_decision_section(entry)}
    
    ## Validation History
    
    {_render_validation_history()}
    
    ## Context Provided
    
    {_render_context_provided(entries)}
    ```
  - [x] 2.3: Create parent directory if it doesn't exist: `await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)`
  - [x] 2.4: Write via `await write_text_async(path, content)`

- [x] Task 3: Implement `append_entry()` async function (AC: #1, #6)
  - [x] 3.1: Function signature: `async def append_entry(path: Path, entry: ProvenanceEntry) -> None`
  - [x] 3.2: If file does not exist → delegate to `write_entries(path, [entry])`
  - [x] 3.3: If file exists → read via `read_text_async(path)`, find `## Validation History` marker, insert new decision subsection before it, write back via `write_text_async(path, content)`
  - [x] 3.4: Update `## Context Provided` section by re-rendering with all references (parse existing refs from file + new entry refs)

- [x] Task 4: Update `output/__init__.py` exports (AC: #8)
  - [x] 4.1: Update `__all__` to `["append_entry", "render_validation_row", "write_entries"]`
  - [x] 4.2: Add imports:
    ```python
    from arcwright_ai.output.provenance import append_entry, render_validation_row, write_entries
    ```

- [x] Task 5: Create unit tests in `tests/test_output/test_provenance.py` (AC: #9)
  - [x] 5.1: Test `write_entries()` single entry — verify markdown heading, all three sections present, decision formatted correctly
  - [x] 5.2: Test `write_entries()` multiple entries — verify all decisions rendered in order
  - [x] 5.3: Test `append_entry()` to non-existent file — creates valid provenance file
  - [x] 5.4: Test `append_entry()` to existing file — new decision inserted before Validation History section
  - [x] 5.5: Test long rationale `<details>` wrapping (>500 chars)
  - [x] 5.6: Test short rationale inline rendering (<=500 chars)
  - [x] 5.7: Test many alternatives `<details>` wrapping (>5 items)
  - [x] 5.8: Test few alternatives inline rendering (<=5 items, comma-separated)
  - [x] 5.9: Test empty alternatives → "None considered"
  - [x] 5.10: Test empty ac_references → "None" in decision, "No context references recorded" in Context Provided
  - [x] 5.11: Test `render_validation_row()` returns correct table row format
  - [x] 5.12: Test ac_references deduplication and alphabetical sort
  - [x] 5.13: Test story_slug extraction from path parent directory
  - [x] 5.14: Verify all tests use `tmp_path` fixture for file I/O (no hardcoded paths)

- [x] Task 6: Run quality gates (AC: #10, #11, #12, #13)
  - [x] 6.1: `ruff check .` — zero violations against FULL repository
  - [x] 6.2: `ruff format --check .` — zero formatting issues
  - [x] 6.3: `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 6.4: `pytest` — all tests pass (372 existing + 16 new = 388 total)
  - [x] 6.5: Verify Google-style docstrings on all public functions

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `output → core` only. The `output/provenance.py` module must NEVER import from `engine/`, `agent/`, `validation/`, `context/`, `scm/`, or `cli/`. It consumes `ProvenanceEntry` from `core/types.py` and async I/O primitives from `core/io.py`. That's the entire dependency surface.

**D3 — Provenance Format**: One markdown file per story. Three sections: Agent Decisions (subsections per decision), Validation History (table), Context Provided (bullet list of references). Collapsible `<details>` blocks for large content. This is the format the PR generator (`scm/pr.py`, Story 6.4) will read to assemble PR bodies.

**D5 — Run Directory Schema & Write Policy**: Provenance lives at `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md`. LangGraph state is authority during execution; run directory files are transition checkpoints. The provenance module does NOT construct paths — it receives them from callers. The constant `VALIDATION_FILENAME = "validation.md"` from `core/constants.py` governs the filename.

**D3↔D5 Binding**: The path `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md` is a stable contract between the provenance writer (`output/provenance.py`) and the PR generator (`scm/pr.py`). This module is the writer side of that contract.

### Existing Code to Reuse — DO NOT REINVENT

- **`ProvenanceEntry`** already exists in `core/types.py` as an `ArcwrightModel` (frozen Pydantic model) with fields: `decision` (str), `alternatives` (list[str]), `rationale` (str), `ac_references` (list[str]), `timestamp` (str, ISO 8601). Use it directly — do NOT create a new dataclass or duplicate definition.
- **`write_text_async()`** and **`read_text_async()`** in `core/io.py` — use these for all file I/O. They use `asyncio.to_thread()` wrapping `Path.read_text`/`Path.write_text` with explicit `encoding="utf-8"`.
- **`VALIDATION_FILENAME`** constant in `core/constants.py` — value is `"validation.md"`. Do NOT hardcode this string.
- **`_serialize_validation_checkpoint()`** in `engine/nodes.py` — this exists and currently writes basic validation data to `validation.md`. This story does NOT modify or replace it. Story 4.4 will wire the richer provenance format into the engine nodes. For now, the two coexist — `_serialize_validation_checkpoint` is an internal engine function, and `output/provenance.py` is the standalone provenance module.

### Relationship to Other Stories in Epic 4

- **Story 4.1 (this)**: Creates `output/provenance.py` — standalone provenance recording module
- **Story 4.2**: Creates `output/run_manager.py` — run directory lifecycle and `run.yaml` management
- **Story 4.3**: Creates `output/summary.py` — run summary and halt report generation
- **Story 4.4**: Wires Stories 4.1, 4.2, 4.3 into the LangGraph engine nodes — THAT is where `_serialize_validation_checkpoint()` gets replaced or enhanced with the richer provenance format

### Testing Patterns

- Use `tmp_path` fixture for all file I/O tests — never write to real project directories
- Use `pytest.mark.asyncio` for all async test functions
- Follow the counter-based assertion pattern established in Epic 3 for verifying content structure
- Create `ProvenanceEntry` test fixtures with known values for deterministic assertions
- Test both the write path (new file) and the append path (existing file) thoroughly

### Project Structure Notes

The `output/` package layout after this story:

```
src/arcwright_ai/output/
├── __init__.py          # Updated: exports append_entry, write_entries, render_validation_row
├── provenance.py        # NEW: Decision logging + markdown generation
├── run_manager.py       # UNCHANGED: Still empty stub (Story 4.2)
└── summary.py           # UNCHANGED: Still empty stub (Story 4.3)
```

Test structure:

```
tests/test_output/
├── __init__.py          # EXISTS: Empty
├── .gitkeep             # EXISTS: Can be removed after adding test_provenance.py
└── test_provenance.py   # NEW: All provenance unit tests
```

### Known Pitfalls from Epics 1-3

1. **`__all__` ordering must be alphabetical** — ruff enforces this. Exports in `output/__init__.py` must be sorted.
2. **No aspirational exports** — only export symbols that actually exist and are implemented. Do NOT pre-export planned Story 4.2/4.3 symbols.
3. **`from __future__ import annotations`** at the top of every module — required for `X | None` union syntax.
4. **`frozen=True`** on `ArcwrightModel` — `ProvenanceEntry` instances are immutable. Do not attempt to mutate fields.
5. **Quality gate commands must be run against the FULL repository** (`ruff check .`, not just `ruff check src/arcwright_ai/output/`), and failures in ANY file must be reported honestly. Do not self-report "zero violations" if violations exist anywhere.
6. **Off-by-one in state mutation sequences** — when building markdown with indices/counters, verify expected values at each point explicitly.
7. **Structured log event payloads must include ALL fields documented in ACs** — not applicable to this story directly (no log events), but carry the principle forward.
8. **Use `asyncio.to_thread()` for synchronous operations in async functions** — `path.parent.mkdir()` is synchronous, wrap it: `await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)`.
9. **File list in Dev Agent Record must match actual git changes** — verify against `git status` before claiming completion.
10. **Google-style docstrings on ALL public functions** — include Args, Returns, Raises sections.

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 3: Provenance Format]
- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/architecture.md — Async Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Python Code Style Patterns]
- [Source: _spec/planning-artifacts/epics.md — Epic 4, Story 4.1]
- [Source: _spec/planning-artifacts/prd.md — FR12, FR13, FR14]
- [Source: _spec/implementation-artifacts/epic-3-retro-2026-03-04.md — Action Items]
- [Source: src/arcwright_ai/core/types.py — ProvenanceEntry model]
- [Source: src/arcwright_ai/core/constants.py — VALIDATION_FILENAME, DIR_STORIES, etc.]
- [Source: src/arcwright_ai/core/io.py — write_text_async, read_text_async]
- [Source: src/arcwright_ai/engine/nodes.py — _serialize_validation_checkpoint (existing, not modified)]
- [Source: src/arcwright_ai/output/__init__.py — current empty __all__]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No debug log entries — implementation proceeded without blockers.

### Completion Notes List

- Implemented `output/provenance.py` with full rendering pipeline: `_render_decision_section`, `_render_validation_history`, `_render_context_provided`, `_extract_story_slug`, `_parse_refs_from_decisions` (private helpers) and `render_validation_row`, `write_entries`, `append_entry` (public API).
- `Path` and `ProvenanceEntry` moved to `TYPE_CHECKING` block per ruff TC rules (safe with `from __future__ import annotations`).
- `<details>` collapsible blocks applied for rationale >500 chars and alternatives >5 items.
- `append_entry` correctly parses existing `- **References**:` lines to rebuild the `## Context Provided` section after insertion.
- `output/__init__.py` updated with alphabetically sorted `__all__` and imports from `output.provenance`.
- 16 new tests in `tests/test_output/test_provenance.py` covering all 13 AC#9 test cases plus ancillary coverage.
- All quality gates passed: `ruff check .` (0 violations), `ruff format --check .` (clean), `mypy --strict src/` (0 errors), `pytest` (388 passed, 0 failures).
- `_serialize_validation_checkpoint()` in `engine/nodes.py` untouched — Story 4.4 handles that migration.
- Code review follow-up fix applied: replaced synchronous `path.exists()` call in async `append_entry()` with `await asyncio.to_thread(path.exists)` to align with project async I/O patterns.
- Story documentation synchronized with actual git changes, including sprint tracking file update.
- Optional review cleanup applied: added explicit `@pytest.mark.asyncio` decorators to all async tests in `tests/test_output/test_provenance.py` to align with architecture testing conventions.

### File List

- `src/arcwright_ai/output/provenance.py` — NEW: Full provenance recording module
- `src/arcwright_ai/output/__init__.py` — MODIFIED: Updated `__all__` and imports
- `tests/test_output/test_provenance.py` — NEW: 16 unit tests for provenance module
- `_spec/implementation-artifacts/sprint-status.yaml` — MODIFIED: Story 4.1 status synchronized after review completion

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted review)

### Date

2026-03-04

### Outcome

Approved after fixes.

### Findings Resolved

- Fixed async I/O pattern issue in `append_entry()` by moving existence check to `asyncio.to_thread`.
- Updated story File List to include `sprint-status.yaml` change for git/story consistency.
- Synced story status from `review` to `done` and updated sprint tracking accordingly.

### Change Log

- 2026-03-04: Implemented Story 4.1 — Provenance Recorder. Created `output/provenance.py` with `write_entries`, `append_entry`, `render_validation_row` public API and full rendering pipeline. Updated `output/__init__.py` exports. Added 16 unit tests. All quality gates green (388 tests pass).
- 2026-03-04: Code review fixes applied — async `path.exists()` check moved to thread, story documentation reconciled with git changes, and status advanced to `done`.
- 2026-03-04: Optional review fix applied — async tests explicitly marked with `pytest.mark.asyncio` for consistency with project testing patterns.
