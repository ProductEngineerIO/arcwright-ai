# Story 7.1: BudgetState Model & Cost Accumulation

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running autonomous dispatches,
I want every SDK invocation's token usage and cost tracked accurately,
so that I have full visibility into what each story and run costs.

## Acceptance Criteria (BDD)

1. **Given** `BudgetState` in `core/types.py` (currently has `invocation_count`, `total_tokens`, `estimated_cost`, `max_invocations`, `max_cost`) **When** this story is implemented **Then** `BudgetState` is extended with per-story tracking fields: `total_tokens_input: int = 0`, `total_tokens_output: int = 0`, and `per_story: dict[str, StoryCost] = {}` mapping story slug → `StoryCost`.

2. **Given** a new `StoryCost` model **When** defined in `core/types.py` **Then** it is a frozen `ArcwrightModel` with fields: `tokens_input: int = 0`, `tokens_output: int = 0`, `cost: Decimal = Decimal("0")`, `invocations: int = 0` **And** it is exported in `__all__`.

3. **Given** a new `ModelPricing` config sub-model **When** defined in `core/config.py` **Then** it has fields: `input_rate: Decimal` (cost per 1M input tokens), `output_rate: Decimal` (cost per 1M output tokens) **And** it is nested under `ModelConfig` as `pricing: ModelPricing` with sensible defaults for claude-opus-4-5 (e.g., `input_rate=Decimal("15.00")`, `output_rate=Decimal("75.00")`).

4. **Given** `ModelPricing` configuration **When** loaded from `config.yaml` **Then** pricing can be overridden via config file under `model.pricing.input_rate` / `model.pricing.output_rate` **And** environment variable overrides are supported via `ARCWRIGHT_MODEL_PRICING_INPUT_RATE` and `ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE`.

5. **Given** the `agent_dispatch_node` in `engine/nodes.py` **When** the SDK invocation completes successfully **Then** the budget update uses `InvocationResult.tokens_input` and `InvocationResult.tokens_output` (SDK-reported, not prompt-length estimates) to maintain ≤ 10% variance from actual billing per NFR12b **And** cost is computed as: `(tokens_input / 1_000_000) * pricing.input_rate + (tokens_output / 1_000_000) * pricing.output_rate` using `Decimal` arithmetic.

6. **Given** the budget update in `agent_dispatch_node` **When** invocation completes **Then** both run-level fields (`total_tokens_input`, `total_tokens_output`, `invocation_count`, `estimated_cost`) AND `per_story[story_slug]` (`StoryCost`) are updated in a single `model_copy(update={...})` call — 100% capture with no missed calls per NFR12a.

7. **Given** the `_serialize_budget` function in `output/run_manager.py` **When** `BudgetState` with `per_story` data is serialized **Then** `per_story` is serialized as a nested dict with each `StoryCost`'s `Decimal` fields converted to strings (YAML-safe) **And** `_reconstruct_budget_from_dict` in `cli/resume.py` correctly deserializes `per_story` back to `dict[str, StoryCost]` with proper `Decimal` reconstruction.

8. **Given** `BudgetState` is persisted to `run.yaml` at every state transition via run manager **When** the run progresses through stories **Then** `run.yaml` budget section reflects cumulative totals AND per-story breakdowns after each agent invocation.

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 728 existing tests continue to pass.

13. **Given** new tests in `tests/test_core/test_types_budget.py` and updates to `tests/test_engine/test_nodes.py` **When** the test suite runs **Then** tests cover:
    (a) `StoryCost` construction with defaults and explicit values;
    (b) `StoryCost` is frozen (immutable after construction);
    (c) `BudgetState` new fields (`total_tokens_input`, `total_tokens_output`, `per_story`) default correctly;
    (d) `BudgetState.per_story` accumulation — two invocations for same story slug → single `StoryCost` entry with summed values;
    (e) `BudgetState.per_story` — two different story slugs → separate entries;
    (f) Cost calculation uses `Decimal` arithmetic (no float) — verify `Decimal("15.00") * Decimal("12345") / Decimal("1000000")` matches expected precision;
    (g) `_serialize_budget` handles `per_story` with `Decimal` → `str` conversion;
    (h) `_reconstruct_budget_from_dict` round-trips `per_story` correctly;
    (i) `ModelPricing` defaults load correctly;
    (j) `ModelPricing` config override from YAML works;
    (k) `ModelPricing` env var override works;
    (l) Existing `agent_dispatch_node` tests still pass with the new budget fields;
    (m) Budget update in `agent_dispatch_node` populates `per_story[story_slug]` correctly.

## Boundary Conditions

- **Boundary 1 (Frozen immutability):** `BudgetState` and `StoryCost` are both frozen. Updates must use `model_copy(update={...})`. The `per_story` dict itself is stored as a `dict[str, StoryCost]` — since the model is frozen, the entire dict is replaced on update (not mutated in place).
- **Boundary 2 (Decimal precision):** All cost arithmetic uses `Decimal`, never `float`. Serialization converts to `str`; deserialization converts back to `Decimal`.
- **Boundary 3 (Config backward compatibility):** Existing `config.yaml` files without `model.pricing` section must still load — `ModelPricing` has defaults.
- **Boundary 4 (run.yaml backward compatibility):** Existing `run.yaml` files without `per_story` in the budget section must deserialize without error — `_reconstruct_budget_from_dict` treats missing `per_story` as empty dict.

## Tasks / Subtasks

- [ ] Task 1: Define `StoryCost` model in `core/types.py` (AC: #2)
  - [ ] 1.1: Add `StoryCost(ArcwrightModel)` with fields: `tokens_input: int = 0`, `tokens_output: int = 0`, `cost: Decimal = Decimal("0")`, `invocations: int = 0`.
  - [ ] 1.2: Add Google-style docstring.
  - [ ] 1.3: Add `"StoryCost"` to `__all__`.

- [ ] Task 2: Extend `BudgetState` with per-story tracking fields (AC: #1)
  - [ ] 2.1: Add `total_tokens_input: int = 0` field.
  - [ ] 2.2: Add `total_tokens_output: int = 0` field.
  - [ ] 2.3: Add `per_story: dict[str, StoryCost] = Field(default_factory=dict)` field. Note: Pydantic frozen models allow `dict` fields — the `dict` reference is frozen, but it is replaced wholesale on `model_copy`.
  - [ ] 2.4: Update `BudgetState` docstring to document new fields.

- [ ] Task 3: Add `ModelPricing` config sub-model (AC: #3, #4)
  - [ ] 3.1: In `core/config.py`, add `ModelPricing(ArcwrightModel)` with `model_config = ConfigDict(frozen=True, extra="ignore", ...)`, fields `input_rate: Decimal = Decimal("15.00")`, `output_rate: Decimal = Decimal("75.00")`.
  - [ ] 3.2: Add `pricing: ModelPricing = Field(default_factory=ModelPricing)` to `ModelConfig`.
  - [ ] 3.3: Add `"ModelPricing"` to `config.py`'s `__all__`.
  - [ ] 3.4: Add env var constants `ENV_MODEL_PRICING_INPUT_RATE = "ARCWRIGHT_MODEL_PRICING_INPUT_RATE"` and `ENV_MODEL_PRICING_OUTPUT_RATE = "ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE"` to `core/constants.py` and `__all__`.
  - [ ] 3.5: Update `_apply_env_overrides()` in `config.py` to handle the pricing env vars — convert string values to `Decimal`.

- [ ] Task 4: Add cost calculation helper (AC: #5)
  - [ ] 4.1: In `core/types.py` (or a new `core/budget.py` if preferred), add a function `calculate_invocation_cost(tokens_input: int, tokens_output: int, pricing: ModelPricing) -> Decimal` that computes: `Decimal(tokens_input) / Decimal("1000000") * pricing.input_rate + Decimal(tokens_output) / Decimal("1000000") * pricing.output_rate`.
  - [ ] 4.2: Google-style docstring with Args, Returns.

- [ ] Task 5: Update `agent_dispatch_node` budget update logic (AC: #5, #6)
  - [ ] 5.1: Import `StoryCost` and `calculate_invocation_cost` (or inline the computation).
  - [ ] 5.2: After `invoke_agent` succeeds, compute `invocation_cost = calculate_invocation_cost(result.tokens_input, result.tokens_output, state.config.model.pricing)`.
  - [ ] 5.3: Build updated `per_story` dict: copy existing `state.budget.per_story`, get or create `StoryCost` for `str(state.story_id)`, create new `StoryCost` with summed fields, store back.
  - [ ] 5.4: Replace the existing `new_budget = state.budget.model_copy(update={...})` to include: `total_tokens_input`, `total_tokens_output`, `per_story`, and use the pricing-based `invocation_cost` instead of `result.total_cost` for `estimated_cost`.
  - [ ] 5.5: Ensure `result.total_cost` from the SDK is NOT used for `estimated_cost` — use the pricing-based calculation for consistency (SDK may use different pricing). However, log both values for auditability.

- [ ] Task 6: Update `_serialize_budget` in `output/run_manager.py` (AC: #7, #8)
  - [ ] 6.1: Handle `per_story` serialization: iterate over the `per_story` dict, call `.model_dump()` on each `StoryCost`, convert `Decimal` fields to `str`.
  - [ ] 6.2: Ensure existing `estimated_cost` and `max_cost` string conversion is preserved.

- [ ] Task 7: Update `_reconstruct_budget_from_dict` in `cli/resume.py` (AC: #7)
  - [ ] 7.1: Parse `per_story` from the budget dict — if present, reconstruct each value as `StoryCost(tokens_input=..., tokens_output=..., cost=Decimal(str(...)), invocations=...)`.
  - [ ] 7.2: If `per_story` key is missing (old run.yaml), default to empty dict.
  - [ ] 7.3: Add `total_tokens_input` and `total_tokens_output` reconstruction with defaults of 0.

- [ ] Task 8: Create unit tests (AC: #13)
  - [ ] 8.1: Create `tests/test_core/test_types_budget.py` with tests (a)-(f) from AC #13.
  - [ ] 8.2: Add serialization round-trip tests (g)-(h) — can go in `tests/test_output/test_run_manager.py` or the new file.
  - [ ] 8.3: Add config tests (i)-(k) in `tests/test_core/test_config.py` (extend existing).
  - [ ] 8.4: Update `tests/test_engine/test_nodes.py` to verify `agent_dispatch_node` budget update includes `per_story` (l)-(m).

- [ ] Task 9: Verify all quality gates (AC: #9, #10, #11, #12)
  - [ ] 9.1: Run `ruff check .` — zero violations.
  - [ ] 9.2: Run `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [ ] 9.3: Verify all docstrings are Google-style.
  - [ ] 9.4: Run full test suite — all 728+ tests pass (existing + new).

## Dev Notes

### Existing Code Landscape

- **`BudgetState`** already exists in `core/types.py` with `invocation_count`, `total_tokens`, `estimated_cost`, `max_invocations`, `max_cost`. This story extends it — does NOT replace it.
- **`agent_dispatch_node`** already updates budget after SDK call (lines ~368-375 of `engine/nodes.py`): `invocation_count + 1`, `total_tokens + input + output`, `estimated_cost + result.total_cost`. This needs modification to add `total_tokens_input`, `total_tokens_output`, `per_story`, and pricing-based cost.
- **`_serialize_budget`** in `run_manager.py` calls `budget.model_dump()` then converts Decimal→str. Needs extension for nested `per_story`.
- **`_reconstruct_budget_from_dict`** in `cli/resume.py` reconstructs from run.yaml dict. Needs extension for `per_story` + new fields.
- **`route_budget_check`** already checks `max_invocations` and `max_cost` — no changes needed in this story (Story 7.2 will enhance it).
- **`InvocationResult`** in `agent/invoker.py` already provides `tokens_input`, `tokens_output`, `total_cost` — this story consumes those.

### Pricing Defaults

Claude Opus 4.5 (current default): `$15/1M input tokens`, `$75/1M output tokens`. These are the defaults in `ModelPricing`. Users override via config or env vars for different models.

### Frozen Model Update Pattern

Since `BudgetState` is frozen, the `per_story` dict update requires:
```python
existing_story_cost = state.budget.per_story.get(slug, StoryCost())
new_story_cost = StoryCost(
    tokens_input=existing_story_cost.tokens_input + result.tokens_input,
    tokens_output=existing_story_cost.tokens_output + result.tokens_output,
    cost=existing_story_cost.cost + invocation_cost,
    invocations=existing_story_cost.invocations + 1,
)
new_per_story = {**state.budget.per_story, slug: new_story_cost}
new_budget = state.budget.model_copy(update={"per_story": new_per_story, ...})
```
