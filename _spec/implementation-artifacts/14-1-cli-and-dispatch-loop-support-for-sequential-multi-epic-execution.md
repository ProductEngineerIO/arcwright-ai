# Story 14.1: CLI and Dispatch-Loop Support for Sequential Multi-Epic Execution

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running Arcwright AI,
I want to supply an ordered list of epics to `arcwright dispatch` via a new `--epics` option,
so that each epic in the list is dispatched and fully completed — one at a time, in the order given — without me having to manually re-run `dispatch` after each epic finishes.

## Acceptance Criteria

1. **Epic-spec parsing and validation.** Given `arcwright dispatch --epics "2,3,4"` (or `"epic-2,epic-3,epic-4"`, or space-separated `"2 3 4"`), each element is validated using the same rules as the existing `--epic` option (`_extract_epic_number`: `"4"`, `"epic-4"`, `"EPIC-4"`). An invalid element produces a clear `ProjectError`-style CLI error and exits `EXIT_CONFIG` before any dispatch begins. A duplicate epic number in the list also produces a clear error before any dispatch begins.
2. **Mutual exclusivity with `--story`/`--epic`.** Supplying `--epics` together with `--story` or `--epic` produces a CLI error and exits with a non-zero code before any dispatch begins (mirrors the existing `--story`+`--epic` mutual-exclusivity check in `dispatch_command`).
3. **Mutual exclusivity with `--resume`.** Supplying `--epics` together with `--resume` produces a CLI error and exits with a non-zero code. Resuming remains scoped to a single halted epic via the existing `--resume --epic X` flow; resuming a partially-completed multi-epic sequence is explicitly out of scope for this story.
4. **Single upfront aggregate confirmation.** Unless `--yes`/`-y` is passed, the CLI shows exactly one confirmation prompt before any epic starts, listing: the ordered list of epics, each epic's story count, the combined story count across the whole sequence, and an aggregate estimated cost range (sum of each epic's existing per-epic estimate, using `_estimate_cost_range`). Declining aborts with no dispatch at all (same `typer.Abort` pattern as the existing single-epic confirmation).
5. **Strict sequential ordering, one independent run per epic.** Epics dispatch strictly in the order supplied. Each epic runs through the existing `_dispatch_epic_async` pipeline unchanged (own `run_id`, own worktrees, own run directory under `.arcwright-ai/runs/`). The next epic in the list is only started after the current epic's dispatch call returns `EXIT_SUCCESS`.
6. **Immediate halt on any epic failure.** If any epic in the sequence returns a non-`EXIT_SUCCESS` code (validation exhaustion, budget exceeded, SDK/agent error, or merge failure — all already handled inside `_dispatch_epic_async`/`HaltController`), the sequence loop stops immediately. Subsequent epics in the list are never started. The overall process exits with the halted epic's own exit code.
7. **Clear mid-sequence halt reporting.** On a mid-sequence halt, terminal output (via `typer.echo(..., err=True)`) states: which epic halted, which epics (if any) completed successfully before it, and which epics in the list were never started. This is in addition to the existing per-epic halt output already produced by `_dispatch_epic_async`/`HaltController`.
8. **Aggregate success summary.** When every epic in the sequence completes successfully, the CLI prints an aggregate summary line (total epics dispatched, total stories across all epics, combined cost, combined tokens) after the last epic's own existing per-epic summary output. Combined cost/tokens are computed by reading each completed epic's run metadata via the existing `_find_latest_run_for_epic` helper (already imported in `dispatch.py` from `arcwright_ai.cli.resume`) rather than by changing `_dispatch_epic_async`'s return contract.
9. **No change to existing single-epic behavior.** `--story` and `--epic` (including `--epic ... --resume`) behave exactly as before. This story is purely additive — no changes to `_dispatch_epic_async`, `_dispatch_story_async`, `HaltController`, or the per-epic confirmation/summary output.
10. **Test coverage.** Unit/integration tests in `tests/test_cli/test_dispatch.py` cover: (a) successful multi-epic sequence dispatch in order, (b) mid-sequence halt where a later epic in the list is never started, (c) invalid epic-spec rejection, (d) duplicate epic-spec rejection, (e) mutual-exclusivity errors for `--epics` with `--story`, `--epic`, and `--resume`.
11. **Quality gate.** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Add `--epics` CLI option and validation (AC: #1, #2, #3)
  - [x] 1.1: In `src/arcwright_ai/cli/dispatch.py`, add a new `epics: Annotated[str | None, typer.Option("--epics", help="Comma or space-separated ordered list of epics to dispatch sequentially (e.g., \"2,3,4\")")] = None` parameter to `dispatch_command`.
  - [x] 1.2: Add a small parsing helper, e.g. `_parse_epic_list(epics_arg: str) -> list[str]`, that splits on commas and/or whitespace, strips empty tokens, and returns the ordered list of raw epic-spec strings (do not dedupe yet — dedupe is a validation step, not a normalization step).
  - [x] 1.3: In `dispatch_command`, add validation branches (mirroring the existing `story`/`epic` mutual-exclusivity checks near the top of the function):
    - `epics` together with `story` → error, `typer.Exit(code=1)`
    - `epics` together with `epic` → error, `typer.Exit(code=1)`
    - `epics` together with `resume=True` → error, `typer.Exit(code=1)`
    - `epics` provided but empty after parsing → error, `typer.Exit(code=1)`
  - [x] 1.4: When `epics` is provided (and passes the above checks), call `asyncio.run(_dispatch_epics_async(parsed_list, skip_confirm=yes))` instead of the existing single-epic/story branches, and use its returned exit code for `typer.Exit(code=...)`.

- [x] Task 2: Implement `_dispatch_epics_async` sequence orchestrator (AC: #4, #5, #6, #7, #8, #9)
  - [x] 2.1: Add `async def _dispatch_epics_async(epic_specs: list[str], *, skip_confirm: bool = False) -> int` in `dispatch.py`, placed near `_dispatch_epic_async` for locality.
  - [x] 2.2: Discover `project_root` and `config` once (same pattern as `_dispatch_epic_async`'s opening lines) — reuse `_discover_project_root()` and `load_config()`.
  - [x] 2.3: For each epic spec, call `_extract_epic_number(spec)` to validate format and normalize to a bare number; raise/echo a `ProjectError`-style message and return `EXIT_CONFIG` on the first invalid spec (fail fast, before touching any epic). Check for duplicate normalized epic numbers across the list and fail the same way if any duplicates are found.
  - [x] 2.4: For each validated epic, call `_find_epic_stories(epic_spec, artifacts_dir)` (existing helper) to get its ordered story list for the confirmation summary — do this for *all* epics up front, before dispatching any of them, so the aggregate confirmation and fail-fast validation happen before any side effects.
  - [x] 2.5: Build and print the aggregate confirmation (unless `skip_confirm`): echo the epic list in order with each epic's story count, the combined story count, and an aggregate cost estimate — sum the low/high bounds from `_estimate_cost_range(project_root, story_count)` called once per epic with that epic's story count (reuse the existing helper; do not reimplement estimation logic). Use `typer.confirm("\nProceed with sequential dispatch?", abort=True)` exactly like the existing single-epic confirmation so a decline raises `typer.Abort`; catch that the same way `dispatch_command`/`_dispatch_epic_async` callers do and return `EXIT_SUCCESS` on cancellation.
  - [x] 2.6: Loop over the ordered epic specs. For each, call `await _dispatch_epic_async(epic_spec, skip_confirm=True, resume=False)` — always pass `skip_confirm=True` here regardless of the outer `skip_confirm` value, since the aggregate confirmation in 2.5 already covered user consent for the whole sequence and the per-epic confirmation must not fire again.
  - [x] 2.7: After each epic call returns, check the exit code. If it is `EXIT_SUCCESS`, record the epic as completed and continue to the next. If it is non-zero, echo a clear halt message identifying the halted epic, the list of epics completed before it, and the list of epics never started (i.e., all epics after the current index), then return that exit code immediately without starting any further epics.
  - [x] 2.8: After a fully successful sequence (all epics returned `EXIT_SUCCESS`), for each completed epic call `_find_latest_run_for_epic(project_root, epic_spec)` (already imported from `arcwright_ai.cli.resume`) to read back that epic's final `run.yaml` budget totals, sum cost/tokens across all epics, and echo the aggregate summary line (total epics, total stories, combined cost, combined tokens). Return `EXIT_SUCCESS`.
  - [x] 2.9: Do not modify `_dispatch_epic_async`, `_dispatch_story_async`, `HaltController`, `_show_dispatch_confirmation`, or `_estimate_cost_range` — only add new code that calls them.

- [x] Task 3: Unit tests (AC: #10, #11)
  - [x] 3.1: In `tests/test_cli/test_dispatch.py`, follow the existing `_patch_epic_deps(monkeypatch, tmp_path, results)` fixture pattern (used by `test_epic_dispatch_story_ordering` and similar tests) to stub `graph.ainvoke`/`create_run`/`update_run_status`/`update_story_status` for two or three fake epics, each with one or two stories.
  - [x] 3.2: Add `test_dispatch_epics_sequential_success` — three epics, all stories succeed; assert all epics ran in order and the aggregate summary was printed.
  - [x] 3.3: Add `test_dispatch_epics_halts_on_first_epic_failure` — first epic's story fails/escalates; assert the second and third epics in the list were never dispatched (e.g., assert `build_story_graph`/`graph.ainvoke` was never invoked for their stories) and the returned exit code matches the failed epic's exit code.
  - [x] 3.4: Add `test_dispatch_epics_rejects_invalid_epic_spec` and `test_dispatch_epics_rejects_duplicate_epic` — assert `EXIT_CONFIG` and no dispatch side effects occurred.
  - [x] 3.5: Add `test_dispatch_rejects_epics_with_story`, `test_dispatch_rejects_epics_with_epic`, `test_dispatch_rejects_epics_with_resume` — CLI-level mutual exclusivity checks (mirror the existing `test_dispatch_rejects_both_story_and_epic` pattern).
  - [x] 3.6: Run `uv run ruff check src/ tests/ && uv run mypy --strict src/ && uv run pytest` — zero failures, zero regressions.

## Dev Notes

- **This is purely additive.** No existing function signatures change. `_dispatch_epic_async(epic_spec, *, skip_confirm, resume)` is reused as-is, called once per epic from the new orchestrator with `skip_confirm=True` on every call (the aggregate prompt in the new orchestrator replaces the per-epic prompt for this code path only).
- **Package DAG:** `cli/dispatch.py` already imports `_find_latest_run_for_epic` from `arcwright_ai.cli.resume` — no new import boundary is introduced by reusing it in Task 2.8.
- **Exit code taxonomy (unchanged):** `EXIT_SUCCESS=0`, `EXIT_VALIDATION=1`, `EXIT_AGENT=2`, `EXIT_CONFIG=3`, `EXIT_SCM=4`, `EXIT_INTERNAL=5` (from `core/constants.py`). The sequence orchestrator must propagate whichever of these `_dispatch_epic_async` returns on halt — do not invent a new exit code for "sequence halted."
- **Existing confirmation/estimate helpers to reuse, not reimplement:** `_show_dispatch_confirmation()` (~L410-460) and `_estimate_cost_range()` (~L350-420) in `dispatch.py`. The aggregate confirmation is new code but should call `_estimate_cost_range` per epic and sum the results rather than duplicating its historical-run-scanning logic.
- **Epic discovery/validation helpers to reuse:** `_extract_epic_number()` and `_find_epic_stories()` (both already in `dispatch.py`) — do not write new parsing/glob logic for individual epic specs.
- **`--resume` stays single-epic scoped.** This story explicitly does not attempt to resume a halted multi-epic sequence from its failure point; that would require persisting sequence-level state and is out of scope (flagged as a mutual-exclusivity CLI error instead, AC #3).
- **Halt behavior matches D10 (CI-aware merge wait) and existing `HaltController` semantics** (Story 12.4 / 5.2-5.4) — a merge-failure halt inside one epic in the sequence is treated exactly like any other epic-level halt: the sequence stops, subsequent epics don't start.

### Project Structure Notes

- All changes are confined to `src/arcwright_ai/cli/dispatch.py` (new option, new parsing helper, new `_dispatch_epics_async` orchestrator) and `tests/test_cli/test_dispatch.py` (new test coverage). No new modules, no changes to `engine/`, `scm/`, `output/`, or `core/`.
- Follows the existing convention in `dispatch.py` of private (`_`-prefixed) async helper functions per dispatch mode (`_dispatch_story_async`, `_dispatch_epic_async`) — the new `_dispatch_epics_async` follows the same naming and signature style.

### References

- [Source: src/arcwright_ai/cli/dispatch.py] — `dispatch_command`, `_dispatch_epic_async`, `_dispatch_story_async`, `_show_dispatch_confirmation`, `_estimate_cost_range`, `_extract_epic_number`, `_find_epic_stories`
- [Source: src/arcwright_ai/core/constants.py] — Exit code constants (`EXIT_SUCCESS`, `EXIT_VALIDATION`, `EXIT_AGENT`, `EXIT_CONFIG`, `EXIT_SCM`, `EXIT_INTERNAL`)
- [Source: _spec/planning-artifacts/prd.md#Functional Requirements] — FR40 (new), FR1, FR3, FR4, FR5
- [Source: _spec/implementation-artifacts/12-4-dispatch-loop-halt-on-merge-failure.md] — Precedent for epic-level halt semantics and terminal messaging conventions
- [Source: _spec/implementation-artifacts/5-1-epic-dispatch-cli-to-engine-pipeline.md] — Original single-epic dispatch pipeline this story extends
- [Source: tests/test_cli/test_dispatch.py] — `_patch_epic_deps` fixture pattern and existing epic-dispatch test conventions to follow

## Dev Agent Record

### Agent Model Used

Claude (GitHub Copilot dev-story workflow)

### Debug Log References

### Completion Notes List

- Ultimate context engine analysis completed - comprehensive developer guide created
- Added `--epics` option, `_parse_epic_list()` helper, and mutual-exclusivity validation (`--epics` + `--story`/`--epic`/`--resume`, and empty-after-parsing) to `dispatch_command` in `src/arcwright_ai/cli/dispatch.py`.
- Added `_dispatch_epics_async()` orchestrator: validates every epic spec and checks for duplicates up front (fail-fast, before any dispatch), discovers each epic's story list up front, shows a single aggregate confirmation (epic list, per-epic story counts, combined story count, summed `_estimate_cost_range` estimate), then loops calling the unchanged `_dispatch_epic_async(spec, skip_confirm=True, resume=False)` once per epic in order. Halts immediately on the first non-`EXIT_SUCCESS` result, echoing which epic halted, which epics completed, and which were never started. On full success, reads back each epic's `run.yaml` budget via `_find_latest_run_for_epic` (best-effort; degrades gracefully if metadata is unavailable) to print a combined cost/token summary.
- No changes were made to `_dispatch_epic_async`, `_dispatch_story_async`, `HaltController`, `_show_dispatch_confirmation`, or `_estimate_cost_range` — purely additive.
- Added 7 new tests in `tests/test_cli/test_dispatch.py` covering: sequential multi-epic success (with mixed comma/space parsing), mid-sequence halt (later epic never dispatched), invalid epic-spec rejection, duplicate-epic rejection, and mutual-exclusivity errors for `--epics` with `--story`, `--epic`, and `--resume`.
- Quality gate: `uv run ruff check src/ tests/`, `uv run mypy --strict src/`, and `uv run pytest` (full suite) all pass with zero regressions introduced by this story. (5 pre-existing failures in `tests/test_core/test_config.py` and `tests/test_core/test_constants.py` were confirmed present on `main` prior to this story and are unrelated to this change.)

### File List

- `src/arcwright_ai/cli/dispatch.py` (modified)
- `tests/test_cli/test_dispatch.py` (modified)
- `_spec/planning-artifacts/epics.md` (modified — Epic 14 entry)
- `_spec/planning-artifacts/prd.md` (modified — FR40)
- `_spec/implementation-artifacts/sprint-status.yaml` (modified — epic-14 / story 14.1 tracking)
- `README.md` (modified — roadmap status line)

### Change Log

- 2026-08-11: Implemented `--epics` CLI option and `_dispatch_epics_async` sequential multi-epic dispatch orchestrator with aggregate confirmation, fail-fast validation, mid-sequence halt reporting, and aggregate success summary. Added full test coverage (AC #1-#11). Status moved to review.
- 2026-08-11: Code review (adversarial): verified all 11 ACs, all `[x]` tasks, and quality gate claims by independently re-running `ruff check`, `mypy --strict`, and the full `pytest` suite (confirmed the 5 pre-existing failures on `main` are unrelated). Added the four modified planning-artifact files (`epics.md`, `prd.md`, `sprint-status.yaml`, `README.md`) to the File List for transparency. No code changes required. Status moved to done.
