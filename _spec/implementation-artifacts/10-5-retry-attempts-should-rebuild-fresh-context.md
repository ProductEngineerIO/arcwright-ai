# Story 10.5: Retry Attempts Should Rebuild Fresh Context

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer of Arcwright AI,
I want each retry attempt to run with a fresh execution context,
So that retries do not inherit stale context bundles or worktree state from prior failed attempts.

## Bug Report

**Observed behavior:**
When validation returns a retry outcome, execution loops from `validate` to `budget_check` to `agent_dispatch` without re-running `preflight`. This means retry attempts reuse the existing `context_bundle` and existing worktree state.

**Impact:**
- Retry can operate on stale context if planning artifacts or resolved references changed.
- Retry can be influenced by leftover filesystem state from a prior failed attempt.
- Behavior is less deterministic and can mask root-cause failures.

## Acceptance Criteria (BDD)

### AC 1: Retry context is rebuilt before next agent dispatch

**Given** a story attempt fails V3 validation and routes to retry
**When** the next attempt begins
**Then** context is rebuilt from disk before `agent_dispatch` (either by routing through `preflight` or an equivalent explicit refresh step)
**And** the updated context is the one used to build the retry prompt.

### AC 2: Retry keeps feedback but does not reuse stale context

**Given** prior validation feedback exists from the failed attempt
**When** the retry prompt is assembled
**Then** previous feedback is included
**And** context sections (story, requirements, architecture, conventions) are sourced from freshly rebuilt context, not a stale cached bundle.

### AC 3: Retry executes in isolated fresh working state

**Given** a retry is triggered
**When** file edits are performed on the next attempt
**Then** retry runs in isolated deterministic working state
**And** residual uncommitted files from the failed attempt do not leak into retry behavior.

### AC 4: Regression tests for retry freshness

**Given** the engine test suite
**When** retry-related tests run
**Then** there is at least one regression test proving stale context is not reused across retries
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [ ] Task 1: Update retry routing/flow for fresh context rebuild (AC: #1, #3)
  - [ ] 1.1: Choose implementation approach: route retries through `preflight` or add explicit context refresh step before `agent_dispatch`.
  - [ ] 1.2: Ensure worktree behavior is deterministic for retries (recreate or clean/reset as needed).

- [ ] Task 2: Preserve validation feedback in retry prompt (AC: #2)
  - [ ] 2.1: Keep `Previous Validation Feedback` injection behavior unchanged.
  - [ ] 2.2: Verify feedback + fresh context are both present in retry prompt assembly.

- [ ] Task 3: Add regression tests (AC: #4)
  - [ ] 3.1: Add test proving retry does not reuse stale context bundle.
  - [ ] 3.2: Add test proving retry working state is deterministic.

- [ ] Task 4: Run quality gates (AC: #4)
  - [ ] 4.1: Run `ruff check src/ tests/`.
  - [ ] 4.2: Run `mypy --strict src/`.
  - [ ] 4.3: Run `pytest`.

## Dev Notes

### Scope Boundaries

- Do not change non-retry happy path behavior.
- Preserve existing budget and retry-count semantics.
- Keep provenance and validation checkpoint outputs consistent with current format.

### Candidate Files

- `src/arcwright_ai/engine/graph.py`
- `src/arcwright_ai/engine/nodes.py`
- `src/arcwright_ai/engine/state.py`
- `tests/test_engine/`

## Dev Agent Record

### Agent Model Used

GPT-5.3-Codex

### Completion Notes

- Story added to Epic 10 as a new bug item.

### File List

- `_spec/implementation-artifacts/10-5-retry-attempts-should-rebuild-fresh-context.md`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/planning-artifacts/epics.md`
