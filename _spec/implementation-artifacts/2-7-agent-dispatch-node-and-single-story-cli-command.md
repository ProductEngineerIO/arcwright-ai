# Story 2.7: Agent Dispatch Node & Single Story CLI Command

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer,
I want to run `arcwright-ai dispatch --story STORY-N.N` and have the full preflight → budget_check → agent_dispatch pipeline execute for a single story,
so that I can verify the core execution loop works end-to-end.

## Acceptance Criteria (BDD)

1. **Given** the LangGraph StateGraph with implemented preflight and agent_dispatch nodes **When** I run `arcwright-ai dispatch --story 2.1` **Then** the CLI parses the story identifier and loads the corresponding story file from the `_spec/implementation-artifacts/` directory by globbing for `{epic_num}-{story_num}-*.md`.

2. **Given** a valid story file and loaded configuration **When** the engine dispatches the story **Then** the engine builds and runs the StateGraph for the single story: preflight → budget_check → agent_dispatch → validate → commit.

3. **Given** the full graph pipeline **When** the preflight node completes **Then** the preflight node assembles context (already implemented in Story 2.6), the budget_check node passes (first run, no budget consumed), and the agent_dispatch node invokes the Claude Code SDK via `invoke_agent()`.

4. **Given** a successful agent invocation **When** the agent returns output **Then** agent output is written to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/agent-output.md` via `write_text_async()`.

5. **Given** a successful agent invocation returning token usage **When** the agent_dispatch node processes the `InvocationResult` **Then** `StoryState.budget` is updated with: `invocation_count` incremented by 1, `total_tokens` incremented by `tokens_input + tokens_output`, `estimated_cost` incremented by `total_cost`.

6. **Given** cli dispatch execution **When** the story starts and completes **Then** CLI output shows story start, agent invocation, and completion status using Rich/Typer formatting to stderr.

7. **Given** a run with JSONL logging configured **When** the pipeline executes **Then** structured JSONL events are written to `.arcwright-ai/runs/<run-id>/log.jsonl` for: `run.start`, `story.start`, `context.resolve`, `agent.dispatch`, `agent.response` — using the D8 envelope format (`ts`, `event`, `level`, `data`).

8. **Given** successful agent completion **When** the validate and commit placeholders pass through **Then** exit code is 0 (validation not yet wired — Epic 3 scope).

9. **Given** the CLI dispatch command **When** invoked with `--epic EPIC-N` (e.g., `--epic 2`) **Then** it dispatches all stories in the epic sequentially in dependency order per FR1/FR3 by finding all `{epic_num}-*-*.md` files in implementation-artifacts sorted by story number (basic sequential iteration only — no pre-dispatch confirmation, scope validation, or cost estimates; full epic dispatch UX is Story 5.1).

10. **Given** a mock SDK client **When** running integration tests **Then** the integration test verifies the full CLI → engine → context → agent pipeline with `MockSDKClient`, asserting: story state reaches SUCCESS, agent output is written to checkpoint, budget is updated, and JSONL log events are emitted.

11. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

12. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement real `agent_dispatch_node` in `engine/nodes.py` (AC: #3, #4, #5, #7)
  - [x] 1.1: Add imports at top of `engine/nodes.py`: `from arcwright_ai.agent.invoker import InvocationResult, invoke_agent` and `from arcwright_ai.agent.prompt import build_prompt` and `from arcwright_ai.agent.sandbox import validate_path` and `from arcwright_ai.core.constants import AGENT_OUTPUT_FILENAME` and `from arcwright_ai.core.types import BudgetState` (already imported for route_budget_check)
  - [x] 1.2: Replace the placeholder `agent_dispatch_node` body with real implementation:
    - Log `engine.node.enter` with `{"node": "agent_dispatch", "story": str(state.story_id)}`
    - Guard: if `state.context_bundle is None`, raise `ContextError("agent_dispatch_node requires context_bundle from preflight")`
    - Build prompt: `prompt = build_prompt(state.context_bundle)`
    - Log `agent.dispatch` with `{"story": str(state.story_id), "model": state.config.model.version, "prompt_length": len(prompt)}`
    - Call `result = await invoke_agent(prompt, model=state.config.model.version, cwd=state.project_root, sandbox=validate_path)`
    - (`agent.response` event is already emitted inside `invoke_agent` — do NOT duplicate)
    - Store output: update state with `agent_output=result.output_text`
    - Update budget: create new `BudgetState` with incremented values from `result`
    - Build checkpoint path: same pattern as preflight — `state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)`
    - Ensure directory exists: `await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)`
    - Write checkpoint: `await write_text_async(checkpoint_dir / AGENT_OUTPUT_FILENAME, result.output_text)`
    - Transition: RUNNING → VALIDATING via `model_copy(update={...})`
    - Log `engine.node.exit` with final status
    - Return full `StoryState`
  - [x] 1.3: Wrap `invoke_agent` call in `try/except AgentError` — on `AgentError`, log `agent.error` and `engine.node.exit` events with current status and re-raise (following the preflight ContextError pattern from Story 2.6)
  - [x] 1.4: Add Google-style docstring with Args, Returns, Raises sections

- [x] Task 2: Implement JSONL file handler for run logging (AC: #7)
  - [x] 2.1: Create `_JsonlFileHandler` class (private) in `cli/dispatch.py` — subclass `logging.FileHandler`
    - Override `emit(record)` to write JSON objects with D8 envelope: `{"ts": ISO8601, "event": record.getMessage(), "level": record.levelname.lower(), "data": getattr(record, "data", {})}`
    - Use `json.dumps()` + newline for each entry
    - Wrap in `try/except` with `self.handleError(record)` fallback
  - [x] 2.2: Create `_setup_run_logging(run_dir: Path) -> _JsonlFileHandler` helper in `cli/dispatch.py`
    - Instantiates handler pointing to `run_dir / LOG_FILENAME`
    - Attaches handler to `logging.getLogger("arcwright_ai")` so all child loggers' events propagate
    - Returns the handler reference for cleanup

- [x] Task 3: Implement run ID generation and story file discovery (AC: #1)
  - [x] 3.1: Create `_generate_run_id() -> RunId` helper in `cli/dispatch.py`
    - Format: `datetime.now(timezone.utc).strftime(RUN_ID_DATETIME_FORMAT)` + `-` + `uuid.uuid4().hex[:4]`
    - Uses `RUN_ID_DATETIME_FORMAT` from `core/constants.py`
    - Returns `RunId(formatted_string)`
  - [x] 3.2: Create `_find_story_file(story_spec: str, artifacts_dir: Path) -> tuple[Path, StoryId, EpicId]` helper in `cli/dispatch.py`
    - Parse `story_spec`: support formats `"2.7"`, `"2-7"`, `"2.7"` → extract `epic_num`, `story_num`
    - Glob for `artifacts_dir / f"{epic_num}-{story_num}-*.md"`
    - If no match: raise `ProjectError(f"No story file found for {story_spec}")`
    - If match: extract `StoryId` from filename stem (e.g., `"2-7-agent-dispatch-node-and-single-story-cli-command"`)
    - Return `(path, StoryId(stem), EpicId(f"epic-{epic_num}"))`
  - [x] 3.3: Create `_find_epic_stories(epic_spec: str, artifacts_dir: Path) -> list[tuple[Path, StoryId, EpicId]]` helper in `cli/dispatch.py`
    - Parse `epic_spec`: support formats `"2"`, `"epic-2"` → extract `epic_num`
    - Glob for `artifacts_dir / f"{epic_num}-*-*.md"` (exclude files matching `epic-*-retrospective*`)
    - Sort results by story number (second element of filename)
    - If no matches: raise `ProjectError(f"No story files found for epic {epic_spec}")`
    - Return sorted list of `(path, StoryId, EpicId)` tuples

- [x] Task 4: Implement CLI dispatch command in `cli/dispatch.py` (AC: #1, #2, #6, #8, #9)
  - [x] 4.1: Define `dispatch_command` with Typer options:
    ```python
    def dispatch_command(
        story: Annotated[str | None, typer.Option("--story", help="Story identifier (e.g., 2.7 or 2-7)")] = None,
        epic: Annotated[str | None, typer.Option("--epic", help="Epic identifier (e.g., 2 or epic-2)")] = None,
    ) -> None:
    ```
    - Validate: exactly one of `--story` or `--epic` must be provided
    - Delegate to `asyncio.run(_dispatch_story_async(...))` or `asyncio.run(_dispatch_epic_async(...))`
  - [x] 4.2: Implement `async _dispatch_story_async(story_spec: str) -> int`:
    - Discover `project_root` via `Path.cwd()` (or walk up looking for `.arcwright-ai/` or `_spec/`)
    - Load config: `load_config(project_root)` — wrap in try/except `ConfigError`
    - Find story file: `_find_story_file(story_spec, artifacts_dir)`
    - Generate run ID: `_generate_run_id()`
    - Create run directory: `run_dir = project_root / DIR_ARCWRIGHT / DIR_RUNS / str(run_id)` + `mkdir(parents=True, exist_ok=True)`
    - Set up JSONL logging: `handler = _setup_run_logging(run_dir)`
    - Emit `run.start` log event (via logger)
    - Emit `story.start` log event
    - Rich/Typer output to stderr: story ID, run ID, starting
    - Create initial `StoryState`:
      ```python
      initial_state = StoryState(
          story_id=story_id,
          epic_id=epic_id,
          run_id=run_id,
          story_path=story_path,
          project_root=project_root,
          config=config,
      )
      ```
    - Build graph: `graph = build_story_graph()`
    - Invoke: `result = await graph.ainvoke(initial_state)`
    - Extract final status from result
    - Rich/Typer output: completion status, cost summary, run path
    - Clean up: remove JSONL handler from logger
    - Return exit code (0 for success)
  - [x] 4.3: Implement `async _dispatch_epic_async(epic_spec: str) -> int`:
    - Same setup as story dispatch (config, project root)
    - Find all stories: `_find_epic_stories(epic_spec, artifacts_dir)`
    - Generate single run ID for the entire epic
    - Set up run directory and JSONL logging
    - Emit `run.start`
    - For each story in order:
      - Emit `story.start`
      - Create `StoryState` with shared run_id and config
      - Build and invoke graph
      - On success: continue to next story
      - On exception: report error, exit with appropriate code
    - Clean up logging handler
    - Return exit code
  - [x] 4.4: Add error handling and exit code mapping:
    - `ContextError` → exit code 3 (EXIT_CONFIG)
    - `AgentError` → exit code 2 (EXIT_AGENT)
    - `ConfigError` → exit code 3 (EXIT_CONFIG)
    - `ArcwrightError` → exit code 5 (EXIT_INTERNAL)
    - Unhandled → exit code 5 (EXIT_INTERNAL)
  - [x] 4.5: Add Rich/Typer formatting for user output to stderr per D8:
    - Story start: `typer.echo(f"▶ Dispatching story {story_id}...", err=True)`
    - Agent invocation: `typer.echo(f"  🤖 Agent invoked ({model})", err=True)`
    - Completion: `typer.echo(f"✓ Story {story_id} completed (status: {status})", err=True)`
    - Cost: `typer.echo(f"  💰 Cost: ${cost} | Tokens: {tokens}", err=True)`
    - Run path: `typer.echo(f"  📁 Run: {run_dir}", err=True)`

- [x] Task 5: Register dispatch command in `cli/app.py` (AC: #1)
  - [x] 5.1: Add import: `from arcwright_ai.cli.dispatch import dispatch_command`
  - [x] 5.2: Register: `app.command(name="dispatch")(dispatch_command)`

- [x] Task 6: Update tests in `tests/test_engine/test_nodes.py` (AC: #3, #4, #5)
  - [x] 6.1: Add agent_dispatch_node test fixture: `dispatch_ready_state(story_state_with_project)` that:
    - Runs preflight_node on the story_state_with_project to populate context_bundle
    - Monkeypatches `invoke_agent` to return a mock `InvocationResult` (avoids real SDK)
    - Returns the state with status RUNNING and context_bundle populated
  - [x] 6.2: Test `test_agent_dispatch_node_invokes_sdk_and_transitions_to_validating` — asserts result.status == VALIDATING and result.agent_output is not None
  - [x] 6.3: Test `test_agent_dispatch_node_updates_budget` — asserts result.budget.invocation_count == 1, total_tokens > 0, estimated_cost > 0
  - [x] 6.4: Test `test_agent_dispatch_node_writes_agent_output_checkpoint` — asserts checkpoint file exists at expected path with expected content
  - [x] 6.5: Test `test_agent_dispatch_node_raises_context_error_when_bundle_missing` — creates state with context_bundle=None, asserts ContextError raised
  - [x] 6.6: Test `test_agent_dispatch_node_raises_agent_error_on_sdk_failure` — monkeypatches invoke_agent to raise AgentError, asserts it propagates
  - [x] 6.7: Test `test_agent_dispatch_node_emits_structured_log_events` — caplog captures `engine.node.enter`, `agent.dispatch`, `engine.node.exit`

- [x] Task 7: Create `tests/test_cli/test_dispatch.py` (AC: #1, #6, #8, #9, #10)
  - [x] 7.1: Test `test_dispatch_story_parses_story_identifier` — test `_find_story_file` with various formats ("2.7", "2-7")
  - [x] 7.2: Test `test_dispatch_story_raises_on_missing_story` — test `_find_story_file` with nonexistent story
  - [x] 7.3: Test `test_find_epic_stories_returns_sorted_list` — test `_find_epic_stories` sorting
  - [x] 7.4: Test `test_generate_run_id_format` — test `_generate_run_id` returns valid format
  - [x] 7.5: Test `test_jsonl_handler_writes_correct_format` — test `_JsonlFileHandler` output format
  - [x] 7.6: Integration test `test_dispatch_story_end_to_end_with_mock_sdk` — uses `tmp_path` project fixture, monkeypatches `invoke_agent`, invokes CLI dispatch command via Typer `CliRunner`, asserts: exit code 0, agent output checkpoint written, JSONL log events present, budget updated
  - [x] 7.7: Test `test_dispatch_requires_story_or_epic_option` — neither option → error
  - [x] 7.8: Test `test_dispatch_rejects_both_story_and_epic` — both options → error

- [x] Task 8: Update graph integration tests in `tests/test_engine/test_graph.py` (AC: #2, #3)
  - [x] 8.1: Update `test_graph_success_path_end_to_end` to monkeypatch `invoke_agent` with mock, verify the full path with real agent dispatch now invoking the SDK (agent_dispatch is no longer a placeholder)

- [x] Task 9: Validate all quality gates (AC: #11, #12, #13)
  - [x] 9.1: Run `ruff check .` — zero violations
  - [x] 9.2: Run `ruff format --check .` — no formatting diffs
  - [x] 9.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 9.4: Run `pytest tests/test_engine/ -v` — all new and existing tests pass
  - [x] 9.5: Run `pytest tests/test_cli/ -v` — all new and existing tests pass
  - [x] 9.6: Run `pytest` — full test suite passes (no regressions)

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Map non-success terminal graph states (`ESCALATED`, `RETRY`) to non-zero exits in `_dispatch_story_async` instead of always returning success. [arcwright-ai/src/arcwright_ai/cli/dispatch.py]
- [x] [AI-Review][HIGH] Stop epic dispatch on non-success terminal state from `graph.ainvoke()` (currently treated as success when no exception is raised). [arcwright-ai/src/arcwright_ai/cli/dispatch.py]
- [x] [AI-Review][MEDIUM] Strengthen AC10 integration assertions to verify required JSONL events (`context.resolve`, `agent.dispatch`, `agent.response`) and budget update evidence. [arcwright-ai/tests/test_cli/test_dispatch.py]
- [x] [AI-Review][MEDIUM] Restore logger level after `_setup_run_logging` to avoid leaking DEBUG level across subsequent commands/tests. [arcwright-ai/src/arcwright_ai/cli/dispatch.py]
- [x] [AI-Review][MEDIUM] Align Dev Agent Record `File List` with git reality (missing tracked changes such as `arcwright-ai/pyproject.toml` and this story artifact). [_spec/implementation-artifacts/2-7-agent-dispatch-node-and-single-story-cli-command.md]

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `engine/` and `cli/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
- `engine/nodes.py` importing from `agent/` (invoker, prompt, sandbox) is **valid** per the DAG — `engine` depends on all domain packages.
- `cli/dispatch.py` importing from `engine/` and `core/` is **valid** — `cli` depends on `engine` + `core`.
- `cli/dispatch.py` must NOT import directly from `agent/`, `context/`, or other domain packages — engine mediates all domain interactions.

#### D1: State Model — Hybrid Preflight + Downstream Consumption
The `preflight` node assembles context into `StoryState.context_bundle`. The `agent_dispatch` node consumes it to build the prompt. No re-resolution. The bundle flows through LangGraph state.

#### D2: Retry & Halt Strategy
- **Agent errors are immediate halts** — `AgentError` from the SDK propagates as an exception, not a retry signal.
- **Validation retries only** — retry logic is in the validate → budget_check loop (Epic 3 scope).
- The `agent_dispatch_node` catches `AgentError` for logging only, then re-raises.

#### D4: Context Injection — Dispatch-Time Assembly
Context was assembled in preflight (Story 2.6). The agent_dispatch node calls `build_prompt(state.context_bundle)` to convert the bundle into an SDK prompt string. No additional context resolution happens here.

#### D5: Run Directory Schema & Write Policy
- LangGraph state is authority during execution. Run directory files are transition checkpoints.
- Preflight writes `context-bundle.md` (Story 2.6).
- Agent dispatch writes `agent-output.md` (THIS story).
- Validation writes `validation.md` (Epic 3 scope).
- JSONL log is append-only throughout the run.

#### D6: Error Handling — AgentError Exit Code 2
`AgentError` (and subclasses `AgentTimeoutError`, `AgentBudgetError`) map to exit code 2. The CLI dispatch command catches `ArcwrightError` subclasses and maps to the correct exit code.

#### D8: Logging & Observability — Two Channels
1. **User output** — Rich/Typer formatted text to stderr (story start/complete, errors)
2. **Structured log** — JSONL to `.arcwright-ai/runs/<run-id>/log.jsonl` (machine-readable events)

The JSONL handler is attached to the `arcwright_ai` root logger, so events from all child loggers (`arcwright_ai.engine.nodes`, `arcwright_ai.agent.invoker`, `arcwright_ai.context.injector`, etc.) propagate and are captured.

#### CLI — Thin Wrapper Pattern
```python
@app.command()
def dispatch_command(...) -> None:
    """Dispatch a story or epic for execution."""
    asyncio.run(_dispatch_async(...))
```
The CLI parses arguments and delegates to async functions. All orchestration logic (run ID, logging setup, state creation, graph invocation) lives in the async functions within `cli/dispatch.py`.

---

### Existing Code to Consume (NOT Create)

These modules are already fully implemented from previous stories. This story's code will **call** them — no modifications needed:

| Module | Function/Class | Source Story | Purpose |
|---|---|---|---|
| `agent/invoker.py` | `invoke_agent(prompt, *, model, cwd, sandbox, max_turns)` | Story 2.5 | Claude Code SDK async invocation, returns `InvocationResult` |
| `agent/invoker.py` | `InvocationResult` | Story 2.5 | Frozen dataclass: `output_text`, `tokens_input`, `tokens_output`, `total_cost`, `duration_ms`, `session_id`, `num_turns`, `is_error` |
| `agent/prompt.py` | `build_prompt(bundle: ContextBundle) -> str` | Story 2.5 | Converts `ContextBundle` to SDK prompt string |
| `agent/sandbox.py` | `validate_path(path, project_root, operation) -> bool` | Story 2.4 | Pure sandbox validator, conforms to `PathValidator` protocol |
| `context/injector.py` | `build_context_bundle(story_path, project_root)` | Story 2.2 | Async reference resolution, returns `ContextBundle` |
| `context/injector.py` | `serialize_bundle_to_markdown(bundle)` | Story 2.2 | Converts bundle to checkpoint markdown |
| `engine/graph.py` | `build_story_graph() -> CompiledStateGraph` | Story 2.1 | Compiles the LangGraph StateGraph |
| `engine/state.py` | `StoryState`, `ProjectState` | Story 2.1 | Mutable Pydantic state models |
| `engine/nodes.py` | `preflight_node(state) -> StoryState` | Story 2.6 | Real preflight — resolves context, writes checkpoint |
| `engine/nodes.py` | `budget_check_node(state) -> StoryState` | Story 2.1 | Budget check with RETRY→RUNNING transition |
| `engine/nodes.py` | `validate_node(state) -> StoryState` | Story 2.1 | Placeholder — always returns SUCCESS |
| `engine/nodes.py` | `commit_node(state) -> StoryState` | Story 2.1 | Placeholder — passes through |
| `core/types.py` | `BudgetState`, `ContextBundle`, `StoryId`, `EpicId`, `RunId` | Story 1.2 | Frozen Pydantic models and typed wrappers |
| `core/lifecycle.py` | `TaskState` | Story 1.2 | StrEnum: QUEUED, PREFLIGHT, RUNNING, VALIDATING, SUCCESS, RETRY, ESCALATED |
| `core/config.py` | `load_config(project_root) -> RunConfig` | Story 1.3 | Two-tier config loader |
| `core/io.py` | `write_text_async(path, content)` | Story 1.2 | Async file write via `asyncio.to_thread()` |
| `core/constants.py` | `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_STORIES`, `AGENT_OUTPUT_FILENAME`, `LOG_FILENAME`, `RUN_ID_DATETIME_FORMAT`, `EXIT_*` | Story 1.1 | Path constants and exit codes |
| `core/exceptions.py` | `AgentError`, `ContextError`, `ConfigError`, `ProjectError`, `ArcwrightError` | Story 1.2 | Exception hierarchy |
| `tests/fixtures/mock_sdk.py` | `MockSDKClient` | Story 2.5 | Configurable mock for SDK testing |
| `tests/conftest.py` | `tmp_project(tmp_path)` | Story 1.1 | Minimal project directory fixture |

### `invoke_agent` Signature (From agent/invoker.py)

```python
async def invoke_agent(
    prompt: str,
    *,
    model: str,
    cwd: Path,
    sandbox: PathValidator,
    max_turns: int | None = None,
) -> InvocationResult:
```

The function accepts a sandbox validator via dependency injection. The `agent_dispatch_node` passes `validate_path` from `agent/sandbox.py`.

### `InvocationResult` Fields (From agent/invoker.py)

```python
@dataclass(frozen=True)
class InvocationResult:
    output_text: str
    tokens_input: int
    tokens_output: int
    total_cost: Decimal
    duration_ms: int
    session_id: str
    num_turns: int
    is_error: bool
```

### `BudgetState` Update Pattern

`BudgetState` is frozen (inherits from `ArcwrightModel`). Updates require `model_copy(update={...})`:

```python
new_budget = state.budget.model_copy(update={
    "invocation_count": state.budget.invocation_count + 1,
    "total_tokens": state.budget.total_tokens + result.tokens_input + result.tokens_output,
    "estimated_cost": state.budget.estimated_cost + result.total_cost,
})
```

### Agent Dispatch Node Implementation Skeleton

```python
async def agent_dispatch_node(state: StoryState) -> StoryState:
    """Agent dispatch node — invokes Claude Code SDK with assembled context.

    Builds the SDK prompt from the preflight context bundle, invokes the
    agent, captures output and token usage, writes the agent output
    checkpoint, and transitions status from RUNNING → VALIDATING.

    Args:
        state: Current story execution state (expected status: RUNNING,
            context_bundle populated by preflight).

    Returns:
        Updated state with agent_output, budget updated, status VALIDATING.

    Raises:
        ContextError: If context_bundle is None (preflight did not run).
        AgentError: If the SDK invocation fails.
    """
    logger.info("engine.node.enter", extra={"data": {"node": "agent_dispatch", "story": str(state.story_id)}})

    if state.context_bundle is None:
        raise ContextError("agent_dispatch_node requires context_bundle from preflight")

    prompt = build_prompt(state.context_bundle)
    logger.info(
        "agent.dispatch",
        extra={"data": {"story": str(state.story_id), "model": state.config.model.version, "prompt_length": len(prompt)}},
    )

    try:
        result = await invoke_agent(
            prompt,
            model=state.config.model.version,
            cwd=state.project_root,
            sandbox=validate_path,
        )
    except AgentError:
        logger.info(
            "agent.error",
            extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(state.status)}},
        )
        logger.info(
            "engine.node.exit",
            extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(state.status)}},
        )
        raise

    # Update budget
    new_budget = state.budget.model_copy(update={
        "invocation_count": state.budget.invocation_count + 1,
        "total_tokens": state.budget.total_tokens + result.tokens_input + result.tokens_output,
        "estimated_cost": state.budget.estimated_cost + result.total_cost,
    })

    # Write agent output checkpoint
    checkpoint_dir: Path = (
        state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)
    )
    await asyncio.to_thread(checkpoint_dir.mkdir, parents=True, exist_ok=True)
    await write_text_async(checkpoint_dir / AGENT_OUTPUT_FILENAME, result.output_text)

    # Transition: RUNNING → VALIDATING
    updated = state.model_copy(update={
        "agent_output": result.output_text,
        "budget": new_budget,
        "status": TaskState.VALIDATING,
    })

    logger.info(
        "engine.node.exit",
        extra={"data": {"node": "agent_dispatch", "story": str(state.story_id), "status": str(updated.status)}},
    )
    return updated
```

### JSONL File Handler Design

```python
import json
import logging
from datetime import datetime, timezone

class _JsonlFileHandler(logging.FileHandler):
    """Structured JSONL file handler per Decision 8.

    Captures structured log events from arcwright_ai.* loggers and writes
    them as JSON Lines to the run's log.jsonl file.
    """

    def emit(self, record: logging.LogRecord) -> None:
        try:
            data = getattr(record, "data", {})
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(),
                "event": record.getMessage(),
                "level": record.levelname.lower(),
                "data": data if isinstance(data, dict) else {},
            }
            self.stream.write(json.dumps(entry) + "\n")
            self.flush()
        except Exception:
            self.handleError(record)
```

### CLI Dispatch Flow

```python
import asyncio
from pathlib import Path

import typer

def dispatch_command(
    story: Annotated[str | None, typer.Option("--story", help="Story ID (e.g., 2.7)")] = None,
    epic: Annotated[str | None, typer.Option("--epic", help="Epic ID (e.g., 2)")] = None,
) -> None:
    """Dispatch a story or epic for AI agent execution."""
    if story and epic:
        typer.echo("Error: specify --story or --epic, not both.", err=True)
        raise typer.Exit(code=1)
    if not story and not epic:
        typer.echo("Error: specify --story or --epic.", err=True)
        raise typer.Exit(code=1)
    if story:
        code = asyncio.run(_dispatch_story_async(story))
    else:
        code = asyncio.run(_dispatch_epic_async(epic))
    raise typer.Exit(code=code)
```

### Story File Discovery

Story files are in `{project_root}/_spec/implementation-artifacts/` with naming convention `{epic_num}-{story_num}-{slug}.md`. The CLI dispatch command finds them by globbing:

```python
def _find_story_file(story_spec: str, artifacts_dir: Path) -> tuple[Path, StoryId, EpicId]:
    # Parse "2.7" or "2-7" → epic_num=2, story_num=7
    # Glob: artifacts_dir / "2-7-*.md"
    # Return (path, StoryId(stem), EpicId(f"epic-{epic_num}"))
```

The `methodology.artifacts_path` config field provides the spec directory path. Implementation artifacts are at `{artifacts_path}/implementation-artifacts/`.

### Run ID Generation

Format from D5: `YYYYMMDD-HHMMSS-<short-uuid>` (e.g., `20260302-143052-a7f3`).

```python
import uuid
from datetime import datetime, timezone
from arcwright_ai.core.constants import RUN_ID_DATETIME_FORMAT

def _generate_run_id() -> RunId:
    dt = datetime.now(timezone.utc).strftime(RUN_ID_DATETIME_FORMAT)
    short_uuid = uuid.uuid4().hex[:4]
    return RunId(f"{dt}-{short_uuid}")
```

### Project Root Discovery

For MVP, the simplest approach: use `Path.cwd()` as the project root. Validate by checking for `.arcwright-ai/` or `_spec/` directory. If not found, raise `ProjectError`.

### `from __future__ import annotations` — Required First Line

Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

### `__all__` Must Be Alphabetically Sorted (RUF022)

`ruff` enforces RUF022. After adding `dispatch_command` to `cli/dispatch.py`'s `__all__`, ensure alphabetical order.

### Async-First for All I/O

- `invoke_agent()` is async — uses Claude Code SDK's async generator
- `write_text_async()` is async — uses `asyncio.to_thread()` for file writes
- Directory creation (`mkdir`) must be wrapped in `asyncio.to_thread()`
- The CLI entry point wraps with `asyncio.run()`

### Graph Integration Impact

After this story, `agent_dispatch_node` is no longer a placeholder. It requires:
1. A populated `state.context_bundle` (from preflight)
2. A valid SDK configuration (model version, API key)
3. A real project directory for checkpoint writes

This means **all existing graph integration tests** in `test_graph.py` that run the full graph will now attempt a real SDK invocation. These tests MUST be updated to monkeypatch `invoke_agent` with a mock.

**CRITICAL: Update `test_graph.py` tests!** The three existing tests (`test_graph_success_path_end_to_end`, `test_graph_invocation_no_errors`, `test_graph_budget_exceeded_path_escalates_and_exits`) currently pass because agent_dispatch is a no-op placeholder. After this story, they will fail unless `invoke_agent` is mocked.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution.

---

### Previous Story Intelligence

**From Story 2.6 (Preflight Node — Context Assembly & Dispatch Preparation):**
- Real preflight node writes checkpoint to `.arcwright-ai/runs/<run-id>/stories/<story-slug>/context-bundle.md`
- Checkpoint path: `state.project_root / DIR_ARCWRIGHT / DIR_RUNS / str(state.run_id) / DIR_STORIES / str(state.story_id)`
- `build_context_bundle()` is fully async — uses `asyncio.gather()` internally
- `ContextError` is raised when story file cannot be read — the only "hard error"
- `serialize_bundle_to_markdown()` is synchronous — no `await`
- Error handling pattern: log `engine.node.enter`, catch error → log error event + `engine.node.exit` → re-raise
- Tests use `story_state_with_project` fixture backed by `tmp_path` with real BMAD artifacts
- Existing graph integration tests (`test_graph.py`) use `graph_project_state` fixture

**From Story 2.5 (Agent Invoker — Claude Code SDK Integration):**
- `invoke_agent()` returns `InvocationResult` with `output_text`, `tokens_input`, `tokens_output`, `total_cost` (Decimal)
- Rate limit backoff is handled internally by `invoke_agent()` — transparent to callers
- `agent.response` structured log event is already emitted inside `invoke_agent()` — do NOT re-emit in the node
- SDK imports are lazy (inside functions) for testability via monkeypatching
- `MockSDKClient` is the canonical test fixture — use it via `tests/fixtures/mock_sdk.py`
- Tests monkeypatch `claude_code_sdk.query` to inject mock, then call `invoke_agent()`

**From Story 2.4 (Agent Sandbox — Path Validation Layer):**
- `validate_path` is a pure function conforming to `PathValidator` protocol
- Imported at module level, passed to `invoke_agent()` as `sandbox` parameter
- Defense-in-depth: validate inputs even when callers are expected to be correct

**From Story 2.1 (LangGraph State Models & Graph Skeleton):**
- `StoryState` is mutable (`frozen=False`) — `model_copy(update={...})` creates new instance
- All graph nodes: `async def node_name(state: StoryState) -> StoryState`
- Existing `make_story_state` fixture returns minimal StoryState with `Path("/project")` — not real filesystem
- `graph_project_state` fixture (added in 2.6) uses real `tmp_path` with BMAD artifacts

**From Stories 1.4 & 1.5 (CLI Commands):**
- CLI commands use `typer.echo(..., err=True)` for output to stderr per D8
- Typer commands registered via `app.command(name="...")(function)`
- Exit codes mapped from exceptions via `raise typer.Exit(code=N)`
- Tests use `typer.testing.CliRunner` for CLI integration testing
- `CliRunner.invoke(app, ["command", "--flag", "value"])`

---

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
async def test_agent_dispatch_node_invokes_sdk_and_transitions_to_validating(): ...
async def test_agent_dispatch_node_updates_budget(): ...
def test_find_story_file_parses_dot_format(): ...
def test_dispatch_story_end_to_end_with_mock_sdk(): ...
```

**Async tests:** `asyncio_mode = "auto"` in `pyproject.toml` so `@pytest.mark.asyncio` is NOT required. However, existing tests in `test_nodes.py` use it explicitly — **maintain consistency within each file**.

**Monkeypatching `invoke_agent` for node tests:**
```python
@pytest.fixture
def mock_invoke_result() -> InvocationResult:
    return InvocationResult(
        output_text="# Mock Implementation\nDone.",
        tokens_input=500,
        tokens_output=200,
        total_cost=Decimal("0.05"),
        duration_ms=1000,
        session_id="test-session-001",
        num_turns=3,
        is_error=False,
    )

async def test_agent_dispatch_node_invokes_sdk(
    story_state_with_project: StoryState,
    monkeypatch: pytest.MonkeyPatch,
    mock_invoke_result: InvocationResult,
) -> None:
    # Run preflight first to populate context_bundle
    state = await preflight_node(story_state_with_project)

    async def _mock_invoke(*args, **kwargs):
        return mock_invoke_result

    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock_invoke)
    result = await agent_dispatch_node(state)
    assert result.status == TaskState.VALIDATING
    assert result.agent_output == "# Mock Implementation\nDone."
```

**CLI integration test pattern:**
```python
from typer.testing import CliRunner
from arcwright_ai.cli.app import app

runner = CliRunner()

def test_dispatch_story_end_to_end(tmp_path, monkeypatch):
    # Set up tmp_path with project structure + BMAD artifacts + story file
    # Monkeypatch invoke_agent
    # Monkeypatch load_config to return test config
    # Monkeypatch Path.cwd() to return tmp_path
    result = runner.invoke(app, ["dispatch", "--story", "2.1"])
    assert result.exit_code == 0
```

**Fixture pattern for graph tests with mocked agent:**
```python
@pytest.fixture
def mock_agent(monkeypatch: pytest.MonkeyPatch) -> None:
    """Monkeypatch invoke_agent for graph integration tests."""
    async def _mock(*args, **kwargs):
        return InvocationResult(
            output_text="Mock output",
            tokens_input=100,
            tokens_output=50,
            total_cost=Decimal("0.01"),
            duration_ms=100,
            session_id="mock-session",
            num_turns=1,
            is_error=False,
        )
    monkeypatch.setattr("arcwright_ai.engine.nodes.invoke_agent", _mock)
```

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries.

**Test isolation:** Each test creates its own state via fixtures. No shared mutable state between tests.

---

### Project Structure Notes

**Files to MODIFY:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/engine/nodes.py` | MODIFY | Replace placeholder `agent_dispatch_node` with real SDK invocation; add new imports |
| `src/arcwright_ai/cli/dispatch.py` | MODIFY | Implement full dispatch command with story/epic handling, run lifecycle, JSONL logging |
| `src/arcwright_ai/cli/app.py` | MODIFY | Register `dispatch_command` |
| `tests/test_engine/test_nodes.py` | MODIFY | Add agent_dispatch_node tests with mock SDK |
| `tests/test_engine/test_graph.py` | MODIFY | Update graph integration tests to mock agent_dispatch SDK calls |

**Files to CREATE:**

| File | Action | Content |
|---|---|---|
| `tests/test_cli/test_dispatch.py` | CREATE | CLI dispatch tests: story finder, run ID, JSONL handler, end-to-end |

**Files NOT touched** (no changes needed):
- `agent/invoker.py` — fully implemented in Story 2.5, consumed as-is
- `agent/prompt.py` — fully implemented in Story 2.5, consumed as-is
- `agent/sandbox.py` — fully implemented in Story 2.4, consumed as-is
- `context/injector.py` — fully implemented in Story 2.2, consumed as-is
- `core/types.py` — `BudgetState`, `ContextBundle` already defined
- `core/io.py` — `write_text_async` already defined
- `core/constants.py` — all needed constants already defined
- `core/config.py` — `load_config`, `RunConfig` already defined
- `core/exceptions.py` — all needed exceptions already defined
- `core/lifecycle.py` — `TaskState` already defined
- `engine/state.py` — `StoryState` already has all needed fields
- `engine/graph.py` — graph already has all nodes wired (agent_dispatch already wired)
- `engine/__init__.py` — already exports all needed symbols
- `tests/fixtures/mock_sdk.py` — `MockSDKClient` already implemented

**Alignment with architecture:**
- `engine/nodes.py` → `agent_dispatch_node` matches architecture's node list
- `cli/dispatch.py` → dispatch commands match architecture's CLI surface
- D1 mapping: preflight assembles → agent dispatch consumes `context_bundle` from state
- D2 mapping: AgentError → immediate halt, re-raise from node
- D4 mapping: `build_prompt(bundle)` converts context to SDK prompt
- D5 mapping: `agent-output.md` checkpoint written at state transition boundary
- D6 mapping: `AgentError` → exit code 2, `ContextError` → exit code 3
- D8 mapping: JSONL handler + structured events for all pipeline steps
- FR1/FR3: Epic dispatch basic sequential iteration
- FR2: Single story dispatch via `--story` flag
- FR16: Context injection consumed via `build_prompt(state.context_bundle)`
- FR19: Stateless SDK invocation via `invoke_agent()`
- FR20: Sandbox enforcement via `validate_path` injection

---

### Cross-Story Context (Epic 2 Stories That Interact with 2.7)

| Story | Relationship to 2.7 | Impact |
|---|---|---|
| 2.1: LangGraph State Models | Provides `StoryState`, `ProjectState`, graph skeleton | Graph already has `agent_dispatch` wired; this story replaces the placeholder body |
| 2.2: Context Injector | Provides `build_context_bundle()` consumed by preflight | Preflight populates `context_bundle` in state; agent dispatch reads it |
| 2.3: Context Answerer | Answerer rules included in `ContextBundle` | Part of the bundle consumed by `build_prompt()` |
| 2.4: Agent Sandbox | Provides `validate_path` passed to `invoke_agent()` | Defense-in-depth path validation for all agent file operations |
| 2.5: Agent Invoker | Provides `invoke_agent()`, `InvocationResult`, `build_prompt()` | Core SDK integration consumed by `agent_dispatch_node` |
| 2.6: Preflight Node | Populates `state.context_bundle`; writes `context-bundle.md` | Agent dispatch depends on preflight having run — context_bundle must be non-None |
| 3.1-3.4: Validation Pipeline | Will replace placeholder `validate_node` | After this story, validate is still a placeholder. Epic 3 wires real validation. |
| 5.1: Epic Dispatch CLI | Full epic dispatch UX with confirmation, estimates | This story's `--epic` is basic sequential only. Story 5.1 adds full UX. |

**Important handoff note for Epic 3:** After this story, the full pipeline runs: preflight (real) → budget_check (real) → agent_dispatch (REAL) → validate (placeholder) → commit (placeholder). Epic 3 replaces `validate_node` with real V3/V6 validation. The `ValidationResult` type flowing from validate to commit is still a placeholder `dict[str, Any]` in `StoryState`.

---

### Git Intelligence

Last 10 commits:
```
f0468df docs(story): create Story 2.6 — Preflight Node, Context Assembly & Dispatch Preparation
fe1eec7 feat(agent): implement Story 2.5 Claude Code SDK invoker integration
ff813cc docs(story): create Story 2.5 — Agent Invoker, Claude Code SDK Integration
edc85eb fix(agent): harden sandbox relative-path resolution and finalize Story 2.4
3d16d16 feat(agent): implement Story 2.4 — Agent Sandbox Path Validation Layer
c404c4c feat(context): implement Story 2.3 — Context Answerer, Static Rule Lookup Engine
f91e3a5 chore(story-2.2): post-format fixes, finalize story file, and sprint status
bcdbba7 feat(context): implement Story 2.2 — Context Injector, BMAD Artifact Reader & Reference Resolver
70d73e6 chore(story-2.1): finalize story file, quality-gate fixes, and sprint status
51fdf4d feat(engine): implement Story 2.1 — LangGraph state models and graph skeleton
```

**Patterns established:**
- Commit prefix for this story: `feat(engine):` for engine node changes + `feat(cli):` for dispatch command
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- Existing node tests in `test_engine/test_nodes.py` — extend, don't replace
- Existing CLI tests in `test_cli/` — `test_init.py`, `test_validate_setup.py` as patterns

**Relevant files from previous stories:**
- `src/arcwright_ai/engine/nodes.py` — current placeholder `agent_dispatch_node` to replace
- `src/arcwright_ai/cli/dispatch.py` — current empty placeholder to implement
- `src/arcwright_ai/cli/app.py` — register new dispatch command
- `src/arcwright_ai/agent/invoker.py` — `invoke_agent()` to consume
- `src/arcwright_ai/agent/prompt.py` — `build_prompt()` to consume
- `src/arcwright_ai/agent/sandbox.py` — `validate_path` to consume
- `tests/fixtures/mock_sdk.py` — `MockSDKClient` for testing
- `tests/test_engine/test_nodes.py` — existing tests to extend
- `tests/test_engine/test_graph.py` — existing integration tests to update
- `tests/test_cli/test_init.py` — test pattern for CLI commands
- `tests/conftest.py` — `tmp_project` fixture

---

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision-1 — Hybrid preflight context assembly, D1↔D4 binding]
- [Source: _spec/planning-artifacts/architecture.md#Decision-2 — Retry & halt strategy, AgentError = immediate halt]
- [Source: _spec/planning-artifacts/architecture.md#Decision-4 — Dispatch-time assembly, build_prompt from context bundle]
- [Source: _spec/planning-artifacts/architecture.md#Decision-5 — Run directory schema, agent-output.md checkpoint]
- [Source: _spec/planning-artifacts/architecture.md#Decision-6 — AgentError → exit code 2, ContextError → exit code 3]
- [Source: _spec/planning-artifacts/architecture.md#Decision-8 — JSONL structured logging, two output channels]
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG — engine depends on agent + context + core, cli depends on engine + core]
- [Source: _spec/planning-artifacts/architecture.md#Async-Patterns — asyncio.run() in CLI, async graph nodes]
- [Source: _spec/planning-artifacts/architecture.md#Testing-Patterns — MockSDKClient as canonical fixture]
- [Source: _spec/planning-artifacts/architecture.md#Project-Structure — cli/dispatch.py, engine/nodes.py]
- [Source: _spec/planning-artifacts/epics.md#Story-2.7 — Acceptance criteria, story definition]
- [Source: _spec/planning-artifacts/prd.md#FR1 — Dispatch all stories in an epic]
- [Source: _spec/planning-artifacts/prd.md#FR2 — Dispatch a single story]
- [Source: _spec/planning-artifacts/prd.md#FR3 — Sequential execution in dependency order]
- [Source: _spec/planning-artifacts/prd.md#FR16 — Context injection into agent prompt]
- [Source: _spec/planning-artifacts/prd.md#FR19 — Stateless Claude Code SDK invocation]
- [Source: _spec/planning-artifacts/prd.md#FR20 — Agent sandbox enforcement]
- [Source: _spec/planning-artifacts/prd.md#FR22 — Rate limit backoff (handled by invoke_agent)]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — Known pitfalls, Action Items 1-3]
- [Source: _spec/implementation-artifacts/2-6-preflight-node-context-assembly-and-dispatch-preparation.md — Preflight implementation details, handoff contract]
- [Source: _spec/implementation-artifacts/2-5-agent-invoker-claude-code-sdk-integration.md — MockSDKClient, InvocationResult, invoke_agent patterns]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — Current placeholder agent_dispatch_node]
- [Source: arcwright-ai/src/arcwright_ai/cli/dispatch.py — Current empty dispatch module]
- [Source: arcwright-ai/src/arcwright_ai/cli/app.py — Current app with init + validate-setup]
- [Source: arcwright-ai/src/arcwright_ai/agent/invoker.py — invoke_agent, InvocationResult]
- [Source: arcwright-ai/src/arcwright_ai/agent/prompt.py — build_prompt]
- [Source: arcwright-ai/src/arcwright_ai/agent/sandbox.py — validate_path, PathValidator protocol]
- [Source: arcwright-ai/src/arcwright_ai/engine/graph.py — build_story_graph with all nodes wired]
- [Source: arcwright-ai/src/arcwright_ai/engine/state.py — StoryState, ProjectState]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — DIR_ARCWRIGHT, DIR_RUNS, DIR_STORIES, AGENT_OUTPUT_FILENAME, LOG_FILENAME, RUN_ID_DATETIME_FORMAT, EXIT_*]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — BudgetState, ContextBundle, StoryId, EpicId, RunId]
- [Source: arcwright-ai/src/arcwright_ai/core/config.py — load_config, RunConfig]
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py — AgentError, ContextError, ConfigError, ProjectError]
- [Source: arcwright-ai/src/arcwright_ai/core/lifecycle.py — TaskState, VALID_TRANSITIONS]
- [Source: arcwright-ai/tests/fixtures/mock_sdk.py — MockSDKClient canonical test fixture]
- [Source: arcwright-ai/tests/test_engine/test_nodes.py — Existing preflight + budget_check + routing tests]
- [Source: arcwright-ai/tests/test_engine/test_graph.py — Existing graph integration tests (must be updated)]
- [Source: arcwright-ai/tests/conftest.py — tmp_project fixture]
- [Source: arcwright-ai/pyproject.toml — asyncio_mode="auto", dependencies, entry points]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-5 (GitHub Copilot)

### Debug Log References

- Logger effective level issue: `arcwright_ai` logger defaults to WARNING; fixed by setting level to DEBUG in `_setup_run_logging` so INFO structured events reach the JSONL handler.

### Completion Notes List

- ✅ Task 1: Replaced placeholder `agent_dispatch_node` with real implementation — invokes Claude Code SDK via `invoke_agent()`, writes `agent-output.md` checkpoint, updates `BudgetState`, transitions RUNNING → VALIDATING. Added Google-style docstring.
- ✅ Task 2: Implemented `_JsonlFileHandler` (D8 envelope: ts/event/level/data) and `_setup_run_logging` in `cli/dispatch.py`.
- ✅ Task 3: Implemented `_generate_run_id()` (YYYYMMDD-HHMMSS-xxxx format), `_find_story_file()` (parses "2.7"/"2-7"), `_find_epic_stories()` (sorted by story number, excludes retrospectives).
- ✅ Task 4: Implemented `dispatch_command`, `_dispatch_story_async`, `_dispatch_epic_async` with full error handling, exit code mapping, and Rich/Typer stderr output per D8.
- ✅ Task 5: Registered `dispatch` command in `cli/app.py`.
- ✅ Task 6: Added 6 agent_dispatch_node tests in `test_engine/test_nodes.py` (transitions, budget, checkpoint, context error, agent error, log events). Replaced old placeholder test with AC-compliant ContextError test.
- ✅ Task 7: Created `tests/test_cli/test_dispatch.py` with 13 tests: story/epic finders, run ID, JSONL handler, full integration test (exit 0, checkpoint written, JSONL events present), mutual-exclusion guards.
- ✅ Task 8: Updated `test_engine/test_graph.py` — added `mock_agent` fixture, updated all 3 graph integration tests to mock `invoke_agent`.
- ✅ Task 9: All quality gates pass — `ruff check .` (0 violations), `ruff format --check .` (66 files formatted), `mypy --strict src/` (0 errors), `pytest` (302 passed, 0 failures).

### File List

**Modified:**
- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/src/arcwright_ai/cli/dispatch.py`
- `arcwright-ai/src/arcwright_ai/cli/app.py`
- `arcwright-ai/pyproject.toml`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `arcwright-ai/tests/test_engine/test_graph.py`
- `_spec/implementation-artifacts/2-7-agent-dispatch-node-and-single-story-cli-command.md`

**Created:**
- `arcwright-ai/tests/test_cli/test_dispatch.py`

**Sprint status updated:**
- `_spec/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-03-02: Implemented Story 2.7 — real `agent_dispatch_node` (SDK invocation, budget update, checkpoint write), full `cli/dispatch.py` dispatch command with `--story`/`--epic` support, JSONL run logging, story/epic file discovery, run ID generation. Added 19 new tests across 3 test files. All 302 tests pass, ruff/mypy clean.
- 2026-03-02: Senior Developer Review (AI) completed. Identified 2 HIGH and 3 MEDIUM issues. Added `Review Follow-ups (AI)` action items and moved story status to `in-progress` pending fixes.
- 2026-03-02: Implemented all AI review follow-up fixes: terminal status exit mapping for story/epic dispatch, non-success epic short-circuit, logger level restoration after run logging, and stronger AC10 integration assertions for required JSONL events and budget evidence. Story moved back to `review`.

## Senior Developer Review (AI)

### Reviewer

- Reviewer: Ed (AI Senior Developer Review)
- Date: 2026-03-02
- Outcome: Changes Requested

### Summary

- Story reviewed against ACs, task claims, and git diff reality.
- Git vs Story discrepancies found: 3
- Issues found: 2 High, 3 Medium, 0 Low

### Findings

#### HIGH

1. **Exit code can report success on non-success final state**
    - In single-story dispatch, the function always returns `EXIT_SUCCESS` after graph invocation, even when final status is `ESCALATED`.
    - Evidence: `arcwright-ai/src/arcwright_ai/cli/dispatch.py` (`_dispatch_story_async`) unconditionally returns success after printing final status.
    - Impact: Violates expected failure signaling and can mask halted/failed runs.

2. **Epic dispatch can continue/complete despite non-success terminal states**
    - Epic loop treats any non-exception graph return as success and continues; it does not gate on terminal status.
    - Evidence: `arcwright-ai/src/arcwright_ai/cli/dispatch.py` (`_dispatch_epic_async`) prints completion for each story and returns success for the epic without status checks.
    - Impact: Can report epic success while stories are escalated.

#### MEDIUM

1. **AC10 verification is partial in integration test coverage**
    - The integration test does not assert presence of required events (`context.resolve`, `agent.dispatch`, `agent.response`) and does not assert budget values from final state artifacts.
    - Evidence: `arcwright-ai/tests/test_cli/test_dispatch.py` (`test_dispatch_story_end_to_end_with_mock_sdk`).

2. **Logger level side-effect leakage**
    - `_setup_run_logging` forces `arcwright_ai` logger to DEBUG and never restores previous level.
    - Evidence: `arcwright-ai/src/arcwright_ai/cli/dispatch.py`.
    - Impact: Global logging behavior can change across subsequent CLI invocations/tests.

3. **Dev Agent Record file list mismatch with actual git changes**
    - Story file list omits changed files present in git (`arcwright-ai/pyproject.toml`) and did not track this story artifact addition in the list.
    - Evidence: git diff file list vs Dev Agent Record section in this story file.

### Git vs Story Discrepancies

- Files in git changes but missing from Dev Agent Record File List:
  - `arcwright-ai/pyproject.toml`
  - `_spec/implementation-artifacts/2-7-agent-dispatch-node-and-single-story-cli-command.md`
- Story claims quality gates fully passed, but current environment cannot reproduce due missing dependency (`langgraph`) in configured system Python.

### Validation Notes

- Attempted targeted test run failed at collection because the configured Python environment lacks required project dependencies (`ModuleNotFoundError: langgraph`).
- Command attempted: `/opt/homebrew/bin/python3 -m pytest tests/test_cli/test_dispatch.py tests/test_engine/test_nodes.py tests/test_engine/test_graph.py -q`

