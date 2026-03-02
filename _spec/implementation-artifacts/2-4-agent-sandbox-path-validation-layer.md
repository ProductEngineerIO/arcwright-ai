# Story 2.4: Agent Sandbox — Path Validation Layer

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer ensuring agent safety,
I want an application-level path validation layer that prevents the agent from modifying files outside the project boundary,
so that story execution cannot corrupt the main branch, other worktrees, or the host system.

## Acceptance Criteria (BDD)

1. **Given** `agent/sandbox.py` implemented as a pure validator function **When** the sandbox validates a file operation **Then** `validate_path(path: Path, project_root: Path, operation: str) -> bool` returns `True` only if the resolved path is within `project_root`.

2. **Given** a path that contains traversal components (e.g., `../../etc/passwd`) **When** `validate_path` is called **Then** it rejects the path and raises `SandboxViolation` (subclass of `AgentError`) with a descriptive message including the offending path and the operation attempted.

3. **Given** a symlink whose target resolves outside `project_root` **When** `validate_path` is called **Then** it detects the symlink escape and raises `SandboxViolation` with a message identifying the symlink and its resolved target.

4. **Given** a temp file operation **When** `validate_temp_path` is called **Then** it validates that the path targets `.arcwright-ai/tmp/` (and subdirectories) only — temp files anywhere else raise `SandboxViolation`.

5. **Given** `agent/sandbox.py` **When** its imports are inspected **Then** it has zero coupling to Claude Code SDK — it validates `(path, operation) → allow/deny` as a pure function depending only on `core/`.

6. **Given** the sandbox's public API **When** used by the invoker (Story 2.5) **Then** the sandbox is designed for dependency injection — a `PathValidator` Protocol is defined so the invoker depends on the protocol, not the concrete implementation.

7. **Given** unit tests in `tests/test_agent/test_sandbox.py` **When** `pytest tests/test_agent/test_sandbox.py` is run **Then** tests cover: valid paths (within project), path traversal rejection, symlink escape detection, temp file validation, `.arcwright-ai/` subdirectory access.

8. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

9. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

10. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Add `SandboxViolation` exception to `core/exceptions.py` (AC: #2, #5)
  - [x] 1.1: Add `SandboxViolation` class as a subclass of `AgentError` with docstring: "Raised when an agent file operation targets a path outside the project boundary or violates sandbox rules."
  - [x] 1.2: Add `"SandboxViolation"` to `__all__` in `core/exceptions.py` — maintain alphabetical order (RUF022)
  - [x] 1.3: Add Google-style docstring

- [x] Task 2: Update `core/__init__.py` to export `SandboxViolation` (AC: #5)
  - [x] 2.1: Add `SandboxViolation` to the import block from `arcwright_ai.core.exceptions`
  - [x] 2.2: Add `"SandboxViolation"` to `__all__` in `core/__init__.py` — maintain alphabetical order (RUF022)

- [x] Task 3: Implement `PathValidator` Protocol and `validate_path` in `agent/sandbox.py` (AC: #1, #2, #3, #5, #6, #10)
  - [x] 3.1: Add `from __future__ import annotations` as first line (already present as placeholder)
  - [x] 3.2: Add imports: `logging`, `os` from stdlib; `Path` from `pathlib` (behind `TYPE_CHECKING`); `Protocol` and `runtime_checkable` from `typing`; `SandboxViolation` from `arcwright_ai.core.exceptions`; `DIR_ARCWRIGHT`, `DIR_TMP` from `arcwright_ai.core.constants`
  - [x] 3.3: Create module-level logger: `logger = logging.getLogger(__name__)`
  - [x] 3.4: Define `@runtime_checkable` class `PathValidator(Protocol)` with `def __call__(self, path: Path, project_root: Path, operation: str) -> bool: ...` — this protocol enables dependency injection of the sandbox validator into the invoker
  - [x] 3.5: Implement `def validate_path(path: Path, project_root: Path, operation: str) -> bool`:
    - Resolve `project_root` to absolute via `project_root.resolve()`
    - Resolve `path` to absolute via `path.resolve()` (follows symlinks)
    - Check if resolved path starts with resolved project_root using `os.path.commonpath()` or `.is_relative_to()`
    - If NOT within project_root → raise `SandboxViolation` with message including path, project_root, and operation
    - Check for symlink escape: if `path` is a symlink (or any parent component is), verify `path.resolve()` is still within `project_root.resolve()` — the `.resolve()` call above already handles this, but add an explicit check using `path.exists()` and comparing `str(path.resolve())` to detect escapes
    - Check for path traversal: detect `..` components in the **original** (non-resolved) path string — even if resolution lands within project_root, explicit `..` usage is suspicious and should be rejected for defense-in-depth
    - Log successful validation: `logger.debug("agent.sandbox.allow", extra={"data": {"path": str(path), "operation": operation}})`
    - Return `True`
  - [x] 3.6: Add Google-style docstring with Args, Returns, Raises sections

- [x] Task 4: Implement `validate_temp_path` in `agent/sandbox.py` (AC: #4, #10)
  - [x] 4.1: Implement `def validate_temp_path(path: Path, project_root: Path) -> bool`:
    - First call `validate_path(path, project_root, "write_temp")` to ensure within project boundary
    - Then verify the resolved path is under `project_root / DIR_ARCWRIGHT / DIR_TMP` — using `Path.is_relative_to()`
    - If NOT under tmp directory → raise `SandboxViolation` with message: "Temp files must be written to {project_root}/.arcwright-ai/tmp/, got: {path}"
    - Log successful validation: `logger.debug("agent.sandbox.allow_temp", extra={"data": {"path": str(path)}})`
    - Return `True`
  - [x] 4.2: Add Google-style docstring with Args, Returns, Raises sections

- [x] Task 5: Update `agent/sandbox.py` and `agent/__init__.py` exports (AC: #8)
  - [x] 5.1: Set `__all__` in `agent/sandbox.py`: `["PathValidator", "validate_path", "validate_temp_path"]` (alphabetical per RUF022)
  - [x] 5.2: Update `agent/__init__.py` to import and re-export: `PathValidator`, `validate_path`, `validate_temp_path` from `agent.sandbox`
  - [x] 5.3: Update `agent/__init__.py` `__all__` in alphabetical order — replace empty list with new exports. Remove any aspirational comments about future exports (no aspirational exports — pitfall from Epic 1)

- [x] Task 6: Write unit tests in `tests/test_agent/test_sandbox.py` (AC: #7)
  - [x] 6.1: Create `tests/test_agent/test_sandbox.py` with `from __future__ import annotations`
  - [x] 6.2: Create helper fixtures:
    - `project_root(tmp_path)` — creates `tmp_path / "my-project"` directory with `.arcwright-ai/tmp/` subdirectory, returns the project directory path
    - `arcwright_tmp(project_root)` — returns `project_root / ".arcwright-ai" / "tmp"` path (already created by `project_root` fixture)
  - [x] 6.3: Test `test_validate_path_allows_file_within_project` — create a file at `project_root / "src" / "main.py"`, call `validate_path` → returns `True`
  - [x] 6.4: Test `test_validate_path_allows_nested_subdirectory` — validate a path like `project_root / "src" / "deep" / "nested" / "file.py"` → returns `True`
  - [x] 6.5: Test `test_validate_path_rejects_path_traversal` — path `project_root / ".." / "etc" / "passwd"` → raises `SandboxViolation` with "traversal" or ".." in the message
  - [x] 6.6: Test `test_validate_path_rejects_absolute_outside_project` — path `/etc/passwd` → raises `SandboxViolation`
  - [x] 6.7: Test `test_validate_path_rejects_symlink_escape` — create a symlink inside project pointing to `/tmp` (outside project), validate the symlink path → raises `SandboxViolation`
  - [x] 6.8: Test `test_validate_path_allows_symlink_within_project` — create a symlink inside project pointing to another directory within project, validate → returns `True`
  - [x] 6.9: Test `test_validate_path_rejects_double_dot_even_if_resolves_inside` — path like `project_root / "src" / ".." / "src" / "file.py"` which resolves inside project but contains `..` → raises `SandboxViolation` (defense-in-depth)
  - [x] 6.10: Test `test_validate_temp_path_allows_arcwright_tmp` — path `project_root / ".arcwright-ai" / "tmp" / "scratch.txt"` → returns `True`
  - [x] 6.11: Test `test_validate_temp_path_allows_nested_tmp` — path `project_root / ".arcwright-ai" / "tmp" / "sub" / "file.txt"` → returns `True`
  - [x] 6.12: Test `test_validate_temp_path_rejects_non_tmp_arcwright` — path `project_root / ".arcwright-ai" / "runs" / "file.txt"` → raises `SandboxViolation`
  - [x] 6.13: Test `test_validate_temp_path_rejects_project_root_file` — path `project_root / "src" / "file.py"` as temp → raises `SandboxViolation`
  - [x] 6.14: Test `test_validate_temp_path_rejects_outside_project` — path `/tmp/file.txt` as temp → raises `SandboxViolation`
  - [x] 6.15: Test `test_validate_path_allows_arcwright_subdirectory` — path `project_root / ".arcwright-ai" / "runs" / "12345" / "output.md"` → returns `True` (it's within project, just not temp)
  - [x] 6.16: Test `test_sandbox_violation_is_agent_error_subclass` — verify `issubclass(SandboxViolation, AgentError)` is `True`
  - [x] 6.17: Test `test_sandbox_violation_carries_details` — raise `SandboxViolation("msg", details={"path": "/bad"})`, verify `.message` and `.details` are accessible
  - [x] 6.18: Test `test_path_validator_protocol_satisfied` — verify `isinstance(validate_path, PathValidator)` is `True` (runtime checkable protocol)
  - [x] 6.19: Test `test_validate_path_operation_appears_in_error` — trigger `SandboxViolation` and verify the `operation` string appears in the exception message

- [x] Task 7: Validate all quality gates (AC: #8, #9)
  - [x] 7.1: Run `ruff check .` — zero violations
  - [x] 7.2: Run `ruff format --check .` — no formatting diffs
  - [x] 7.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 7.4: Run `pytest tests/test_agent/test_sandbox.py -v` — all new tests pass
  - [x] 7.5: Run `pytest` — full test suite passes (no regressions)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `agent/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
`agent/` depends ONLY on `core/`. It must NOT import from `engine/`, `context/`, `validation/`, `output/`, or `scm/`. The `engine/` package will wire `agent/sandbox.py` into the agent_dispatch node (Story 2.7). This story implements the standalone path validation logic — no engine integration.

#### Boundary 3: Agent Invoker ↔ Sandbox (Architecture Doc)
- Invoker receives sandbox as a validator function via **dependency injection**
- Sandbox has **zero knowledge of Claude Code SDK** — it validates `(path, operation) → allow/deny`
- Invoker calls sandbox **before applying** any file operation from agent output
- The `PathValidator` Protocol is the contract between sandbox and invoker

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. When populating `agent/sandbox.py` and updating `agent/__init__.py`, sort all entries alphabetically.

#### Pure Synchronous Functions — No Async Needed
Unlike Story 2.2/2.3 which used async for file I/O during indexing, the sandbox is purely synchronous. `validate_path` and `validate_temp_path` perform only `Path.resolve()` and `Path.is_relative_to()` — stdlib synchronous operations. No `asyncio.to_thread()` wrapping needed. No `read_text_async()` calls.

#### Structured Logging — Not `print()`, Not Unstructured Strings
```python
logger.debug("agent.sandbox.allow", extra={"data": {"path": str(path), "operation": operation}})
logger.info("agent.sandbox.deny", extra={"data": {"path": str(path), "operation": operation, "reason": "path_traversal"}})
```
**Never:** `logger.info(f"Path {path} rejected")` or `print(...)`.

#### Error Handling — Raise `SandboxViolation`, Never Return `False`
The `validate_path` function returns `True` on success and raises `SandboxViolation` on any violation. It never returns `False`. This is a safety design choice — callers cannot accidentally ignore a `False` return. The exception forces handling.

```python
# Correct pattern:
if validate_path(path, project_root, "write"):
    # proceed with write

# The function will raise SandboxViolation before returning False,
# so the caller never sees a False return.
```

#### `SandboxViolation` Exception — New Addition to Hierarchy
The architecture doc references `SandboxViolation` in the exception hierarchy comment for `agent/sandbox.py`. It's not yet in `core/exceptions.py`. This story adds it:

```python
class SandboxViolation(AgentError):
    """Raised when an agent file operation targets a path outside the project boundary."""
```

This maps to exit code 2 (`EXIT_AGENT`) since it's a subclass of `AgentError`.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented. `agent/sandbox.py` currently has empty `__all__` — this story replaces it with real exports. `agent/__init__.py` has a comment about a future `invoke_agent` — remove the comment, add only real exports.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. Not directly relevant here — no Pydantic models in this story.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. Not directly relevant here — no config models in this story.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. `tests/test_agent/__init__.py` already exists.

---

### Previous Story Intelligence (Story 2.3 Learnings)

**From Story 2.3 (Context Answerer — Static Rule Lookup Engine):**

- `IndexedSection` used `@dataclass(frozen=True)` — follow same pattern if data classes needed. This story doesn't need data classes since it's all pure functions.
- `Path` is guarded behind `TYPE_CHECKING` per TC003 ruff rule. Runtime-needed imports stay top-level.
- Structured logging pattern: `logger.info("event.name", extra={"data": {...}})` — event name as first arg, structured data in `extra["data"]`.
- `__all__` in `context/__init__.py` was extended with new exports while preserving existing ones. Follow same approach for `agent/__init__.py`.
- `asyncio_mode=auto` in `pyproject.toml` — `@pytest.mark.asyncio` not needed on async tests. But this story has no async tests — all functions are synchronous.
- Test fixtures use `tmp_path` for creating temporary structures.

**From Story 2.3 Debug Log:**
- No debug issues encountered. Clean implementation.
- Senior review found missing imports and missing precompiled regex map. For this story: ensure all imports are present and any module-level compiled patterns exist.

**From Story 2.2 (Context Injector):**
- `Path` moved to `TYPE_CHECKING` block per TC003 ruff rule.
- Module-level compiled regex constants used for FR/NFR pattern matching. Not directly needed here, but useful pattern reference.

---

### Technical Specifications

#### `PathValidator` Protocol

```python
@runtime_checkable
class PathValidator(Protocol):
    """Protocol for path validation functions.

    The invoker depends on this protocol, not the concrete ``validate_path``
    function, enabling dependency injection and test doubles.
    """

    def __call__(self, path: Path, project_root: Path, operation: str) -> bool:
        """Validate that *path* is permitted for *operation* within *project_root*.

        Args:
            path: The file path to validate.
            project_root: The project root directory — the sandbox boundary.
            operation: Description of the file operation (e.g., "read", "write",
                "delete") for error context.

        Returns:
            ``True`` if the path is allowed.

        Raises:
            SandboxViolation: If the path violates sandbox rules.
        """
        ...
```

#### `validate_path` Function

```python
def validate_path(path: Path, project_root: Path, operation: str) -> bool:
    """Validate that a file operation path is within the project boundary.

    Resolves the path, checks for path traversal and symlink escapes, and
    ensures the resolved path falls within *project_root*.

    Args:
        path: The file path to validate (may be relative or absolute).
        project_root: The project root directory — the sandbox boundary.
        operation: Description of the file operation for error messages.

    Returns:
        ``True`` if the path is within the project boundary.

    Raises:
        SandboxViolation: If the path is outside the project boundary,
            contains path traversal components, or escapes via symlink.
    """
```

**Implementation logic:**

1. **Defense-in-depth `..` check**: Inspect `path.parts` for any `".."` component. If found, immediately raise `SandboxViolation` — even if the resolved path would land inside the project. This prevents crafted paths like `project/src/../../project/src/file.py`.

2. **Resolve and boundary check**: Resolve both `path` and `project_root` to absolute paths using `.resolve()` (which follows symlinks). Use `resolved_path.is_relative_to(resolved_root)` (Python 3.9+) to verify containment. If not relative, raise `SandboxViolation`.

3. **Symlink escape detection**: The `.resolve()` in step 2 already follows symlinks. If `path` contains a symlink pointing outside `project_root`, the resolved path will be outside and step 2 catches it. For extra safety, if the original `path` exists and is a symlink, log a `agent.sandbox.symlink_resolved` event with both the original and resolved paths.

4. **Log and return**: Log `agent.sandbox.allow` at debug level, return `True`.

#### `validate_temp_path` Function

```python
def validate_temp_path(path: Path, project_root: Path) -> bool:
    """Validate that a temp file path targets ``.arcwright-ai/tmp/`` only.

    First validates the path is within the project boundary, then checks
    it targets the designated temp directory.

    Args:
        path: The temp file path to validate.
        project_root: The project root directory.

    Returns:
        ``True`` if the path is within ``.arcwright-ai/tmp/``.

    Raises:
        SandboxViolation: If the path is outside the project boundary or
            targets a directory other than ``.arcwright-ai/tmp/``.
    """
```

**Implementation logic:**

1. Call `validate_path(path, project_root, "write_temp")` — reuse boundary validation.
2. Compute `tmp_dir = (project_root / DIR_ARCWRIGHT / DIR_TMP).resolve()`.
3. Check `path.resolve().is_relative_to(tmp_dir)`.
4. If not under tmp → raise `SandboxViolation` with message: `f"Temp files must target {tmp_dir}, got: {path.resolve()}"`.
5. Return `True`.

#### Constants Used

From `core/constants.py` (already defined):
- `DIR_ARCWRIGHT = ".arcwright-ai"` — the Arcwright state directory
- `DIR_TMP = "tmp"` — the temp file subdirectory

---

### Project Structure Notes

**Files to create/modify:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/core/exceptions.py` | MODIFY | Add `SandboxViolation` exception class and `__all__` entry |
| `src/arcwright_ai/core/__init__.py` | MODIFY | Add `SandboxViolation` to import and `__all__` |
| `src/arcwright_ai/agent/sandbox.py` | MODIFY (was placeholder) | `PathValidator` protocol, `validate_path`, `validate_temp_path` |
| `src/arcwright_ai/agent/__init__.py` | MODIFY | Add `PathValidator`, `validate_path`, `validate_temp_path` exports |
| `tests/test_agent/test_sandbox.py` | CREATE | Unit tests for all sandbox functionality |

**Files NOT touched** (no changes needed):
- `core/types.py` — no new types needed
- `core/io.py` — no file I/O primitives used (this is pure path logic)
- `core/constants.py` — `DIR_ARCWRIGHT` and `DIR_TMP` already defined
- `core/lifecycle.py` — no state transitions in this story
- `core/events.py` — using standard `logging` module, no event emitter changes
- `context/` — no context changes
- `engine/` — no engine integration (Story 2.7 scope)
- `cli/` — no CLI changes
- `agent/invoker.py` — invoker wiring is Story 2.5 scope
- `agent/prompt.py` — prompt building is Story 2.5 scope

**Alignment with architecture:**
- `agent/sandbox.py` matches architecture's project tree: "Path validator: (path, op) → allow/deny"
- FR20 mapping: `agent/sandbox.py` — "Validates all agent file operations stay within worktree"
- FR21 mapping: `agent/sandbox.py` — "Ensures temp files written to .arcwright-ai/ not project root"
- NFR7 mapping: `agent/sandbox.py` — "Application-level enforcement, independent of SDK"
- Boundary 3: "Invoker receives sandbox as a validator function via dependency injection"

---

### Cross-Story Context (Epic 2 Stories That Interact with 2.4)

| Story | Relationship to 2.4 | Impact |
|---|---|---|
| 2.5: Agent Invoker | Invoker calls `validate_path` before applying every agent file operation | Invoker takes `PathValidator` as a constructor/function parameter — dependency injection, not direct import |
| 2.6: Preflight Node | Sets the project_root and worktree path that becomes the sandbox boundary | Preflight determines `StoryState.project_root` which is passed to sandbox by the invoker |
| 2.7: Agent Dispatch Node | Wires invoker + sandbox together in the LangGraph pipeline | The dispatch node creates the invoker with sandbox injected |
| 6.2: Worktree Manager | Worktree path becomes the effective sandbox boundary per story | During story execution, `project_root` for sandbox is the worktree path, not the main project root |

**Important note for Story 2.5 handoff:** The `validate_path` function takes `project_root: Path` as a parameter. During actual story execution (Stories 2.7 / 6.2), the invoker will pass the **worktree path** as `project_root`, not the main project root. The sandbox doesn't know or care about worktrees — it just validates against whatever root it's given. This is the correct design for Boundary 3 separation.

---

### Git Intelligence

Last 5 commits:
```
c404c4c feat(context): implement Story 2.3 — Context Answerer, Static Rule Lookup Engine
f91e3a5 chore(story-2.2): post-format fixes, finalize story file, and sprint status
bcdbba7 feat(context): implement Story 2.2 — Context Injector, BMAD Artifact Reader & Reference Resolver
70d73e6 chore(story-2.1): finalize story file, quality-gate fixes, and sprint status
51fdf4d feat(engine): implement Story 2.1 — LangGraph state models and graph skeleton
```

**Patterns established:**
- Commit prefix: `feat(agent):` for new feature in agent package — use this prefix for this story
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- `agent/__init__.py` currently has empty exports — will be populated for the first time

**Files from previous stories that are relevant:**
- `src/arcwright_ai/core/exceptions.py` — exception hierarchy to extend with `SandboxViolation`
- `src/arcwright_ai/core/__init__.py` — re-exports to extend
- `src/arcwright_ai/core/constants.py` — `DIR_ARCWRIGHT`, `DIR_TMP` constants to use
- `src/arcwright_ai/agent/sandbox.py` — current empty placeholder to implement
- `src/arcwright_ai/agent/__init__.py` — current empty exports to populate

---

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
def test_validate_path_allows_file_within_project(): ...
def test_validate_path_rejects_path_traversal(): ...
def test_validate_temp_path_allows_arcwright_tmp(): ...
```

**All tests are synchronous:** Both `validate_path` and `validate_temp_path` are synchronous functions. No `async def` test functions needed. No `@pytest.mark.asyncio` required.

**Note:** `asyncio_mode=auto` is configured in `pyproject.toml`, so async tests would work without explicit decorators — but this story has none.

**File fixtures:** Use `tmp_path` fixture for creating temporary project structures:
```python
@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    root = tmp_path / "my-project"
    root.mkdir()
    (root / ".arcwright-ai" / "tmp").mkdir(parents=True)
    (root / "src").mkdir()
    return root
```

**Symlink tests:** Use `Path.symlink_to()` to create symlinks. Platform note: symlinks work on macOS and Linux. On Windows, symlinks may require elevated privileges — but CI runs on Linux, so this is not a concern.

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries:
```python
assert validate_path(valid_path, project_root, "write") is True

with pytest.raises(SandboxViolation, match="outside.*project"):
    validate_path(evil_path, project_root, "write")
```

**Test isolation:** Each test creates its own state via fixtures. No shared mutable state between tests.

---

### References

- [Source: _spec/planning-artifacts/architecture.md#Boundary-3 — Agent Invoker ↔ Sandbox dependency injection contract]
- [Source: _spec/planning-artifacts/architecture.md#Safety-Chain — FR6→20→21→36 mapping]
- [Source: _spec/planning-artifacts/architecture.md#Decision-6 — AgentError hierarchy, exit code 2]
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG — agent/ depends only on core/]
- [Source: _spec/planning-artifacts/architecture.md#Project-Structure — agent/sandbox.py: "Path validator: (path, op) → allow/deny"]
- [Source: _spec/planning-artifacts/architecture.md#NFR-Structure-Mapping — NFR7: agent/sandbox.py application-level enforcement]
- [Source: _spec/planning-artifacts/epics.md#Story-2.4 — Acceptance criteria, story definition]
- [Source: _spec/planning-artifacts/prd.md#FR20 — Agent file operations cannot escape project base directory]
- [Source: _spec/planning-artifacts/prd.md#FR21 — Temp files to .arcwright-ai/tmp/, cleaned up]
- [Source: _spec/planning-artifacts/prd.md#NFR7 — Agent file operations cannot escape the project base directory]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — Known pitfalls, Action Items 1-3]
- [Source: _spec/implementation-artifacts/2-3-context-answerer-static-rule-lookup-engine.md — Previous story patterns, structured logging]
- [Source: arcwright-ai/src/arcwright_ai/agent/sandbox.py — Current empty placeholder]
- [Source: arcwright-ai/src/arcwright_ai/agent/__init__.py — Current empty exports]
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py — AgentError base class for SandboxViolation]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — DIR_ARCWRIGHT, DIR_TMP constants]

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted code review)

### Findings

1. **HIGH — Relative paths resolved against process CWD, not `project_root`** in `validate_path`, which could incorrectly deny valid in-project paths or validate against the wrong boundary depending on invocation context.
2. **HIGH — `validate_temp_path` repeated the same relative-path resolution issue**, causing valid temp-relative paths to be misclassified when the process CWD differed from the story worktree root.
3. **MEDIUM — Boundary check used `os.path.commonpath()` string logic instead of `Path`-native containment**, diverging from project path-handling conventions and making path semantics less explicit.

### Resolution Applied

- Updated `validate_path` to resolve non-absolute paths relative to `project_root` before boundary enforcement.
- Updated `validate_temp_path` to resolve non-absolute paths relative to `project_root` before tmp-directory enforcement.
- Replaced `os.path.commonpath()` boundary logic with `Path.is_relative_to()` using resolved `Path` objects.
- Added regression tests for relative sandbox paths:
  - `test_validate_path_allows_relative_path_within_project`
  - `test_validate_temp_path_allows_relative_tmp_path`

### Verification

- `.venv/bin/python -m pytest tests/test_agent/test_sandbox.py -q` → **19 passed**
- `.venv/bin/python -m ruff check src/arcwright_ai/agent/sandbox.py tests/test_agent/test_sandbox.py` → **All checks passed**
- `.venv/bin/python -m mypy --strict src/arcwright_ai/agent/sandbox.py` → **Success: no issues found**

### Review Outcome

**Approved — changes requested issues fixed.**

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No debug issues encountered. Clean implementation.

### Completion Notes List

- Implemented `SandboxViolation` as a subclass of `AgentError` in `core/exceptions.py` with Google-style docstring.
- Updated `core/__init__.py` to import and re-export `SandboxViolation` (added to both import block and `__all__`).
- Implemented `PathValidator` protocol (`@runtime_checkable`) and `validate_path` function in `agent/sandbox.py` with defense-in-depth `..` component detection, resolved-path boundary checks, symlink escape detection via `.resolve()`, and structured event logging.
- Implemented `validate_temp_path` function that delegates to `validate_path` first then checks `.is_relative_to()` against the `.arcwright-ai/tmp/` directory.
- Updated `agent/__init__.py` to export `PathValidator`, `validate_path`, `validate_temp_path`; removed aspirational comments per Epic 1 retro action.
- Created `tests/test_agent/test_sandbox.py` with 19 unit tests covering all acceptance criteria: valid paths, traversal rejection, symlink escape detection, temp file validation, protocol satisfaction, exception hierarchy, error message quality, and relative-path handling.
- Updated `tests/test_core/test_exceptions.py` `test_all_symbols_exported` to include `SandboxViolation` in its expected set.
- Added post-review hardening for relative-path behavior in sandbox validation and temp-path validation.
- Review verification passed: `pytest tests/test_agent/test_sandbox.py -q` — 19/19 passed; `ruff check` on touched files — clean; `mypy --strict src/arcwright_ai/agent/sandbox.py` — clean.

### File List

- `src/arcwright_ai/core/exceptions.py` — MODIFIED: Added `SandboxViolation` class and `__all__` entry
- `src/arcwright_ai/core/__init__.py` — MODIFIED: Added `SandboxViolation` import and `__all__` entry
- `src/arcwright_ai/agent/sandbox.py` — MODIFIED (was placeholder): `PathValidator` protocol, `validate_path`, `validate_temp_path` implemented
- `src/arcwright_ai/agent/__init__.py` — MODIFIED: Added `PathValidator`, `validate_path`, `validate_temp_path` exports; removed aspirational comments
- `tests/test_agent/test_sandbox.py` — CREATED: 19 unit tests for all sandbox functionality
- `tests/test_core/test_exceptions.py` — MODIFIED: Added `SandboxViolation` to `test_all_symbols_exported` expected set
- `src/arcwright_ai/agent/sandbox.py` — MODIFIED (review): Resolved relative paths against `project_root`; switched boundary check to `Path.is_relative_to()`
- `tests/test_agent/test_sandbox.py` — MODIFIED (review): Added relative-path regression tests

### Change Log

- feat(agent): implement Story 2.4 — Agent Sandbox Path Validation Layer (Date: 2026-03-02)
- fix(agent): code review hardening for sandbox relative-path validation and pathlib boundary checks (Date: 2026-03-02)
