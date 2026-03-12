# Story 8.1: ModelRole Enum, ModelSpec, ModelRegistry & Config Migration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer configuring Arcwright AI,
I want to assign different models to different pipeline roles (generation vs. review),
so that I can optimize cost and quality by using a fast model for code generation and a thorough model for code review.

## Acceptance Criteria (BDD)

1. **Given** `core/types.py` and `core/config.py` as the foundation for model configuration **When** the role-based model registry is implemented **Then** `ModelRole` is defined as a `StrEnum` in `core/config.py` with values `GENERATE = "generate"` and `REVIEW = "review"`.

2. **Given** the `ModelRole` enum exists **When** `ModelSpec` is defined **Then** it is a frozen Pydantic model (in `core/config.py`) with fields: `version` (str) and `pricing` (ModelPricing, default factory).

3. **Given** `ModelSpec` exists **When** `ModelRegistry` is defined **Then** it is a frozen Pydantic model with a `roles: dict[str, ModelSpec]` field and a `get(role: ModelRole | str) -> ModelSpec` method that returns the spec for the requested role, falling back to the `generate` role if the requested role is not configured, raising `ConfigError` if no `generate` fallback exists.

4. **Given** `ModelRegistry` exists **When** `RunConfig` is updated **Then** `RunConfig.model` (singular, `ModelConfig`) is replaced by `RunConfig.models` (`ModelRegistry`).

5. **Given** both old and new YAML formats may exist **When** config is loaded **Then** backward-compatible migration is implemented:
   - If `models` key exists → use new registry format
   - If `model` (singular) key exists → auto-migrate to `models.generate` with a `DeprecationWarning`
   - If neither → use defaults (`generate` role with `claude-sonnet-4-20250514`)

6. **Given** the new config format **When** YAML is written **Then** it supports both minimal (just `generate`) and full (`generate` + `review`) configurations per the architecture Decision 9 specification.

7. **Given** the new `ARCWRIGHT_AI_MODEL_{ROLE}_VERSION` and `ARCWRIGHT_AI_MODEL_{ROLE}_PRICING_{FIELD}` env var pattern **When** environment overrides are applied **Then** role-specific env vars are correctly merged into the corresponding registry entry.

8. **Given** the existing `ARCWRIGHT_MODEL_VERSION` env var **When** it is set **Then** it is treated as an alias for `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` with a `DeprecationWarning`.

9. **Given** the new `models` config structure **When** unknown-key detection runs **Then** `_KNOWN_SECTION_FIELDS` and `_KNOWN_SUBSECTION_FIELDS` are updated for the `models` key and its nested structure.

10. **Given** `core/constants.py` **When** new env var constants are added **Then** `__all__` is updated with new `ENV_MODEL_GENERATE_VERSION`, `ENV_MODEL_REVIEW_VERSION`, etc.; old `ENV_MODEL_*` constants are retained as deprecated aliases.

11. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

12. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

14. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 809 existing tests continue to pass.

15. **Given** new and updated tests in `tests/test_core/test_config.py` **When** the test suite runs **Then** tests cover:
    (a) New `models` format loads correctly with both `generate` and `review` roles;
    (b) Old `model` singular key auto-migrates to `models.generate` with deprecation warning;
    (c) Missing both `model` and `models` keys uses defaults (`generate` with `claude-sonnet-4-20250514`);
    (d) Env var overrides with `ARCWRIGHT_AI_MODEL_{ROLE}_*` pattern work for both roles;
    (e) Legacy `ARCWRIGHT_MODEL_VERSION` env var maps to generate role with deprecation warning;
    (f) Fallback behavior when only `generate` is configured and `review` is requested;
    (g) `ConfigError` when `generate` role is missing and a role is requested;
    (h) All existing config tests updated to use the new `models` field.

## Boundary Conditions

- **Boundary 1 (Backward compatibility):** The old `model` (singular) YAML key must continue working during a transition period. The `DeprecationWarning` should include a migration hint: "Replace 'model:' with 'models: { generate: ... }' in your config". Both global and project tier configs may use old or new format independently — the deep merge must handle mixed formats.
- **Boundary 2 (Empty roles dict):** `ModelRegistry(roles={})` should raise a validation error — at minimum, `generate` must be present. Validate this in `ModelRegistry.__init__` or as a Pydantic `model_validator`.
- **Boundary 3 (Unknown role names):** `ModelRegistry.get("unknown_role")` should fall back to `generate`, not raise. Only raise `ConfigError` if even `generate` is missing.
- **Boundary 4 (Env var precedence):** Role-specific env vars (`ARCWRIGHT_AI_MODEL_GENERATE_VERSION`) must override YAML values. The legacy `ARCWRIGHT_MODEL_VERSION` must have lower precedence than `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` — if both are set, the new name wins.
- **Boundary 5 (Config validation ordering):** The old→new migration in `load_config()` must happen *before* `_apply_env_overrides()` so that env vars can target the migrated `models.generate.*` structure.
- **Boundary 6 (ModelPricing stays in config.py):** `ModelPricing` already lives in `core/config.py` — no move needed. `core/types.py` has the `TYPE_CHECKING` import for `ModelPricing` in `calculate_invocation_cost()` — this pattern continues to work unchanged.
- **Boundary 7 (Default model change):** The architecture specifies default `generate` model as `claude-sonnet-4-20250514` (previously `claude-opus-4-5`). The migration must NOT change the default for users who had no explicit model config — they get the new default. BUT: the old `ModelConfig` default was `claude-opus-4-5`, so users migrating from `model:` key with no explicit version should keep getting their old configured value, not be silently downgraded.

## Tasks / Subtasks

- [x] Task 1: Add `ModelRole` StrEnum and `ModelSpec` model to `core/config.py` (AC: #1, #2)
  - [x] 1.1: Define `ModelRole(StrEnum)` with `GENERATE = "generate"` and `REVIEW = "review"` in `core/config.py`, placed after `ModelPricing` and before `ModelConfig`.
  - [x] 1.2: Define `ModelSpec(ArcwrightModel)` with `model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)`, field `version: str = "claude-sonnet-4-20250514"`, and field `pricing: ModelPricing = Field(default_factory=ModelPricing)`. Place after `ModelRole`.
  - [x] 1.3: Add `ModelRole`, `ModelSpec`, `ModelRegistry` to the module `__all__` list.

- [x] Task 2: Add `ModelRegistry` model with `get()` fallback logic (AC: #3)
  - [x] 2.1: Define `ModelRegistry(ArcwrightModel)` with `model_config = ConfigDict(frozen=True, extra="ignore", str_strip_whitespace=True)` and field `roles: dict[str, ModelSpec]`.
  - [x] 2.2: Implement `get(self, role: ModelRole | str) -> ModelSpec` method: resolve `key = role.value if isinstance(role, ModelRole) else role`; if `key in self.roles` return it; if `ModelRole.GENERATE.value in self.roles` return generate fallback; otherwise raise `ConfigError(f"No model configured for role '{key}' and no 'generate' fallback")`.
  - [x] 2.3: Add a Pydantic `@model_validator(mode="after")` to ensure `roles` is non-empty and contains at least a `generate` entry. Raise `ValueError("ModelRegistry requires at least a 'generate' role")` if violated.

- [x] Task 3: Update `RunConfig` to use `ModelRegistry` (AC: #4)
  - [x] 3.1: Change `RunConfig.model: ModelConfig = Field(default_factory=ModelConfig)` to `RunConfig.models: ModelRegistry = Field(default_factory=lambda: ModelRegistry(roles={"generate": ModelSpec(version="claude-sonnet-4-20250514")}))`.
  - [x] 3.2: Keep `ModelConfig` class definition in the file (it's needed for backward-compat migration logic and for existing code that may reference the type) but it is no longer a field on `RunConfig`.

- [x] Task 4: Implement backward-compatible config migration in `load_config()` (AC: #5)
  - [x] 4.1: After the deep merge and before `_apply_env_overrides()`, add a migration block: if `"models"` key is present in `merged` → transform from flat `{generate: {version: ..., pricing: ...}, review: {...}}` to `{roles: {generate: {...}, review: {...}}}` (wrapping in `roles` key for Pydantic).
  - [x] 4.2: If `"model"` (singular) key is present and `"models"` is NOT → emit `warnings.warn("Config key 'model' is deprecated. Replace with 'models: { generate: ... }'", DeprecationWarning, stacklevel=2)` and transform `merged["model"]` into `merged["models"] = {"roles": {"generate": merged.pop("model")}}`.
  - [x] 4.3: If neither `"model"` nor `"models"` is present → no migration needed; Pydantic defaults handle it.
  - [x] 4.4: Remove the old `"model"` key from `merged` after migration to prevent Pydantic unknown-field errors (since `RunConfig` no longer has `model` field).

- [x] Task 5: Update `_apply_env_overrides()` for role-based env vars (AC: #7, #8)
  - [x] 5.1: Add new env var application logic: scan for `ARCWRIGHT_AI_MODEL_{ROLE}_VERSION` and `ARCWRIGHT_AI_MODEL_{ROLE}_PRICING_{FIELD}` patterns for each known role (`generate`, `review`). Apply to `merged["models"]["roles"][role][field]`.
  - [x] 5.2: Handle the legacy `ARCWRIGHT_MODEL_VERSION` → if set and `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` is NOT set, map it to `merged["models"]["roles"]["generate"]["version"]` with `DeprecationWarning`. If both are set, the new `ARCWRIGHT_AI_MODEL_GENERATE_VERSION` wins (already applied by role-specific logic).
  - [x] 5.3: Remove old `_env_set_str(merged, "model", "version", ENV_MODEL_VERSION)` and old `_env_set_decimal(merged, "model", "pricing", ...)` calls since `model` field no longer exists on `RunConfig`.
  - [x] 5.4: Ensure `_apply_env_overrides()` creates the `models.roles` nested structure if it doesn't exist yet (use `merged.setdefault("models", {}).setdefault("roles", {}).setdefault(role, {})`).

- [x] Task 6: Update `_KNOWN_SECTION_FIELDS` and `_KNOWN_SUBSECTION_FIELDS` (AC: #9)
  - [x] 6.1: Replace `"model": frozenset(ModelConfig.model_fields.keys())` with `"models": frozenset({"generate", "review"})` in `_KNOWN_SECTION_FIELDS` (treating role names as "known fields" of the `models` section).
  - [x] 6.2: Replace `"model": {"pricing": frozenset(ModelPricing.model_fields.keys())}` with `"models": {"generate": frozenset(ModelSpec.model_fields.keys()), "review": frozenset(ModelSpec.model_fields.keys())}` in `_KNOWN_SUBSECTION_FIELDS`.
  - [x] 6.3: Update `_warn_unknown_keys_recursive()` to handle the new nesting depth: `models.{role}.{field}` and `models.{role}.pricing.{field}`.

- [x] Task 7: Update `core/constants.py` with new env var constants (AC: #10)
  - [x] 7.1: Add new constants: `ENV_MODEL_GENERATE_VERSION = "ARCWRIGHT_AI_MODEL_GENERATE_VERSION"`, `ENV_MODEL_REVIEW_VERSION = "ARCWRIGHT_AI_MODEL_REVIEW_VERSION"`, `ENV_MODEL_GENERATE_PRICING_INPUT_RATE = "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE"`, `ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE = "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE"`, `ENV_MODEL_REVIEW_PRICING_INPUT_RATE = "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE"`, `ENV_MODEL_REVIEW_PRICING_OUTPUT_RATE = "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_OUTPUT_RATE"`.
  - [x] 7.2: Retain old constants (`ENV_MODEL_VERSION`, `ENV_MODEL_PRICING_INPUT_RATE`, `ENV_MODEL_PRICING_OUTPUT_RATE`) with comments marking them as deprecated aliases.
  - [x] 7.3: Update `__all__` to include new constant names.

- [x] Task 8: Update all existing tests that construct `RunConfig` (AC: #14, #15h)
  - [x] 8.1: In `tests/test_core/test_config.py` — updated all `cfg.model.*` assertions to `cfg.models.get(ModelRole.GENERATE).*`. Updated 13 references across 8 test functions.
  - [x] 8.2: In `tests/test_engine/test_nodes.py` — `make_run_config()` continues to work with new defaults since `RunConfig.models` defaults to a `ModelRegistry` with `generate` role. Verified all 5 references to `state.config.model.*` work via the backward-compat property.
  - [x] 8.3: Added backward-compat `@property model` on `RunConfig` that returns `self.models.get(ModelRole.GENERATE)` with `DeprecationWarning`. Property will be removed in Story 8.2.

- [x] Task 9: Create new unit tests for role-based model config (AC: #15a-g)
  - [x] 9.1: `test_models_new_format_loads_both_roles` — YAML with `models: { generate: {version: ...}, review: {version: ...} }` loads correctly, both roles accessible via `cfg.models.get(ModelRole.GENERATE)` and `cfg.models.get(ModelRole.REVIEW)`.
  - [x] 9.2: `test_model_singular_key_migrates_with_deprecation_warning` — YAML with `model: {version: ..., pricing: {...}}` triggers `DeprecationWarning` and migrates to `cfg.models.roles["generate"]`.
  - [x] 9.3: `test_no_model_or_models_uses_defaults` — empty config (except `api`) uses default `generate` role with `claude-sonnet-4-20250514`.
  - [x] 9.4: `test_env_var_override_generate_version` — set `ARCWRIGHT_AI_MODEL_GENERATE_VERSION=test-model`, verify `cfg.models.get(ModelRole.GENERATE).version == "test-model"`.
  - [x] 9.5: `test_env_var_override_review_version` — set `ARCWRIGHT_AI_MODEL_REVIEW_VERSION=review-model`, verify review role gets override.
  - [x] 9.6: `test_env_var_override_role_pricing` — set `ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE=1.50`, verify pricing override.
  - [x] 9.7: `test_legacy_env_var_maps_to_generate_with_deprecation` — set `ARCWRIGHT_MODEL_VERSION=legacy-model`, verify generates deprecation warning and maps to generate role.
  - [x] 9.8: `test_new_env_var_takes_precedence_over_legacy` — set both `ARCWRIGHT_MODEL_VERSION=old` and `ARCWRIGHT_AI_MODEL_GENERATE_VERSION=new`, verify `cfg.models.get(ModelRole.GENERATE).version == "new"`.
  - [x] 9.9: `test_get_review_falls_back_to_generate_when_not_configured` — only `generate` configured, `get(ModelRole.REVIEW)` returns generate spec.
  - [x] 9.10: `test_get_raises_config_error_when_generate_missing` — `model_construct` with custom-only registry, `get("missing")` raises `ConfigError`.
  - [x] 9.11: `test_model_registry_empty_roles_raises` — `ModelRegistry(roles={})` raises validation error.
  - [x] 9.12: `test_known_keys_warns_on_unknown_models_subkey` — verify unknown-key detection works for `models.unknown_role`.

- [x] Task 10: Verify all quality gates (AC: #11, #12, #13, #14)
  - [x] 10.1: Run `ruff check .` — zero violations. ✅
  - [x] 10.2: Run `.venv/bin/python -m mypy --strict src/` — zero errors. ✅
  - [x] 10.3: Verify all docstrings are Google-style. ✅ All new classes have Google-style docstrings with Args/Returns/Raises sections.
  - [x] 10.4: Run full test suite — 821 tests pass (809 original + 12 new). ✅

## Dev Notes

### Critical Analysis: What Exists vs What This Story Changes

**Existing code (DO NOT recreate):**
- `ModelPricing` in `core/config.py` (line 75) — stays exactly as-is; both `ModelConfig` and `ModelSpec` reference it
- `ModelConfig` in `core/config.py` (line 88) — keep the class definition (needed for migration path), but remove from `RunConfig` field
- `calculate_invocation_cost()` in `core/types.py` (line 190) — unchanged, uses `ModelPricing` via `TYPE_CHECKING` import
- `_deep_merge()`, `_warn_unknown_keys()`, `_translate_pydantic_error()` — helper functions unchanged
- `load_yaml()` in `core/io.py` — YAML loader unchanged

**New code to create:**
- `ModelRole(StrEnum)` — new enum in `core/config.py`
- `ModelSpec(ArcwrightModel)` — new model in `core/config.py` (structurally identical to `ModelConfig` but name aligned with architecture Decision 9)
- `ModelRegistry(ArcwrightModel)` — new model in `core/config.py` with `roles` dict and `get()` method
- Migration logic in `load_config()` — old→new format conversion
- New env var override logic in `_apply_env_overrides()`

### Exact Locations to Modify

**`src/arcwright_ai/core/config.py`** — Primary file:

1. **New classes** (after `ModelPricing`, before `ModelConfig`):
   - `ModelRole(StrEnum)` — ~2 values
   - `ModelSpec` — fields: `version: str`, `pricing: ModelPricing = Field(default_factory=ModelPricing)`
   - `ModelRegistry` — fields: `roles: dict[str, ModelSpec]`; method: `get(role) -> ModelSpec`

2. **`RunConfig`** (line 170):
   - Change `model: ModelConfig = Field(default_factory=ModelConfig)` → `models: ModelRegistry = Field(default_factory=lambda: ModelRegistry(roles={"generate": ModelSpec(version="claude-sonnet-4-20250514")}))`
   - Add backward-compat `@property` `model` that returns `self.models.get(ModelRole.GENERATE)` with deprecation warning

3. **`_KNOWN_SECTION_FIELDS`** (line 193):
   - Replace `"model"` entry with `"models"` entry

4. **`_KNOWN_SUBSECTION_FIELDS`** (line 199):
   - Replace `"model"` entry with `"models"` entry

5. **`_apply_env_overrides()`** (line 438):
   - Replace old `model.*` env var application with new `models.roles.{role}.*` pattern
   - Add legacy `ARCWRIGHT_MODEL_VERSION` → generate fallback

6. **`load_config()`** (line 494):
   - Add migration block between deep merge and env override steps

7. **`__all__`** (line 37):
   - Add `ModelRole`, `ModelSpec`, `ModelRegistry`

**`src/arcwright_ai/core/constants.py`** — Secondary file:

1. Add new env var constants for each role+field combination
2. Mark old `ENV_MODEL_VERSION`, `ENV_MODEL_PRICING_*` as deprecated
3. Update `__all__`

**`tests/test_core/test_config.py`** — Test updates:

- 13 references to `cfg.model.*` across ~8 test functions need updating to `cfg.models.get(ModelRole.GENERATE).*` or `cfg.models.roles["generate"].*`
- Existing tests that write `model:` in YAML fixtures should continue to work via the migration path — OR be updated to use `models:` format. **Recommendation:** Update fixtures to new format so tests validate the intended path.

**`tests/test_engine/test_nodes.py`** — Test updates:

- `make_run_config()` (line 59): Returns `RunConfig(api=..., limits=...)` — will work with new defaults since `models` has a default factory
- 5 references to `state.config.model.pricing` / `state.config.model.version` — will work via the backward-compat `model` property on `RunConfig` added in Task 8.3

### Architecture Compliance: Decision 9

Source: [architecture.md, "Decision 9: Role-Based Model Registry"](architecture.md)

- `ModelRole` as `StrEnum` — **MATCH**
- `ModelSpec` with `version` + `pricing` — **MATCH**
- `ModelRegistry` with `roles: dict[str, ModelSpec]` and `get()` fallback — **MATCH**
- `RunConfig.models: ModelRegistry` replacing `model: ModelConfig` — **MATCH**
- Default generate model `claude-sonnet-4-20250514` — **MATCH**
- Env var pattern `ARCWRIGHT_AI_MODEL_{ROLE}_*` — **MATCH**
- Backward compat: `model` → `models.generate` with deprecation — **MATCH**

### Import Note: StrEnum

Python 3.11+ has `StrEnum` in stdlib `enum`. If the project targets Python 3.10+, use `from enum import StrEnum`. Check `pyproject.toml` for the `requires-python` value. If `>= 3.11`, stdlib `StrEnum` is fine. If `>= 3.10`, either use `from enum import StrEnum` (only available 3.11+) or add a fallback: `try: from enum import StrEnum; except ImportError: ...`. The architecture Decision 9 uses `StrEnum` without qualification — verify compatibility.

### Node References (Story 8.2 Scope, NOT This Story)

There are exactly 6 references to `state.config.model.*` in `engine/nodes.py` (lines 422, 446, 487, 570, 617, 861) and 2 references in `cli/dispatch.py` (line 412) and `output/run_manager.py` (line 193). These are updated in Story 8.2, NOT this story. The backward-compat `model` property on `RunConfig` ensures they continue working during the transition.

### Current Environment Variable Constants

Old constants to deprecate (keep but mark deprecated):
- `ENV_MODEL_VERSION = "ARCWRIGHT_MODEL_VERSION"` (line 130)
- `ENV_MODEL_PRICING_INPUT_RATE = "ARCWRIGHT_MODEL_PRICING_INPUT_RATE"` (line 131)
- `ENV_MODEL_PRICING_OUTPUT_RATE = "ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE"` (line 132)

New constants to add:
- `ENV_MODEL_GENERATE_VERSION = "ARCWRIGHT_AI_MODEL_GENERATE_VERSION"`
- `ENV_MODEL_REVIEW_VERSION = "ARCWRIGHT_AI_MODEL_REVIEW_VERSION"`
- `ENV_MODEL_GENERATE_PRICING_INPUT_RATE = "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE"`
- `ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE = "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE"`
- `ENV_MODEL_REVIEW_PRICING_INPUT_RATE = "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE"`
- `ENV_MODEL_REVIEW_PRICING_OUTPUT_RATE = "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_OUTPUT_RATE"`

### Previous Story Learnings (from Story 7.4)

- Best-effort try/except pattern for I/O operations is well-established
- `model_copy(update={...})` is the standard mutation pattern for frozen Pydantic models
- All engine node tests mock `update_run_status` as `AsyncMock` via `monkeypatch` autouse fixture
- 809 tests currently in the suite — none must break
- `ruff check .` and `mypy --strict src/` are quality gates

### Project Structure Notes

- All source under `arcwright-ai/src/arcwright_ai/`
- All tests under `arcwright-ai/tests/`
- `core/config.py` is the single source of truth for configuration models
- `core/constants.py` centralizes all magic strings and env var names
- `core/types.py` holds domain models — `ModelPricing` is intentionally NOT here (it's in config.py)
- No circular imports: `types.py` uses `TYPE_CHECKING` for `ModelPricing` import

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision 9: Role-Based Model Registry]
- [Source: _spec/planning-artifacts/epics.md#Epic 8, Story 8.1]
- [Source: arcwright-ai/src/arcwright_ai/core/config.py — full file, 549 lines]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — full file, 165 lines]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — full file, ~210 lines]
- [Source: arcwright-ai/tests/test_core/test_config.py — 446 lines, 13 model refs]
- [Source: arcwright-ai/tests/test_engine/test_nodes.py — 2671 lines, 5 model refs]
- [Source: _spec/implementation-artifacts/7-4-cost-tracking-integration-with-engine-pipeline.md — previous story context]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-5 (GitHub Copilot)

### Debug Log References

- **ModelSpec.version default**: Added `version: str = "claude-sonnet-4-20250514"` default to `ModelSpec` to support partial env-var-only role configuration. Without a default, Pydantic validation fails when env vars create a partial `models.roles.generate` dict with no `version` key.
- **Review-only env var guard**: Added a guard at the end of `_apply_env_overrides()` ensuring `models.roles.generate` always exists whenever any `models.roles.*` entry is created by env vars — prevents `ModelRegistry` @model_validator from failing when only a review-role env var is set.

### Completion Notes List

- `ModelRole(StrEnum)`, `ModelSpec`, `ModelRegistry` implemented in `core/config.py` per architecture Decision 9.
- `RunConfig.model` field replaced by `RunConfig.models: ModelRegistry`. Backward-compat `@property model` added for smooth Story 8.2 transition.
- Backward-compatible migration in `load_config()`: flat `models:` YAML wrapped into `{roles: ...}`; old `model:` migrated to `models.generate` with `DeprecationWarning`; old `ModelConfig` default version preserved.
- `_apply_env_overrides()` rewritten for role-based pattern; legacy env vars handled with deprecation warnings and generate-role fallback.
- Unknown-key detection extended for both `models.{role}.{field}` and `models.roles.{role}.{field}` nesting, including `pricing` sub-keys.
- 6 new env var constants added to `core/constants.py`; old constants kept with deprecated annotations.
- All 13 `cfg.model.*` references in `test_config.py` updated to new API; 14 new tests added covering AC #15a-g plus unknown-key regression cases.
- Quality gates: `ruff check .` ✅  `mypy --strict src/` ✅  823 tests pass ✅

### File List

- `arcwright-ai/src/arcwright_ai/core/config.py`
- `arcwright-ai/src/arcwright_ai/core/constants.py`
- `arcwright-ai/tests/test_core/test_config.py`
- `arcwright-ai/tests/test_core/test_constants.py`
- `_spec/planning-artifacts/architecture.md`
- `_spec/planning-artifacts/epics.md`
- `_spec/implementation-artifacts/epic-7-retrospective.md`
- `_spec/implementation-artifacts/8-1-modelrole-enum-modelspec-modelregistry-and-config-migration.md`
- `_spec/implementation-artifacts/sprint-status.yaml`

### Change Log

- **2026-03-12**: Implemented Story 8.1 — ModelRole Enum, ModelSpec, ModelRegistry & Config Migration. Role-based model registry with full backward compatibility. Added 6 new env var constants. Updated 25 existing tests; added 12 new tests. 809 existing tests continue passing; total 821.
- **2026-03-12 (Code Review Fixes)**: Fixed unknown-key recursion for both `models:` and `models.roles:` schemas, added nested pricing unknown-key warnings, and added regression tests for wrapped schema + nested pricing unknown-key handling.

## Senior Developer Review (AI)

### Reviewer

Ed (GPT-5.3-Codex) — 2026-03-12

### Outcome

✅ **Approved after fixes**

### Findings Resolved

1. **HIGH** — Unknown-key detection missed nested `models.{role}.pricing.{field}` unknown keys.
  - **Fix:** Added explicit recursion for role pricing maps and warning emission for unknown pricing fields.
2. **HIGH** — Valid wrapped schema `models.roles.{role}` produced false unknown-key warnings.
  - **Fix:** Added wrapped-shape awareness in unknown-key traversal and allowed `models.roles` as a valid section key.
3. **MEDIUM** — Story file list omitted changed files present in git status.
  - **Fix:** Updated File List to include all currently changed implementation and documentation artifacts.

### Validation Evidence

- `pytest -q tests/test_core/test_config.py` → 39 passed
- `ruff check src/arcwright_ai/core/config.py tests/test_core/test_config.py` → passed
- `.venv/bin/python -m mypy --strict src/` → passed
