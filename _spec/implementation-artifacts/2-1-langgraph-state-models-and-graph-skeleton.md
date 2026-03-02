# Story 2.1: LangGraph State Models & Graph Skeleton

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer building the orchestration engine,
I want the Pydantic state models (`ProjectState`, `StoryState`) and a minimal LangGraph StateGraph skeleton with placeholder nodes,
so that subsequent stories can implement real node logic into a working graph framework.

## Acceptance Criteria (BDD)

1. **Given** the `engine/` package and `core/` types from Epic 1 **When** state models and graph are implemented **Then** `engine/state.py` defines `StoryState` (mutable, `frozen=False`) with fields: `story_id`, `epic_id`, `run_id`, `story_path`, `project_root`, `status` (TaskState), `context_bundle` (optional ContextBundle), `agent_output` (optional str), `validation_result` (optional), `retry_count` (int), `budget` (BudgetState), `config` (RunConfig reference).

2. **Given** the `engine/` package **When** state models are implemented **Then** `engine/state.py` defines `ProjectState` with fields: `epic_id`, `run_id`, `stories` (list of StoryState), `config`, `status`, `completed_stories`, `current_story_index`.

3. **Given** the existing `BudgetState` in `core/types.py` **When** Story 2.1 is implemented **Then** `BudgetState` defines the core engine fields: `invocation_count` (int), `total_tokens` (int), `estimated_cost` (Decimal), `max_invocations` (int), `max_cost` (Decimal) — sufficient for the `budget_check` node to function. Per-story breakdown, pricing model, and run.yaml serialization are owned by Story 7.1.

4. **Given** the `engine/` package **When** graph is implemented **Then** `engine/graph.py` defines `build_story_graph()` that returns a compiled LangGraph `StateGraph` with nodes: `preflight`, `budget_check`, `agent_dispatch`, `validate`, `commit`, and conditional edges: budget_check → agent_dispatch (if OK) or escalated (if exceeded), validate → commit (success) or budget_check (retry) or escalated.

5. **Given** the graph nodes **When** implemented **Then** all nodes are placeholder async functions that log entry/exit and pass through state with appropriate status transitions.

6. **Given** the node implementations **When** inspected **Then** `engine/nodes.py` contains all node function stubs with correct signatures: `async def preflight_node(state: StoryState) -> StoryState`.

7. **Given** a compiled graph **When** invoked with a test `StoryState` **Then** graph can be compiled and invoked without errors.

8. **Given** unit tests **When** `pytest tests/test_engine/` is run **Then** unit tests verify graph construction, node routing (success path, retry path, escalated path), and state model validation.

9. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

10. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 0: Reconcile BudgetState fields in `core/types.py` (AC: #3) — **PREREQUISITE from Epic 1 Retro**
  - [x] 0.1: Add `from decimal import Decimal` import to `core/types.py`
  - [x] 0.2: Rename field `estimated_cost_usd: float` → `estimated_cost: Decimal` with default `Decimal("0")`
  - [x] 0.3: Remove field `token_ceiling: int` (token ceiling is in `LimitsConfig.tokens_per_story`, not BudgetState)
  - [x] 0.4: Rename field `cost_ceiling_usd: float` → `max_cost: Decimal` with default `Decimal("0")`
  - [x] 0.5: Add field `max_invocations: int = 0` (0 = unlimited)
  - [x] 0.6: Update `BudgetState` docstring to reflect new field names and Decimal types
  - [x] 0.7: Update `tests/test_core/test_types.py` — fix all BudgetState tests to use new field names and `Decimal` values. Replace `pytest.approx(0.05)` with `Decimal("0.05")`. Remove `token_ceiling` assertions. Add `max_invocations` assertions.
  - [x] 0.8: Run `pytest tests/test_core/test_types.py -v` — all tests pass

- [x] Task 1: Implement `StoryState` in `engine/state.py` (AC: #1, #6, #11)
  - [x] 1.1: Add `from __future__ import annotations` as first line
  - [x] 1.2: Import required types: `Path` from pathlib; `Any` from typing; `BaseModel`, `ConfigDict`, `Field` from pydantic; `BudgetState`, `ContextBundle`, `EpicId`, `RunId`, `StoryId` from `arcwright_ai.core.types`; `TaskState` from `arcwright_ai.core.lifecycle`; `RunConfig` from `arcwright_ai.core.config`
  - [x] 1.3: Define `StoryState(BaseModel)` with `model_config = ConfigDict(frozen=False, extra="forbid")` — NOT inheriting from `ArcwrightModel` (which is frozen)
  - [x] 1.4: Add fields: `story_id: StoryId`, `epic_id: EpicId`, `run_id: RunId`, `story_path: Path`, `project_root: Path`, `status: TaskState = TaskState.QUEUED`, `context_bundle: ContextBundle | None = None`, `agent_output: str | None = None`, `validation_result: dict[str, Any] | None = None`, `retry_count: int = 0`, `budget: BudgetState = Field(default_factory=BudgetState)`, `config: RunConfig`
  - [x] 1.5: Add Google-style docstring with all field descriptions

- [x] Task 2: Implement `ProjectState` in `engine/state.py` (AC: #2, #11)
  - [x] 2.1: Define `ProjectState(BaseModel)` with `model_config = ConfigDict(frozen=False, extra="forbid")`
  - [x] 2.2: Add fields: `epic_id: EpicId`, `run_id: RunId`, `stories: list[StoryState] = Field(default_factory=list)`, `config: RunConfig`, `status: TaskState = TaskState.QUEUED`, `completed_stories: int = 0`, `current_story_index: int = 0`
  - [x] 2.3: Add Google-style docstring with all field descriptions

- [x] Task 3: Implement placeholder node functions in `engine/nodes.py` (AC: #5, #6, #11)
  - [x] 3.1: Add `from __future__ import annotations` and imports: `logging` from stdlib; `TaskState` from `arcwright_ai.core.lifecycle`; `StoryState` from `arcwright_ai.engine.state`
  - [x] 3.2: Create module-level logger: `logger = logging.getLogger(__name__)`
  - [x] 3.3: Implement `async def preflight_node(state: StoryState) -> StoryState` — log entry, transition status QUEUED → PREFLIGHT → RUNNING via `model_copy(update={...})`, log exit, return updated state
  - [x] 3.4: Implement `async def budget_check_node(state: StoryState) -> StoryState` — log entry; transition to ESCALATED when budget is exceeded, transition RETRY → RUNNING via `model_copy`, log exit, and return updated state
  - [x] 3.5: Implement `async def agent_dispatch_node(state: StoryState) -> StoryState` — log entry, transition status RUNNING → VALIDATING via `model_copy`, log exit, return updated state
  - [x] 3.6: Implement `async def validate_node(state: StoryState) -> StoryState` — log entry, transition status VALIDATING → SUCCESS via `model_copy` (placeholder always succeeds), log exit, return updated state
  - [x] 3.7: Implement `async def commit_node(state: StoryState) -> StoryState` — log entry, log exit, return state unchanged (already SUCCESS)
  - [x] 3.8: Implement routing function `def route_budget_check(state: StoryState) -> str`: return `"exceeded"` if `state.budget.invocation_count >= state.budget.max_invocations > 0` OR `state.budget.estimated_cost >= state.budget.max_cost > Decimal(0)`, else return `"ok"`
  - [x] 3.9: Implement routing function `def route_validation(state: StoryState) -> str`: return `"success"` if `state.status == TaskState.SUCCESS`, `"retry"` if `state.status == TaskState.RETRY`, else `"escalated"`
  - [x] 3.10: Update `__all__` with all public symbols in alphabetical order

- [x] Task 4: Implement `build_story_graph()` in `engine/graph.py` (AC: #4, #7, #11)
  - [x] 4.1: Add `from __future__ import annotations` and imports: `StateGraph`, `START`, `END` from `langgraph.graph`; `StoryState` from `arcwright_ai.engine.state`; all node functions and routing functions from `arcwright_ai.engine.nodes`
  - [x] 4.2: Implement `def build_story_graph() -> CompiledStateGraph` (import `CompiledStateGraph` from `langgraph.graph.state`)
  - [x] 4.3: Create `StateGraph(StoryState)`, add all 5 nodes
  - [x] 4.4: Add edges: `START → "preflight"`, `"preflight" → "budget_check"`, `"agent_dispatch" → "validate"`, `"commit" → END`
  - [x] 4.5: Add conditional edges: `"budget_check"` → `route_budget_check` → `{"ok": "agent_dispatch", "exceeded": END}`, `"validate"` → `route_validation` → `{"success": "commit", "retry": "budget_check", "escalated": END}`
  - [x] 4.6: Return `graph.compile()`
  - [x] 4.7: Update `__all__` to export `"build_story_graph"`
  - [x] 4.8: Add Google-style docstring

- [x] Task 5: Update `engine/__init__.py` exports (AC: #9)
  - [x] 5.1: Import and re-export: `build_story_graph` from `engine.graph`; `ProjectState`, `StoryState` from `engine.state`; all node functions and routing functions from `engine.nodes`
  - [x] 5.2: Update `__all__` in alphabetical order per RUF022

- [x] Task 6: Write unit tests in `tests/test_engine/test_state.py` (AC: #8)
  - [x] 6.1: Create `tests/test_engine/test_state.py` with `from __future__ import annotations`
  - [x] 6.2: Create helper fixture `make_run_config` that builds a minimal `RunConfig` (requires `ApiConfig` with a dummy `claude_api_key`)
  - [x] 6.3: Test `test_story_state_creation_with_required_fields` — construct StoryState with required fields, verify defaults (status=QUEUED, context_bundle=None, retry_count=0, etc.)
  - [x] 6.4: Test `test_story_state_is_mutable` — assign new field value (e.g., `state.status = TaskState.RUNNING`), verify it sticks
  - [x] 6.5: Test `test_story_state_forbids_extra_fields` — construct with `extra_field="x"` → PydanticValidationError
  - [x] 6.6: Test `test_story_state_model_copy_updates` — use `model_copy(update={"status": TaskState.RUNNING})`, verify new state has RUNNING while original is unchanged
  - [x] 6.7: Test `test_project_state_creation_with_required_fields` — construct ProjectState, verify defaults
  - [x] 6.8: Test `test_project_state_stories_default_empty_list` — verify `stories` defaults to `[]`
  - [x] 6.9: Test `test_project_state_forbids_extra_fields` — extra fields rejected

- [x] Task 7: Write unit tests in `tests/test_engine/test_nodes.py` (AC: #8)
  - [x] 7.1: Create `tests/test_engine/test_nodes.py` with `from __future__ import annotations`
  - [x] 7.2: Create fixture `make_story_state` that builds a minimal StoryState with dummy config
  - [x] 7.3: Test `test_preflight_node_transitions_to_running` — state starts QUEUED, after preflight_node it's RUNNING
  - [x] 7.4: Test `test_budget_check_node_passes_through_when_running` — state at RUNNING, budget_check returns RUNNING
  - [x] 7.5: Test `test_budget_check_node_transitions_retry_to_running` — state at RETRY, budget_check returns RUNNING
  - [x] 7.6: Test `test_agent_dispatch_node_transitions_to_validating` — state at RUNNING, after agent_dispatch it's VALIDATING
  - [x] 7.7: Test `test_validate_node_transitions_to_success` — state at VALIDATING, after validate it's SUCCESS
  - [x] 7.8: Test `test_commit_node_preserves_success` — state at SUCCESS, after commit still SUCCESS
  - [x] 7.9: Test `test_route_budget_check_returns_ok_when_within_limits` — budget with 0 max (unlimited) → "ok"
  - [x] 7.10: Test `test_route_budget_check_returns_exceeded_on_invocation_limit` — invocations at or above max_invocations → "exceeded"
  - [x] 7.11: Test `test_route_budget_check_returns_exceeded_on_cost_limit` — estimated_cost at or above max_cost → "exceeded"
  - [x] 7.12: Test `test_route_validation_returns_success` — state with SUCCESS → "success"
  - [x] 7.13: Test `test_route_validation_returns_retry` — state with RETRY → "retry"
  - [x] 7.14: Test `test_route_validation_returns_escalated` — state with ESCALATED → "escalated"

- [x] Task 8: Write unit tests in `tests/test_engine/test_graph.py` (AC: #4, #7, #8)
  - [x] 8.1: Create `tests/test_engine/test_graph.py` with `from __future__ import annotations`
  - [x] 8.2: Test `test_build_story_graph_returns_compiled_graph` — call `build_story_graph()`, verify return type is `CompiledStateGraph`
  - [x] 8.3: Test `test_graph_contains_all_expected_nodes` — compiled graph has nodes: preflight, budget_check, agent_dispatch, validate, commit
  - [x] 8.4: Test `test_graph_success_path_end_to_end` — invoke graph with a valid initial StoryState, verify final status is SUCCESS
  - [x] 8.5: Test `test_graph_invocation_no_errors` — invoke graph, verify no exception raised

- [x] Task 9: Validate all quality gates (AC: #9, #10)
  - [x] 9.1: Run `ruff check .` — zero violations
  - [x] 9.2: Run `ruff format --check .` — no formatting diffs
  - [x] 9.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 9.4: Run `pytest tests/test_engine/ -v` — all new tests pass
  - [x] 9.5: Run `pytest` — full test suite passes (no regressions; BudgetState test updates required)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `engine/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
`engine/` can import from `core/` and from domain packages (`validation/`, `agent/`, `context/`, `output/`, `scm/`). However, Story 2.1 only imports from `core/` — no domain package imports needed yet. Domain packages are wired in by later stories (2.2–2.7).

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. When populating `engine/state.py`, `engine/nodes.py`, `engine/graph.py`, and `engine/__init__.py`, sort all entries.

#### Placeholder Modules Ship with Empty `__all__: list[str] = []` Only — No Aspirational Exports
Exception: this story IS populating the engine modules, so exports are real, not aspirational.

#### Graph Node Return Type Pattern
All LangGraph graph nodes **return the full `StoryState` object** (not partial dicts). Use Pydantic's `.model_copy(update={...})` for updates:
```python
async def preflight_node(state: StoryState) -> StoryState:
    return state.model_copy(update={"status": TaskState.RUNNING})
```

#### Mutable State Models for LangGraph
`StoryState` and `ProjectState` use `frozen=False` explicitly — they do NOT inherit from `ArcwrightModel` (which has `frozen=True`). Instead, they inherit directly from `BaseModel` with `ConfigDict(frozen=False, extra="forbid")`.

#### BudgetState Stays Frozen
`BudgetState` remains in `core/types.py` inheriting `ArcwrightModel` (`frozen=True`). Updates via `model_copy(update={...})`. The `StoryState.budget` field holds a `BudgetState` instance; when the budget_check node needs to update it, it creates a new `BudgetState` and puts it in the state via `model_copy`.

#### Structured Logging — Not `print()`, Not Unstructured Strings
```python
logger.info("engine.node.enter", extra={"data": {"node": "preflight", "story": str(state.story_id)}})
```
**Never:** `logger.info(f"Entering preflight for {state.story_id}")` or `print(...)`.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. Applies to `ProjectState.stories` and any list/dict defaults.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. StoryState and ProjectState use `extra="forbid"` because they are internal engine state, not user config.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. `tests/test_engine/__init__.py` already exists.

---

### BudgetState Reconciliation (CRITICAL — From Retro Action 3)

The Epic 1 retrospective identified a **field name discrepancy** between the existing `BudgetState` and Epic 2's expected contract:

| Current Field | New Field | Change |
|---|---|---|
| `invocation_count: int = 0` | `invocation_count: int = 0` | No change |
| `total_tokens: int = 0` | `total_tokens: int = 0` | No change |
| `estimated_cost_usd: float = 0.0` | `estimated_cost: Decimal = Decimal("0")` | Rename + type change |
| `token_ceiling: int = 0` | *(removed)* | Token ceiling lives in `LimitsConfig.tokens_per_story` |
| `cost_ceiling_usd: float = 0.0` | `max_cost: Decimal = Decimal("0")` | Rename + type change |
| *(new)* | `max_invocations: int = 0` | NEW — invocation count ceiling (0 = unlimited) |

**Why Decimal, not float:** Financial calculations require exact decimal arithmetic. `float` introduces IEEE 754 rounding errors (e.g., `0.1 + 0.2 != 0.3`). `Decimal` provides exact representation. Pydantic v2 natively supports `Decimal` — no extra configuration needed.

**Impact on existing tests:** `tests/test_core/test_types.py` has 3 BudgetState tests that must be updated:
- `test_budget_state_default_values` — update field names, use `Decimal("0")` instead of `0.0`
- `test_budget_state_custom_values` — update field names, use `Decimal("0.05")` instead of `pytest.approx(0.05)`, remove `token_ceiling`, add `max_invocations`
- `test_budget_state_is_frozen` — no change needed (still frozen)

---

### Technical Specifications

#### StoryState Field Details

```python
class StoryState(BaseModel):
    """Mutable state for a single story execution in the LangGraph StateGraph.

    This is the primary state object threaded through all graph nodes.
    Mutable (frozen=False) because LangGraph updates state during traversal.

    Attributes:
        story_id: Identifier for this story (e.g., '2-1-state-models').
        epic_id: Parent epic identifier (e.g., 'epic-2').
        run_id: Unique run identifier (e.g., '20260302-143052-a7f3').
        story_path: Path to the story markdown file.
        project_root: Root directory of the project.
        status: Current lifecycle state (queued → ... → success/escalated).
        context_bundle: Assembled context from preflight (None until preflight runs).
        agent_output: Raw agent response text (None until agent runs).
        validation_result: Validation results (None until validation runs; typed as
            dict for now — will become ValidationResult model in Epic 3).
        retry_count: Number of retry attempts so far.
        budget: Token/cost consumption tracker.
        config: Run-level configuration reference.
    """
    model_config = ConfigDict(frozen=False, extra="forbid")

    story_id: StoryId
    epic_id: EpicId
    run_id: RunId
    story_path: Path
    project_root: Path
    status: TaskState = TaskState.QUEUED
    context_bundle: ContextBundle | None = None
    agent_output: str | None = None
    validation_result: dict[str, Any] | None = None
    retry_count: int = 0
    budget: BudgetState = Field(default_factory=BudgetState)
    config: RunConfig
```

#### ProjectState Field Details

```python
class ProjectState(BaseModel):
    """Mutable state for an epic-level execution containing multiple stories.

    Attributes:
        epic_id: Epic being dispatched (e.g., 'epic-2').
        run_id: Unique run identifier.
        stories: Ordered list of StoryState objects in this epic.
        config: Shared run configuration.
        status: Overall epic execution status.
        completed_stories: Count of stories that reached SUCCESS.
        current_story_index: Zero-based index of the story currently executing.
    """
    model_config = ConfigDict(frozen=False, extra="forbid")

    epic_id: EpicId
    run_id: RunId
    stories: list[StoryState] = Field(default_factory=list)
    config: RunConfig
    status: TaskState = TaskState.QUEUED
    completed_stories: int = 0
    current_story_index: int = 0
```

#### Graph Construction Pattern

```python
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

def build_story_graph() -> CompiledStateGraph:
    graph = StateGraph(StoryState)
    graph.add_node("preflight", preflight_node)
    graph.add_node("budget_check", budget_check_node)
    graph.add_node("agent_dispatch", agent_dispatch_node)
    graph.add_node("validate", validate_node)
    graph.add_node("commit", commit_node)
    graph.add_edge(START, "preflight")
    graph.add_edge("preflight", "budget_check")
    graph.add_conditional_edges("budget_check", route_budget_check, {"ok": "agent_dispatch", "exceeded": END})
    graph.add_edge("agent_dispatch", "validate")
    graph.add_conditional_edges("validate", route_validation, {"success": "commit", "retry": "budget_check", "escalated": END})
    graph.add_edge("commit", END)
    return graph.compile()
```

#### Routing Function Contracts

**`route_budget_check(state: StoryState) -> str`**
- Returns `"exceeded"` if:
  - `state.budget.max_invocations > 0` AND `state.budget.invocation_count >= state.budget.max_invocations`
  - OR `state.budget.max_cost > Decimal(0)` AND `state.budget.estimated_cost >= state.budget.max_cost`
- Returns `"ok"` otherwise (including when max values are 0 = unlimited)

**`route_validation(state: StoryState) -> str`**
- Returns `"success"` if `state.status == TaskState.SUCCESS`
- Returns `"retry"` if `state.status == TaskState.RETRY`
- Returns `"escalated"` otherwise (covers `TaskState.ESCALATED` and defensive fallback)

#### Placeholder Node Status Transitions

| Node | Entry Status | Exit Status | Notes |
|---|---|---|---|
| `preflight_node` | QUEUED | RUNNING | Transitions through PREFLIGHT internally |
| `budget_check_node` | RUNNING or RETRY | RUNNING | Transitions RETRY → RUNNING if needed |
| `agent_dispatch_node` | RUNNING | VALIDATING | — |
| `validate_node` | VALIDATING | SUCCESS | Placeholder always succeeds |
| `commit_node` | SUCCESS | SUCCESS | No status change |

#### LangGraph API Reference (langgraph >=0.2, <1.0)

Key imports:
```python
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
```

- `StateGraph(state_type)` — creates a new graph with the given Pydantic model as state
- `graph.add_node(name, fn)` — registers an async node function
- `graph.add_edge(from, to)` — unconditional edge
- `graph.add_conditional_edges(from, router_fn, path_map)` — conditional routing
- `graph.compile()` → `CompiledStateGraph` — ready for invocation
- `await compiled_graph.ainvoke(initial_state)` — async invocation
- `START` and `END` are special sentinel nodes

**mypy note:** LangGraph's type stubs may be incomplete. If `mypy --strict` complains about LangGraph imports, use targeted `# type: ignore[import-untyped]` on import lines only. Do NOT disable mypy errors globally.

#### Test Helper Pattern (RunConfig Construction)

Tests need a `RunConfig` instance for `StoryState.config`. Since `RunConfig` requires `ApiConfig.claude_api_key`, construct a minimal config:

```python
from arcwright_ai.core.config import ApiConfig, RunConfig

def make_run_config() -> RunConfig:
    return RunConfig(api=ApiConfig(claude_api_key="test-key-not-real"))
```

This can be a fixture or a helper function in test files.

---

### Project Structure Notes

**Files to create/modify:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/core/types.py` | MODIFY | Reconcile BudgetState fields (Decimal, rename, add max_invocations) |
| `src/arcwright_ai/engine/state.py` | MODIFY (was placeholder) | Add StoryState and ProjectState Pydantic models |
| `src/arcwright_ai/engine/nodes.py` | MODIFY (was placeholder) | Add 5 placeholder node functions + 2 routing functions |
| `src/arcwright_ai/engine/graph.py` | MODIFY (was placeholder) | Add build_story_graph() function |
| `src/arcwright_ai/engine/__init__.py` | MODIFY (was empty) | Add real exports |
| `tests/test_core/test_types.py` | MODIFY | Update BudgetState tests for new field names |
| `tests/test_engine/test_state.py` | CREATE | StoryState and ProjectState tests |
| `tests/test_engine/test_nodes.py` | CREATE | Node function and routing function tests |
| `tests/test_engine/test_graph.py` | CREATE | Graph construction and invocation tests |

**Files NOT touched** (no changes needed):
- `core/__init__.py` — BudgetState is already exported; no new core types added
- `core/lifecycle.py` — TaskState and transitions already correct for this story
- `core/constants.py` — no new constants needed
- `core/config.py` — RunConfig unchanged
- `cli/` — no CLI changes in this story

---

### Previous Story Intelligence (Epic 1 Learnings)

**From Story 1.5 (CLI Validate-Setup):**
- Command registration pattern in `cli/app.py` works cleanly — import + `app.command(name=...)(fn)`. Relevant for Story 2.7 when dispatch command is added.
- Test fixtures use `tmp_path` for project scaffolding; `RunConfig` construction requires explicit `ApiConfig(claude_api_key="...")` — never rely on env vars in tests.

**From Story 1.2 (Core Types):**
- `ArcwrightModel` base class enforces `frozen=True`, `extra="forbid"`, `str_strip_whitespace=True`.
- `StoryState`/`ProjectState` must NOT inherit from `ArcwrightModel` — they need `frozen=False`.
- `Field(default_factory=list)` is the pattern for mutable defaults. Used in `ProvenanceEntry`. Must use for `ProjectState.stories`.
- `BudgetState` uses `model_copy(update={...})` for updates since it's frozen.

**From Story 1.3 (Config System):**
- Config sub-models override `extra="ignore"` — but engine state models use `extra="forbid"` since they are internal state, not user-facing config.
- `RunConfig` construction requires at minimum `api=ApiConfig(claude_api_key="...")`.

**From Epic 1 Retro:**
- **BudgetState field mismatch** is the #1 pre-story resolution item. Task 0 addresses this.
- Story spec IS the agent's memory. Everything the dev agent needs is in this document.
- Pattern prevention beats pattern detection — known gotchas front-loaded above.

---

### Git Intelligence

Last 5 commits:
```
5cf30a9 retro: complete Epic 1 retrospective
03a8e08 feat(cli): implement Story 1.5 — CLI validate-setup command
e56b320 feat(cli): implement Story 1.4 — CLI init command
9295f8a fix(story-1.3): address review findings and finalize config system
54d2269 feat(core): implement Story 1.2 core foundation and tests
```

**Patterns established:**
- Commit prefix `feat(package):` for new features
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- All core types and config are stable — no pending changes expected

---

### Cross-Story Context (Epic 2 Stories That Build on 2.1)

Story 2.1 creates the skeleton; subsequent stories replace placeholder nodes with real implementations:

| Story | Replaces Node | Dependencies on 2.1 |
|---|---|---|
| 2.2: Context Injector | `preflight_node` (context assembly) | Consumes `StoryState.context_bundle` field |
| 2.3: Context Answerer | `preflight_node` (answerer lookup) | Adds answerer_rules to `ContextBundle` |
| 2.4: Agent Sandbox | Used inside `agent_dispatch_node` | Validates paths from `StoryState.project_root` |
| 2.5: Agent Invoker | `agent_dispatch_node` (real SDK call) | Writes to `StoryState.agent_output`, updates `BudgetState` |
| 2.6: Preflight Node | `preflight_node` (full impl) | Uses full context injection, writes checkpoint |
| 2.7: Dispatch CLI | Adds CLI entry point | Builds and invokes graph from `build_story_graph()` |

`validation_result: dict[str, Any] | None` will be refined to a proper `ValidationResult` model in Epic 3 (Story 3.3). For now, a dict placeholder is sufficient since the validate_node is a placeholder that doesn't produce real results.

---

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 1: LangGraph State Model]
- [Source: _spec/planning-artifacts/architecture.md — Async Patterns, Graph node return type pattern]
- [Source: _spec/planning-artifacts/architecture.md — Pydantic Model Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/architecture.md — Data Flow diagram]
- [Source: _spec/planning-artifacts/epics.md — Epic 2, Story 2.1 AC]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — BudgetState field discrepancy, Action Items 1-3]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — Current BudgetState definition]
- [Source: arcwright-ai/src/arcwright_ai/core/lifecycle.py — TaskState enum and VALID_TRANSITIONS]
- [Source: arcwright-ai/src/arcwright_ai/core/config.py — RunConfig model]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- TCH violations in nodes.py required keeping `StoryState` at runtime import (LangGraph resolves node function annotations via Python 3.14 `annotationlib` at graph construction time; TYPE_CHECKING guard caused NameError). Suppressed with `# noqa: TC001`.
- `CompiledStateGraph` has 4 generic type parameters (`StateT, ContextT, InputT, OutputT`); annotated as `CompiledStateGraph[StoryState, Any, Any, Any]` to satisfy mypy `--strict`.
- `# type: ignore[import-untyped]` comments removed from `langgraph` imports after confirming mypy resolves them without error on this platform.

### Completion Notes List

- ✅ Task 0: BudgetState reconciled in `core/types.py` — renamed fields to `estimated_cost: Decimal` and `max_cost: Decimal`, removed `token_ceiling`, added `max_invocations`. 19 core/types tests pass.
- ✅ Task 1: `StoryState` defined in `engine/state.py` with `frozen=False`, `extra="forbid"`, all required fields, and Google-style docstrings.
- ✅ Task 2: `ProjectState` defined in `engine/state.py` with `stories: list[StoryState] = Field(default_factory=list)` and all required fields.
- ✅ Task 3: 5 placeholder async node functions + 2 routing functions implemented in `engine/nodes.py` with structured logging and correct status transitions.
- ✅ Task 4: `build_story_graph()` implemented in `engine/graph.py` returning compiled `StateGraph[StoryState, ...]` with all 5 nodes and conditional edges.
- ✅ Task 5: `engine/__init__.py` updated with full alphabetically-sorted `__all__` including all public symbols.
- ✅ Tasks 6–8: 28 new tests across `test_state.py`, `test_nodes.py`, `test_graph.py` — all pass including end-to-end graph invocation.
- ✅ Task 9: All quality gates pass — ruff check clean, ruff format clean, mypy --strict 0 errors, 199/199 tests pass.
- ✅ Review fixes applied: budget-exceeded path now explicitly transitions to `TaskState.ESCALATED` before graph termination, and graph tests now assert conditional route mappings plus exceeded-path escalation behavior.

### File List

- `src/arcwright_ai/core/types.py` (modified — BudgetState field reconciliation)
- `src/arcwright_ai/engine/__init__.py` (modified — full public API exports)
- `src/arcwright_ai/engine/graph.py` (modified — build_story_graph() implementation)
- `src/arcwright_ai/engine/nodes.py` (modified — 5 node functions + 2 routing functions)
- `src/arcwright_ai/engine/state.py` (modified — StoryState and ProjectState models)
- `tests/test_core/test_types.py` (modified — BudgetState tests updated for Decimal fields)
- `tests/test_engine/test_graph.py` (created — graph construction and invocation tests)
- `tests/test_engine/test_nodes.py` (created — node function and routing function tests)
- `tests/test_engine/test_state.py` (created — StoryState and ProjectState model tests)

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted review)

### Date

2026-03-02

### Outcome

Approve

### Findings Resolved

- Fixed AC #4 alignment: budget-exceeded flow now explicitly marks story state as escalated in `budget_check_node` before routing to graph end.
- Added graph-level routing assertions for success/retry/escalated route maps.
- Added graph invocation coverage for budget-exceeded path to verify terminal status is `TaskState.ESCALATED`.
- Added node-level coverage for budget-exceeded transition in `budget_check_node`.
- Re-verified quality gates in project environment: `ruff check .`, `.venv/bin/python -m mypy --strict src/`, `.venv/bin/pytest -q`.

## Change Log

- 2026-03-02: Implemented Story 2.1 — LangGraph state models and graph skeleton. Reconciled BudgetState fields (Decimal types, rename, add max_invocations). Implemented StoryState, ProjectState, 5 placeholder nodes, 2 routing functions, build_story_graph(). Added 28 engine tests. All quality gates pass (ruff, mypy --strict, 199 tests).
- 2026-03-02: Senior code review fixes applied — budget exceeded now sets `TaskState.ESCALATED` in `budget_check_node`; added graph routing assertions and exceeded-path graph test; story status advanced to `done`.
