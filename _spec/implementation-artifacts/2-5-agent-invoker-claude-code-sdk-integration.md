# Story 2.5: Agent Invoker — Claude Code SDK Integration

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer dispatching a story,
I want the system to invoke Claude Code SDK with the assembled context bundle and receive the agent's implementation output,
so that stories are implemented by the AI agent in a stateless, sandboxed session.

## Acceptance Criteria (BDD)

1. **Given** `agent/prompt.py` module **When** the prompt builder processes a `ContextBundle` **Then** it assembles the SDK prompt from the bundle: story text + resolved requirements + architecture excerpts + project conventions formatted as a single prompt string.

2. **Given** `agent/invoker.py` module **When** a story is dispatched to the agent **Then** it invokes Claude Code SDK via the `claude_code_sdk.query()` async iterator with: the assembled prompt, model version from config, and session-specific parameters (`cwd`, `permission_mode`, `max_turns`).

3. **Given** a story execution **When** the agent invocation completes **Then** each invocation is stateless — no persistent agent state between stories per FR19.

4. **Given** the invoker processes SDK messages **When** a `ToolUseBlock` with a file-writing tool name is encountered **Then** the invoker passes the file path through the sandbox validator (injected as `PathValidator`) before the operation proceeds; `SandboxViolation` is raised and the invocation is aborted if the validator rejects the path.

5. **Given** the SDK raises `ClaudeSDKError` (or subclasses: `ProcessError`, `CLIConnectionError`, `CLIJSONDecodeError`) **When** the invoker catches the error **Then** it wraps the SDK exception as the appropriate `AgentError` subclass per D6 — `AgentError` for general SDK failures, `AgentTimeoutError` for timeout scenarios — preserving the original exception message in `details`.

6. **Given** the SDK returns a rate-limit indication (HTTP 429 pattern or `CLIConnectionError`) **When** the invoker detects a rate limit **Then** it triggers exponential backoff with jitter per FR22: starting at 1s, doubling each retry, capping at 60s, maximum 5 attempts before raising `AgentError`; each wait is logged as structured event `agent.rate_limit` with `wait_seconds` and `attempt` in `extra["data"]`.

7. **Given** the SDK's `ResultMessage` at the end of the async iterator **When** the invoker processes it **Then** token consumption (`ResultMessage.usage` dict — `input_tokens`, `output_tokens`) and `ResultMessage.total_cost_usd` are captured and returned alongside the agent output text for budget tracking via an `InvocationResult` dataclass.

8. **Given** the agent needs to write temporary files **When** temp file paths are validated **Then** they target `.arcwright-ai/tmp/` per FR21, and the invoker creates the temp directory if it doesn't exist.

9. **Given** `tests/fixtures/mock_sdk.py` **When** the `MockSDKClient` is updated **Then** it provides a configurable fixture that returns: `output_text` (str), `tokens_input` (int), `tokens_output` (int), `total_cost_usd` (float), `error` (optional exception type), `tool_use_calls` (optional list of `ToolUseBlock`-like dicts) — matching the real SDK's `query()` async iterator interface (yielding typed messages, not raw dicts). All downstream stories that test through the engine pipeline use this fixture.

10. **Given** unit tests in `tests/test_agent/test_invoker.py` and `tests/test_agent/test_prompt.py` **When** `pytest tests/test_agent/` is run **Then** tests use the updated `MockSDKClient` fixture (not ad-hoc mocks): success response, failure response, rate limit response with backoff verification, malformed response, sandbox violation during tool use.

11. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

12. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

13. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Define `InvocationResult` dataclass in `agent/invoker.py` (AC: #7)
  - [x] 1.1: Add `from __future__ import annotations` (already present as placeholder)
  - [x] 1.2: Add imports: `asyncio`, `logging`, `random`, `time` from stdlib; `Decimal` from `decimal`; `Path` from `pathlib` (behind `TYPE_CHECKING`); dataclass types; `ContextBundle` from `core/types`; `AgentError`, `AgentTimeoutError` from `core/exceptions`; `PathValidator` from `agent/sandbox`; `DIR_ARCWRIGHT`, `DIR_TMP` from `core/constants`
  - [x] 1.3: Define `@dataclass(frozen=True) class InvocationResult` with fields: `output_text: str`, `tokens_input: int`, `tokens_output: int`, `total_cost: Decimal`, `duration_ms: int`, `session_id: str`, `num_turns: int`, `is_error: bool`
  - [x] 1.4: Add Google-style docstring to `InvocationResult`

- [x] Task 2: Implement `build_prompt` in `agent/prompt.py` (AC: #1, #13)
  - [x] 2.1: Add imports: `ContextBundle` from `core/types`
  - [x] 2.2: Implement `def build_prompt(bundle: ContextBundle) -> str` that formats the bundle into a structured prompt string with clearly delineated sections: `## Story`, `## Requirements`, `## Architecture`, `## Conventions`
  - [x] 2.3: Each section is included only if the corresponding bundle field is non-empty
  - [x] 2.4: Add Google-style docstring with Args, Returns sections
  - [x] 2.5: Set `__all__` in `agent/prompt.py`: `["build_prompt"]` 

- [x] Task 3: Implement `invoke_agent` in `agent/invoker.py` (AC: #2, #3, #4, #5, #6, #7, #8)
  - [x] 3.1: Create module-level logger: `logger = logging.getLogger(__name__)`
  - [x] 3.2: Define constants: `_BACKOFF_BASE: float = 1.0`, `_BACKOFF_CAP: float = 60.0`, `_BACKOFF_MAX_RETRIES: int = 5`, `_RATE_LIMIT_PATTERN` regex for detecting 429/rate-limit in error messages
  - [x] 3.3: Implement `async def invoke_agent(prompt: str, *, model: str, cwd: Path, sandbox: PathValidator, max_turns: int | None = None) -> InvocationResult`:
    - Import `claude_code_sdk` and its types at function level (lazy import for testability)
    - Build `ClaudeCodeOptions(model=model, cwd=str(cwd), permission_mode="bypassPermissions", max_turns=max_turns)`
    - Call `claude_code_sdk.query(prompt=prompt, options=options)` to get the async iterator
    - Iterate through messages, collecting: `AssistantMessage` text content blocks into output, `ToolUseBlock` calls for sandbox validation (file-writing tools: `Write`, `Edit`, `MultiEdit`, `CreateFile`), `ResultMessage` for budget data
    - On `ToolUseBlock` with file-writing tool: extract file path from `input` dict, call `sandbox(Path(file_path), cwd, tool_name)` — if `SandboxViolation` is raised, log and re-raise
    - After iteration completes: extract `ResultMessage.usage` for tokens, `ResultMessage.total_cost_usd` for cost, return `InvocationResult`
  - [x] 3.4: Add Google-style docstring with Args, Returns, Raises sections
  - [x] 3.5: Implement rate limit detection and exponential backoff with jitter wrapper around the `query()` call

- [x] Task 4: Implement rate limit backoff helper (AC: #6)
  - [x] 4.1: Implement `async def _invoke_with_backoff(prompt: str, options: Any) -> AsyncIterator[...]`:
    - Loop up to `_BACKOFF_MAX_RETRIES` attempts
    - On each attempt, call `claude_code_sdk.query(prompt=prompt, options=options)`
    - If `ClaudeSDKError` is raised and message matches rate-limit pattern: calculate sleep = min(_BACKOFF_BASE * 2^attempt + random jitter(0, 0.5), _BACKOFF_CAP), log `agent.rate_limit` event, `await asyncio.sleep(sleep)`, retry
    - If non-rate-limit error or max retries exceeded: wrap as `AgentError` and raise
  - [x] 4.2: Add Google-style docstring

- [x] Task 5: Implement SDK error wrapping (AC: #5)
  - [x] 5.1: Implement `def _wrap_sdk_error(error: Exception) -> AgentError`:
    - `ClaudeSDKError` with timeout indicators → `AgentTimeoutError`
    - All other `ClaudeSDKError` subclasses → `AgentError` with original message in `details`
    - Generic `Exception` → `AgentError` as catch-all
  - [x] 5.2: Ensure original exception is chained via `raise ... from error`

- [x] Task 6: Update `agent/invoker.py` and `agent/prompt.py` exports (AC: #11)
  - [x] 6.1: Set `__all__` in `agent/invoker.py`: `["InvocationResult", "invoke_agent"]` (alphabetical per RUF022)
  - [x] 6.2: Update `agent/__init__.py` to import and re-export: `InvocationResult`, `build_prompt`, `invoke_agent` from their respective modules, plus existing sandbox exports
  - [x] 6.3: Update `agent/__init__.py` `__all__` in alphabetical order

- [x] Task 7: Update `MockSDKClient` in `tests/fixtures/mock_sdk.py` (AC: #9)
  - [x] 7.1: Refactor `MockClaudeCodeSDK` → `MockSDKClient` class that returns typed SDK message objects (`AssistantMessage`, `TextBlock`, `ResultMessage`, `ToolUseBlock`) instead of raw dicts
  - [x] 7.2: Configure via `__init__` params: `output_text: str = "Done."`, `tokens_input: int = 100`, `tokens_output: int = 50`, `total_cost_usd: float = 0.01`, `error: type[Exception] | None = None`, `error_message: str = "Simulated error"`, `tool_use_calls: list[dict[str, Any]] | None = None`, `is_rate_limit: bool = False`
  - [x] 7.3: Implement `async def query(self, *, prompt: str, options: Any = None) -> AsyncIterator[...]` that yields messages matching real SDK sequence: optional `ToolUseBlock`s → `AssistantMessage` with `TextBlock` content → `ResultMessage` with usage/cost data
  - [x] 7.4: If `error` is set, raise the error at the configured point (before or during iteration)
  - [x] 7.5: If `is_rate_limit` is True, raise `ClaudeSDKError("rate limit")` on first call, succeed on subsequent calls (tests backoff)
  - [x] 7.6: Preserve backward compatibility or update existing test references to use new fixture

- [x] Task 8: Write unit tests for `agent/prompt.py` in `tests/test_agent/test_prompt.py` (AC: #10, #13)
  - [x] 8.1: Create `tests/test_agent/test_prompt.py` with `from __future__ import annotations`
  - [x] 8.2: Test `test_build_prompt_full_bundle` — all ContextBundle fields populated → prompt contains all sections
  - [x] 8.3: Test `test_build_prompt_empty_optional_sections` — only `story_content` set → only story section present, no empty sections
  - [x] 8.4: Test `test_build_prompt_includes_architecture` — architecture_sections populated → `## Architecture` section appears
  - [x] 8.5: Test `test_build_prompt_includes_requirements` — domain_requirements populated → `## Requirements` section appears
  - [x] 8.6: Test `test_build_prompt_returns_string` — return type is str

- [x] Task 9: Write unit tests for `agent/invoker.py` in `tests/test_agent/test_invoker.py` (AC: #10)
  - [x] 9.1: Create `tests/test_agent/test_invoker.py` with `from __future__ import annotations`
  - [x] 9.2: Create fixtures: `mock_sdk` using `MockSDKClient`, `project_root(tmp_path)` with `.arcwright-ai/tmp/` dir, `sandbox` using real `validate_path` function
  - [x] 9.3: Test `test_invoke_agent_success_returns_result` — mock SDK returns text → `InvocationResult` with correct `output_text`, `tokens_input`, `tokens_output`, `total_cost`
  - [x] 9.4: Test `test_invoke_agent_failure_raises_agent_error` — mock SDK raises `ProcessError` → `AgentError` raised with details
  - [x] 9.5: Test `test_invoke_agent_rate_limit_retries_with_backoff` — mock SDK raises rate limit on first call, succeeds on second → result returned, `agent.rate_limit` event logged
  - [x] 9.6: Test `test_invoke_agent_rate_limit_exhausted_raises` — mock SDK always raises rate limit → `AgentError` after max retries
  - [x] 9.7: Test `test_invoke_agent_malformed_response` — mock SDK yields unexpected message type → `AgentError` or graceful handling
  - [x] 9.8: Test `test_invoke_agent_sandbox_violation` — mock SDK yields `ToolUseBlock` with path outside project → `SandboxViolation` raised
  - [x] 9.9: Test `test_invoke_agent_tool_use_within_project` — mock SDK yields `ToolUseBlock` with valid path → no error, invocation completes
  - [x] 9.10: Test `test_invoke_agent_captures_token_usage` — verify `InvocationResult.tokens_input` and `tokens_output` match SDK response
  - [x] 9.11: Test `test_invoke_agent_stateless` — two sequential invocations yield independent results (no shared state)
  - [x] 9.12: Test `test_invocation_result_is_frozen_dataclass` — verify `InvocationResult` is a frozen dataclass

- [x] Task 10: Validate all quality gates (AC: #11, #12)
  - [x] 10.1: Run `ruff check .` — zero violations
  - [x] 10.2: Run `ruff format --check .` — no formatting diffs
  - [x] 10.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 10.4: Run `pytest tests/test_agent/ -v` — all new tests pass
  - [x] 10.5: Run `pytest` — full test suite passes (no regressions)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `agent/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
`agent/` depends ONLY on `core/`. It must NOT import from `engine/`, `context/`, `validation/`, `output/`, or `scm/`. The `engine/` package wires `agent/invoker.py` into the `agent_dispatch` node (Story 2.7). This story implements the SDK integration — no engine wiring.

#### Boundary 3: Agent Invoker ↔ Sandbox (Architecture Doc)
- Invoker receives sandbox as a `PathValidator` validator function via **dependency injection**
- Sandbox has **zero knowledge of Claude Code SDK** — it validates `(path, operation) → allow/deny`
- Invoker calls sandbox **before** the agent's file operation takes effect
- The `PathValidator` Protocol is the contract between sandbox and invoker

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. When populating `agent/invoker.py`, `agent/prompt.py`, and updating `agent/__init__.py`, sort all entries alphabetically.

#### Async-First for SDK Calls
The `claude_code_sdk.query()` function returns an `AsyncIterator`. The invoker must be an `async def` function. The caller (engine's `agent_dispatch` node in Story 2.7) will `await` the result.

#### Structured Logging — Not `print()`, Not Unstructured Strings
```python
logger.info("agent.dispatch", extra={"data": {"story": story_id, "model": model}})
logger.info("agent.rate_limit", extra={"data": {"attempt": attempt, "wait_seconds": wait}})
logger.info("agent.response", extra={"data": {"tokens_input": 1200, "tokens_output": 800, "cost_usd": "0.01"}})
```
**Never:** `logger.info(f"Invoked agent with {tokens} tokens")` or `print(...)`.

#### Error Handling — Wrap SDK Errors, Never Swallow
All `ClaudeSDKError` exceptions must be caught and wrapped as `AgentError` (or appropriate subclass). The original error must be chained via `raise AgentError(...) from sdk_error`. Never catch and ignore.

---

### Claude Code SDK API Reference (v0.0.10+)

**CRITICAL: The SDK API differs significantly from the existing `MockClaudeCodeSDK` in `tests/fixtures/mock_sdk.py`. The mock must be updated to match the real typed API.**

#### Entry Point
```python
from claude_code_sdk import query, ClaudeCodeOptions

# Returns AsyncIterator of typed message objects
async for message in query(prompt="...", options=options):
    ...
```

#### `query()` Signature
```python
async def query(
    *,
    prompt: str | AsyncIterable[dict[str, Any]],
    options: ClaudeCodeOptions | None = None,
    transport: Transport | None = None,
) -> AsyncIterator[UserMessage | AssistantMessage | SystemMessage | ResultMessage | StreamEvent]
```

#### `ClaudeCodeOptions` Key Fields
```python
ClaudeCodeOptions(
    model="claude-sonnet-4-20250514",   # Model version from config
    cwd="/path/to/worktree",            # Working directory for file operations
    permission_mode="bypassPermissions", # Skip interactive permission prompts
    max_turns=None,                      # Optional turn limit
    allowed_tools=["Read", "Write", "Edit", "MultiEdit", "Bash"],  # Permitted tools
    system_prompt="...",                 # Optional system-level context
)
```

#### Message Types (yield order: AssistantMessage* → ResultMessage)
```python
# AssistantMessage — agent's response with content blocks
AssistantMessage(
    content: list[TextBlock | ToolUseBlock | ThinkingBlock],
    model: str,
    parent_tool_use_id: str | None = None,
)

# TextBlock — plain text output
TextBlock(text: str)

# ToolUseBlock — agent requesting a tool call (file write, bash, etc.)
ToolUseBlock(id: str, name: str, input: dict[str, Any])
# Tool names for file operations: "Write", "Edit", "MultiEdit", "CreateFile"
# input dict for Write: {"file_path": "src/main.py", "content": "..."}

# ResultMessage — final message with usage/cost (always last in stream)
ResultMessage(
    subtype: str,
    duration_ms: int,
    duration_api_ms: int,
    is_error: bool,
    num_turns: int,
    session_id: str,
    total_cost_usd: float | None = None,
    usage: dict[str, Any] | None = None,  # {"input_tokens": N, "output_tokens": M}
    result: str | None = None,
)
```

#### SDK Error Hierarchy
```python
ClaudeSDKError(Exception)       # Base SDK error
├── ProcessError                # Agent process crashed / non-zero exit
├── CLIConnectionError          # Can't connect to Claude CLI process
│   └── CLINotFoundError        # Claude CLI not installed
└── CLIJSONDecodeError          # Malformed JSON from CLI
```

**Rate limit detection:** The SDK does not have a dedicated `RateLimitError`. Rate limits surface as `CLIConnectionError` or `ProcessError` with messages containing "rate limit", "429", or "too many requests". Detect via regex pattern matching on the error message.

#### Sandbox Integration via `can_use_tool` Callback

**IMPORTANT DESIGN INSIGHT:** The `ClaudeCodeOptions.can_use_tool` callback provides a native hook for sandboxing:
```python
async def can_use_tool(
    tool_name: str,
    tool_input: dict[str, Any],
    context: ToolPermissionContext,
) -> PermissionResultAllow | PermissionResultDeny:
    ...
```

However, this callback is an **alternative approach** to post-hoc validation. For this story, we implement **both**:
1. **`can_use_tool` callback** — pass file-writing tool calls through `PathValidator` at the SDK level, returning `PermissionResultDeny` for violations. This is the primary enforcement mechanism.
2. **Post-iteration validation** — after collecting all `ToolUseBlock`s, verify paths as a secondary check (defense-in-depth).

This dual approach ensures sandbox enforcement even if the SDK's `can_use_tool` mechanism changes in future versions.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented. `agent/invoker.py` and `agent/prompt.py` currently have empty `__all__` — this story replaces them with real exports.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. Not directly relevant here — `InvocationResult` is a dataclass, not Pydantic.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. Not directly relevant here — no config models in this story.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. `tests/test_agent/__init__.py` already exists.

---

### Previous Story Intelligence (Story 2.4 Learnings)

**From Story 2.4 (Agent Sandbox — Path Validation Layer):**

- `PathValidator` protocol is `@runtime_checkable` — can use `isinstance(validate_path, PathValidator)` for runtime verification
- `validate_path` returns `True` on success, raises `SandboxViolation` on violation — never returns `False`. Callers must handle the exception, not check a boolean return.
- `validate_temp_path` delegates to `validate_path` first, then checks `.arcwright-ai/tmp/` containment
- Defense-in-depth: `..` components in path rejected even if resolution lands inside project
- Relative paths resolved against `project_root` — fixed in post-review. The invoker should always pass absolute paths to avoid ambiguity.
- Structured logging pattern: `logger.info("agent.sandbox.deny", extra={"data": {...}})` — event name as first arg, structured data in `extra["data"]`
- `SandboxViolation` is a subclass of `AgentError` — maps to exit code 2 (EXIT_AGENT)

**From Story 2.4 Debug Log:**
- No debug issues encountered. Clean implementation.

**From Story 2.3 (Context Answerer):**
- `@dataclass(frozen=True)` pattern for immutable data holders — use same pattern for `InvocationResult`
- `Path` guarded behind `TYPE_CHECKING` per TC003 ruff rule
- `asyncio_mode=auto` in `pyproject.toml` — `@pytest.mark.asyncio` not needed on async tests

**From Story 2.2 (Context Injector):**
- Module-level compiled regex constants for pattern matching — use same pattern for rate limit detection
- `ContextBundle` is the input to the prompt builder — already defined in `core/types.py`

---

### Technical Specifications

#### `InvocationResult` Dataclass

```python
@dataclass(frozen=True)
class InvocationResult:
    """Result of a single Claude Code SDK invocation.

    Captures the agent's output text, token consumption, cost, and
    session metadata for budget tracking and provenance.

    Attributes:
        output_text: The agent's full text output (concatenated TextBlocks).
        tokens_input: Input tokens consumed (from SDK usage report).
        tokens_output: Output tokens consumed (from SDK usage report).
        total_cost: Estimated cost in USD (Decimal for exact arithmetic).
        duration_ms: Wall-clock duration of the invocation in milliseconds.
        session_id: SDK session identifier for debugging.
        num_turns: Number of conversational turns in the session.
        is_error: Whether the SDK reported an error condition.
    """

    output_text: str
    tokens_input: int
    tokens_output: int
    total_cost: Decimal
    duration_ms: int
    session_id: str
    num_turns: int
    is_error: bool
```

#### `build_prompt` Function

```python
def build_prompt(bundle: ContextBundle) -> str:
    """Assemble an SDK prompt string from a ContextBundle.

    Formats the bundle's story content, resolved requirements, architecture
    excerpts, and project conventions into a structured prompt with clearly
    delineated markdown sections.

    Args:
        bundle: The assembled context payload from the preflight node.

    Returns:
        A formatted prompt string ready for ``claude_code_sdk.query()``.
    """
```

**Implementation logic:**

1. Start with `## Story\n\n{bundle.story_content}`
2. If `bundle.domain_requirements` is non-empty: append `\n\n## Requirements\n\n{bundle.domain_requirements}`
3. If `bundle.architecture_sections` is non-empty: append `\n\n## Architecture\n\n{bundle.architecture_sections}`
4. If `bundle.answerer_rules` is non-empty: append `\n\n## Project Conventions\n\n{bundle.answerer_rules}`
5. Return the concatenated string

#### `invoke_agent` Function

```python
async def invoke_agent(
    prompt: str,
    *,
    model: str,
    cwd: Path,
    sandbox: PathValidator,
    max_turns: int | None = None,
) -> InvocationResult:
    """Invoke Claude Code SDK to execute a story implementation.

    Calls the SDK's ``query()`` async iterator, processes streaming messages,
    validates file operations through the injected sandbox, and captures
    token usage for budget tracking.

    Args:
        prompt: The assembled prompt string from ``build_prompt()``.
        model: Claude model version identifier (e.g., ``"claude-sonnet-4-20250514"``).
        cwd: Working directory for agent file operations (typically the worktree path).
        sandbox: Path validator function (``PathValidator`` protocol) for sandbox enforcement.
        max_turns: Optional maximum conversational turns.

    Returns:
        ``InvocationResult`` containing agent output, token usage, and cost.

    Raises:
        AgentError: On SDK invocation failure (network, process crash, malformed response).
        AgentTimeoutError: On SDK timeout.
        SandboxViolation: If the agent attempts a file operation outside the sandbox boundary.
    """
```

**Implementation logic:**

1. **Build options:**
   ```python
   from claude_code_sdk import ClaudeCodeOptions, query as sdk_query
   from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock
   from claude_code_sdk._errors import ClaudeSDKError

   options = ClaudeCodeOptions(
       model=model,
       cwd=str(cwd),
       permission_mode="bypassPermissions",
       max_turns=max_turns,
       can_use_tool=_make_tool_validator(sandbox, cwd),
   )
   ```

2. **Stream and collect messages:**
   ```python
   output_parts: list[str] = []
   result_message: ResultMessage | None = None

   async for message in _invoke_with_backoff(prompt, options):
       if isinstance(message, AssistantMessage):
           for block in message.content:
               if isinstance(block, TextBlock):
                   output_parts.append(block.text)
               elif isinstance(block, ToolUseBlock):
                   _validate_tool_use(block, sandbox, cwd)
       elif isinstance(message, ResultMessage):
           result_message = message
   ```

3. **Build result:** Extract tokens from `result_message.usage`, cost from `result_message.total_cost_usd`, assemble `InvocationResult`.

4. **Handle missing ResultMessage:** If no `ResultMessage` received, raise `AgentError("SDK stream ended without ResultMessage")`.

#### `_make_tool_validator` — SDK-level Sandbox Hook

```python
def _make_tool_validator(
    sandbox: PathValidator, cwd: Path,
) -> Callable[[str, dict[str, Any], Any], Awaitable[PermissionResultAllow | PermissionResultDeny]]:
    """Create a ``can_use_tool`` callback that validates file operations via the sandbox.

    Args:
        sandbox: The injected path validator.
        cwd: The working directory (sandbox boundary).

    Returns:
        An async callback compatible with ``ClaudeCodeOptions.can_use_tool``.
    """
```

**Implementation:**
- File-writing tools (`Write`, `Edit`, `MultiEdit`, `CreateFile`): extract `file_path` from `tool_input`, call `sandbox(Path(file_path), cwd, tool_name)`, return `PermissionResultAllow()` on success or `PermissionResultDeny(reason="...")` on `SandboxViolation`
- All other tools: return `PermissionResultAllow()` (non-file tools are not sandboxed)

#### Rate Limit Backoff

```python
_RATE_LIMIT_RE = re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE)
_BACKOFF_BASE: float = 1.0
_BACKOFF_CAP: float = 60.0
_BACKOFF_MAX_RETRIES: int = 5
```

**Logic:**
```python
for attempt in range(_BACKOFF_MAX_RETRIES):
    try:
        return sdk_query(prompt=prompt, options=options)
    except ClaudeSDKError as e:
        if _RATE_LIMIT_RE.search(str(e)):
            wait = min(_BACKOFF_BASE * (2 ** attempt) + random.uniform(0, 0.5), _BACKOFF_CAP)
            logger.info("agent.rate_limit", extra={"data": {"attempt": attempt + 1, "wait_seconds": round(wait, 2)}})
            await asyncio.sleep(wait)
        else:
            raise _wrap_sdk_error(e) from e
raise AgentError("Rate limit: max retries exhausted", details={"attempts": _BACKOFF_MAX_RETRIES})
```

#### Constants Used

From `core/constants.py` (already defined):
- `DIR_ARCWRIGHT = ".arcwright-ai"` — the Arcwright state directory  
- `DIR_TMP = "tmp"` — the temp file subdirectory

New module-level constants in `agent/invoker.py`:
- `_BACKOFF_BASE: float = 1.0`
- `_BACKOFF_CAP: float = 60.0`
- `_BACKOFF_MAX_RETRIES: int = 5`
- `_RATE_LIMIT_RE: re.Pattern[str]` — compiled regex for rate limit detection
- `_FILE_WRITE_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "MultiEdit", "CreateFile"})` — tool names that require sandbox validation

---

### Project Structure Notes

**Files to create/modify:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/agent/invoker.py` | MODIFY (was placeholder) | `InvocationResult` dataclass, `invoke_agent`, `_invoke_with_backoff`, `_wrap_sdk_error`, `_make_tool_validator`, `_validate_tool_use` |
| `src/arcwright_ai/agent/prompt.py` | MODIFY (was placeholder) | `build_prompt` function |
| `src/arcwright_ai/agent/__init__.py` | MODIFY | Add `InvocationResult`, `build_prompt`, `invoke_agent` exports alongside existing sandbox exports |
| `tests/fixtures/mock_sdk.py` | MODIFY | Refactor `MockClaudeCodeSDK` → `MockSDKClient` with typed message objects matching real SDK |
| `tests/test_agent/test_invoker.py` | CREATE | Unit tests for invoker (success, failure, rate limit, malformed, sandbox violation) |
| `tests/test_agent/test_prompt.py` | CREATE | Unit tests for prompt builder |

**Files NOT touched** (no changes needed):
- `core/types.py` — `ContextBundle`, `BudgetState` already defined
- `core/exceptions.py` — `AgentError`, `AgentTimeoutError`, `SandboxViolation` already defined
- `core/constants.py` — `DIR_ARCWRIGHT`, `DIR_TMP` already defined
- `core/io.py` — no file I/O primitives used directly by invoker
- `core/lifecycle.py` — no state transitions in this story
- `core/events.py` — using standard `logging` module, no event emitter changes
- `context/` — no context changes
- `engine/` — no engine integration (Story 2.7 scope)
- `cli/` — no CLI changes
- `agent/sandbox.py` — fully implemented in Story 2.4, used as-is

**Alignment with architecture:**
- `agent/invoker.py` matches architecture's project tree: "Claude Code SDK async integration"
- `agent/prompt.py` matches architecture's project tree: "Prompt construction helpers"
- FR19 mapping: `agent/invoker.py` — "Stateless agent invocation, one session per story"
- FR20 mapping: `agent/sandbox.py` via `PathValidator` injection — "Validates all agent file operations"
- FR22 mapping: `agent/invoker.py` — "Rate limit backoff and queuing"
- D6 mapping: `agent/invoker.py` — "AgentError hierarchy for SDK error wrapping"
- Boundary 3: "Invoker receives sandbox as a validator function via dependency injection"

---

### Cross-Story Context (Epic 2 Stories That Interact with 2.5)

| Story | Relationship to 2.5 | Impact |
|---|---|---|
| 2.4: Agent Sandbox | Provides `PathValidator` protocol and `validate_path` function | Invoker takes `PathValidator` as a parameter — dependency injection, not direct import of sandbox implementation |
| 2.6: Preflight Node | Assembles `ContextBundle` that feeds into `build_prompt` | Preflight calls `context/injector.py` → stores bundle in state → engine calls `build_prompt(bundle)` |
| 2.7: Agent Dispatch Node | Wires `invoke_agent` into the LangGraph pipeline | The dispatch node calls `invoke_agent()` with prompt from `build_prompt()`, model from config, cwd from state, sandbox validator |
| 3.2: V3 Reflexion | Uses same SDK invocation pattern for reflexion prompt | V3 reflexion may reuse `invoke_agent` or call `query()` directly — either way, `MockSDKClient` fixture is shared |
| 3.4: Validate & Retry | Passes reflexion feedback back through `invoke_agent` on retry | Retry prompt = original prompt + reflexion feedback; invoker doesn't change, prompt changes |

**Important note for Story 2.7 handoff:** The `invoke_agent` function takes `cwd: Path` as the sandbox boundary. During actual story execution (Stories 2.7 / 6.2), the engine's `agent_dispatch` node will pass the **worktree path** as `cwd`, not the main project root. The invoker doesn't know or care about worktrees — it just validates against whatever `cwd` it's given.

**Important note for MockSDKClient:** The updated `MockSDKClient` in `tests/fixtures/mock_sdk.py` becomes the **canonical test fixture** for all subsequent stories (3.2, 3.4, 5.1, 7.1, 7.2, 7.4) that test through the agent dispatch path. The mock must support configurable scenarios (success, failure, rate limit, tool use) and return typed SDK message objects.

---

### Git Intelligence

Last 5 commits:
```
edc85eb fix(agent): harden sandbox relative-path resolution and finalize Story 2.4
3d16d16 feat(agent): implement Story 2.4 — Agent Sandbox Path Validation Layer
c404c4c feat(context): implement Story 2.3 — Context Answerer, Static Rule Lookup Engine
f91e3a5 chore(story-2.2): post-format fixes, finalize story file, and sprint status
bcdbba7 feat(context): implement Story 2.2 — Context Injector, BMAD Artifact Reader & Reference Resolver
```

**Patterns established:**
- Commit prefix: `feat(agent):` for new feature in agent package — use this prefix for this story
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- `agent/__init__.py` was first populated in Story 2.4 — extend it, don't reset

**Files from previous stories that are relevant:**
- `src/arcwright_ai/agent/sandbox.py` — `PathValidator` protocol and `validate_path` to inject into invoker
- `src/arcwright_ai/agent/__init__.py` — current exports to extend (PathValidator, validate_path, validate_temp_path)
- `src/arcwright_ai/core/types.py` — `ContextBundle` (input to prompt builder), `BudgetState` (updated after invocation)
- `src/arcwright_ai/core/exceptions.py` — `AgentError`, `AgentTimeoutError`, `SandboxViolation` exception classes
- `src/arcwright_ai/core/config.py` — `RunConfig` with `model.version` field (provides model name)
- `src/arcwright_ai/core/constants.py` — `DIR_ARCWRIGHT`, `DIR_TMP`
- `tests/fixtures/mock_sdk.py` — existing mock to refactor into typed `MockSDKClient`

---

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
def test_build_prompt_full_bundle(): ...
async def test_invoke_agent_success_returns_result(): ...
async def test_invoke_agent_rate_limit_retries_with_backoff(): ...
```

**Async tests:** `asyncio_mode=auto` in `pyproject.toml` means `@pytest.mark.asyncio` is NOT needed. Just use `async def test_...:`.

**MockSDKClient fixture pattern:**
```python
@pytest.fixture
def mock_sdk() -> MockSDKClient:
    return MockSDKClient(output_text="# Implementation\nDone.", tokens_input=500, tokens_output=200)
```

**Monkeypatch for SDK import:** The invoker imports `claude_code_sdk` at function level. Tests should monkeypatch the `query` function or inject the mock via a factory pattern:
```python
# Option A: Monkeypatch at module level
async def test_invoke_agent_success(monkeypatch, mock_sdk, project_root):
    monkeypatch.setattr("claude_code_sdk.query", mock_sdk.query)
    result = await invoke_agent(prompt="...", model="test", cwd=project_root, sandbox=validate_path)
    assert result.output_text == "# Implementation\nDone."
```

**Sandbox in tests:** Use real `validate_path` function from `agent/sandbox.py` — no mock needed for the sandbox since it's a pure function with no side effects.

**File fixtures:** Use `tmp_path` fixture for creating temporary project structures:
```python
@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "test-project"
    root.mkdir()
    (root / ".arcwright-ai" / "tmp").mkdir(parents=True)
    return root
```

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries:
```python
assert result.output_text == "Done."
assert result.tokens_input == 500

with pytest.raises(AgentError, match="rate limit"):
    await invoke_agent(...)
```

**Test isolation:** Each test creates its own state via fixtures. No shared mutable state between tests.

---

### References

- [Source: _spec/planning-artifacts/architecture.md#Boundary-3 — Agent Invoker ↔ Sandbox dependency injection contract]
- [Source: _spec/planning-artifacts/architecture.md#Decision-6 — AgentError hierarchy, exit code 2]
- [Source: _spec/planning-artifacts/architecture.md#Decision-7 — No persistent agent state between stories]
- [Source: _spec/planning-artifacts/architecture.md#Decision-8 — Structured logging JSONL events]
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG — agent/ depends only on core/]
- [Source: _spec/planning-artifacts/architecture.md#Async-Patterns — asyncio.to_thread, async generators]
- [Source: _spec/planning-artifacts/architecture.md#Project-Structure — agent/invoker.py, agent/prompt.py]
- [Source: _spec/planning-artifacts/architecture.md#Testing-Patterns — MockSDKClient fixture, async tests]
- [Source: _spec/planning-artifacts/epics.md#Story-2.5 — Acceptance criteria, story definition]
- [Source: _spec/planning-artifacts/prd.md#FR19 — Stateless agent invocation, one session per story]
- [Source: _spec/planning-artifacts/prd.md#FR20 — Agent file operations cannot escape project base directory]
- [Source: _spec/planning-artifacts/prd.md#FR21 — Temp files to .arcwright-ai/tmp/, cleaned up]
- [Source: _spec/planning-artifacts/prd.md#FR22 — Rate limit backoff and queuing]
- [Source: _spec/planning-artifacts/prd.md#NFR7 — Application-level path safety enforcement]
- [Source: _spec/planning-artifacts/prd.md#NFR9 — Orchestration overhead < 30s per story]
- [Source: _spec/planning-artifacts/prd.md#NFR13 — SDK version pinned in project dependencies]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — Known pitfalls, Action Items 1-3]
- [Source: _spec/implementation-artifacts/2-4-agent-sandbox-path-validation-layer.md — PathValidator protocol, SandboxViolation, validate_path patterns]
- [Source: _spec/implementation-artifacts/2-3-context-answerer-static-rule-lookup-engine.md — Structured logging, dataclass patterns]
- [Source: arcwright-ai/src/arcwright_ai/agent/invoker.py — Current empty placeholder]
- [Source: arcwright-ai/src/arcwright_ai/agent/prompt.py — Current empty placeholder]
- [Source: arcwright-ai/src/arcwright_ai/agent/__init__.py — Current sandbox exports to extend]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — ContextBundle, BudgetState models]
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py — AgentError hierarchy]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — DIR_ARCWRIGHT, DIR_TMP]
- [Source: arcwright-ai/tests/fixtures/mock_sdk.py — Existing MockClaudeCodeSDK to refactor]
- [Source: arcwright-ai/pyproject.toml — claude-code-sdk>=0.0.10 dependency]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No debug issues encountered. Clean implementation.

### Completion Notes List

- ✅ Implemented `InvocationResult` frozen dataclass with all required fields (output_text, tokens_input, tokens_output, total_cost, duration_ms, session_id, num_turns, is_error)
- ✅ Implemented `build_prompt` in `agent/prompt.py` — formats ContextBundle into structured markdown sections (Story, Requirements, Architecture, Project Conventions); optional sections omitted when empty
- ✅ Implemented `invoke_agent` async function with lazy SDK imports for monkeypatching testability
- ✅ Implemented `_make_tool_validator` creating a `can_use_tool` callback for SDK-level sandbox enforcement (primary)
- ✅ Implemented `_validate_tool_use` for post-stream defense-in-depth sandbox validation (secondary)
- ✅ Implemented `_invoke_with_backoff` async generator with exponential backoff + jitter on rate limit errors; structured `agent.rate_limit` event logging
- ✅ Implemented `_wrap_sdk_error` wrapping ClaudeSDKError subclasses to AgentError/AgentTimeoutError with original message in details
- ✅ All SDK imports lazy (inside functions) — monkeypatching via `monkeypatch.setattr(claude_code_sdk, "query", mock.query)` works correctly
- ✅ Refactored `MockClaudeCodeSDK` → `MockSDKClient` with typed SDK message objects; backward-compatible alias preserved
- ✅ 16 new tests (10 invoker + 6 prompt) — all pass; 277 total suite passes (no regressions)
- ✅ All quality gates: ruff check ✓, ruff format ✓, mypy --strict src/ ✓
- ✅ Post-review fixes applied: temp-path enforcement for `.arcwright-ai/tmp/` plus temp directory auto-create in invoker
- ✅ Post-review fixes applied: sandbox-violation structured logging added for SDK-level and post-stream tool validation paths
- ✅ Post-review fixes applied: `MockSDKClient` now supports configurable error phase (`before`/`during`) and malformed stream simulation (`omit_result_message`)
- ✅ Post-review fixes applied: malformed-response test now uses `MockSDKClient` fixture (no ad-hoc SDK stream monkeypatch)
- ℹ️ SDK introspected at v0.0.25 (story spec referenced v0.0.10+); API compatible
- ℹ️ `_invoke_with_backoff` implemented as async generator (PEP 525) annotated `AsyncGenerator[Any, None]`; mypy --strict accepts this

### File List

- src/arcwright_ai/agent/invoker.py
- src/arcwright_ai/agent/prompt.py
- src/arcwright_ai/agent/__init__.py
- tests/fixtures/mock_sdk.py
- tests/test_agent/test_invoker.py
- tests/test_agent/test_prompt.py
- _spec/implementation-artifacts/sprint-status.yaml

### Senior Developer Review (AI)

Date: 2026-03-02
Reviewer: Ed (AI-assisted code review)
Outcome: Approved after fixes

Summary:
- Fixed all HIGH and MEDIUM findings from adversarial review.
- Verified AC #8 behavior by enforcing temp-path constraints to `.arcwright-ai/tmp/` and ensuring temp directory creation in invoker validation paths.
- Updated test strategy to ensure malformed stream coverage uses canonical `MockSDKClient` fixture.
- Synchronized story documentation and sprint tracking status with final implementation state.

### Change Log

- 2026-03-02: Applied post-review fixes for temp path handling, sandbox violation logging, mock SDK configurability, and malformed response test fixture usage; story advanced to `done`.
