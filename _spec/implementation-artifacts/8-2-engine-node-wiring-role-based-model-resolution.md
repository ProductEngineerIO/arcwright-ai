# Story 8.2: Engine Node Wiring — Role-Based Model Resolution

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system running the execution pipeline,
I want `agent_dispatch_node` to use the `generate` model role and `validate_node` to use the `review` model role,
so that code generation and code review use their configured models independently.

## Acceptance Criteria (BDD)

1. **Given** `ModelRegistry` is available on `state.config.models` (from Story 8.1) **When** `agent_dispatch_node` resolves its model **Then** it calls `state.config.models.get(ModelRole.GENERATE)` to obtain the `ModelSpec` and passes `spec.version` to `invoke_agent()` and `spec.pricing` to `calculate_invocation_cost()`.

2. **Given** the 6 existing references to `state.config.model.version` and `state.config.model.pricing` in `agent_dispatch_node` **When** this story is implemented **Then** ALL 6 references are updated to use `state.config.models.get(ModelRole.GENERATE)`, with the resolved spec stored in a local variable to avoid repeated registry lookups.

3. **Given** `validate_node` calls `run_validation_pipeline()` **When** the model is resolved **Then** `validate_node` calls `state.config.models.get(ModelRole.REVIEW)` to obtain the `ModelSpec` and passes `spec.version` to `run_validation_pipeline()`.

4. **Given** `validate_node` calls `run_validation_pipeline()` which returns `PipelineResult` with `tokens_used` and `cost` **When** validation cost is tracked **Then** the existing budget update logic in `validate_node` (which uses `pipeline_result.tokens_used` and `pipeline_result.cost`) continues to work unchanged — no pricing resolution is needed in `validate_node` itself because `run_validation_pipeline` already calculates and returns cost internally.

5. **Given** `run_validation_pipeline()` in `validation/pipeline.py` receives the model version as a `model: str` parameter **When** role resolution happens **Then** it happens at the node level (in `validate_node`), NOT inside the pipeline — no signature change to `run_validation_pipeline()`.

6. **Given** provenance entries that log model version in `agent_dispatch_node` **When** a `ProvenanceEntry` is created **Then** it logs both the role name and the resolved model version (e.g., `"model": "claude-sonnet-4-20250514", "role": "generate"`) for traceability.

7. **Given** only `generate` role is configured (no `review` role) **When** `validate_node` calls `state.config.models.get(ModelRole.REVIEW)` **Then** it falls back to the `generate` model via `ModelRegistry.get()` — no new fallback logic needed in nodes.

8. **Given** `cli/dispatch.py` line 412 references `config.model.version` **When** this story is implemented **Then** it is updated to `config.models.get(ModelRole.GENERATE).version`.

9. **Given** `output/run_manager.py` line 193 (`_build_config_snapshot()`) references `config.model.version` **When** this story is implemented **Then** it is updated to use `config.models.get(ModelRole.GENERATE).version` AND a new `review_model_version` key is added showing `config.models.get(ModelRole.REVIEW).version` for completeness. The docstring `Returns:` section is updated to reflect the new keys.

10. **Given** the backward-compat `@property model` on `RunConfig` **When** this story is implemented **Then** the `model` property is REMOVED from `RunConfig` since all consumers are now updated. This eliminates the `DeprecationWarning` pathway.

11. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

12. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

14. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 823 existing tests continue to pass.

15. **Given** unit tests in `tests/test_engine/test_nodes.py` **When** the test suite runs **Then** tests verify:
    (a) `agent_dispatch_node` resolves `GENERATE` role — `invoke_agent` receives `models.get(ModelRole.GENERATE).version`;
    (b) `validate_node` resolves `REVIEW` role — `run_validation_pipeline` receives `models.get(ModelRole.REVIEW).version`;
    (c) Fallback to `generate` when `review` not configured — validate_node still works with generate-only config;
    (d) Cost tracking uses correct per-role pricing — `calculate_invocation_cost` receives generate-role pricing in agent_dispatch;
    (e) Provenance entries include role metadata — `alternatives` and/or `rationale` include role name;
    (f) All existing node tests that reference `state.config.model` are updated to `state.config.models`.

## Boundary Conditions

- **Boundary 1 (No review role configured):** When the YAML config only has a `generate` role and no `review` role, `validate_node` calling `state.config.models.get(ModelRole.REVIEW)` will correctly fall back to the `generate` model via `ModelRegistry.get()`. No special-case code needed in the node.
- **Boundary 2 (Provenance backward compat):** Existing provenance entries have `alternatives=[model_version]`. The new format adds a `"role"` field in the rationale string. Do NOT change the `ProvenanceEntry` dataclass — just include role info in the `rationale` and/or `alternatives` string fields.
- **Boundary 3 (RunConfig.model removal):** After removing the `@property model`, any lingering test code or import that references `config.model` will fail at runtime with `AttributeError`. All `config.model.*` references across the ENTIRE codebase must be updated BEFORE removing the property.
- **Boundary 4 (Import additions):** `ModelRole` must be imported in `engine/nodes.py`, `cli/dispatch.py`, and `output/run_manager.py`. Import from `arcwright_ai.core.config`. This may require adjusting the existing import if `RunConfig` is already imported from there, or adding a new import line.
- **Boundary 5 (Test fixture: make_run_config):** `make_run_config()` in `tests/test_engine/test_nodes.py` returns `RunConfig(api=..., limits=...)` — this will continue to work because `RunConfig.models` has a default factory providing `generate` role with `claude-sonnet-4-20250514`. Tests that need a `review` role must construct a `ModelRegistry` with both roles.
- **Boundary 6 (Validation cost tracking unchanged):** `validate_node` does NOT need to call `calculate_invocation_cost` with review-role pricing directly. The `PipelineResult` from `run_validation_pipeline()` already returns `tokens_used` and `cost` (calculated internally by the pipeline using whatever model was passed). The budget update in `validate_node` (lines 892-898) simply uses `pipeline_result.tokens_used` and `pipeline_result.cost` — this does not change.
- **Boundary 7 (Config snapshot enrichment):** `_build_config_snapshot()` in `run_manager.py` currently returns `model_version`. Adding `review_model_version` is additive and backward-compatible (it's just a new key in the snapshot dict). If only `generate` is configured, `review_model_version` will be the same as `model_version` (due to fallback).
- **Boundary 8 (DeprecationWarning in tests):** After removing the `RunConfig.model` property, any tests that still reference `config.model` will fail. The 5 existing test references (`dispatch_ready_state.config.model.pricing` at lines 920, 946, 2140; `dispatch_ready_state.config.model.version` at line 1061; `run_with_yaml.config.model.pricing` at line 2461) must all be updated BEFORE the property is removed.

## Tasks / Subtasks

- [x] Task 1: Update `engine/nodes.py` — `agent_dispatch_node` references (AC: #1, #2, #6)
  - [x] 1.1: Add `from arcwright_ai.core.config import ModelRole` to the imports in `engine/nodes.py`. Since `RunConfig` is not currently imported there (it's used via `StoryState.config` type), add `ModelRole` import alongside other `core.*` imports.
  - [x] 1.2: At the top of `agent_dispatch_node()`, after the initial logger call, resolve the generate model once: `gen_spec = state.config.models.get(ModelRole.GENERATE)`. Use this local variable for all 6 references.
  - [x] 1.3: Update line 422 logging: `"model": state.config.model.version` → `"model": gen_spec.version, "role": "generate"`.
  - [x] 1.4: Update line 446 invoke_agent: `model=state.config.model.version` → `model=gen_spec.version`.
  - [x] 1.5: Update line 487 SDK error cost: `state.config.model.pricing` → `gen_spec.pricing`.
  - [x] 1.6: Update line 570 success cost: `state.config.model.pricing` → `gen_spec.pricing`.
  - [x] 1.7: Update line 617 provenance: `alternatives=[state.config.model.version]` → `alternatives=[gen_spec.version]` AND update `rationale` to include `"role: generate"`.
  - [x] 1.8: Verify: no other `state.config.model` references remain in the function.

- [x] Task 2: Update `engine/nodes.py` — `validate_node` references (AC: #3, #4, #5)
  - [x] 2.1: At the top of `validate_node()`, resolve the review model: `review_spec = state.config.models.get(ModelRole.REVIEW)`.
  - [x] 2.2: Update line 861: `model=state.config.model.version` → `model=review_spec.version`.
  - [x] 2.3: Verify: budget update in validate_node (lines 892-898) uses `pipeline_result.tokens_used` and `pipeline_result.cost` — this is UNCHANGED (validation pipeline returns its own cost).
  - [x] 2.4: Update validation provenance entry to include role info: in the `validation_provenance_entry` rationale, add model role context (e.g., append `f", model: {review_spec.version} (role: review)"` to the rationale string).

- [x] Task 3: Update `cli/dispatch.py` (AC: #8)
  - [x] 3.1: Add `from arcwright_ai.core.config import ModelRole` import.
  - [x] 3.2: Update line 412: `config.model.version` → `config.models.get(ModelRole.GENERATE).version`.

- [x] Task 4: Update `output/run_manager.py` (AC: #9)
  - [x] 4.1: Add `from arcwright_ai.core.config import ModelRole` import.
  - [x] 4.2: Update line 193: `"model_version": config.model.version` → `"model_version": config.models.get(ModelRole.GENERATE).version`.
  - [x] 4.3: Add new key: `"review_model_version": config.models.get(ModelRole.REVIEW).version`.
  - [x] 4.4: Update the `_build_config_snapshot` docstring `Returns:` section to include `review_model_version`.

- [x] Task 5: Remove `RunConfig.model` backward-compat property (AC: #10)
  - [x] 5.1: Delete the entire `@property def model(self) -> ModelSpec:` block from `RunConfig` in `core/config.py` (lines 273-289). This includes the docstring, the `warnings.warn()` call, and the `return` statement.
  - [x] 5.2: Verify: no other source code (outside tests) references `config.model` or `.model.version` or `.model.pricing`. Grep the entire `src/` directory.
  - [x] 5.3: If `warnings` import is only used by the `model` property and the migration logic in `load_config()`, keep the import (migration still uses it). It is still used in `load_config()` for backward-compat migration warnings, so the import stays.

- [x] Task 6: Update all existing tests that reference `config.model` (AC: #14, #15f)
  - [x] 6.1: In `tests/test_engine/test_nodes.py` line 920: `dispatch_ready_state.config.model.pricing` → `dispatch_ready_state.config.models.get(ModelRole.GENERATE).pricing`. Import `ModelRole` at top of test file.
  - [x] 6.2: In `tests/test_engine/test_nodes.py` line 946: same pattern.
  - [x] 6.3: In `tests/test_engine/test_nodes.py` line 1061: `dispatch_ready_state.config.model.version` → `dispatch_ready_state.config.models.get(ModelRole.GENERATE).version`.
  - [x] 6.4: In `tests/test_engine/test_nodes.py` line 2140: `dispatch_ready_state.config.model.pricing` → same pattern.
  - [x] 6.5: In `tests/test_engine/test_nodes.py` line 2461: `run_with_yaml.config.model.pricing` → `run_with_yaml.config.models.get(ModelRole.GENERATE).pricing`.
  - [x] 6.6: Grep entire `tests/` for any other `config.model.` or `.model.version` or `.model.pricing` references. Update all.

- [x] Task 7: Add new tests for role-based resolution (AC: #15a-e)
  - [x] 7.1: `test_agent_dispatch_node_resolves_generate_role` — Mock `invoke_agent` to capture the `model=` keyword arg; assert it equals `state.config.models.get(ModelRole.GENERATE).version`.
  - [x] 7.2: `test_validate_node_resolves_review_role` — Mock `run_validation_pipeline` to capture the `model=` keyword arg; assert it equals `state.config.models.get(ModelRole.REVIEW).version`.
  - [x] 7.3: `test_validate_node_falls_back_to_generate_when_no_review` — Create a `RunConfig` with only `generate` role (default `make_run_config()` already does this), run `validate_node`, verify `run_validation_pipeline` receives the generate model version.
  - [x] 7.4: `test_agent_dispatch_cost_uses_generate_role_pricing` — Verify `calculate_invocation_cost` receives `models.get(ModelRole.GENERATE).pricing` (already partially covered by existing tests but make explicit).
  - [x] 7.5: `test_agent_dispatch_provenance_includes_role` — Call `agent_dispatch_node`, capture the `ProvenanceEntry` passed to `append_entry`, verify `"generate"` or `"role"` appears in `rationale` or `alternatives`.
  - [x] 7.6: `test_validate_node_with_dual_model_config` — Create a `RunConfig` with distinct `generate` and `review` models (e.g., `generate: claude-sonnet-4-20250514`, `review: claude-opus-4-5`), run validate_node, verify `run_validation_pipeline` receives the review model version (not the generate one).

- [x] Task 8: Verify all quality gates (AC: #11, #12, #13, #14)
  - [x] 8.1: Run `ruff check .` — zero violations.
  - [x] 8.2: Run `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 8.3: Verify all docstrings are Google-style.
  - [x] 8.4: Run full test suite — 829 tests pass (823 existing + 6 new tests added in Task 7).

## Dev Notes

### Critical Analysis: What Exists vs What This Story Changes

**Existing code (DO NOT recreate — already implemented in Story 8.1):**
- `ModelRole(StrEnum)` in `core/config.py` line 92 — `GENERATE = "generate"` and `REVIEW = "review"`
- `ModelSpec(ArcwrightModel)` in `core/config.py` line 102 — `version: str` + `pricing: ModelPricing`
- `ModelRegistry(ArcwrightModel)` in `core/config.py` line 118 — `roles: dict[str, ModelSpec]` + `get()` method with generate fallback
- `RunConfig.models: ModelRegistry` in `core/config.py` line 265 — default factory provides `generate` role with `claude-sonnet-4-20250514`
- Migration logic in `load_config()` — `model:` → `models.generate` backward compat
- `make_run_config()` test helper in `tests/test_engine/test_nodes.py` line 59 — already returns `RunConfig` with default `models` (generate role only)

**Backward-compat property to REMOVE (this story's responsibility):**
- `RunConfig.model` `@property` in `core/config.py` lines 273-289 — returns `models.get(ModelRole.GENERATE)` with `DeprecationWarning`. Story 8.1 explicitly states: "Property will be removed in Story 8.2."

**Code to UPDATE (all 8 references using the deprecated `.model` property):**

| # | File | Line | Current Reference | New Reference |
|---|------|------|-------------------|---------------|
| 1 | `engine/nodes.py` | 422 | `state.config.model.version` | `gen_spec.version` (+ add `"role": "generate"` to log) |
| 2 | `engine/nodes.py` | 446 | `state.config.model.version` | `gen_spec.version` |
| 3 | `engine/nodes.py` | 487 | `state.config.model.pricing` | `gen_spec.pricing` |
| 4 | `engine/nodes.py` | 570 | `state.config.model.pricing` | `gen_spec.pricing` |
| 5 | `engine/nodes.py` | 617 | `state.config.model.version` | `gen_spec.version` (+ role in rationale) |
| 6 | `engine/nodes.py` | 861 | `state.config.model.version` | `review_spec.version` |
| 7 | `cli/dispatch.py` | 412 | `config.model.version` | `config.models.get(ModelRole.GENERATE).version` |
| 8 | `output/run_manager.py` | 193 | `config.model.version` | `config.models.get(ModelRole.GENERATE).version` |

**Test references to UPDATE (5 references using deprecated `.model`):**

| # | File | Line | Current Reference |
|---|------|------|-------------------|
| 1 | `test_engine/test_nodes.py` | 920 | `dispatch_ready_state.config.model.pricing` |
| 2 | `test_engine/test_nodes.py` | 946 | `dispatch_ready_state.config.model.pricing` |
| 3 | `test_engine/test_nodes.py` | 1061 | `dispatch_ready_state.config.model.version` |
| 4 | `test_engine/test_nodes.py` | 2140 | `dispatch_ready_state.config.model.pricing` |
| 5 | `test_engine/test_nodes.py` | 2461 | `run_with_yaml.config.model.pricing` |

### Exact Implementation Pattern

**In `agent_dispatch_node` (engine/nodes.py):**
```python
# At the top of the function, after initial logger call:
gen_spec = state.config.models.get(ModelRole.GENERATE)

# Then use gen_spec.version and gen_spec.pricing everywhere
```

**In `validate_node` (engine/nodes.py):**
```python
# At the top of the function, after initial checks:
review_spec = state.config.models.get(ModelRole.REVIEW)

# Then pass review_spec.version to run_validation_pipeline
```

**Import to add in engine/nodes.py:**
```python
from arcwright_ai.core.config import ModelRole
```

### Architecture Compliance: Decision 9

Source: [architecture.md, "Decision 9: Role-Based Model Registry"]

The architecture specifies:
- `agent_dispatch_node` → `invoke_agent()` uses `generate` role — **This story implements it**
- `validate_node` → V3 reflexion → `invoke_agent()` uses `review` role — **This story implements it**
- When only `generate` is configured, `ModelRegistry.get(ModelRole.REVIEW)` falls back to `generate` — **Already implemented in Story 8.1**
- Pipeline receives model version string as before (no signature change) — **No change to `run_validation_pipeline()` signature**

### validation/pipeline.py — No Changes

`run_validation_pipeline()` signature (line 79):
```python
async def run_validation_pipeline(
    agent_output: str,
    story_path: Path,
    project_root: Path,
    *,
    model: str,  # receives version string, NOT ModelSpec
    cwd: Path,
    sandbox: PathValidator,
    attempt_number: int = 1,
) -> PipelineResult:
```
The `model` parameter receives a `str` (model version). Role resolution happens in `validate_node`, not in the pipeline. The pipeline already calculates and returns `tokens_used` and `cost` in `PipelineResult`. **No changes to this file.**

### Previous Story Learnings (from Story 8.1)

- `ModelRole`, `ModelSpec`, `ModelRegistry` are already fully implemented and tested in `core/config.py`
- `RunConfig.model` backward-compat property exists at lines 273-289 — depends on `warnings` import which is also used elsewhere
- `make_run_config()` test helper creates `RunConfig` with default `models` (generate-only) — works without modifications
- 823 tests currently pass. Story 8.1 added 14 new tests. Quality gates: `ruff check .` clean, `mypy --strict src/` clean
- `model_copy(update={...})` is the mutation pattern for frozen Pydantic models
- All engine node tests mock `update_run_status` as `AsyncMock` via `monkeypatch` autouse fixture
- The `ModelConfig` class is RETAINED in `core/config.py` (needed for backward-compat migration in `load_config()`) — do NOT remove it

### Import Context for Modified Files

**`engine/nodes.py` current imports (relevant):**
```python
from arcwright_ai.core.constants import (AGENT_OUTPUT_FILENAME, ...)
from arcwright_ai.core.exceptions import ContextError, ScmError, ValidationError
from arcwright_ai.core.io import write_text_async
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, ProvenanceEntry, StoryCost, calculate_invocation_cost
```
Add: `from arcwright_ai.core.config import ModelRole`

**`cli/dispatch.py` current imports (check):** Need to verify if `RunConfig` is imported from `core.config`. If so, add `ModelRole` to the same import.

**`output/run_manager.py` current imports:** `RunConfig` is used as a type annotation for `_build_config_snapshot(config: RunConfig)`. Add `ModelRole` import.

**`test_engine/test_nodes.py` current imports:** Will need `from arcwright_ai.core.config import ModelRole` at the top of the file alongside existing imports.

### Test Strategy: Creating Dual-Model Config in Tests

For tests that need both `generate` and `review` roles:
```python
from arcwright_ai.core.config import ModelRegistry, ModelRole, ModelSpec

dual_model_config = RunConfig(
    api=ApiConfig(claude_api_key="test-key"),
    models=ModelRegistry(roles={
        "generate": ModelSpec(version="claude-sonnet-4-20250514"),
        "review": ModelSpec(version="claude-opus-4-5"),
    }),
)
```

For tests that only need generate (default behavior — existing `make_run_config()` already provides this):
```python
config = make_run_config()  # generate-only, review falls back to generate
```

### Project Structure Notes

- All source under `arcwright-ai/src/arcwright_ai/`
- All tests under `arcwright-ai/tests/`
- `core/config.py` — home of `ModelRole`, `ModelSpec`, `ModelRegistry`, `RunConfig`
- `engine/nodes.py` — 1604 lines, primary file for this story
- `validation/pipeline.py` — 222 lines, NO changes needed
- `cli/dispatch.py` — 861 lines, single reference to update
- `output/run_manager.py` — 558 lines, single reference to update + enrichment

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision 9: Role-Based Model Registry]
- [Source: _spec/planning-artifacts/epics.md#Epic 8, Story 8.2]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — 1604 lines, 6 model refs at lines 422, 446, 487, 570, 617, 861]
- [Source: arcwright-ai/src/arcwright_ai/cli/dispatch.py — 861 lines, 1 model ref at line 412]
- [Source: arcwright-ai/src/arcwright_ai/output/run_manager.py — 558 lines, 1 model ref at line 193]
- [Source: arcwright-ai/src/arcwright_ai/core/config.py — 788 lines, RunConfig.model property at lines 273-289]
- [Source: arcwright-ai/src/arcwright_ai/validation/pipeline.py — 222 lines, run_validation_pipeline signature at line 79]
- [Source: arcwright-ai/tests/test_engine/test_nodes.py — 2671 lines, 5 model refs at lines 920, 946, 1061, 2140, 2461]
- [Source: _spec/implementation-artifacts/8-1-modelrole-enum-modelspec-modelregistry-and-config-migration.md — previous story context]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Removed `RunConfig.model` backward-compat `@property` from `core/config.py` — all 8 deprecated `config.model.*` references in source code updated before removal.
- `engine/nodes.py` — `agent_dispatch_node`: resolved `gen_spec = state.config.models.get(ModelRole.GENERATE)` once at function entry; used for all 6 model references (logging, invoke_agent call, both cost calculations, and provenance entry). Provenance `alternatives` now contains `[gen_spec.version]` and `rationale` includes `role: generate`.
- `engine/nodes.py` — `validate_node`: resolved `review_spec = state.config.models.get(ModelRole.REVIEW)` before the pipeline call; used for `run_validation_pipeline(model=review_spec.version)`. Provenance `alternatives` includes `[review_spec.version]` and rationale appended with `model: {version} (role: review)`. Budget update (lines 892–898) unchanged — uses `pipeline_result.tokens_used` / `pipeline_result.cost` as before.
- `cli/dispatch.py` line 412: CLI echo updated to `config.models.get(ModelRole.GENERATE).version`.
- `output/run_manager.py` `_build_config_snapshot()`: added `review_model_version` key alongside `model_version`; docstring updated to reflect new key.
- 5 existing test references updated to use `models.get(ModelRole.GENERATE).{pricing,version}` pattern; `ModelRole` added to test imports.
- 6 new tests added: role resolution for agent_dispatch and validate_node, generate-only fallback, dual-model config verification, cost pricing verification, and provenance role metadata.
- Ruff auto-fixed 2 import ordering issues (in `run_manager.py` and `nodes.py`). Mypy --strict: 0 errors. Full suite: **829 tests passing** (823 existing + 6 new).
- Code review follow-up fixes applied: File List now reflects all changed files with workspace-relative paths (including implementation artifact and sprint status sync), and story status advanced from `review` to `done` after verification.

### File List

- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/src/arcwright_ai/cli/dispatch.py`
- `arcwright-ai/src/arcwright_ai/core/config.py`
- `arcwright-ai/src/arcwright_ai/output/run_manager.py`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `_spec/implementation-artifacts/8-2-engine-node-wiring-role-based-model-resolution.md`
- `_spec/implementation-artifacts/sprint-status.yaml`

### Change Log

- **2026-03-12** — Story 8.2 implementation: wired role-based model resolution into engine nodes. `agent_dispatch_node` uses `ModelRole.GENERATE`, `validate_node` uses `ModelRole.REVIEW`. Removed deprecated `RunConfig.model` property. Added `review_model_version` to config snapshot. All 823 existing tests pass + 6 new role-based tests (829 total).
- **2026-03-12** — Code review remediation: corrected File List to include all changed files using workspace-relative paths, updated story status to `done`, and synced sprint tracking for story 8.2.
