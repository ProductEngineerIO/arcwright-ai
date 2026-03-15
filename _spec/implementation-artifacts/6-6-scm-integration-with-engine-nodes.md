# Story 6.6: SCM Integration with Engine Nodes

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a system maintainer,
I want SCM operations wired into the LangGraph execution nodes at the right lifecycle points,
so that worktree isolation and commit happen automatically without manual intervention.

## Acceptance Criteria (BDD)

1. **Given** the LangGraph preflight node **When** a story begins execution **Then** `preflight_node` calls `scm/worktree.py:create_worktree(story_slug, project_root=state.project_root)` before context assembly **And** sets the worktree path in state so that all subsequent nodes use it as the working directory for agent dispatch.

2. **Given** the LangGraph agent_dispatch node **When** the agent is invoked **Then** the `cwd` parameter passed to `invoke_agent()` is the worktree path (not `state.project_root`) **And** the sandbox validator receives the worktree path as its base directory.

3. **Given** the LangGraph commit node (SUCCESS path) **When** validation passes **Then** `commit_node` calls `scm/branch.py:commit_story()` inside the worktree path **And** then calls `scm/worktree.py:remove_worktree()` to dispose of the worktree **And** the run.yaml and story status are updated as before.

4. **Given** the ESCALATED path (halt) **When** the story fails validation after max retries or fails V6 invariants **Then** the worktree is **preserved** for manual inspection (NOT removed) **And** the preserved worktree path is logged to provenance and appears in the halt report.

5. **Given** the RETRY path **When** V3 reflexion validation fails within retry budget **Then** the worktree is **reused** — the agent re-executes in the same worktree with reflexion feedback **And** no worktree teardown/recreate occurs between retry attempts.

6. **Given** all git commands during engine execution **When** any SCM operation is invoked **Then** `create_worktree` and `remove_worktree` run with `cwd=project_root` (project root) **And** `commit_story` and `invoke_agent` run with `cwd=worktree_path` per D7 convention.

7. **Given** `ScmError` is raised during preflight worktree creation **When** the error is caught in `preflight_node` **Then** the story is transitioned to ESCALATED **And** the error is logged with full structured context **And** a halt report is generated so the user can diagnose and resume.

8. **Given** `StoryState` model **When** this story is implemented **Then** a new `worktree_path: Path | None = None` field is added **And** it is populated by `preflight_node` after `create_worktree` succeeds **And** consumed by `agent_dispatch_node` and `commit_node`.

9. **Given** story implementation is complete **When** `ruff check .` is run against the FULL repository **Then** zero violations.

10. **Given** story implementation is complete **When** `.venv/bin/python -m mypy --strict src/` is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

12. **Given** any existing tests in the full test suite **When** this story is complete **Then** no existing tests break. All 676 existing tests continue to pass.

13. **Given** `ScmError` during `commit_node` (e.g., `BranchError` from `commit_story` with no changes) **When** the error is caught **Then** the error is logged as a warning (best-effort, non-fatal to the SUCCESS path) **And** the worktree is still removed (best-effort) after the commit attempt.

14. **Given** an integration test with real git **When** the test suite runs **Then** a test verifies the full lifecycle: preflight (worktree created) → agent_dispatch (ran in worktree) → validate (pass) → commit (committed in worktree, worktree removed) → finalize **And** the worktree directory is gone after commit **And** the branch has the expected commit.

## Tasks / Subtasks

- [x] Task 1: Add `worktree_path` field to `StoryState` (AC: #8)
  - [x] 1.1: In `engine/state.py`, add `worktree_path: Path | None = None` to `StoryState`.
  - [x] 1.2: Ensure the field is optional and defaults to `None` (preserves all existing state construction).
  - [x] 1.3: Update `StoryState` docstring to document the new field.

- [x] Task 2: Modify `preflight_node` to create worktree (AC: #1, #6, #7, #8)
  - [x] 2.1: Add imports for `create_worktree` from `arcwright_ai.scm.worktree` and `ScmError` from `arcwright_ai.core.exceptions`.
  - [x] 2.2: After the `QUEUED → PREFLIGHT` transition and **before** context assembly, call `create_worktree(story_slug=str(state.story_id), project_root=state.project_root)`. Extract the story slug from `state.story_id` — it is already in slug format (e.g., `"2-1-state-models"`).
  - [x] 2.3: Store the returned worktree `Path` in the state update: `worktree_path=created_path`.
  - [x] 2.4: Wrap the `create_worktree` call in a `try/except ScmError` block. On `ScmError`: transition to ESCALATED immediately, log the error with structured context (`scm.preflight.error` event), and write a halt report artifact so diagnosis/resume context is preserved.
  - [x] 2.5: Log `scm.worktree.create` event with worktree_path, story_slug on success.
  - [x] 2.6: Ensure context assembly still receives `state.project_root` (not worktree_path) for `build_context_bundle` — BMAD artifacts are in the main repo, not the worktree.

- [x] Task 3: Modify `agent_dispatch_node` to use worktree_path as cwd (AC: #2, #5, #6)
  - [x] 3.1: Replace `cwd=state.project_root` in the `invoke_agent()` call with `cwd=state.worktree_path if state.worktree_path is not None else state.project_root`. The fallback preserves backward compatibility for tests that don't set worktree_path.
  - [x] 3.2: Update the `sandbox=validate_path` call so that path validation uses the worktree_path as the sandbox boundary (the base directory for allowed file operations). If `validate_path` currently takes `project_root`, pass `state.worktree_path or state.project_root` instead.
  - [x] 3.3: Log the resolved `cwd` in the `agent.dispatch` structured event for observability.

- [x] Task 4: Modify `commit_node` to commit and remove worktree (AC: #3, #6, #13)
  - [x] 4.1: Add imports for `commit_story` from `arcwright_ai.scm.branch` and `remove_worktree` from `arcwright_ai.scm.worktree`.
  - [x] 4.2: Before existing run_manager calls, check `state.worktree_path is not None`. If set:
    - Call `await commit_story(story_slug=str(state.story_id), story_title=<derive from story_id>, story_path=str(state.story_path), run_id=str(state.run_id), worktree_path=state.worktree_path)`. Wrap in `try/except ScmError` — log warning on failure (best-effort, non-fatal).
    - Call `await remove_worktree(str(state.story_id), project_root=state.project_root)`. Wrap in `try/except ScmError` — log warning on failure (best-effort, non-fatal).
  - [x] 4.3: If `state.worktree_path is None`, skip SCM operations (backward-compatible no-op for non-SCM runs or test scenarios).
  - [x] 4.4: Log `scm.commit` and `scm.worktree.remove` structured events with relevant context (commit_hash, worktree_path, story_slug).
  - [x] 4.5: Derive `story_title` from `state.story_id` by replacing dashes with spaces and title-casing (e.g., `"6-6-scm-integration"` → `"Scm Integration"`). Use a simple helper or inline transformation. The exact title format is not critical — it appears in the commit message.

- [x] Task 5: Modify `finalize_node` to preserve worktree on ESCALATED (AC: #4)
  - [x] 5.1: In `finalize_node`, when `state.status == TaskState.ESCALATED` and `state.worktree_path is not None`, add `worktree_path` to the halt report context (best-effort).
  - [x] 5.2: Log `scm.worktree.preserved` event with the worktree_path so the user knows where to inspect.
  - [x] 5.3: Do NOT call `remove_worktree` in the ESCALATED path — the worktree must remain on disk.

- [x] Task 6: Update existing unit tests and add new tests in `tests/test_engine/test_nodes.py` (AC: #1-8, #12)
  - [x] 6.1: Update `make_story_state` fixture to optionally accept `worktree_path` (default `None` for backward compat).
  - [x] 6.2: Add test `test_preflight_node_creates_worktree` — mock `create_worktree` to return a `Path`, verify `state.worktree_path` is set after preflight.
  - [x] 6.3: Add test `test_preflight_node_scm_error_escalates` — mock `create_worktree` to raise `ScmError`, verify the node transitions to `ESCALATED` and writes a halt report.
  - [x] 6.4: Add test `test_agent_dispatch_uses_worktree_cwd` — set `worktree_path` on state, mock `invoke_agent`, verify `cwd` arg is worktree_path.
  - [x] 6.5: Add test `test_agent_dispatch_falls_back_to_project_root` — worktree_path=None, verify `cwd=project_root`.
  - [x] 6.6: Add test `test_commit_node_commits_and_removes_worktree` — mock `commit_story` and `remove_worktree`, verify both called with correct args.
  - [x] 6.7: Add test `test_commit_node_skips_scm_when_no_worktree` — worktree_path=None, verify SCM functions not called.
  - [x] 6.8: Add test `test_commit_node_handles_branch_error_gracefully` — mock `commit_story` to raise `BranchError`, verify warning logged, `remove_worktree` still called.
  - [x] 6.9: Add test `test_commit_node_handles_worktree_error_gracefully` — mock `remove_worktree` to raise `WorktreeError`, verify warning logged, no crash.
  - [x] 6.10: Add test `test_finalize_preserves_worktree_on_escalated` — ESCALATED state with worktree_path, verify `remove_worktree` NOT called, `scm.worktree.preserved` logged.
  - [x] 6.11: All existing 676 tests must pass unchanged after these modifications.

- [x] Task 7: Create integration test in `tests/test_engine/test_scm_integration.py` (AC: #14, #12)
  - [x] 7.1: Use `git_repo` fixture pattern (real git init, initial commit, `.arcwright-ai/worktrees/` dir).
  - [x] 7.2: Test `test_full_story_lifecycle_with_scm` — create worktree → mock agent (write a file in worktree) → mock validation (PASS) → commit → finalize → verify: worktree directory gone, branch has commit, commit message matches template.
  - [x] 7.3: Test `test_escalated_preserves_worktree` — create worktree → mock agent → mock validation (FAIL_V6) → finalize → verify: worktree directory still exists, branch still has the worktree.
  - [x] 7.4: Mark all with `@pytest.mark.slow` and `@pytest.mark.asyncio`.

- [x] Task 8: Run quality gates (AC: #9, #10, #11, #12)
  - [x] 8.1: `ruff check .` — zero violations against FULL repository.
  - [x] 8.2: `ruff format --check .` — zero formatting issues.
  - [x] 8.3: `.venv/bin/python -m mypy --strict src/` — zero errors.
  - [x] 8.4: `pytest` — all tests pass (676 existing + new SCM integration tests).
  - [x] 8.5: Verify Google-style docstrings on all public functions.
  - [x] 8.6: Verify `git diff --name-only` and untracked files; reconcile Dev Agent Record file list.

### Review Follow-ups (AI)

- [x] [AI-Review][HIGH] Pass preserved `worktree_path` into `write_halt_report(...)` so the halt report includes the real preserved path on ESCALATED runs (AC #4). [arcwright-ai/src/arcwright_ai/engine/nodes.py:1012], [arcwright-ai/src/arcwright_ai/output/summary.py:301]
- [x] [AI-Review][HIGH] In preflight SCM failure handling, ensure the run is transitioned to ESCALATED and halt reporting is produced, not only `ContextError` re-raise (AC #7). [arcwright-ai/src/arcwright_ai/engine/nodes.py:105], [arcwright-ai/src/arcwright_ai/engine/nodes.py:120]
- [x] [AI-Review][HIGH] Broaden commit error handling in `commit_node` to catch `ScmError` (not only `BranchError`) for best-effort non-fatal behavior during commit attempts (AC #13). [arcwright-ai/src/arcwright_ai/engine/nodes.py:876]
- [x] [AI-Review][MEDIUM] Strengthen `test_full_story_lifecycle_with_scm` to execute `validate_node` PASS before `commit_node` and assert the full lifecycle contract required by AC #14. [arcwright-ai/tests/test_engine/test_scm_integration.py:113], [arcwright-ai/tests/test_engine/test_scm_integration.py:174], [arcwright-ai/tests/test_engine/test_scm_integration.py:178]
- [x] [AI-Review][MEDIUM] Reconcile Dev Agent Record `File List` with git reality by including undocumented modified/untracked artifacts (`_spec/implementation-artifacts/sprint-status.yaml`, current story file) or removing out-of-scope edits. [arcwright-ai git status], [Dev Agent Record → File List]

## Dev Notes

### Architecture & Design Context

**Package Dependency DAG**: `cli → engine → {validation, agent, context, output, scm} → core`. Story 6.6 modifies `engine/nodes.py` and `engine/state.py` to import from `scm/`. This is valid: `engine → scm → core`. The engine already imports from `agent/`, `context/`, `output/`, `validation/`, and `core/`. Adding `scm` imports is architecturally expected — the engine mediates between all domain packages. [Source: [architecture.md — Package Dependency DAG](../../_spec/planning-artifacts/architecture.md)]

**Decision 7 — Git Operations Strategy**: Worktree lifecycle is:
1. `create_worktree` runs at preflight (before agent, `cwd=project_root`)
2. Agent executes in worktree directory (`cwd=worktree_path`)
3. Validation passes → `commit_story(cwd=worktree_path)` → `remove_worktree(cwd=project_root)`
4. Validation fails → worktree preserved for inspection
5. Halt/budget-exceeded → worktrees preserved, run marked incomplete
All git commands use `cwd=worktree_path` except worktree add/remove which use project root. [Source: [architecture.md — Decision 7](../../_spec/planning-artifacts/architecture.md)]

**Decision 6 — Error Handling**: `ScmError` is the parent exception for all SCM failures. `WorktreeError(ScmError)` for worktree ops, `BranchError(ScmError)` for branch/commit ops. In engine nodes, SCM errors during preflight are fatal (→ ESCALATED), while SCM errors during commit are best-effort (logged as warnings). [Source: [architecture.md — Decision 6](../../_spec/planning-artifacts/architecture.md)]

**Decision 8 — Logging**: Structured events with `logger = logging.getLogger(__name__)` and `extra={"data": {...}}`. New events for this story: `scm.preflight.error`, `scm.worktree.create` (already exists in scm module but now also at engine level), `scm.commit`, `scm.worktree.remove` (engine-level lifecycle events), `scm.worktree.preserved`. [Source: [architecture.md — Decision 8](../../_spec/planning-artifacts/architecture.md)]

**Constraint 4 — Worktree Isolation as Security Model**: Worktrees are the primary isolation boundary. The agent sandbox (`agent/sandbox.py:validate_path`) enforces that file operations stay within the working directory. After this story, the sandbox boundary changes from `project_root` to `worktree_path` during agent execution. [Source: [architecture.md — Constraint 4](../../_spec/planning-artifacts/architecture.md)]

### Key Implementation Decisions

1. **`worktree_path` as state field**: Adding `worktree_path: Path | None = None` to `StoryState` is the cleanest way to thread the worktree through the graph. It's set once in preflight and consumed by agent_dispatch, validate (unchanged), commit, and finalize. `None` means "no SCM integration" — backward-compatible for tests.

2. **Worktree creation BEFORE context assembly**: The worktree must exist before the agent runs, but context assembly reads BMAD artifacts from the main repo (not the worktree). So the order is: create_worktree → build_context_bundle(project_root) → agent runs in worktree.

3. **Sandbox boundary changes to worktree_path**: The `validate_path` sandbox function restricts file operations to a base directory. Currently the base is `project_root`. After worktree integration, the base becomes `worktree_path` — the agent should only modify files within the worktree, not the main repo.

4. **commit_node is best-effort for SCM**: The current `commit_node` already does best-effort writes to run.yaml. SCM operations (commit + remove worktree) follow the same pattern: try, catch, log warning, continue. A failed commit shouldn't prevent run.yaml updates. A failed worktree removal is non-fatal — the user can run `arcwright-ai clean` later.

5. **Retry reuses worktree**: On RETRY, the worktree is NOT torn down. The agent re-enters the same worktree with reflexion feedback. This means the worktree may have partial work from the previous attempt — the agent's prompt should communicate this via the feedback mechanism (already handled by `build_prompt` with feedback).

6. **story_title derivation**: `commit_story` requires a `story_title` string. Derive from `state.story_id` by stripping the numeric prefix and converting dashes to spaces. Example: `StoryId("6-6-scm-integration-with-engine-nodes")` → strip `"6-6-"` → `"scm integration with engine nodes"` → title-case → `"Scm Integration With Engine Nodes"`.

### Existing Code to Reuse — DO NOT REINVENT

- **`create_worktree(story_slug, base_ref=None, *, project_root)`** from `scm/worktree.py` — creates worktree at `.arcwright-ai/worktrees/<slug>`, returns `Path`. Already handles atomic cleanup on failure. [Source: scm/worktree.py]
- **`remove_worktree(story_slug, *, project_root, delete_branch=False)`** from `scm/worktree.py` — idempotent removal. [Source: scm/worktree.py]
- **`commit_story(story_slug, story_title, story_path, run_id, *, worktree_path)`** from `scm/branch.py` — stages all changes, commits with template message, returns commit hash. [Source: scm/branch.py]
- **`validate_path(path, base_dir)`** from `agent/sandbox.py` — validates path is within base directory. [Source: agent/sandbox.py]
- **`invoke_agent(prompt, model, cwd, sandbox)`** from `agent/invoker.py` — the `cwd` parameter controls where the agent executes. [Source: agent/invoker.py]
- **`ScmError`, `WorktreeError`, `BranchError`** from `core/exceptions.py`. [Source: core/exceptions.py]
- **`ContextError`** from `core/exceptions.py` — used when preflight fails. [Source: core/exceptions.py]
- **`TaskState`** from `core/lifecycle.py` — `QUEUED`, `PREFLIGHT`, `RUNNING`, `VALIDATING`, `SUCCESS`, `RETRY`, `ESCALATED`. [Source: core/lifecycle.py]
- **`DIR_ARCWRIGHT`, `DIR_WORKTREES`** from `core/constants.py`. [Source: core/constants.py]
- **`build_context_bundle`, `serialize_bundle_to_markdown`** from `context/injector.py` — must still receive `project_root` (not worktree). [Source: context/injector.py]
- **`build_prompt`** from `agent/prompt.py` — handles feedback injection for retries. [Source: agent/prompt.py]
- **`append_entry`** from `output/provenance.py` — for logging provenance entries. [Source: output/provenance.py]
- **`update_story_status`, `update_run_status`** from `output/run_manager.py` — already called by commit_node. [Source: output/run_manager.py]
- **`write_halt_report`, `write_success_summary`** from `output/summary.py` — already called by finalize_node. [Source: output/summary.py]

### CRITICAL: Agent sandbox.validate_path Integration

The `validate_path` function from `agent/sandbox.py` is passed as a callable to `invoke_agent`. Currently it's called with `state.project_root` context. After this story, it must use `state.worktree_path` as the base directory so the agent cannot write outside the worktree. Check the exact signature of `validate_path` before modifying the call.

```python
# BEFORE (current):
result = await invoke_agent(prompt, model=..., cwd=state.project_root, sandbox=validate_path)

# AFTER (this story):
agent_cwd = state.worktree_path if state.worktree_path is not None else state.project_root
result = await invoke_agent(prompt, model=..., cwd=agent_cwd, sandbox=validate_path)
```

### CRITICAL: Story Title Derivation for Commit Message

```python
def _derive_story_title(story_id: str) -> str:
    """Derive a human-readable title from a story ID slug.

    Args:
        story_id: Story identifier slug (e.g., "6-6-scm-integration").

    Returns:
        Title-cased story name (e.g., "Scm Integration").
    """
    # Strip leading epic-story number prefix: "6-6-scm-integration" → "scm-integration"
    parts = story_id.split("-", 2)
    name_part = parts[2] if len(parts) > 2 else story_id
    return name_part.replace("-", " ").title()
```

### CRITICAL: Worktree Creation Error Handling in Preflight

```python
# In preflight_node, BEFORE context assembly:
try:
    worktree_path = await create_worktree(str(state.story_id), project_root=state.project_root)
except ScmError as exc:
    logger.error(
        "scm.preflight.error",
        extra={"data": {"story": str(state.story_id), "error": exc.message, "details": exc.details}},
    )
    raise ContextError(
        f"Failed to create worktree for story {state.story_id}: {exc.message}",
        details={"story_id": str(state.story_id), **(exc.details or {})},
    ) from exc
```

Note: Raising `ContextError` (not `ScmError`) from preflight keeps the existing error handling contract — the dispatch CLI already handles `ContextError` from preflight. The `from exc` chain preserves the original cause.

### CRITICAL: commit_node Best-Effort Pattern

```python
# In commit_node, AFTER existing run_manager updates:
if state.worktree_path is not None:
    story_title = _derive_story_title(str(state.story_id))
    try:
        commit_hash = await commit_story(
            story_slug=str(state.story_id),
            story_title=story_title,
            story_path=str(state.story_path),
            run_id=str(state.run_id),
            worktree_path=state.worktree_path,
        )
        logger.info("scm.commit", extra={"data": {"story": str(state.story_id), "commit_hash": commit_hash}})
    except BranchError as exc:
        logger.warning("scm.commit.error", extra={"data": {"story": str(state.story_id), "error": exc.message}})

    try:
        await remove_worktree(str(state.story_id), project_root=state.project_root)
        logger.info("scm.worktree.remove", extra={"data": {"story": str(state.story_id)}})
    except WorktreeError as exc:
        logger.warning("scm.worktree.remove.error", extra={"data": {"story": str(state.story_id), "error": exc.message}})
```

### Mocking Strategy for Unit Tests

Mock SCM functions at their callsite in `engine/nodes.py`:

```python
monkeypatch.setattr("arcwright_ai.engine.nodes.create_worktree", mock_create_worktree)
monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", mock_remove_worktree)
monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", mock_commit_story)
```

For the autouse `_mock_output_functions` fixture in test_nodes.py, add SCM mocks as needed (default no-ops) to prevent real git calls in unit tests.

### Integration Test Pattern

Reuse the `git_repo` fixture pattern from `test_worktree_integration.py` and `test_clean_integration.py`:

```python
@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    await git("init", cwd=tmp_path)
    await git("config", "user.email", "test@test.com", cwd=tmp_path)
    await git("config", "user.name", "Test", cwd=tmp_path)
    (tmp_path / "README.md").write_text("# Test")
    await git("add", ".", cwd=tmp_path)
    await git("commit", "-m", "Initial commit", cwd=tmp_path)
    (tmp_path / DIR_ARCWRIGHT / DIR_WORKTREES).mkdir(parents=True)
    return tmp_path
```

The integration test should:
1. Create a real worktree via `create_worktree`
2. Write a test file inside the worktree (simulating agent output)
3. Call `commit_story` inside the worktree
4. Call `remove_worktree` to clean up
5. Verify: worktree dir gone, branch has the commit, commit message matches

### Relationship to Other Stories in Epic 6

- **Story 6.1 (done):** `git()` wrapper — foundation for all git operations.
- **Story 6.2 (done):** `create_worktree`, `remove_worktree`, `list_worktrees` — core worktree lifecycle.
- **Story 6.3 (done):** `commit_story`, `create_branch`, `delete_branch`, `list_branches` — branch management.
- **Story 6.4 (done):** `generate_pr_body` — PR body generation. Not directly consumed by this story, but may be called after commit in a future enhancement.
- **Story 6.5 (done):** `arcwright-ai clean` command — manual worktree cleanup. Independent of engine integration.
- **Story 6.6 (this):** Wires 6.1, 6.2, 6.3 into the engine pipeline. This is the integration story that makes SCM operations automatic during story execution.

### Previous Story Intelligence (6-5)

From Story 6-5 (Worktree Cleanup Command):
- All async functions follow `async def` pattern with `@pytest.mark.asyncio` test decorators.
- Logging uses `logger = logging.getLogger(__name__)` with `extra={"data": {...}}` structured events.
- `monkeypatch.setattr()` used for mocking — mock at the callsite, not the source module.
- `ScmError`, `WorktreeError`, `BranchError` carry `details` dicts for structured error context.
- Integration tests use real git repos via `git_repo(tmp_path)` fixture.
- Quality gates: `ruff check .`, `ruff format --check .`, `mypy --strict src/`, `pytest` all pass at 676 tests.
- B904 ruff error pattern: when re-raising exceptions, use `raise XError(...) from exc`.
- Google-style docstrings required on all public functions with Args, Returns, Raises sections.
- Key learning from 6-5: `git branch --merged` uses `+` prefix for branches checked out in linked worktrees. The `_list_merged_branches` helper strips `*`, `+`, and spaces.

### Git Commit Context

Recent commits on `develop` branch (latest first):
- `0d1b51e` feat(story-6.5): worktree cleanup command — cli clean with merged/all modes
- `4457613` feat(epic-6): stories 6-3 and 6-4 — branch manager, PR body generator
- `3488d40` feat(story-6.2): worktree manager — atomic create/delete with recovery
- `073acf9` feat(story-6.1): git subprocess wrapper — safe shell-out foundation

All SCM primitives (6.1–6.5) are implemented and tested. This story integrates them into the engine.

### Project Structure Notes

- **Modified file**: `src/arcwright_ai/engine/state.py` — add `worktree_path` field to `StoryState`
- **Modified file**: `src/arcwright_ai/engine/nodes.py` — modify `preflight_node`, `agent_dispatch_node`, `commit_node`, `finalize_node`; add `_derive_story_title` helper
- **Modified file**: `tests/test_engine/test_nodes.py` — update existing tests, add new SCM integration tests
- **New file**: `tests/test_engine/test_scm_integration.py` — integration tests with real git
- No changes to `scm/` package — all needed functions are already exported
- No changes to `core/` package — all constants, exceptions, and types already exist
- No changes to `cli/` — dispatch.py constructs StoryState without worktree_path (defaults to None, preflight sets it)
- No changes to `engine/graph.py` — the graph shape is unchanged (same nodes, same edges)

### References

- [Source: architecture.md — Decision 7 (Git Operations Strategy)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Decision 6 (Error Handling Taxonomy)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Decision 8 (Logging & Observability)](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Package Dependency DAG](../../_spec/planning-artifacts/architecture.md)
- [Source: architecture.md — Constraint 4 (Worktree Isolation as Security Model)](../../_spec/planning-artifacts/architecture.md)
- [Source: epics.md — Epic 6 Story 6.6](../../_spec/planning-artifacts/epics.md)
- [Source: epics.md — FR6, FR34, FR36, D7](../../_spec/planning-artifacts/epics.md)
- [Source: story 6-5](6-5-worktree-cleanup-command.md) — previous story patterns and conventions
- [Source: scm/worktree.py](../../arcwright-ai/src/arcwright_ai/scm/worktree.py) — create_worktree, remove_worktree
- [Source: scm/branch.py](../../arcwright-ai/src/arcwright_ai/scm/branch.py) — commit_story, create_branch
- [Source: scm/git.py](../../arcwright-ai/src/arcwright_ai/scm/git.py) — git subprocess wrapper
- [Source: engine/nodes.py](../../arcwright-ai/src/arcwright_ai/engine/nodes.py) — current preflight_node, agent_dispatch_node, commit_node, finalize_node
- [Source: engine/state.py](../../arcwright-ai/src/arcwright_ai/engine/state.py) — StoryState, ProjectState
- [Source: engine/graph.py](../../arcwright-ai/src/arcwright_ai/engine/graph.py) — build_story_graph (graph shape unchanged)
- [Source: core/constants.py](../../arcwright-ai/src/arcwright_ai/core/constants.py) — DIR_ARCWRIGHT, DIR_WORKTREES, BRANCH_PREFIX
- [Source: core/exceptions.py](../../arcwright-ai/src/arcwright_ai/core/exceptions.py) — ScmError, WorktreeError, BranchError, ContextError
- [Source: agent/sandbox.py](../../arcwright-ai/src/arcwright_ai/agent/sandbox.py) — validate_path
- [Source: agent/invoker.py](../../arcwright-ai/src/arcwright_ai/agent/invoker.py) — invoke_agent cwd parameter

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

### Completion Notes List

- Added `worktree_path: Path | None = None` to `StoryState` in `engine/state.py` with full docstring update.
- Modified `preflight_node` to call `create_worktree` before context assembly. `ScmError` is caught, logged, transitioned to `ESCALATED`, and writes a halt report checkpoint. On success, `worktree_path` is set in state. Context assembly still uses `project_root` for BMAD artifact resolution.
- Modified `agent_dispatch_node` to use `state.worktree_path` as `cwd` when set, falling back to `project_root` for backward-compatible test scenarios.
- Added `_derive_story_title` helper that strips numeric N-N- prefix from slug and title-cases the remainder.
- Modified `commit_node` to call `commit_story` then `remove_worktree` when `worktree_path` is set. Both are best-effort (`ScmError` logged as warnings). SCM is a no-op when `worktree_path is None`.
- Modified `finalize_node` to log `scm.worktree.preserved` on ESCALATED path when `worktree_path` is set. No `remove_worktree` call on this path.
- Updated autouse fixtures in `test_nodes.py` and `test_graph.py` to mock SCM functions; added SCM mocks to `test_dispatch.py` end-to-end test.
- Added 15 new unit tests covering all SCM node behaviours. Created `test_scm_integration.py` with 2 real-git `@pytest.mark.slow` integration tests.
- All 691 tests pass (676 existing + 15 new). `ruff check .`, `ruff format --check .`, `mypy --strict src/` all clean.
- Applied AI review follow-up fixes: propagated preserved worktree path into halt reports (`finalize_node` + halt controller), broadened commit/removal catches to `ScmError`, and updated preflight SCM failure behavior to explicit ESCALATED + halt-report checkpoint.
- Strengthened SCM lifecycle integration test to execute `validate_node` PASS before `commit_node`.

### File List

- `arcwright-ai/src/arcwright_ai/engine/state.py`
- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/src/arcwright_ai/cli/halt.py`
- `arcwright-ai/tests/test_engine/test_nodes.py`
- `arcwright-ai/tests/test_engine/test_graph.py`
- `arcwright-ai/tests/test_cli/test_dispatch.py`
- `arcwright-ai/tests/test_cli/test_halt.py`
- `arcwright-ai/tests/test_engine/test_scm_integration.py`
- `_spec/implementation-artifacts/6-6-scm-integration-with-engine-nodes.md`
- `_spec/implementation-artifacts/sprint-status.yaml`

## Senior Developer Review (AI)

### Reviewer

- Reviewer: Ed (AI Code Review)
- Date: 2026-03-08
- Outcome: Approved (follow-ups resolved)

### Summary

All previously identified HIGH/MEDIUM findings are now addressed. Error-path handling, halt-report worktree provenance, and full lifecycle integration coverage have been aligned with AC #4, #7, #13, and #14.

### Findings

1. **[RESOLVED][HIGH] Halt report omits preserved worktree path on ESCALATED runs (AC #4).**
  - `finalize_node` logs `scm.worktree.preserved` but does not pass `worktree_path` into `write_halt_report(...)`.
  - `write_halt_report(...)` already supports `worktree_path`, so this is an unfulfilled integration step.
  - Evidence: `arcwright-ai/src/arcwright_ai/engine/nodes.py:1012`, `arcwright-ai/src/arcwright_ai/output/summary.py:301`.

2. **[RESOLVED][HIGH] Preflight SCM failure path did not complete ESCALATED/halt-report behavior (AC #7).**
  - On `ScmError`, preflight logs and re-raises `ContextError`, but no explicit story escalation/halt-report generation occurs in-node.
  - AC #7 requires ESCALATED transition + diagnosable halt artifact path.
  - Evidence: `arcwright-ai/src/arcwright_ai/engine/nodes.py:105`, `arcwright-ai/src/arcwright_ai/engine/nodes.py:120`.

3. **[RESOLVED][HIGH] Commit error handling was narrower than AC #13 requirement.**
  - `commit_node` catches `BranchError` only; AC language is for `ScmError` during commit path as warning/non-fatal handling.
  - This leaves a class of SCM failures that can still hard-fail commit path.
  - Evidence: `arcwright-ai/src/arcwright_ai/engine/nodes.py:876`.

4. **[RESOLVED][MEDIUM] Full lifecycle integration test did not execute validate PASS step required by AC #14.**
  - Test goes preflight → agent_dispatch → commit directly, skipping `validate_node` pass routing.
  - This does not verify the required lifecycle contract end-to-end.
  - Evidence: `arcwright-ai/tests/test_engine/test_scm_integration.py:113`, `:174`, `:178`.

5. **[RESOLVED][MEDIUM] Story file list/documentation mismatch with git working state.**
  - Current git status includes changed/untracked implementation artifacts not represented in Dev Agent Record `File List`.
  - Transparency/documentation gap for reviewers.

### Checklist Result

- Story loaded and reviewed: ✅
- Story status reviewable: ✅ (restored to `review` after follow-up fixes)
- AC cross-check vs implementation: ✅
- File List vs git audit: ✅
- Tests mapped to ACs: ✅ (full lifecycle now includes validate PASS before commit)
- Security/quality review: ✅
- Review notes appended: ✅
- Change log updated: ✅

### Change Log

- 2026-03-08: Story 6.6 implemented — SCM integration wired into LangGraph engine nodes. Added `worktree_path` to `StoryState`, modified preflight/agent_dispatch/commit/finalize nodes, added `_derive_story_title` helper, 15 unit tests, 2 integration tests.
- 2026-03-08: Senior Developer Review (AI) completed — identified 3 HIGH and 2 MEDIUM findings; added Review Follow-ups (AI); status set to in-progress pending fixes.
- 2026-03-08: Follow-up fixes applied for all AI review findings; review follow-ups marked complete; status returned to review.
- 2026-03-08: Final validation complete (`pytest -q` full suite passing); story status set to done.
