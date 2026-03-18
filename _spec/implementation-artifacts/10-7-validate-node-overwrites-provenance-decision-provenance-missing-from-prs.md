# Story 10.7: Validate Node Overwrites Provenance — Decision Provenance Missing from PRs

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a code reviewer using Arcwright AI,
I want pull requests to contain the Decision Provenance section with all agent decisions recorded during story execution,
So that I can review the reasoning behind implementation choices, not just the code diff.

## Bug Report

### Observed Behavior

`validate_node` in `engine/nodes.py` unconditionally overwrites `validation.md` using `_serialize_validation_checkpoint()`, which writes an entirely different format (`# Validation Result` / `## V6 Invariant Checks` / `## V3 Reflexion Results`) that **lacks the `## Agent Decisions` section**. This destroys the provenance entries previously written by `agent_dispatch_node` via `append_entry()`.

When `commit_node` later calls `generate_pr_body()`, `_extract_decisions()` finds no `## Agent Decisions` header and returns an empty list, rendering "No agent decisions recorded" in every PR.

### Compounding on Retry

On retries, `agent_dispatch_node` calls `append_entry()` on the already-overwritten file (which is now in `_serialize_validation_checkpoint()` format). Because `append_entry()` cannot find the `## Validation History` marker, the new decision block gets appended to the end — but without an `## Agent Decisions` heading wrapping it. `_extract_decisions()` still searches for `## Agent Decisions` and still returns empty.

### Root Cause Data Flow

```
Step 1: agent_dispatch_node → append_entry()
        Creates/updates validation.md in provenance 3-section format:
          # Provenance: <story-slug>
          ## Agent Decisions
            ### Decision: Agent invoked for story ... (attempt 1)
          ## Validation History
          ## Context Provided

Step 2: validate_node → write_text_async(... _serialize_validation_checkpoint())
        ⚠️ UNCONDITIONALLY OVERWRITES validation.md with:
          # Validation Result
          ## V6 Invariant Checks
          ## V3 Reflexion Results
        → ## Agent Decisions section is DESTROYED

Step 3: validate_node → append_entry() (validation provenance, best-effort)
        Tries to append to overwritten file. Finds no ## Validation History marker.
        Appends orphaned ### Decision: block at EOF.

Step 4: commit_node → generate_pr_body() → _extract_decisions()
        Searches for "## Agent Decisions" → NOT FOUND → returns []
        PR body renders: "No agent decisions recorded"
```

### Impact

- **FR12 violated**: Agent decisions are logged but then destroyed — equivalent to not logging.
- **FR15 violated**: Provenance is never attached to PRs.
- **FR35 violated**: PRs lack decision provenance.
- **NFR17 violated**: Decision provenance is not human-readable because it does not exist in the PR.

## Acceptance Criteria (BDD)

### AC 1: Validate node preserves existing provenance

**Given** `agent_dispatch_node` writes provenance entries to `validation.md`
**When** `validate_node` writes validation results
**Then** the existing `## Agent Decisions` section and all `### Decision:` subsections are preserved intact.

### AC 2: PR body includes all agent decisions

**Given** `validate_node` completes
**When** `commit_node` calls `generate_pr_body()`
**Then** `_extract_decisions()` returns all agent decisions recorded during dispatch and validation.

### AC 3: PR contains populated Decision Provenance section

**Given** a story completes with one or more agent decisions
**When** the PR is created via `open_pull_request()`
**Then** the PR body contains a populated `### Decision Provenance` section with each decision's title, timestamp, alternatives, rationale, and references.

### AC 4: Retry cycles preserve all decisions

**Given** a retry cycle occurs (validate → retry → dispatch → validate)
**When** the final PR is generated
**Then** decisions from ALL attempts are present in the provenance, not just the last attempt.

### AC 5: Quality gates pass

**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions.

### AC 6: Integration test coverage

**And** integration-level test coverage verifies the full pipeline: dispatch writes decisions → validate preserves them → PR body includes them.

## Tasks / Subtasks

- [x] Task 1: Fix `validate_node` to preserve provenance when writing validation checkpoint (AC: #1)
  - [x] 1.1: Modify validation checkpoint writing in `validate_node` to merge results into existing provenance instead of overwriting
  - [x] 1.2: Decide approach: either (a) read existing content and merge validation results into it, or (b) write validation checkpoint to a separate section/file, or (c) add a `merge_validation_results()` function in `provenance.py`
  - [x] 1.3: Ensure `_serialize_validation_checkpoint()` output is incorporated into the provenance 3-section format, not as a standalone replacement

- [x] Task 2: Add/update provenance merge function in `provenance.py` (AC: #1, #4)
  - [x] 2.1: Add a function (e.g., `merge_validation_checkpoint()`) that reads existing provenance, injects validation results into the `## Validation History` table, and preserves all existing `## Agent Decisions`
  - [x] 2.2: Ensure the merged output conforms to the Decision 3 provenance format (3-section structure)

- [x] Task 3: Verify the end-to-end PR body generation works (AC: #2, #3)
  - [x] 3.1: After fix, the provenance file should contain `## Agent Decisions` with all decision blocks
  - [x] 3.2: `_extract_decisions()` in `scm/pr.py` should find and parse all decisions
  - [x] 3.3: `_render_pr_body()` should render populated `### Decision Provenance` section

- [x] Task 4: Verify retry scenario preserves all decisions across attempts (AC: #4)
  - [x] 4.1: Confirm that on retry, `agent_dispatch_node` → `append_entry()` → `validate_node` flow preserves decisions from earlier attempts
  - [x] 4.2: The final provenance file should contain decisions from attempt 1, attempt 2, etc.

- [x] Task 5: Add regression tests (AC: #5, #6)
  - [x] 5.1: Unit test: `validate_node` preserves existing `## Agent Decisions` section
  - [x] 5.2: Unit test: validation results are written to `## Validation History` table in provenance
  - [x] 5.3: Integration test: dispatch writes decisions → validate preserves them → PR body includes them
  - [x] 5.4: Integration test: retry cycle preserves decisions from all attempts
  - [x] 5.5: Update existing `test_validate_node_writes_validation_checkpoint` to verify provenance format post-fix

- [x] Task 6: Run quality gates (AC: #5)
  - [x] 6.1: `ruff check src/ tests/`
  - [x] 6.2: `mypy --strict src/`
  - [x] 6.3: `pytest`

## Dev Notes

### Bug Location — The Exact Lines

The bug is at [engine/nodes.py](arcwright-ai/src/arcwright_ai/engine/nodes.py#L1079-L1084) in `validate_node` (approximately line 1079-1084):

```python
# Write validation checkpoint
checkpoint_dir: Path = (
    state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
)
await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
await write_text_async(
    checkpoint_dir / VALIDATION_FILENAME,
    _serialize_validation_checkpoint(pipeline_result, state.retry_count + 1),
)
```

This **unconditionally overwrites** `validation.md` with the `_serialize_validation_checkpoint()` format, which is a completely different format from the provenance 3-section format.

### Architecture Constraint — Decision 3 Provenance Format

Per architecture Decision 3, all provenance files MUST follow the 3-section structure:

```markdown
# Provenance: <story-title>

## Agent Decisions
### Decision: ...
- **Timestamp**: ...
- **Alternatives**: ...
- **Rationale**: ...
- **References**: ...

## Validation History
| Attempt | Result | Feedback |
|---------|--------|----------|
| 1       | pass   | All checks passed |

## Context Provided
- FR1
- AC2
```

The `_serialize_validation_checkpoint()` function violates this contract. The fix must ensure validation results are **merged into** the provenance format, not written as a replacement.

### Architecture Constraint — File Path Contract (D3↔D5 binding)

Provenance files live at `.arcwright-ai/runs/<run-id>/stories/<story-slug>/validation.md`. The `scm/pr.py` module reads from this known path. This is a stable contract between provenance writer (`output/provenance.py`) and PR generator — do NOT change this path.

### Architecture Constraint — Write Policy

Per Decision 5: "Run directory files are written as checkpoints at state transitions only." The validate_node IS a state transition — writing validation results is correct — but the write must preserve existing provenance content.

### Key Source Files

| File | Role | What to change |
|------|------|----------------|
| `src/arcwright_ai/engine/nodes.py` | Bug location — `validate_node` | Replace unconditional overwrite with merge-aware write |
| `src/arcwright_ai/engine/nodes.py` | Serializer — `_serialize_validation_checkpoint()` | May need refactoring or replacement |
| `src/arcwright_ai/output/provenance.py` | Provenance writer | Add `merge_validation_checkpoint()` or similar function |
| `src/arcwright_ai/scm/pr.py` | PR body generator | `_extract_decisions()` — should work correctly once provenance is preserved (no changes expected) |
| `tests/test_engine/test_nodes.py` | Existing test | Update `test_validate_node_writes_validation_checkpoint` assertion (currently checks for `# Validation Result` header — should check for provenance format) |
| `tests/test_output/test_provenance.py` | Provenance tests | Add tests for new merge function |
| `tests/test_scm/test_pr.py` | PR body tests | Add test with realistic post-validate provenance content |

### Recommended Implementation Approach

**Preferred approach: Merge validation results INTO existing provenance file**

1. In `validate_node`, before writing the checkpoint:
   - Read existing `validation.md` if it exists
   - If it exists and contains `## Agent Decisions`, merge validation results into `## Validation History` table
   - If it does not exist, use `write_entries()` to create in correct provenance format

2. Add a function to `provenance.py` (e.g., `merge_validation_results()`) that:
   - Takes existing provenance content and a `PipelineResult`
   - Parses the existing `## Validation History` table
   - Appends a new row with the validation attempt results
   - Returns the updated content with all `## Agent Decisions` preserved

3. Replace the `write_text_async(... _serialize_validation_checkpoint(...))` call with a call to the new merge function.

4. The existing `append_entry()` call for validation provenance (after the checkpoint write) should then work correctly because the file is still in 3-section format.

**Alternative approach — NOT recommended:**
Writing to a separate `validation-checkpoint.md` file would preserve provenance but would add complexity and deviate from the D3↔D5 file path contract.

### `_serialize_validation_checkpoint()` Details

Located at [engine/nodes.py](arcwright-ai/src/arcwright_ai/engine/nodes.py#L784-L810). This function writes:
- `# Validation Result` (wrong header — should be absent or part of provenance)
- `## V6 Invariant Checks` — list of pass/fail checks
- `## V3 Reflexion Results` — list of AC results (if present)

This content needs to be transformed into:
- A `## Validation History` table row: `| attempt | outcome | summary |`
- Optionally: detailed V6/V3 results as part of the validation provenance entry rationale

### `append_entry()` in `provenance.py` — Behavior to Understand

Located at [output/provenance.py](arcwright-ai/src/arcwright_ai/output/provenance.py#L211-L252). This function:
1. If file does not exist → delegates to `write_entries()` (creates fresh 3-section file)
2. If file exists → reads content, inserts new decision before `## Validation History` marker
3. If `## Validation History` marker not found → appends at EOF (which is the broken path today)

After the fix, the validate_node checkpoint write must preserve the `## Validation History` marker so that subsequent `append_entry()` calls work correctly.

### `_extract_decisions()` in `scm/pr.py` — No Changes Expected

Located at [scm/pr.py](arcwright-ai/src/arcwright_ai/scm/pr.py#L265-L330). Searches for `## Agent Decisions` header, then parses `### Decision:` subsections. This function should work correctly once provenance format is preserved — no changes expected here.

### Existing Test That Needs Updating

`test_validate_node_writes_validation_checkpoint` at [test_nodes.py](arcwright-ai/tests/test_engine/test_nodes.py#L516-L537) currently asserts:
```python
assert "# Validation Result" in content
assert "Outcome" in content
```
After the fix, the checkpoint file will be in provenance format, so these assertions need updating to check for `# Provenance:` and `## Validation History` instead.

### Previous Story Intelligence (10.6)

Story 10.6 fixed a related issue where merge outcomes were incorrectly reported. Key learnings:
- The `_merge_immediate` and `_step_a_queue_auto_merge` functions in `scm/pr.py` were modified
- `nodes.py` was updated with `delete_branch=True` flag for worktree cleanup on MERGED
- Provenance rationale was updated from `status=` to `merge_status=` field
- All changes passed 971 tests with `ruff check`, `mypy --strict`, and `pytest`
- Agent model used: Claude Sonnet 4.6

### Testing Patterns (from existing tests)

- Tests use `pytest.mark.asyncio` for async test functions
- Fixtures: `validate_ready_state`, `mock_pipeline_pass`, `make_story_state`
- Import the node functions directly: `from arcwright_ai.engine.nodes import validate_node`
- Constants imported from `arcwright_ai.core.constants`: `VALIDATION_FILENAME`, `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`
- Checkpoint path construction: `state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id) / VALIDATION_FILENAME`

### Git Intelligence

Recent commits on `hotfix/sandbox-issue` branch:
- `1905e91` Fix lint and formatting issues
- `d2f1b34` Track sandbox-denied paths and include in prompts
- `acf6bd4` Merge PR #18 from develop

The main branch is at `acf6bd4`. The hotfix branch has sandbox-related changes. Story 10.7 should be developed on its own branch from `main` or `develop`.

### Project Structure Notes

- Source: `arcwright-ai/src/arcwright_ai/`
- Tests: `arcwright-ai/tests/`
- Run from: `arcwright-ai/` directory (the inner `arcwright-ai/` sub-folder)
- Linting: `ruff check src/ tests/`
- Type checking: `mypy --strict src/`
- Testing: `pytest`

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 3: Provenance Format]
- [Source: _spec/planning-artifacts/architecture.md — Decision 5: Run Directory Schema, Write Policy]
- [Source: _spec/planning-artifacts/prd.md — FR12 (log decisions), FR13 (structured entries), FR14 (write to runs/), FR15 (attach to PRs), FR35 (PRs with decision provenance), NFR17 (human-readable)]
- [Source: _spec/planning-artifacts/epics.md — Epic 10, Story 10.7]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — validate_node, _serialize_validation_checkpoint, agent_dispatch_node, commit_node]
- [Source: arcwright-ai/src/arcwright_ai/output/provenance.py — append_entry, write_entries, render_validation_row]
- [Source: arcwright-ai/src/arcwright_ai/scm/pr.py — generate_pr_body, _extract_decisions, _render_pr_body]
- [Source: _spec/implementation-artifacts/10-6-auto-merge-success-marked-error-on-branch-cleanup-failure.md — Previous story learnings]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

N/A — implementation followed the recommended approach from Dev Notes without blockers.

### Completion Notes List

- Selected approach (a): read existing content and merge validation results into it.
- Added `merge_validation_checkpoint()` to `output/provenance.py` (new public function, added to `__all__`). It:
  - Creates a fresh 3-section provenance file if the path does not exist.
  - Injects the `## Validation History` section when the file exists but lacks one (corruption repair).
  - Replaces the placeholder row `| — | — | — |` on first call.
  - Appends subsequent rows to the table on retry calls.
  - Preserves all existing `## Agent Decisions` content in every code path.
- In `validate_node` (`engine/nodes.py`): removed the unconditional `write_text_async(... _serialize_validation_checkpoint(...))` call. Moved `merge_validation_checkpoint` call inside the existing best-effort try/except block, so both the merge and the `append_entry` decision record are fault-tolerant.
- Updated import in `nodes.py`: added `merge_validation_checkpoint` to the provenance import.
- Updated `test_validate_node_writes_validation_checkpoint` assertions to match provenance format (`# Provenance:` and `## Validation History` instead of `# Validation Result`).
- Added 11 new tests: 8 unit tests in `test_provenance.py` and 3 integration tests in `test_nodes.py`, plus 1 integration test in `test_pr.py`.
- All 983 tests pass; `ruff check` and `mypy --strict` both clean.
- `_serialize_validation_checkpoint()` is now dead code (private function, no callers). Left in place as it poses no risk and removal is out of scope.
- Follow-up fix (code review): normalized legacy/corrupt provenance content in `merge_validation_checkpoint()` so repaired files always contain `## Agent Decisions` and `## Context Provided`, and added regression test coverage for append-after-repair parsing.

### File List

arcwright-ai/src/arcwright_ai/output/provenance.py
arcwright-ai/src/arcwright_ai/engine/nodes.py
arcwright-ai/tests/test_engine/test_nodes.py
arcwright-ai/tests/test_output/test_provenance.py
arcwright-ai/tests/test_scm/test_pr.py
_spec/implementation-artifacts/sprint-status.yaml

## Change Log

- Fix `validate_node` unconditional overwrite of `validation.md` — replace `write_text_async(_serialize_validation_checkpoint(...))` with `merge_validation_checkpoint()` that preserves `## Agent Decisions` (Date: 2026-03-18)
- Add `merge_validation_checkpoint()` to `output/provenance.py` — merges validation row into `## Validation History` while preserving provenance format (Date: 2026-03-18)
- Update `test_validate_node_writes_validation_checkpoint` to assert provenance format (Date: 2026-03-18)
- Add 11 new regression tests covering AC #1–#6 (Date: 2026-03-18)
- Fix legacy repair edge case where repaired files could still miss `## Agent Decisions`, causing PR decision extraction to miss appended entries (Date: 2026-03-18)
