# Story 2.6: Preflight Node — Context Assembly & Dispatch Preparation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer dispatching a story,
I want the preflight graph node to resolve all context, prepare the execution environment, and write the context bundle checkpoint,
so that the agent receives complete context and provenance can trace exactly what information informed the implementation.

## Acceptance Criteria (BDD)

1. **Given** the preflight node in the LangGraph StateGraph **When** a story enters the preflight node **Then** the node invokes `context/injector.py`'s `build_context_bundle()` to resolve all references and build the `ContextBundle`.

2. **Given** a successful context resolution **When** the bundle is built **Then** the assembled bundle is stored in `StoryState.context_bundle`.

3. **Given** `StoryState.context_bundle` is populated **When** the context bundle is checkpointed **Then** it is serialised via `serialize_bundle_to_markdown()` and written as a checkpoint file to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/context-bundle.md` using async I/O via `write_text_async()`.

4. **Given** a story entering the preflight node with `status == QUEUED` **When** the preflight node executes successfully **Then** `StoryState.status` transitions from `queued` to `preflight` (at node entry) then to `running` (after context assembly completes).

5. **Given** context resolution fails (e.g., story file missing, unreadable) **When** `build_context_bundle()` raises `ContextError` **Then** the preflight node re-raises `ContextError` (exit code 3 — user-fixable per D6) without transitioning to `running`.

6. **Given** a preflight execution **When** context resolution completes (success or failure) **Then** structured log events are emitted: `engine.node.enter` at entry, `context.resolve` with `refs_found` and `refs_unresolved` counts (on success), and `engine.node.exit` at exit with current status.

7. **Given** the preflight node returns state **When** the caller inspects the returned value **Then** the node returns the full `StoryState` (not partial dicts) using `model_copy(update={...})` per the architecture pattern.

8. **Given** a checkpoint write **When** the run directory for the story does not exist yet **Then** the preflight node creates the directory structure: `.arcwright-ai/runs/<run-id>/stories/<story-slug>/` using `mkdir(parents=True, exist_ok=True)` before writing the checkpoint.

9. **Given** unit tests in `tests/test_engine/test_nodes.py` **When** `pytest tests/test_engine/test_nodes.py -v` is run **Then** tests verify: successful preflight with bundle written to disk, context error handling (ContextError raised → status stays PREFLIGHT), state transitions (QUEUED → PREFLIGHT → RUNNING), checkpoint file creation at the correct path, and structured log event emission.

10. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

11. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

12. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement real `preflight_node` in `engine/nodes.py` (AC: #1, #2, #4, #5, #6, #7)
  - [x] 1.1: Add imports at top of `engine/nodes.py`: `from arcwright_ai.context.injector import build_context_bundle, serialize_bundle_to_markdown` and `from arcwright_ai.core.io import write_text_async` and `from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, CONTEXT_BUNDLE_FILENAME` and `from arcwright_ai.core.exceptions import ContextError`
  - [x] 1.2: Guard `Path` import behind `TYPE_CHECKING` (TC003 ruff rule): `from pathlib import Path` inside `if TYPE_CHECKING:`
  - [x] 1.3: Replace the placeholder `preflight_node` body with real implementation:
    - Log `engine.node.enter` with `{"node": "preflight", "story": str(state.story_id)}`
    - Transition state: `QUEUED → PREFLIGHT` via `state.model_copy(update={"status": TaskState.PREFLIGHT})`
    - Call `await build_context_bundle(state.story_path, state.project_root)` to assemble the `ContextBundle`
    - Store bundle in state: `state.model_copy(update={"context_bundle": bundle, "status": TaskState.RUNNING})`
    - Build checkpoint path: `state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)`
    - Create checkpoint directory: `checkpoint_dir.mkdir(parents=True, exist_ok=True)` via `asyncio.to_thread()`
    - Serialise bundle: `serialize_bundle_to_markdown(bundle)`
    - Write checkpoint: `await write_text_async(checkpoint_dir / CONTEXT_BUNDLE_FILENAME, serialised)`
    - Log `engine.node.exit` with final status
    - Return the updated `StoryState`
  - [x] 1.4: Wrap `build_context_bundle` call in `try/except ContextError` — on `ContextError`, log `context.error` event with details and re-raise (don't swallow)
  - [x] 1.5: Add Google-style docstring with Args, Returns, Raises sections

- [x] Task 2: Add `asyncio` import to `engine/nodes.py` (AC: #8)
  - [x] 2.1: Add `import asyncio` to the stdlib imports block (needed for `asyncio.to_thread` to make `mkdir` async)

- [x] Task 3: Update tests in `tests/test_engine/test_nodes.py` (AC: #9)
  - [x] 3.1: Add imports: `from arcwright_ai.core.types import ContextBundle`, `from arcwright_ai.core.exceptions import ContextError`, `from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, CONTEXT_BUNDLE_FILENAME`
  - [x] 3.2: Create fixture `story_state_with_project(tmp_path)` that:
    - Creates a minimal project directory with `_spec/planning-artifacts/prd.md` and `_spec/planning-artifacts/architecture.md` (minimal content)
    - Creates a story file at the expected `story_path` with minimal story markdown containing acceptance criteria
    - Returns `StoryState` with `project_root=tmp_path`, `story_path` pointing to the created story file
  - [x] 3.3: Test `test_preflight_node_resolves_context_and_transitions_to_running` — uses `story_state_with_project`, awaits `preflight_node()`, asserts `result.status == TaskState.RUNNING` and `result.context_bundle is not None` and `result.context_bundle.story_content` is non-empty
  - [x] 3.4: Test `test_preflight_node_writes_checkpoint_file` — uses `story_state_with_project` + `tmp_path`, awaits `preflight_node()`, asserts checkpoint file exists at `tmp_path / DIR_ARCWRIGHT / DIR_RUNS / run_id / DIR_STORIES / story_id / CONTEXT_BUNDLE_FILENAME` and file content contains `"# Context Bundle"`
  - [x] 3.5: Test `test_preflight_node_raises_context_error_on_missing_story` — creates `StoryState` with non-existent `story_path`, asserts `pytest.raises(ContextError)` when `preflight_node()` is awaited
  - [x] 3.6: Test `test_preflight_node_transitions_queued_to_preflight_before_running` — monkeypatch `build_context_bundle` to capture the state's status at invocation time (or use a mock that raises to verify intermediate state), assert the intermediate PREFLIGHT state is reached
  - [x] 3.7: Test `test_preflight_node_creates_checkpoint_directory` — uses `tmp_path` with no pre-existing `.arcwright-ai/runs/` directory, asserts the directory is created by the node
  - [x] 3.8: Preserve ALL existing placeholder tests for `preflight_node` (update assertion if the real implementation changes behaviour — it transitions QUEUED → RUNNING same as before, but now also sets `context_bundle`)
  - [x] 3.9: Test `test_preflight_node_emits_structured_log_events` — uses `caplog` fixture, asserts log records contain `engine.node.enter`, `context.resolve`, and `engine.node.exit` events

- [x] Task 4: Validate all quality gates (AC: #10, #11, #12)
  - [x] 4.1: Run `ruff check .` — zero violations
  - [x] 4.2: Run `ruff format --check .` — no formatting diffs
  - [x] 4.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 4.4: Run `pytest tests/test_engine/ -v` — all new and existing tests pass
  - [x] 4.5: Run `pytest` — full test suite passes (no regressions)

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Emit `engine.node.exit` for the `ContextError` path before re-raising so preflight always has a terminal node event, matching AC #6 (`success or failure`). [arcwright-ai/src/arcwright_ai/engine/nodes.py:57-63]
- [x] [AI-Review][HIGH] Add an explicit test that validates the failure-path status contract (`ContextError` path remains at `PREFLIGHT`) rather than inferring only from logs. [arcwright-ai/tests/test_engine/test_nodes.py:228-264]
- [x] [AI-Review][MEDIUM] Reconcile Dev Agent Record File List with git reality (include currently changed story/sprint tracking artifacts) for accurate provenance and review traceability. [_spec/implementation-artifacts/2-6-preflight-node-context-assembly-and-dispatch-preparation.md:474-478]
- [x] [AI-Review][MEDIUM] Add a failure-path log assertion test covering terminal-node logging behavior (entry/error/exit) to prevent regressions in preflight observability. [arcwright-ai/tests/test_engine/test_nodes.py:246-299]

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `engine/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
`engine/` depends on `context/` (to call `build_context_bundle`) and `core/` (types, lifecycle, io, constants, exceptions). This is a **valid** dependency per the DAG — `engine` is allowed to import from domain packages. The `context/` package was already listed as a valid import target for `engine/`.

#### D1↔D4 Binding: Preflight IS Context Assembly
From the architecture document: *"The `preflight` node IS the dispatch-time context assembly described in Decision 4. These are the same architectural moment — not two separate mechanisms."*

The preflight node:
1. Calls `context/injector.py` to resolve references
2. Stores the assembled `ContextBundle` in LangGraph state
3. Writes the checkpoint to the run directory at the state transition boundary

Downstream nodes (`agent_dispatch`, `validate`) consume the bundle from state — they never re-resolve context.

#### Write Policy (D5)
LangGraph state is the authority during graph execution. Run directory files are **transition checkpoints only** — written after preflight completes, before the next node starts. No subsystem reads run directory files during active graph execution.

The checkpoint write happens at the PREFLIGHT → RUNNING boundary: after context assembly succeeds but before the node returns.

#### State Transition Contract
```
QUEUED → PREFLIGHT (at node entry)
PREFLIGHT → RUNNING (after successful context assembly + checkpoint write)
PREFLIGHT → ContextError raised (on context resolution failure — no transition to RUNNING)
```
The `VALID_TRANSITIONS` in `core/lifecycle.py` allows `PREFLIGHT → {RUNNING, ESCALATED}`. The node transitions to RUNNING on success. On `ContextError`, the exception propagates to the engine — the engine is responsible for deciding whether to escalate.

#### Graph Node Return Pattern
All LangGraph nodes return the full `StoryState` via `model_copy(update={...})` — never partial dicts. This is enforced across all nodes in the codebase.

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022. The `engine/nodes.py` `__all__` is already correctly sorted and exported. No change needed to `__all__` — `preflight_node` is already listed.

#### Async-First for All I/O
- `build_context_bundle()` is already async — it uses `asyncio.to_thread()` for file reads
- `write_text_async()` is async — uses `asyncio.to_thread()` for file writes
- Directory creation (`mkdir`) must be wrapped in `asyncio.to_thread()` to avoid blocking the event loop
- The node itself is `async def` — compatible with LangGraph async graph execution

#### Structured Logging — Not `print()`, Not Unstructured Strings
```python
logger.info("engine.node.enter", extra={"data": {"node": "preflight", "story": str(state.story_id)}})
logger.info("context.resolve", extra={"data": {"story": str(state.story_id), "refs_found": N, "refs_unresolved": M}})
logger.info("engine.node.exit", extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(updated.status)}})
```
**Never:** `logger.info(f"Preflight completed for {story_id}")` or `print(...)`.

#### Error Handling — Raise ContextError, Never Swallow
`ContextError` maps to exit code 3 (user-fixable). The preflight node catches it for logging but MUST re-raise. The engine is responsible for halt/escalation logic — the node does not make that decision.

---

### Existing Code to Consume (NOT Create)

These modules are already fully implemented from previous stories. The preflight node will **call** them — no modifications needed:

| Module | Function/Class | Source Story | Purpose |
|---|---|---|---|
| `context/injector.py` | `build_context_bundle(story_path, project_root, *, prd_path, architecture_path)` | Story 2.2 | Resolves FR/NFR/arch references, returns `ContextBundle` |
| `context/injector.py` | `serialize_bundle_to_markdown(bundle)` | Story 2.2 | Converts `ContextBundle` to checkpoint markdown |
| `core/io.py` | `write_text_async(path, content)` | Story 1.2 | Async file write via `asyncio.to_thread()` |
| `core/types.py` | `ContextBundle` | Story 1.2 | Frozen Pydantic model: `story_content`, `architecture_sections`, `domain_requirements`, `answerer_rules` |
| `core/lifecycle.py` | `TaskState` | Story 1.2 | `StrEnum` with states: `QUEUED`, `PREFLIGHT`, `RUNNING`, etc. |
| `core/exceptions.py` | `ContextError` | Story 1.2 | Raised on failed context resolution (exit code 3) |
| `core/constants.py` | `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`, `CONTEXT_BUNDLE_FILENAME` | Story 1.1 | Path constants for checkpoint directory |
| `engine/state.py` | `StoryState` | Story 2.1 | Mutable Pydantic model with `context_bundle: ContextBundle | None`, `status: TaskState` |

### `build_context_bundle` Signature (From context/injector.py)

```python
async def build_context_bundle(
    story_path: Path,
    project_root: Path,
    *,
    prd_path: Path | None = None,
    architecture_path: Path | None = None,
) -> ContextBundle:
```

The function auto-discovers `prd.md` and `architecture.md` under `project_root / _spec / planning-artifacts/` when the optional paths are `None`. The preflight node calls it with just `story_path` and `project_root` — no need to pass explicit PRD/architecture paths.

### `serialize_bundle_to_markdown` Output Format

```markdown
# Context Bundle

## Story Content

{bundle.story_content}

## Resolved Requirements

{bundle.domain_requirements}

## Architecture Sections

{bundle.architecture_sections}

## Answerer Rules

{bundle.answerer_rules}
```

### Checkpoint Path Construction

```python
from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, CONTEXT_BUNDLE_FILENAME

checkpoint_dir = state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
# e.g.: /project/.arcwright-ai/runs/20260302-143052-a7f3/stories/2-6-preflight-node/context-bundle.md
```

### Implementation Skeleton

```python
async def preflight_node(state: StoryState) -> StoryState:
    """Preflight node — resolves context, writes checkpoint, transitions to RUNNING.

    Invokes the context injector to build a ContextBundle from the story's
    BMAD artifacts, stores the bundle in state, serialises it to the run
    directory as a provenance checkpoint, and transitions status from
    QUEUED → PREFLIGHT → RUNNING.

    Args:
        state: Current story execution state (expected status: QUEUED).

    Returns:
        Updated state with context_bundle populated and status set to RUNNING.

    Raises:
        ContextError: If the story file is missing or context resolution fails.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "preflight", "story": str(state.story_id)}})

    # Transition: QUEUED → PREFLIGHT
    state = state.model_copy(update={"status": TaskState.PREFLIGHT})

    # Resolve context
    bundle = await build_context_bundle(state.story_path, state.project_root)

    # Build checkpoint path and write
    checkpoint_dir = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
    serialised = serialize_bundle_to_markdown(bundle)
    await write_text_async(checkpoint_dir / CONTEXT_BUNDLE_FILENAME, serialised)

    # Transition: PREFLIGHT → RUNNING
    updated = state.model_copy(update={"context_bundle": bundle, "status": TaskState.RUNNING})

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "preflight", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated
```

**Important:** The `try/except ContextError` block should wrap ONLY the `build_context_bundle` call — not the checkpoint write. A checkpoint write failure is an I/O issue (likely `RunError` territory), not a context resolution issue.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented. `engine/nodes.py` already has its exports — no change needed.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. Not directly relevant here — no new Pydantic models.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. Not directly relevant here — no config models.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. `tests/test_engine/__init__.py` already exists.

---

### Previous Story Intelligence (Story 2.5 Learnings)

**From Story 2.5 (Agent Invoker — Claude Code SDK Integration):**

- `InvocationResult` is a frozen dataclass — the preflight node does NOT interact with it (that's Story 2.7 scope)
- `build_prompt(bundle: ContextBundle) -> str` converts a `ContextBundle` to an SDK prompt — called by the `agent_dispatch` node (Story 2.7), NOT by preflight
- All SDK imports are lazy (inside functions) for testability via monkeypatching
- `asyncio_mode=auto` in `pyproject.toml` — `@pytest.mark.asyncio` not needed on async tests **BUT** existing tests in `test_nodes.py` use `@pytest.mark.asyncio` explicitly — be consistent with existing file convention
- `MockSDKClient` is the canonical test fixture for Stories 2.7+ — not needed for this story

**From Story 2.4 (Agent Sandbox):**
- `@dataclass(frozen=True)` pattern for immutable data holders
- `Path` guarded behind `TYPE_CHECKING` per TC003 ruff rule
- Defense-in-depth: validate inputs even when callers are expected to be correct
- Structured logging pattern: `logger.info("event.name", extra={"data": {...}})`

**From Story 2.2 (Context Injector):**
- `build_context_bundle()` is fully async — uses `asyncio.gather()` internally for parallel reference resolution
- `ContextError` is raised when the story file cannot be read — the only "hard error" case
- Missing PRD/architecture files result in `context.unresolved` log events — NOT errors
- `serialize_bundle_to_markdown()` is synchronous — no need to `await` it
- The function already emits `context.resolve` structured log event with `refs_found` and `refs_unresolved`

**From Story 2.3 (Context Answerer):**
- `@dataclass(frozen=True)` pattern consistently used for immutable internal data
- Module-level compiled regex constants for pattern matching

**From Story 2.1 (LangGraph State Models & Graph Skeleton):**
- `StoryState` is mutable (`frozen=False`) — `model_copy(update={...})` creates a new instance but the model allows mutation
- All graph nodes have the same signature: `async def node_name(state: StoryState) -> StoryState`
- Existing tests in `test_nodes.py` use a `make_story_state` fixture that returns a minimal `StoryState`
- Existing tests use `@pytest.mark.asyncio` decorator explicitly (not relying on `asyncio_mode=auto`)

---

### Project Structure Notes

**Files to modify:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/engine/nodes.py` | MODIFY | Replace placeholder `preflight_node` with real implementation; add new imports |
| `tests/test_engine/test_nodes.py` | MODIFY | Add new preflight tests with real filesystem assertions; preserve existing tests |

**Files NOT touched** (no changes needed):
- `context/injector.py` — fully implemented in Story 2.2, consumed as-is
- `core/types.py` — `ContextBundle` already defined
- `core/io.py` — `write_text_async` already defined
- `core/exceptions.py` — `ContextError` already defined
- `core/constants.py` — all path constants already defined
- `core/lifecycle.py` — `TaskState` already defined
- `engine/state.py` — `StoryState` already has `context_bundle` field
- `engine/graph.py` — graph already has `preflight` node wired
- `engine/__init__.py` — already exports `preflight_node`
- `agent/` — no agent integration in this story (Story 2.7 scope)
- `cli/` — no CLI changes

**Alignment with architecture:**
- `engine/nodes.py` → `preflight_node` matches architecture's node list
- D1 mapping: "preflight assembles context payload into LangGraph state, downstream nodes consume"
- D4 mapping: "Dispatch-time assembly in preflight node. Strict regex-only reference resolution."
- D5 mapping: "Write policy — checkpoint written at state transition boundary"
- D6 mapping: "ContextError → exit code 3 (user-fixable)"
- D8 mapping: Structured logging for `engine.node.enter`, `context.resolve`, `engine.node.exit`
- FR16 mapping: `context/injector.py` — "Read BMAD artifacts, inject into agent prompt"
- FR18 mapping: `context/injector.py` — "Resolve story dependencies and artifact refs"

---

### Cross-Story Context (Epic 2 Stories That Interact with 2.6)

| Story | Relationship to 2.6 | Impact |
|---|---|---|
| 2.1: LangGraph State Models | Provides `StoryState` with `context_bundle` field and graph skeleton | Preflight node is already wired into the graph; this story replaces the placeholder body |
| 2.2: Context Injector | Provides `build_context_bundle()` and `serialize_bundle_to_markdown()` | Preflight node is the primary consumer of the injector — calls it to resolve all context |
| 2.3: Context Answerer | Answerer rules loaded via `build_context_bundle()` internally | Answerer output is part of the `ContextBundle.answerer_rules` field — transparent to preflight |
| 2.5: Agent Invoker | `build_prompt(bundle)` consumes the `ContextBundle` assembled here | The agent dispatch node (Story 2.7) reads `state.context_bundle` and calls `build_prompt()` |
| 2.7: Agent Dispatch Node | Reads `state.context_bundle` for prompt construction | Story 2.7 depends on preflight having populated the bundle — this story is a prerequisite |
| 4.1: Provenance Recorder | Reads `context-bundle.md` checkpoint for provenance trail | The checkpoint written by preflight is consumed by the provenance system in Epic 4 |

**Important note for Story 2.7 handoff:** After this story, the preflight node populates `state.context_bundle` with a real `ContextBundle`. Story 2.7's `agent_dispatch_node` can then call `build_prompt(state.context_bundle)` to construct the SDK prompt. The handoff contract is the `StoryState.context_bundle` field.

---

### Git Intelligence

Last 5 commits:
```
fe1eec7 feat(agent): implement Story 2.5 Claude Code SDK invoker integration
ff813cc docs(story): create Story 2.5 — Agent Invoker, Claude Code SDK Integration
edc85eb fix(agent): harden sandbox relative-path resolution and finalize Story 2.4
3d16d16 feat(agent): implement Story 2.4 — Agent Sandbox Path Validation Layer
c404c4c feat(context): implement Story 2.3 — Context Answerer, Static Rule Lookup Engine
```

**Patterns established:**
- Commit prefix: `feat(engine):` for new feature in engine package — use this prefix for this story
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- Existing node tests in `test_engine/test_nodes.py` — extend, don't replace

**Files from previous stories that are relevant:**
- `src/arcwright_ai/engine/nodes.py` — current placeholder `preflight_node` to replace
- `src/arcwright_ai/engine/state.py` — `StoryState` with `context_bundle: ContextBundle | None`
- `src/arcwright_ai/context/injector.py` — `build_context_bundle()`, `serialize_bundle_to_markdown()`
- `src/arcwright_ai/core/io.py` — `write_text_async()`
- `src/arcwright_ai/core/constants.py` — `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`, `CONTEXT_BUNDLE_FILENAME`
- `src/arcwright_ai/core/exceptions.py` — `ContextError`
- `tests/test_engine/test_nodes.py` — existing preflight test to preserve/extend
- `tests/conftest.py` — `tmp_project` fixture

---

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
async def test_preflight_node_resolves_context_and_transitions_to_running(): ...
async def test_preflight_node_writes_checkpoint_file(): ...
async def test_preflight_node_raises_context_error_on_missing_story(): ...
```

**Async tests:** Existing tests in `test_nodes.py` use `@pytest.mark.asyncio` explicitly — maintain this convention for consistency within the file.

**Fixture pattern for filesystem tests:**
```python
@pytest.fixture
def story_state_with_project(tmp_path: Path) -> StoryState:
    """Create a StoryState backed by a real project directory with BMAD artifacts."""
    spec_dir = tmp_path / "_spec" / "planning-artifacts"
    spec_dir.mkdir(parents=True)
    (spec_dir / "prd.md").write_text("# PRD\n\n## FR1\nTest requirement", encoding="utf-8")
    (spec_dir / "architecture.md").write_text("# Architecture\n\n### Decision 1\nTest decision", encoding="utf-8")

    story_path = tmp_path / "_spec" / "implementation-artifacts" / "2-6-preflight.md"
    story_path.parent.mkdir(parents=True, exist_ok=True)
    story_path.write_text(
        "# Story 2.6\n\n## Acceptance Criteria\n\n1. Test AC\n\n## Dev Notes\n\nFR1, Decision 1\n",
        encoding="utf-8",
    )

    return StoryState(
        story_id=StoryId("2-6-preflight-node"),
        epic_id=EpicId("epic-2"),
        run_id=RunId("20260302-143052-a7f3"),
        story_path=story_path,
        project_root=tmp_path,
        config=make_run_config(),
    )
```

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries:
```python
assert result.status == TaskState.RUNNING
assert result.context_bundle is not None
assert result.context_bundle.story_content != ""

with pytest.raises(ContextError):
    await preflight_node(bad_state)
```

**Test isolation:** Each test creates its own state via fixtures. No shared mutable state between tests.

---

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision-1 — Hybrid preflight context assembly, D1↔D4 binding]
- [Source: _spec/planning-artifacts/architecture.md#Decision-4 — Dispatch-time assembly, strict regex, no fuzzy matching]
- [Source: _spec/planning-artifacts/architecture.md#Decision-5 — Run directory schema, checkpoint write policy]
- [Source: _spec/planning-artifacts/architecture.md#Decision-6 — ContextError → exit code 3, user-fixable]
- [Source: _spec/planning-artifacts/architecture.md#Decision-8 — Structured logging JSONL events]
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG — engine depends on context + core]
- [Source: _spec/planning-artifacts/architecture.md#Async-Patterns — asyncio.to_thread, graph node return pattern]
- [Source: _spec/planning-artifacts/architecture.md#Project-Structure — engine/nodes.py node implementations]
- [Source: _spec/planning-artifacts/epics.md#Story-2.6 — Acceptance criteria, story definition]
- [Source: _spec/planning-artifacts/prd.md#FR16 — Read BMAD artifacts, inject into agent prompt]
- [Source: _spec/planning-artifacts/prd.md#FR18 — Resolve story dependencies and artifact refs]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — Known pitfalls, Action Items 1-3]
- [Source: _spec/implementation-artifacts/2-5-agent-invoker-claude-code-sdk-integration.md — Testing patterns, structured logging, async conventions]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — Current placeholder preflight_node]
- [Source: arcwright-ai/src/arcwright_ai/engine/state.py — StoryState with context_bundle field]
- [Source: arcwright-ai/src/arcwright_ai/context/injector.py — build_context_bundle, serialize_bundle_to_markdown]
- [Source: arcwright-ai/src/arcwright_ai/core/io.py — write_text_async]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, CONTEXT_BUNDLE_FILENAME]
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py — ContextError hierarchy]
- [Source: arcwright-ai/src/arcwright_ai/core/lifecycle.py — TaskState, VALID_TRANSITIONS]
- [Source: arcwright-ai/tests/test_engine/test_nodes.py — Existing preflight placeholder tests]
- [Source: arcwright-ai/tests/conftest.py — tmp_project fixture]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Ruff SIM117: Nested `with` statements in `test_preflight_node_transitions_queued_to_preflight_before_running` flattened to single `with caplog.at_level(logging.INFO), pytest.raises(ContextError):` — fixed immediately.
- `test_graph.py` end-to-end integration tests failed after preflight became real I/O: added `graph_project_state` fixture with real BMAD artifacts to all three graph invocation tests.

### Completion Notes List

- Replaced placeholder `preflight_node` in `engine/nodes.py` with full implementation: QUEUED→PREFLIGHT state transition, `build_context_bundle()` call, `try/except ContextError` with structured log, checkpoint directory creation via `asyncio.to_thread(mkdir)`, `serialize_bundle_to_markdown()` + `write_text_async()` for checkpoint write, PREFLIGHT→RUNNING transition, `engine.node.exit` log.
- Added 6 new tests in `tests/test_engine/test_nodes.py` covering: successful context resolution + RUNNING status, checkpoint file written to correct path, `ContextError` raised on missing story, PREFLIGHT intermediate state verified via monkeypatched exception path + caplog, directory creation from scratch, and structured log event emission.
- Updated `tests/test_engine/test_graph.py`: all three end-to-end graph invocation tests now use a `graph_project_state` fixture backed by a real `tmp_path` project directory — required because the real `preflight_node` performs filesystem I/O.
- All quality gates pass: `ruff check .` zero violations, `ruff format --check .` zero diffs, `mypy --strict src/` zero errors, `pytest` 283/283 passed.

### File List

- `src/arcwright_ai/engine/nodes.py` — replaced placeholder `preflight_node` with real implementation; added `asyncio`, `TYPE_CHECKING`, `build_context_bundle`, `serialize_bundle_to_markdown`, `CONTEXT_BUNDLE_FILENAME`, `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`, `ContextError`, `write_text_async` imports
- `tests/test_engine/test_nodes.py` — added `story_state_with_project` fixture; updated existing preflight test to use real fs fixture; added 6 new preflight tests; added `logging`, `ContextBundle`, `ContextError`, `CONTEXT_BUNDLE_FILENAME`, `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES` imports
- `tests/test_engine/test_graph.py` — added `graph_project_state` fixture; updated 3 end-to-end graph invocation tests to use real fs fixture
- `_spec/implementation-artifacts/2-6-preflight-node-context-assembly-and-dispatch-preparation.md` — updated with senior developer review findings and follow-up tasks
- `_spec/implementation-artifacts/sprint-status.yaml` — synced story status to `in-progress` after review findings

## Senior Developer Review (AI)

### Reviewer

Ed (GPT-5.3-Codex) — 2026-03-02

### Outcome

Approved

### Summary

- Verified implementation and tests against ACs with focused execution of `pytest tests/test_engine/test_nodes.py -v` and `pytest tests/test_engine/test_graph.py -v` (both passing).
- Implemented all 2 HIGH and 2 MEDIUM follow-up fixes and revalidated with focused test/lint/type checks.
- Story status moved to `done` after review findings were fully addressed.

### Findings

1. **[HIGH] AC #6 mismatch on failure-path exit logging**  
  AC #6 requires terminal preflight logging semantics across success/failure (`engine.node.enter` + terminal `engine.node.exit`, with `context.resolve` on success). The current `ContextError` branch logs `context.error` and re-raises without an `engine.node.exit` event.  
  Evidence: `arcwright-ai/src/arcwright_ai/engine/nodes.py` (`try/except` around `build_context_bundle`) and AC text in this story (`success or failure`).

2. **[HIGH] AC #9 verification gap for failure status contract**  
  AC #9 explicitly states tests should verify `ContextError raised → status stays PREFLIGHT`. Current tests assert the exception and infer status through logged extra data, but do not directly assert state contract behavior in a dedicated failure-path status assertion.  
  Evidence: `arcwright-ai/tests/test_engine/test_nodes.py` (`test_preflight_node_raises_context_error_on_missing_story`, `test_preflight_node_transitions_queued_to_preflight_before_running`).

3. **[MEDIUM] Story File List / git discrepancy**  
  Git includes modified tracking/documentation artifacts not reflected in the original File List, reducing traceability of what actually changed during review cycle.  
  Evidence: git changed files include `_spec/implementation-artifacts/sprint-status.yaml` and this story file.

4. **[MEDIUM] Missing dedicated failure-path terminal logging test**  
  Existing structured logging test covers success path only; there is no explicit assertion that failure path emits the required terminal event sequence. This leaves AC #6 behavior vulnerable to regression.  
  Evidence: `arcwright-ai/tests/test_engine/test_nodes.py::test_preflight_node_emits_structured_log_events`.

## Change Log

- 2026-03-02: Story 2.6 implemented — real `preflight_node` replaces placeholder; QUEUED→PREFLIGHT→RUNNING state transitions; context bundle assembled via `build_context_bundle()`; checkpoint written to `.arcwright-ai/runs/<run-id>/stories/<story-id>/context-bundle.md`; 6 new unit tests added; graph integration tests updated with real fs fixtures; all 283 tests pass; `ruff`, `mypy --strict`, `ruff format` all green.
- 2026-03-02: Senior developer AI code review completed (story 2.6). Outcome: Changes Requested. Added 4 review follow-up tasks (2 HIGH, 2 MEDIUM), updated status to `in-progress`, and synced sprint tracking.
- 2026-03-02: Addressed all AI review follow-ups: added `engine.node.exit` on preflight `ContextError` path, expanded failure-path assertions (status-transition contract + terminal log sequence), and revalidated with `pytest tests/test_engine/test_nodes.py -v`, `ruff check`, and `mypy --strict src/`. Story approved and set to `done`.
