# Epic 7 Retrospective: Cost Tracking & Budget Enforcement

**Date**: 2026-03-11
**Epic**: Cost Tracking & Budget Enforcement (16 planned pts, 16 actual pts)
**Stories**: 4 (all originally planned)
**Status**: All stories done

---

## Summary

Epic 7 delivered the cost tracking and budget enforcement layer — `BudgetState` model extensions with per-story tracking, dual-ceiling budget enforcement (invocation count + cost ceiling), human-readable cost display across CLI status and all summary types, and crash-resilient `run.yaml` budget persistence at every state transition. All 4 stories shipped with zero regressions, clean quality gates, and no scope creep.

---

## Metrics

| Metric | Value |
|--------|-------|
| Stories completed | 4/4 |
| Planned story points | 16 |
| Actual story points | 16 |
| Source files modified | 9 |
| Source LOC added/modified | ~849 (+) / ~41 (-) |
| Test files modified | 10 |
| Test LOC added/modified | ~1,759 (+) / ~13 (-) |
| New tests added (epic 7) | 81 (728 → 809) |
| Test:Source LOC ratio | 2.07:1 |
| Full suite tests (post-epic) | 809 passed |
| Ruff violations | 0 |
| Mypy (--strict) errors | 0 |
| Total project source LOC | 12,418 |
| Total project test LOC | 18,102 |
| Stories requiring code review rework | 2 (7.2, 7.3, 7.4 — review cycles) |

---

## What Went Well

### 1. Clean Scope — No Unplanned Stories
Unlike Epic 6 (which added Story 6.7 mid-epic), Epic 7 shipped exactly what was planned: 4 stories, 16 points. The epic planning correctly traced the full cost tracking lifecycle from model → enforcement → display → integration. The Epic 6 retro recommendation to "trace the full user journey" when planning was clearly applied.

### 2. Decimal-Only Arithmetic Discipline
All cost calculations use Python `Decimal` throughout, from `ModelPricing` config through `calculate_invocation_cost` to `format_cost` display. No float conversions anywhere in the pipeline. This was caught and enforced during code review of Story 7.3, where an initial `float()` conversion in `format_cost` was flagged and removed. The Decimal discipline ensures billing accuracy per NFR12b.

### 3. Best-Effort / Non-Fatal Pattern Continued from Epic 6
The architectural pattern of making ancillary operations non-fatal (established in Epic 6 for push/PR/cleanup) was consistently applied in Epic 7:
- `run.yaml` budget persistence wrapped in try/except (Story 7.4)
- Provenance recording on budget halt wrapped in try/except (Story 7.2)
- Token estimation on SDK error path as fallback (Story 7.4)

This pattern now spans two epics and is a proven project convention.

### 4. Layered Story Progression
The 4 stories built cleanly on each other: 7.1 (model) → 7.2 (enforcement) → 7.3 (display) → 7.4 (integration). Each story had clear boundaries and minimal code overlap. The sequential dependency chain meant each story had a solid foundation to build on.

### 5. Test Pyramid Excellence
81 new tests added across 10 files, with a 2.07:1 test-to-source LOC ratio for this epic. Coverage spans:
- Unit tests for `StoryCost`/`BudgetState` model construction and Decimal arithmetic
- Config tests for `ModelPricing` defaults, YAML overrides, and env var overrides
- Node tests for budget enforcement, provenance recording, and `run.yaml` persistence
- Formatting tests for all 4 cost display functions
- Integration tests for multi-story cost accumulation and `run.yaml` verification
- Serialization round-trip tests for `_serialize_budget` / `_reconstruct_budget_from_dict`

### 6. Existing Test Suite Stability
All 728 pre-existing tests continued to pass throughout the epic. The frozen model pattern (`model_copy(update={...})`) made `BudgetState` extensions backward compatible — existing fixtures with default values required no changes.

---

## What Could Be Improved

### 1. Code Review Cycles on Multiple Stories
Stories 7.2, 7.3, and 7.4 each required at least one review rework cycle with AI-review findings. Common themes:
- **Story 7.2**: Where to raise `AgentBudgetError` (node vs dispatch layer) required architectural analysis. The story spec's "Critical Implementation Warning" correctly predicted this, but the dev still needed course correction.
- **Story 7.3**: `format_cost` initially used `float()` conversion, violating the Decimal-only boundary. Also, halted-run cost display was incomplete (missing per-story table).
- **Story 7.4**: Partial SDK usage fallback on error path wasn't implemented initially, and integration tests bypassed the full graph execution path.

**Root cause**: The stories were well-specified at the AC level, but boundary conditions and integration behaviors required deeper analysis during implementation than the initial dev pass provided.

### 2. Story 7.2 Architecture Decision Was Non-Trivial
The question of where `AgentBudgetError` should be raised (in `budget_check_node` directly vs. in the dispatch layer after graph returns) required careful analysis of LangGraph's error handling semantics. Raising in the node would abort graph execution and skip `finalize_node`. The story spec documented this warning, but the implementation still had to iterate. Future stories modifying graph node behavior should include a mandatory "study the graph error propagation path" task.

### 3. Integration Test Depth vs. Speed Tradeoff
Story 7.4's integration tests initially called `agent_dispatch_node` directly rather than running the full graph pipeline. While this is faster and simpler, it doesn't validate the `budget_check → agent_dispatch → validate → finalize` integration path. The review flagged this and tests were enhanced, but it signals a recurring tension between test execution speed and integration confidence.

### 4. Story 7.1 Status Shows `ready-for-dev` in File
The story file header still shows `Status: ready-for-dev` despite being marked `done` in sprint-status.yaml. This is a minor documentation hygiene issue — story file status headers should be updated when the story is completed.

---

## Previous Retrospective Follow-Through

**Epic 6 Retrospective Recommendations for Epic 7:**

| Recommendation | Status | Evidence |
|---|---|---|
| Review the node modification pattern (best-effort wrapping, structured logging, state updates) before modifying `agent_dispatch_node` and `commit_node` | ✅ Completed | Story 7.4 dev notes explicitly reference the established pattern from `commit_node` line 1099. Best-effort budget persistence follows identical try/except + structured logging pattern. |
| Keep the `make_story_state` fixture kwargs-based with backward-compatible defaults | ✅ Completed | Budget fields added with defaults — all existing fixtures continued to work without modification. |
| Keep the "non-fatal enhancement" pattern for cost display | ✅ Completed | `format_cost`/`format_tokens` handle None/missing values gracefully. Status and summaries degrade cleanly when per_story is empty. |

**Assessment**: All 3 recommendations from Epic 6's retro were followed. The team applied previous learnings effectively.

---

## Risks Identified

| Risk | Severity | Mitigation |
|------|----------|------------|
| Token estimation heuristic (len/4) on SDK errors may overcount or undercount | Low | Flagged with `estimated=True` marker in budget telemetry; only used as fallback when SDK reports no usage data |
| `ModelPricing` defaults hardcoded for Claude Opus 4.5 | Low | Configurable via `config.yaml` and env vars (`ARCWRIGHT_MODEL_PRICING_INPUT_RATE/OUTPUT_RATE`); defaults are correct for current model |
| `per_story` dict grows unbounded for large epics | Low | Dict size is proportional to number of stories (typically <20); no practical memory concern |
| Cost display precision (2 decimal places) may hide fractions for very cheap invocations | Low | Acceptable for human display; raw Decimal values preserved in `run.yaml` for audit |

---

## Architecture Decisions Validated

- **D2 (Retry & Halt Strategy)**: Dual budget model (invocation count + cost ceiling) enforced pre-invocation. Whichever ceiling is hit first triggers halt. V3 retries share the same budget — validated across Stories 7.2 and 7.4.
- **D5 (Write Policy)**: LangGraph state remains authoritative during execution. `run.yaml` writes are crash-recovery checkpoints, not authoritative reads. This distinction was critical in Story 7.4's design.
- **D6 (Error Taxonomy)**: `AgentBudgetError` → exit code 2. Raised from dispatch layer (not graph node) to preserve `finalize_node` execution.
- **NFR10 (Pre-invocation enforcement)**: Budget checked before SDK call, not after. Overshoot limited to at most one invocation.
- **NFR12a (100% capture)**: Every SDK invocation path (success + error) now updates BudgetState, closing the gap identified in Story 7.4.
- **NFR12b (≤10% billing variance)**: Cost uses SDK-reported token counts with exact Decimal arithmetic. Estimation fallback only on SDK error path.
- **FR23/FR24/FR25**: Token tracking, cost visibility, and ceiling enforcement all delivered.

---

## Technical Debt Report

| Item | Severity | Owner | Notes |
|------|----------|-------|-------|
| `engine/nodes.py` growing large (1,400+ lines) | Medium | Architect | Key file modified in Epics 2, 3, 4, 5, 6, and 7. Story 7.4 added ~140 lines. Consider splitting into `nodes_dispatch.py`, `nodes_validate.py`, `nodes_finalize.py` if growth continues. |
| Story file status headers not updated on completion | Low | SM/Dev | Minor hygiene — story `.md` files show `Status: ready-for-dev` after completion. Could be automated in the `dev-story` workflow completion step. |
| Integration tests for budget persistence don't run full graph | Low | QA | Story 7.4 review improved this, but full end-to-end graph execution for multi-story cost accumulation would add confidence. Growth-phase improvement. |

---

## Key Team Contributions

- **Amelia (Dev)**: Implemented all 4 stories with consistent quality. Budget update pattern in `agent_dispatch_node` was particularly well-executed — Decimal arithmetic, per-story accumulation, and the frozen model update pattern were clean from the start.
- **Quinn (QA)**: Test coverage discipline exceptional — 81 new tests with comprehensive boundary condition coverage. The `test_cost_formatting.py` suite (25 tests) is a model for formatting function testing.
- **Bob (SM)**: Story sequencing (model → enforcement → display → integration) was optimal. Each story had clear boundaries and minimal rework.
- **Winston (Architect)**: The best-effort persistence pattern and dispatch-layer error raising guidance prevented architectural missteps.
- **Ed (Project Lead)**: Drove code reviews that caught Decimal/float boundary violations, incomplete halted-run displays, and integration test coverage gaps. Review quality directly improved the final code.

---

## Final Assessment

Epic 7 delivered a complete, production-quality cost tracking and budget enforcement layer in 4 stories with zero scope creep, zero regressions, and clean quality gates. The Decimal-only arithmetic chain from pricing config through calculation to display ensures billing accuracy. The best-effort persistence pattern from Epic 6 was successfully extended to budget tracking. The codebase (12,418 source LOC, 809 tests, 18,102 test LOC) is in excellent shape.

Epic 7 is the final epic in the current roadmap. All 7 epics (34 stories) are now complete. The project has progressed from scaffold through orchestration engine, validation pipeline, decision provenance, halt/resume, SCM integration, and cost tracking — delivering a fully functional autonomous AI agent dispatch system with comprehensive quality controls.
