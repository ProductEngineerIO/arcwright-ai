# Story 10.12: Quality Gate — Automated Lint, Format, Type-Check & Test Validation

Status: done

## Story

As a maintainer running Arcwright AI story execution,
I want the validation pipeline to automatically run linting, formatting, type-checking, and tests against agent-generated code after LLM-based AC review,
so that PRs never contain lint violations, formatting drift, type errors, or failing tests — and the agent gets actionable feedback to fix any issues it introduced.

## Acceptance Criteria

1. **Given** the agent has written code to the worktree **When** `validate_node` runs the validation pipeline **Then** the Quality Gate executes after both V6 and V3 pass
2. **Given** the Quality Gate auto-fix phase runs **When** `ruff check --fix` or `ruff format` modifies files in the worktree **Then** a structured summary of all auto-applied fixes (file path, rule ID, description) is captured and included as informational feedback in the `QualityFeedback` payload
3. **Given** the auto-fix phase completes **When** the check phase runs `ruff check`, `mypy --strict`, and `pytest` **Then** all three tools execute against the full project in the worktree and their diagnostic output (stderr/stdout) is captured
4. **Given** all three check-phase tools exit with code 0 **When** the Quality Gate result is evaluated **Then** the pipeline returns `PipelineOutcome.PASS` with the auto-fix summary available as informational feedback
5. **Given** any check-phase tool exits with a non-zero code **When** the Quality Gate result is evaluated **Then** the pipeline returns `PipelineOutcome.FAIL_QUALITY` with a `QualityFeedback` payload containing: (a) the auto-fix summary, (b) per-tool diagnostic output for each failing tool, and (c) a structured instruction block telling the agent to fix the reported issues
6. **Given** `PipelineOutcome.FAIL_QUALITY` is returned **When** `route_validation` evaluates the outcome **Then** it routes to `RETRY` if `retry_count < retry_budget`, or `ESCALATED` if retries are exhausted — identical to `FAIL_V3` routing
7. **Given** a retry occurs after `FAIL_QUALITY` **When** `build_prompt` constructs the retry prompt **Then** a `## Previous Quality Gate Feedback` section is included with the auto-fix summary and all failing tool diagnostics, so the agent can see exactly what to fix
8. **Given** a retry occurs after `FAIL_QUALITY` **When** the next attempt's Quality Gate runs **Then** auto-fix runs again on the new agent output (fresh worktree state per Story 10.5) and the full check suite re-executes
9. **Given** a subprocess (`ruff`, `mypy`, or `pytest`) hangs or exceeds a configurable timeout **When** the Quality Gate evaluates the result **Then** the timed-out tool is treated as a failure with a diagnostic message indicating the timeout, and the pipeline returns `FAIL_QUALITY`
10. **And** `PipelineOutcome` enum is extended with `FAIL_QUALITY = "fail_quality"`
11. **And** `QualityFeedback` model is added alongside `ReflexionFeedback` with fields for auto-fix summary and per-tool diagnostics
12. **And** `PipelineResult` is extended with a `quality_feedback` field
13. **And** provenance entries record Quality Gate results (tools run, pass/fail per tool, auto-fix count)
14. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

## Tasks / Subtasks

- [x] Task 1 — Create `quality_gate.py` module (AC: #1, #2, #3, #9)
  - [x] 1.1 Create `QualityFeedback` model: `auto_fix_summary: list[AutoFixEntry]`, `tool_results: list[ToolResult]`, `passed: bool`
  - [x] 1.2 Create `AutoFixEntry` model: `file_path: str`, `rule_id: str`, `description: str`
  - [x] 1.3 Create `ToolResult` model: `tool_name: str`, `passed: bool`, `exit_code: int`, `stdout: str`, `stderr: str`, `timed_out: bool`
  - [x] 1.4 Implement `_run_subprocess()` — async subprocess wrapper with configurable timeout, captures stdout/stderr, returns `ToolResult`
  - [x] 1.5 Implement `_run_auto_fix()` — runs `ruff check --fix` then `ruff format` in worktree, captures diff of changes as `AutoFixEntry` list
  - [x] 1.6 Implement `_run_checks()` — runs `ruff check`, `mypy --strict`, `pytest` sequentially, returns list of `ToolResult`
  - [x] 1.7 Implement `run_quality_gate(project_root: Path, worktree_path: Path, *, timeout: int) -> QualityGateResult` — orchestrates auto-fix + checks
  - [x] 1.8 Create `QualityGateResult` model: `passed: bool`, `feedback: QualityFeedback`

- [x] Task 2 — Extend `PipelineOutcome` and `PipelineResult` (AC: #10, #11, #12)
  - [x] 2.1 Add `FAIL_QUALITY = "fail_quality"` to `PipelineOutcome` enum
  - [x] 2.2 Add `quality_feedback: QualityFeedback | None = None` field to `PipelineResult`
  - [x] 2.3 Update `__all__` exports in `validation/__init__.py`

- [x] Task 3 — Integrate Quality Gate into pipeline (AC: #1, #4, #5)
  - [x] 3.1 In `run_validation_pipeline()`, after V3 passes, call `run_quality_gate()` with worktree path
  - [x] 3.2 If Quality Gate passes → return `PipelineOutcome.PASS` with `quality_feedback` populated
  - [x] 3.3 If Quality Gate fails → return `PipelineOutcome.FAIL_QUALITY` with `quality_feedback` populated
  - [x] 3.4 Add `worktree_path` parameter to `run_validation_pipeline()` signature (needed for subprocess execution context)

- [x] Task 4 — Update routing and retry feedback (AC: #6, #7, #8)
  - [x] 4.1 In `validate_node` in `engine/nodes.py`, handle `FAIL_QUALITY` identically to `FAIL_V3` for retry routing
  - [x] 4.2 Add `quality_feedback` field to `StoryState` (or use `PipelineResult.quality_feedback` via `validation_result`)
  - [x] 4.3 In `build_prompt()` in `agent/prompt.py`, add `quality_feedback: QualityFeedback | None = None` parameter
  - [x] 4.4 Inject `## Previous Quality Gate Feedback` section: auto-fix summary + per-tool diagnostics for failing tools
  - [x] 4.5 In `agent_dispatch_node`, pass `quality_feedback` from `state.validation_result` to `build_prompt()`

- [x] Task 5 — Provenance recording (AC: #13)
  - [x] 5.1 Record Quality Gate results in provenance entry: tools run, pass/fail per tool, auto-fix count
  - [x] 5.2 Include quality gate timing and diagnostic summary in `feedback_summary` string

- [x] Task 6 — Tests (AC: #14)
  - [x] 6.1 Unit tests for `_run_subprocess()` — success, failure, timeout
  - [x] 6.2 Unit tests for `_run_auto_fix()` — no changes, some fixes applied, captures summary
  - [x] 6.3 Unit tests for `_run_checks()` — all pass, some fail, timeout on one tool
  - [x] 6.4 Unit tests for `run_quality_gate()` — full pass, auto-fix only, check failures
  - [x] 6.5 Unit tests for `QualityFeedback` model serialization
  - [x] 6.6 Pipeline integration test: V6 pass → V3 pass → Quality Gate pass → `PipelineOutcome.PASS`
  - [x] 6.7 Pipeline integration test: V6 pass → V3 pass → Quality Gate fail → `PipelineOutcome.FAIL_QUALITY`
  - [x] 6.8 Routing test: `FAIL_QUALITY` routes to `RETRY` when budget available
  - [x] 6.9 Routing test: `FAIL_QUALITY` routes to `ESCALATED` when budget exhausted
  - [x] 6.10 Prompt injection test: `build_prompt()` includes `## Previous Quality Gate Feedback` with tool diagnostics
  - [x] 6.11 Retry test: fresh Quality Gate run on retry attempt

## Dev Notes

### Problem Context

The validation pipeline currently validates agent output in two stages:
1. **V6 invariant checks** — deterministic: file existence, snake_case naming, Python syntax, YAML validity (zero tokens)
2. **V3 reflexion** — LLM-based: evaluates story acceptance criteria using the review model (costs tokens)

Neither stage runs the project's actual quality toolchain. The agent can produce code that passes all ACs but ships with:
- Ruff lint violations (unused imports, bad patterns)
- Formatting drift (line length, import ordering)
- Mypy type errors (missing annotations, type mismatches)
- Failing tests (regressions, broken imports)

These are only caught if the operator manually runs `hatch run check` after the PR is created.

### Pipeline Ordering

```
V6 (free, fast) → V3 (LLM, evaluates ACs) → Quality Gate (subprocess, lint/format/test)
 fail → halt      fail → retry                fail → retry
```

**Why last?** V3 evaluates the agent's raw output for AC compliance. If ACs aren't met, retry immediately without wasting time on lint/test. The Quality Gate's auto-fix phase (formatting, import sorting) modifies worktree files — running it after V3 ensures AC evaluation isn't performed on altered code. Auto-fix changes are semantically neutral (formatting only), so they don't invalidate V3's verdict.

### Quality Gate Two-Phase Design

**Phase 1: Auto-fix (safe, deterministic)**
```bash
ruff check --fix src/ tests/    # Fix auto-fixable lint issues
ruff format src/ tests/          # Apply consistent formatting
```
- Capture diff of all changes made
- Parse ruff output for rule IDs, file paths, descriptions
- Store as `AutoFixEntry` list for agent awareness on retry

**Phase 2: Check (diagnostic)**
```bash
ruff check src/ tests/           # Report remaining unfixable lint issues
mypy --strict src/               # Type checking
pytest                           # Full test suite
```
- Each tool runs sequentially (avoids resource contention)
- Capture stdout/stderr per tool
- Record exit code and timeout status

### Subprocess Execution Details

All subprocesses run inside the **worktree directory** (not project root). The worktree is set up by `preflight_node` via `create_worktree()` and is available as `state.worktree_path`.

**Critical**: The worktree has a different directory structure than the main repo. The `arcwright-ai/` subfolder contains `pyproject.toml`, `src/`, and `tests/`. Therefore:
- `ruff` and `mypy` config is read from `arcwright-ai/pyproject.toml` via `--config` flag
- `pytest` runs from within the `arcwright-ai/` subdirectory
- The `worktree_path` points to the repo root; commands should `cwd` to `worktree_path / "arcwright-ai"`

**Timeout**: Use `asyncio.wait_for()` wrapping `asyncio.create_subprocess_exec()`. Default timeout should be configurable but reasonable:
- `ruff check --fix` / `ruff format` / `ruff check`: 30s each (fast tools)
- `mypy --strict`: 120s (type-checking can be slow)
- `pytest`: 300s (full test suite may be extensive)

### How `run_validation_pipeline` Changes

Current signature:
```python
async def run_validation_pipeline(
    agent_output: str,
    story_path: Path,
    project_root: Path,
    *,
    model: str,
    cwd: Path,
    sandbox: PathValidator,
    api_key: str,
    attempt_number: int = 1,
) -> PipelineResult:
```

**Add `worktree_path: Path | None = None` parameter.** When provided, the Quality Gate runs after V3. When `None` (backward compatibility), the Quality Gate is skipped.

Updated flow inside the function:
```python
# Step 1: V6 (existing)
# Step 2: Short-circuit if V6 failed (existing)
# Step 3: V3 reflexion (existing)
# Step 4: Short-circuit if V3 failed (existing)
# Step 5 (NEW): Quality Gate
if worktree_path is not None:
    qg_result = await run_quality_gate(project_root, worktree_path)
    if not qg_result.passed:
        return PipelineResult(
            passed=False,
            outcome=PipelineOutcome.FAIL_QUALITY,
            v6_result=v6_result,
            v3_result=v3_result,
            quality_feedback=qg_result.feedback,
            tokens_used=v3_result.tokens_used,
            ...
        )
# Step 6: Return PASS with quality_feedback populated
```

### How `validate_node` Changes

The `validate_node` function in `engine/nodes.py` already handles `FAIL_V3` with retry routing. `FAIL_QUALITY` uses the **exact same pattern**:

```python
# After existing FAIL_V3 block:
if pipeline_result.outcome == PipelineOutcome.FAIL_QUALITY:
    # Same retry budget check as FAIL_V3
    new_retry_count = state.retry_count + 1
    if state.retry_count >= state.config.limits.retry_budget:
        # Exhausted → ESCALATED (same halt report pattern)
        ...
    # Retry available → RETRY (same state update pattern)
    ...
```

The provenance entry for Quality Gate failures should include:
- Which tools passed/failed
- Number of auto-fixes applied
- Summary of failing diagnostics

### How `build_prompt` Changes

Add a new optional `quality_feedback` parameter. When provided and the gate failed, inject:

```markdown
## Previous Quality Gate Feedback

**Auto-fixes applied (informational):**
- `src/arcwright_ai/engine/nodes.py`: I001 (import sorting)
- `src/arcwright_ai/validation/quality_gate.py`: E501 (line too long)

**Failing checks — fix these issues:**

### ruff check (exit code 1)
```
src/arcwright_ai/validation/quality_gate.py:45:5: F841 local variable 'x' is assigned to but never used
```

### mypy --strict (exit code 1)
```
src/arcwright_ai/validation/quality_gate.py:78: error: Missing return statement  [return]
```

### pytest (exit code 1)
```
FAILED tests/test_validation/test_quality_gate.py::test_run_checks - AssertionError
```

**Fix all failing checks above before completing this story.**
```

### Feedback Injection in `agent_dispatch_node`

The quality feedback is available via `state.validation_result.quality_feedback` (since `PipelineResult` now carries it). In `agent_dispatch_node`:

```python
quality_feedback = (
    state.validation_result.quality_feedback
    if state.validation_result is not None
    else None
)
prompt = build_prompt(
    state.context_bundle,
    feedback=feedback,                      # V3 ReflexionFeedback (existing)
    quality_feedback=quality_feedback,       # NEW: QualityFeedback
    working_directory=agent_cwd,
    sandbox_feedback=state.sandbox_feedback,
)
```

**Important**: On `FAIL_QUALITY`, V3 already passed, so `feedback` (ReflexionFeedback) will be `None`. Only `quality_feedback` carries diagnostic data. Both feedback channels can coexist in the prompt for edge cases where both fail in a retry cycle.

### Key Code Locations

| Component | File | Key Functions |
|-----------|------|---------------|
| Validation pipeline | `src/arcwright_ai/validation/pipeline.py` | `run_validation_pipeline()`, `PipelineOutcome`, `PipelineResult` |
| V6 checks | `src/arcwright_ai/validation/v6_invariant.py` | `run_v6_validation()` — reference for check pattern |
| V3 reflexion | `src/arcwright_ai/validation/v3_reflexion.py` | `ReflexionFeedback` — parallel model for `QualityFeedback` |
| Engine nodes | `src/arcwright_ai/engine/nodes.py` | `validate_node()`, `route_validation()`, `agent_dispatch_node()` |
| Prompt builder | `src/arcwright_ai/agent/prompt.py` | `build_prompt()` — add quality feedback injection |
| Engine state | `src/arcwright_ai/engine/state.py` | `StoryState` — `validation_result` field already carries `PipelineResult` |
| Provenance | `src/arcwright_ai/output/provenance.py` | `append_entry()`, `merge_validation_checkpoint()` |
| Git wrapper | `src/arcwright_ai/scm/git.py` | `git()` — reference for async subprocess pattern |
| Config | `src/arcwright_ai/core/config.py` | `LimitsConfig.retry_budget` |
| Types | `src/arcwright_ai/core/types.py` | `ArcwrightModel` base class, `ProvenanceEntry` |
| Pyproject | `arcwright-ai/pyproject.toml` | `[tool.ruff]`, `[tool.mypy]`, `[tool.pytest]`, `[tool.hatch.envs.default.scripts]` |

### Existing Patterns to Follow

**Async subprocess pattern** (from `scm/git.py`):
```python
proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=str(cwd),
)
stdout, stderr = await proc.communicate()
```

**Pydantic model pattern** (from `core/types.py`):
```python
class QualityFeedback(ArcwrightModel):
    """Feedback from the Quality Gate validation stage."""
    passed: bool
    auto_fix_summary: list[AutoFixEntry] = Field(default_factory=list)
    tool_results: list[ToolResult] = Field(default_factory=list)
```

**Pipeline short-circuit pattern** (from `pipeline.py`):
```python
if not v6_result.passed:
    return PipelineResult(passed=False, outcome=PipelineOutcome.FAIL_V6, ...)
```

**Provenance entry recording** (from `engine/nodes.py`):
```python
provenance_entry = ProvenanceEntry(
    decision=f"Quality Gate attempt {attempt_number}: {outcome_str}",
    alternatives=[],
    rationale=f"Tools: ruff(pass), mypy(fail), pytest(pass). Auto-fixes: 3",
    ac_references=[],
    timestamp=datetime.now(tz=UTC).isoformat(),
)
await append_entry(checkpoint_dir / VALIDATION_FILENAME, provenance_entry)
```

**API key access** (Story 10.10 — `SecretStr`):
```python
api_key = state.config.api.claude_api_key.get_secret_value()
```

### Previous Story Intelligence

**Story 10.11** (most recent in Epic 10): Added `extract_agent_decisions()` in `commit_node` before `generate_pr_body()`. Template brace escaping was needed for literal `{...}` in prompt strings. The `output/decisions.py` module follows the same async pattern this story should use for subprocess calls.

**Story 10.10**: Changed `claude_api_key` to `SecretStr`. All API key access uses `.get_secret_value()`.

**Story 10.7**: Fixed provenance preservation. `merge_validation_checkpoint()` now preserves `## Agent Decisions` and `## Implementation Decisions`. Quality Gate entries go in the existing `## Agent Decisions` section via `append_entry()`.

**Story 10.5**: Retry attempts rebuild fresh context. Each retry starts with a fresh worktree state, so the Quality Gate's auto-fix changes from a prior attempt are NOT carried over — the gate runs clean each time.

**Story 10.4**: SCM guardrail system prompt prevents agent from running git commands. Not relevant to Quality Gate (subprocess tools are run by the pipeline, not the agent).

### Critical Design Decisions

1. **No new state field needed**: `QualityFeedback` lives inside `PipelineResult.quality_feedback`. Since `state.validation_result` already holds the full `PipelineResult`, the quality feedback is accessible via `state.validation_result.quality_feedback` — no additional `StoryState` field required.

2. **Sequential tool execution**: Run ruff, mypy, pytest sequentially (not parallel) to avoid resource contention and simplify diagnostic output capture. Total additional time is ~30-60s for a clean run.

3. **Auto-fix before checks**: Run `ruff check --fix` and `ruff format` before the check phase. This means the check phase sees the auto-fixed code, so `ruff check` only reports truly unfixable issues. The auto-fix summary is still captured for agent awareness.

4. **Full test suite**: Run `pytest` without filters. The project's test suite is the source of truth for regression detection. Running a subset risks missing cross-module regressions.

5. **Timeout per tool, not aggregate**: Each tool has its own timeout. A slow `pytest` shouldn't eat into `mypy`'s budget.

### Project Structure Notes

- All source in `arcwright-ai/src/arcwright_ai/` — standard Python package layout
- Tests mirror source structure: `tests/test_validation/`, `tests/test_engine/`
- Constants in `core/constants.py`, types in `core/types.py`
- Async file I/O via `output/fs.py` (`write_text_async`, `read_text_async`)
- Subprocess wrapper pattern in `scm/git.py` (`git()` async helper)
- New module goes in `validation/quality_gate.py` (alongside `v6_invariant.py` and `v3_reflexion.py`)

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 2 (V6/V3 Pipeline), Decision 3 (Provenance)]
- [Source: _spec/planning-artifacts/epics.md — Story 10.12]
- [Source: arcwright-ai/src/arcwright_ai/validation/pipeline.py — Pipeline orchestration, PipelineOutcome, PipelineResult]
- [Source: arcwright-ai/src/arcwright_ai/validation/v6_invariant.py — V6 check registry pattern]
- [Source: arcwright-ai/src/arcwright_ai/validation/v3_reflexion.py — ReflexionFeedback model]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — validate_node, route_validation, retry routing]
- [Source: arcwright-ai/src/arcwright_ai/agent/prompt.py — build_prompt feedback injection]
- [Source: arcwright-ai/src/arcwright_ai/engine/state.py — StoryState fields]
- [Source: arcwright-ai/src/arcwright_ai/scm/git.py — async subprocess pattern]
- [Source: arcwright-ai/pyproject.toml — tool.ruff, tool.mypy, tool.pytest configs]
- [Source: _spec/implementation-artifacts/10-11-llm-extracted-agent-decisions-in-pr-body.md — Previous story patterns]
- [Source: _spec/implementation-artifacts/10-7-validate-node-overwrites-provenance-decision-provenance-missing-from-prs.md — Provenance preservation]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Regex bug: `[A-Z]\d+` pattern in `_RUFF_AUTOFIX_PATTERN` only matched single-letter rule prefixes (e.g., `I001`, `F841`). Multi-letter prefixes like `UP007`, `RUF100` were silently dropped. Fixed by changing to `[A-Z]+\d+`. Caught by unit test `test_parse_auto_fixes_multiple_fixes`.
- End-to-end CLI dispatch test `test_dispatch_story_end_to_end_with_mock_sdk` started failing because the quality gate ran for real against a tmp_path fake project (no `pyproject.toml`). Fixed by adding `run_quality_gate` monkeypatch to that test.

### Completion Notes List

- `QualityFeedback` lives inside `PipelineResult.quality_feedback` — no new `StoryState` field needed.
- `FAIL_QUALITY` routing in `validate_node` uses identical retry/escalation pattern as `FAIL_V3`.
- Quality Gate skipped (backward compat) when `worktree_path=None` in `run_validation_pipeline()`.
- Subprocess cwd is `worktree_path / "arcwright-ai"` (contains `pyproject.toml`, `src/`, `tests/`).
- All 1152 tests pass; 0 regressions.

### File List

**New files:**
- `arcwright-ai/src/arcwright_ai/validation/quality_gate.py`
- `arcwright-ai/tests/test_validation/test_quality_gate.py`

**Modified files:**
- `arcwright-ai/src/arcwright_ai/validation/pipeline.py` — `FAIL_QUALITY` enum value, `quality_feedback` field, `worktree_path` param, quality gate integration
- `arcwright-ai/src/arcwright_ai/validation/__init__.py` — exports for quality gate types
- `arcwright-ai/src/arcwright_ai/engine/nodes.py` — `FAIL_QUALITY` routing block, `quality_feedback` extraction in dispatch, provenance feedback_summary
- `arcwright-ai/src/arcwright_ai/agent/prompt.py` — `quality_feedback` param, `## Previous Quality Gate Feedback` injection
- `arcwright-ai/tests/test_validation/test_pipeline.py` — quality gate integration tests (6.6/6.7/6.no-worktree)
- `arcwright-ai/tests/test_engine/test_nodes.py` — FAIL_QUALITY routing tests (6.8/6.9/6.11)
- `arcwright-ai/tests/test_agent/test_prompt.py` — quality feedback prompt injection tests (6.10)
- `arcwright-ai/tests/test_cli/test_dispatch.py` — added `run_quality_gate` mock to end-to-end test
- `_spec/planning-artifacts/epics.md` — amended Story 10.12 details in planning artifact
- `_spec/implementation-artifacts/10-13-pr-creation-retry-with-backoff-for-github-api-lag.md` — adjacent implementation artifact drafted during Epic 10 progression
- `_spec/implementation-artifacts/10-12-quality-gate-automated-lint-format-type-check-and-test-validation.md` — this file
- `_spec/implementation-artifacts/sprint-status.yaml` — `10-12` status → `review`
