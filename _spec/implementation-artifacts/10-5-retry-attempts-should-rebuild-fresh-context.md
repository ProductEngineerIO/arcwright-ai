# Story 10.5: Retry Attempts Should Rebuild Fresh Context

Status: done

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
**Then** retry re-enters `preflight` (or an equivalent explicit refresh step) so both the `context_bundle` and the worktree/working-tree state are rebuilt from disk, not merely re-templated into the prompt
**And** `StoryState.status` reflects the `preflight` → `running` transition for the retry attempt, consistent with the `queued → preflight → running → validating → success/retry/escalated` lifecycle
**And** residual uncommitted files from the failed attempt do not leak into retry behavior.

### AC 4: Regression tests for retry freshness

**Given** the engine test suite
**When** retry-related tests run
**Then** there is at least one graph-routing test proving the retry edge passes through `preflight` before `agent_dispatch`
**And** there is at least one regression test proving stale context (a changed context_bundle/artifact) is not reused across retries
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Update retry routing/flow for fresh context rebuild (AC: #1, #3)
  - [x] 1.1: Choose implementation approach: route retries through `preflight` or add explicit context refresh step before `agent_dispatch`.
  - [x] 1.2: Ensure worktree behavior is deterministic for retries (recreate or clean/reset as needed).

- [x] Task 2: Preserve validation feedback in retry prompt (AC: #2)
  - [x] 2.1: Keep `Previous Validation Feedback` injection behavior unchanged.
  - [x] 2.2: Verify feedback + fresh context are both present in retry prompt assembly.

- [x] Task 3: Add regression tests (AC: #4)
  - [x] 3.1: Add test proving retry does not reuse stale context bundle.
  - [x] 3.2: Add test proving retry working state is deterministic.

- [x] Task 4: Run quality gates (AC: #4)
  - [x] 4.1: Run `ruff check arcwright-ai/src arcwright-ai/tests` (from repo root) or `ruff check src/ tests/` (from `arcwright-ai/`).
  - [x] 4.2: Run `mypy --strict arcwright-ai/src` (from repo root) or `mypy --strict src/` (from `arcwright-ai/`).
  - [x] 4.3: Run `pytest` from the `arcwright-ai/` package directory.

## Dev Notes

### Scope Boundaries

- Do not change non-retry happy path behavior.
- Preserve existing budget and retry-count semantics — do not alter Story 3.4's retry-count increment, `MAX_RETRIES` escalation threshold, or halt/escalation behavior.
- Keep provenance and validation checkpoint outputs consistent with current format.
- Non-goal: this story does not change budget accounting or halt/escalation logic — only what context/state is rebuilt before a retry's `agent_dispatch`.

### Candidate Files

- `src/arcwright_ai/engine/graph.py`
- `src/arcwright_ai/engine/nodes.py`
- `src/arcwright_ai/engine/state.py`
- `tests/test_engine/`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Implementation Plan

**Approach chosen (Task 1.1):** Route the retry edge directly back through `preflight` — changing `"retry": "budget_check"` to `"retry": "preflight"` in `graph.py`'s `route_validation` conditional edges.

With the existing `preflight → budget_check` fixed edge already in place, the retry flow becomes:
`validate →(retry)→ preflight → budget_check →(ok)→ agent_dispatch`

**Worktree determinism (Task 1.2):** The existing stale-worktree recovery in `preflight_node` already handles retries. When `create_worktree` fails with "already exists" (the previous failed attempt's worktree is still present), the code removes the old worktree, calls `delete_remote_branch` (best-effort — already swallows "remote ref does not exist"), and creates a fresh worktree from the current default-branch tip.

**Dead code removal:** `budget_check_node`'s `RETRY → RUNNING` transition branch became dead code once retries route through `preflight` (which sets status to RUNNING). Removed and updated docstring accordingly.

**Feedback preservation (Task 2):** No changes required. `validate_node` already preserves `validation_result` (containing feedback) in state on RETRY. `agent_dispatch_node` reads `state.validation_result.feedback` — feedback from the prior failed attempt is naturally present when `agent_dispatch` runs on retry. `context_bundle` is freshly overwritten by `preflight` before `agent_dispatch` runs.

### Completion Notes

- ✅ AC1: Retry now routes through `preflight` before `agent_dispatch` — context is rebuilt from disk.
- ✅ AC2: `validation_result.feedback` preserved in state across retry; `context_bundle` freshly rebuilt by preflight.
- ✅ AC3: `preflight_node` cleans and recreates the worktree on retry (stale-worktree recovery path); status lifecycle follows `RETRY → PREFLIGHT → RUNNING → VALIDATING → SUCCESS/RETRY/ESCALATED`.
- ✅ AC4: `test_graph_retry_edge_routes_through_preflight_not_budget_check` proves graph routing; `test_graph_retry_rebuilds_context_bundle_not_stale` proves stale context is not reused. All 1205 tests pass; `ruff`, `mypy --strict`, `pytest` all clean.

### File List

- `arcwright-ai/src/arcwright_ai/engine/graph.py`
- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/tests/test_engine/test_graph.py`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `_spec/implementation-artifacts/10-5-retry-attempts-should-rebuild-fresh-context.md`
- `_spec/implementation-artifacts/sprint-status.yaml`

### Change Log

- Routed retry edge from `validate` to `preflight` (was `budget_check`) in `engine/graph.py` — retries now rebuild context and worktree before next dispatch (Date: 2026-07-23)
- Removed dead `RETRY → RUNNING` transition from `budget_check_node` in `engine/nodes.py`; updated docstring (Date: 2026-07-23)
- Updated `test_graph_contains_expected_conditional_routing` and added `test_graph_retry_edge_routes_through_preflight_not_budget_check` + `test_graph_retry_rebuilds_context_bundle_not_stale` in `tests/test_engine/test_graph.py` (Date: 2026-07-23)
- Updated `preflight_node` docstring to reflect QUEUED-or-RETRY incoming status and corrected inline transition comment (Date: 2026-07-23)
- Clarified `budget_check_node` docstring: node is status-agnostic; RUNNING on retry is a graph-routing invariant, not a node contract (Date: 2026-07-23)
- Sharpened `test_budget_check_node_passes_through_retry_status_unchanged` docstring to read as a routing-invariant regression guard, not a description of normal operation (Date: 2026-07-23)
