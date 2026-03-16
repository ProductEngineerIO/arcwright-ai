# Story 10.4: Agent SCM Guardrails & Commit-Node Resilience

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a user running Arcwright AI story execution,
I want the pipeline to always push a branch and create a PR when the agent produces code changes,
So that successful validation runs are not silently left unpushed due to the agent committing changes itself during dispatch.

## Bug Report

**Observed behaviour (run `20260316-220432-ad5442`):**
The agent (Claude) ran with `permission_mode="bypassPermissions"` in its dispatch phase and executed `git commit` itself inside the worktree. When the pipeline's `commit_node` subsequently ran `git add . && git status --porcelain`, the working tree was already clean. `commit_story()` raised `BranchError("no_changes")`, `commit_hash` stayed `None`, and the entire push → PR → auto-merge chain was silently skipped. The story still reported "success" despite no PR being created.

**Root cause — two-part defect:**

1. **No SCM guardrails in agent prompt or system prompt.** `build_prompt()` (`agent/prompt.py`) assembles story/requirements/architecture/conventions — but contains zero instructions telling the agent not to run `git commit`, `git push`, or other SCM commands. The `ClaudeCodeOptions` in `invoker.py` sets `permission_mode="bypassPermissions"` and no `system_prompt`, giving the agent unrestricted shell access. The sandbox (`can_use_tool`) only enforces file-path boundaries, not command restrictions.

2. **`commit_story()` has no fallback for agent-created commits.** (`scm/branch.py` line 182) It only checks `git status --porcelain` for uncommitted changes. If the agent already committed, the worktree is clean and the function raises `BranchError` instead of detecting the agent's commit via `git log`. Since `commit_hash` stays `None`, the downstream `if commit_hash is not None:` gate in `commit_node()` (`engine/nodes.py`) causes push/PR/merge to be entirely skipped.

## Acceptance Criteria (BDD)

### AC 1: System prompt prohibits agent SCM operations

**Given** the agent is invoked via `claude_code_sdk.query()` in `invoker.py`
**When** `ClaudeCodeOptions` is constructed
**Then** a `system_prompt` field is set that contains explicit instructions prohibiting the agent from running `git commit`, `git push`, `git checkout`, `git branch`, or any other SCM-mutating commands
**And** the system prompt states that all SCM operations are managed by the pipeline and the agent must only write/modify files

### AC 2: commit_story detects agent-created commits

**Given** the agent has already committed changes during dispatch (worktree is clean, but HEAD has moved forward from the branch creation point)
**When** `commit_story()` runs in `scm/branch.py`
**Then** instead of immediately raising `BranchError`, it checks whether new commits exist on the branch since worktree creation (e.g. comparing HEAD against the merge-base or the original branch-point ref)
**And** if agent-created commits are found, it returns the latest commit hash without making an additional commit

### AC 3: Pipeline push/PR/merge proceeds with agent-created commits

**Given** `commit_story()` returns a valid commit hash (either pipeline-created or agent-created)
**When** `commit_node()` runs in `engine/nodes.py`
**Then** `commit_hash` is not `None`
**And** push, PR creation, and auto-merge proceed as normal through the existing `if commit_hash is not None:` gate

### AC 4: Normal pipeline-created commits are unaffected

**Given** the agent did NOT commit during dispatch (worktree has uncommitted changes)
**When** `commit_story()` runs
**Then** it stages and commits as before, returning the new commit hash
**And** push/PR/merge proceeds as normal (no regression)

### AC 5: Mixed scenario — agent commit plus uncommitted changes

**Given** the agent committed some changes during dispatch but also left additional unstaged/uncommitted changes in the worktree
**When** `commit_story()` runs
**Then** it stages and commits the remaining uncommitted changes on top of the agent's commit
**And** returns the latest commit hash
**And** push/PR/merge proceeds as normal

### AC 6: Logging for agent-created commit detection

**Given** `commit_story()` detects that the agent already committed (worktree clean but HEAD advanced)
**When** it returns the agent-created commit hash
**Then** a structured log event is emitted at `INFO` level with key `"scm.commit.agent_created"` containing the commit hash and story slug

### AC 7: Tests cover all commit scenarios

**Given** the test suite
**When** tests are run
**Then** there are tests for:
  - Normal commit (uncommitted changes → pipeline commits)
  - Agent-created commit (clean worktree, HEAD advanced → returns existing hash)
  - Mixed scenario (agent committed + more uncommitted changes → pipeline commits on top)
  - System prompt is present in `ClaudeCodeOptions`
**And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions (baseline: 925 tests)

## Tasks / Subtasks

- [x] Task 1: Add system_prompt to ClaudeCodeOptions (AC: #1)
  - [x] 1.1: In `src/arcwright_ai/agent/invoker.py`, add a module-level constant `_SCM_GUARDRAIL_PROMPT` near the existing module-level constants (~line 35). Content must explicitly prohibit: `git commit`, `git push`, `git checkout`, `git branch`, `git merge`, `git rebase`, `git reset`, `git stash`, `git tag`, and any other SCM-mutating shell commands. Must state: "All version control operations are managed by the Arcwright AI pipeline. You must only create, modify, or delete files."
  - [x] 1.2: In `invoke_agent()` (~line 515), add `system_prompt=_SCM_GUARDRAIL_PROMPT` to the existing `ClaudeCodeOptions(...)` constructor call
  - [x] 1.3: Add unit test in `tests/test_agent/test_invoker.py` verifying the `system_prompt` field is set on `ClaudeCodeOptions` and contains SCM prohibition keywords

- [x] Task 2: Make `commit_story()` resilient to agent-created commits (AC: #2, #3, #4, #5, #6)
  - [x] 2.1: Add `base_ref: str | None = None` keyword-only parameter to `commit_story()` signature in `src/arcwright_ai/scm/branch.py` (~line 182)
  - [x] 2.2: After `git add .` and `git status --porcelain` returns empty, BEFORE raising `BranchError`, add a fallback check: if `base_ref` is provided, run `git rev-parse HEAD` and compare against `base_ref`
  - [x] 2.3: If HEAD != base_ref → agent has committed. Emit structured log `"scm.commit.agent_created"` at INFO level with `story_slug` and `commit_hash`, then return the HEAD hash
  - [x] 2.4: If HEAD == base_ref OR `base_ref` is `None` → raise `BranchError` as before (preserves backward compatibility)
  - [x] 2.5: When porcelain is NOT empty (AC: #5), the existing `git commit` path is unchanged — `git add .` already stages everything, including changes on top of agent commits
  - [x] 2.6: Update `__all__` in `scm/__init__.py` if needed (currently exports `commit_story` — signature change is backward-compatible, no update needed)

- [x] Task 3: Pass base_ref from `commit_node` to `commit_story()` (AC: #2, #3)
  - [x] 3.1: In `src/arcwright_ai/engine/nodes.py`, `commit_node()` (~line 1323), resolve the base ref before calling `commit_story()`. Use `git merge-base HEAD <default_branch>` executed in the worktree via the `git()` wrapper. This avoids adding a new field to `StoryState`.
  - [x] 3.2: Pass the resolved base ref to `commit_story(... base_ref=resolved_base_ref)` (~line 1395)
  - [x] 3.3: Wrap the base_ref resolution in try/except — if it fails, pass `base_ref=None` so `commit_story()` falls back to existing behavior
  - [x] 3.4: Import `_detect_default_branch` is already available in nodes.py (line 38-42); use `state.config.scm.default_branch` or the detected default branch for the merge-base call

- [x] Task 4: Add tests for all commit scenarios (AC: #7)
  - [x] 4.1: In `tests/test_scm/test_branch.py`, add test: agent committed changes (porcelain empty, HEAD != base_ref via mock) → returns commit hash, no error raised, INFO log emitted
  - [x] 4.2: Add test: agent committed some + left uncommitted changes (porcelain not empty) → stages, commits, returns new hash (existing path, but verify with base_ref provided)
  - [x] 4.3: Add test: truly empty worktree (porcelain empty, HEAD == base_ref) → raises `BranchError`
  - [x] 4.4: Add test: backward compat — `base_ref=None` with empty porcelain → raises `BranchError` (existing behavior preserved)
  - [x] 4.5: In `tests/test_agent/test_invoker.py`, add test: system_prompt is set on `ClaudeCodeOptions` and contains SCM prohibition keywords ("git commit", "git push", etc.)
  - [x] 4.6: Run full suite: `uv run ruff check src/ tests/ && uv run pytest` — 932 passed (7 new tests), 0 failures

## Dev Notes

### Architecture Compliance

- **Package DAG (Mandatory):** `scm` and `agent` are sibling domain packages depending only on `core`. Changes to `invoker.py` (agent package) and `branch.py` (scm package) are independent. `engine/nodes.py` mediates between them — this is correct per the DAG: `engine → {agent, scm} → core`.
- **D7 (No Force Operations):** This story does NOT introduce any force operations. The `commit_story()` change detects agent-created commits via `git rev-parse` comparison, not force-reset.
- **D7 (Single Gateway — Boundary 4):** All git subprocess calls continue to go through `arcwright_ai.scm.git.git()`. No direct subprocess calls introduced.
- **Best-effort SCM pattern:** The `commit_node` wraps all SCM operations in try/except with warning-level logging. This story preserves that pattern — the new `base_ref` comparison is inside the existing try block.
- **Structured logging convention:** All log events use `logger.info("dotted.event.key", extra={"data": {...}})` pattern. New log event `"scm.commit.agent_created"` follows this convention.

### Exact Code Locations & Implementation Details

#### Task 1: `invoker.py` — System Prompt Addition

**File:** `src/arcwright_ai/agent/invoker.py`

**Add constant near line 35** (after `_FILE_WRITE_TOOLS`):
```python
_SCM_GUARDRAIL_PROMPT: str = (
    "CRITICAL: Do NOT run any git or version control commands. "
    "Specifically, do NOT run: git commit, git push, git checkout, git branch, "
    "git merge, git rebase, git reset, git stash, git tag, or any command that "
    "modifies the git repository state. All version control operations "
    "(commit, push, branch, PR creation) are managed by the Arcwright AI pipeline. "
    "You must only create, modify, or delete files. The pipeline will handle "
    "all git operations after you complete your work."
)
```

**Modify `invoke_agent()` ClaudeCodeOptions constructor (~line 515):**
```python
options = ClaudeCodeOptions(
    model=model,
    cwd=str(cwd),
    permission_mode="bypassPermissions",
    max_turns=max_turns,
    system_prompt=_SCM_GUARDRAIL_PROMPT,
    can_use_tool=_make_tool_validator(sandbox, cwd),
)
```

**Claude Code SDK note:** `ClaudeCodeOptions` accepts `system_prompt: str | None` — this is a standard field, no SDK upgrade needed.

#### Task 2: `branch.py` — Commit Resilience

**File:** `src/arcwright_ai/scm/branch.py`
**Function:** `commit_story()` (line ~182)

**Add `base_ref` parameter:**
```python
async def commit_story(
    story_slug: str,
    story_title: str,
    story_path: str,
    run_id: str,
    *,
    worktree_path: Path,
    base_ref: str | None = None,  # NEW: branch creation point for agent-commit detection
) -> str:
```

**New logic after `git status --porcelain` returns empty (currently line ~230):**

Replace the immediate `BranchError` raise with:
```python
if not status_result.stdout.strip():
    # Worktree is clean — check if agent already committed
    if base_ref is not None:
        head_result = await git("rev-parse", "HEAD", cwd=worktree_path)
        head_sha = head_result.stdout.strip()
        if head_sha != base_ref:
            # Agent created commits — HEAD advanced past branch creation point
            logger.info(
                "scm.commit.agent_created",
                extra={
                    "data": {
                        "story_slug": story_slug,
                        "commit_hash": head_sha,
                        "base_ref": base_ref,
                        "worktree_path": str(worktree_path),
                    }
                },
            )
            return head_sha
    # Truly empty — no agent commits and no uncommitted changes
    logger.error(
        "git.commit.error",
        extra={...},  # existing error logging
    )
    raise BranchError(...)
```

**When porcelain is NOT empty:** No changes needed. The existing `git add .` → `git commit` path already handles the AC #5 mixed scenario: `git add .` stages everything, including changes on top of agent commits, and the commit succeeds normally.

**Critical: Do NOT change the flow when `status_result.stdout.strip()` is truthy.** The existing path handles both normal commits AND the mixed scenario (agent committed + additional uncommitted changes).

#### Task 3: `nodes.py` — Pass Base Ref to `commit_story()`

**File:** `src/arcwright_ai/engine/nodes.py`
**Function:** `commit_node()` (line ~1323)

**Add base_ref resolution before the `commit_story()` call (~line 1395):**

```python
# Resolve base ref for agent-commit detection (Story 10.4)
resolved_base_ref: str | None = None
try:
    default_branch = state.config.scm.default_branch or "main"
    base_result = await git("merge-base", "HEAD", default_branch, cwd=state.worktree_path)
    resolved_base_ref = base_result.stdout.strip()
except Exception as exc:
    logger.debug(
        "scm.commit.base_ref_resolution_failed",
        extra={"data": {"story": story_slug, "error": str(exc)}},
    )
    # Fall through with None — commit_story() falls back to existing behavior

commit_hash = await commit_story(
    story_slug=story_slug,
    story_title=story_title,
    story_path=str(state.story_path),
    run_id=run_id,
    worktree_path=state.worktree_path,
    base_ref=resolved_base_ref,  # NEW
)
```

**Import note:** `git` from `arcwright_ai.scm.git` is NOT currently imported in `nodes.py`. You'll need to add: `from arcwright_ai.scm.git import git` to the imports at the top of the file. Verify this doesn't violate the package DAG — `engine` → `scm` → `core` is valid per the architecture.

**Alternative approach:** If importing `git` directly into `nodes.py` feels wrong (it bypasses the `branch.py` abstraction), create a small helper like `get_merge_base(branch1, branch2, *, cwd)` in `branch.py` and import that instead. But given that `nodes.py` already imports `commit_story`, `push_branch`, `fetch_and_sync`, and `delete_remote_branch` directly from `scm/branch.py`, importing `git` from `scm/git.py` follows the same pattern. `engine` → `scm` is a valid edge in the package DAG.

### Testing Strategy

**Test baseline:** 925 tests (verified 2026-03-16)

**Test file for branch operations:** `tests/test_scm/test_branch.py` (~800 lines)

Existing fixtures and patterns:
```python
async def _ok(stdout: str = "", stderr: str = "") -> GitResult:
    return GitResult(stdout=stdout, stderr=stderr)
```

All tests mock `arcwright_ai.scm.branch.git` (the imported `git` function). For `commit_story()` tests, control:
- `git add .` → `_ok()`
- `git status --porcelain` → `_ok(stdout="")` for clean, `_ok(stdout="M file.py\n")` for dirty
- `git rev-parse HEAD` → `_ok(stdout="abc123def456")` for known SHA
- `git commit -m ...` → `_ok()`

**Test file for invoker:** `tests/test_agent/test_invoker.py` (~600 lines)

Uses `mock_sdk` fixture that patches `claude_code_sdk.query`. To test system_prompt, capture the `ClaudeCodeOptions` instance passed to the SDK query call and assert `system_prompt` contains expected prohibition keywords.

### Previous Story Intelligence

**Story 10.3 (LangGraph Major Upgrade):**
- Completed successfully, 921 tests passed at time (now 925)
- Risk was in `graph.builder.branches` internal API — rewritten to use public API
- No changes to SCM or agent packages — clean separation
- Key learning: Major dependency upgrades can be done safely when API surface is narrow

**Story 6.6 (SCM Integration with Engine Nodes):**
- Established the `commit_node` pattern: best-effort SCM operations, `ScmError` caught at WARNING level
- Created the `if commit_hash is not None:` gate for push/PR/merge
- This gate is the exact code path this story ensures works correctly

**Story 6.7 (Push Branch and Open Pull Request):**
- Established merge-ours reconciliation for stale remote branches
- Push/PR are best-effort, never halt execution
- Auto-merge (Story 9.3) added later — all downstream of `commit_hash` check

**Story 2.5 (Agent Invoker):**
- Established `invoke_agent()` as single entry point
- `ClaudeCodeOptions` constructed with `permission_mode="bypassPermissions"` and `can_use_tool`
- No `system_prompt` was set — that's the gap this story fills

### Git Intelligence (Recent Commits)

```
5d9b82c (HEAD) feat: auto-load .env file via python-dotenv
5544860 docs: add LangSmith tracing setup instructions
ac915b0 docs: add CHANGELOG, fix package name typo
36cc06a feat: add python -m arcwright_ai entry point
fab3783 fix: strip STORY- prefix in dispatch --story argument
```

Recent work: documentation and DX improvements. No SCM or agent code changes since Epic 9.

### Project Structure Notes

```
arcwright-ai/src/arcwright_ai/
├── agent/
│   ├── invoker.py          ← Task 1: Add _SCM_GUARDRAIL_PROMPT + system_prompt param
│   ├── prompt.py            (no changes)
│   └── sandbox.py           (no changes)
├── scm/
│   ├── branch.py           ← Task 2: Add base_ref param to commit_story()
│   ├── git.py               (no changes — subprocess wrapper)
│   ├── pr.py                (no changes)
│   └── worktree.py          (no changes)
├── engine/
│   ├── nodes.py            ← Task 3: Resolve base_ref, pass to commit_story()
│   ├── graph.py             (no changes)
│   └── state.py             (no changes — no new state fields needed)
└── core/
    ├── constants.py          (no changes)
    └── exceptions.py         (BranchError already defined, no changes)
```

### Risk Assessment

**LOW-MEDIUM.** All changes are additive:
- `invoker.py`: Adding one parameter to an existing constructor — lowest risk
- `branch.py`: Adding an optional keyword-only parameter with `None` default — backward-compatible by design
- `nodes.py`: Wrapping base_ref resolution in try/except with fallback to `None` — cannot break existing behavior

**Regression risk:** LOW. When `base_ref=None` (default), `commit_story()` behaves exactly as before. All existing callers pass no `base_ref`, so they continue working. Only `commit_node` in `nodes.py` passes the new parameter.

### References

- [Source: _spec/planning-artifacts/architecture.md — D7 Git Operations Strategy, Boundary 4]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/epics.md — Epic 10, Story 10.4]
- [Source: arcwright-ai/src/arcwright_ai/agent/invoker.py — invoke_agent(), ClaudeCodeOptions constructor ~line 515]
- [Source: arcwright-ai/src/arcwright_ai/scm/branch.py — commit_story() ~line 182]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — commit_node() ~line 1323, preflight_node() ~line 85]
- [Source: arcwright-ai/src/arcwright_ai/engine/state.py — StoryState.base_ref ~line 58]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — BRANCH_PREFIX ~line 89, COMMIT_MESSAGE_TEMPLATE ~line 102]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No debug issues encountered. All tasks completed cleanly on first pass.

### Completion Notes List

- ✅ Task 1: Added `_SCM_GUARDRAIL_PROMPT` module-level constant after `_FILE_WRITE_TOOLS` in `invoker.py` with explicit prohibitions for git commit, push, checkout, branch, merge, rebase, reset, stash, tag. Added `system_prompt=_SCM_GUARDRAIL_PROMPT` to `ClaudeCodeOptions` constructor in `invoke_agent()`. No SDK upgrade needed — `system_prompt` is a standard existing field.
- ✅ Task 2: Added `base_ref: str | None = None` keyword-only parameter to `commit_story()` in `branch.py`. After detecting empty porcelain, added fallback: if `base_ref is not None`, runs `git rev-parse HEAD` and compares vs base_ref. If HEAD != base_ref → emits `scm.commit.agent_created` INFO log and returns agent's commit hash. Backward-compatible: default `None` preserves existing BranchError behavior.
- ✅ Task 3: Added `from arcwright_ai.scm.git import git` import to `nodes.py`. In `commit_node()`, added base_ref resolution using `git merge-base HEAD <default_branch>` before calling `commit_story()`. Wrapped in try/except with DEBUG log and fallback to `None` on failure. Passed as `base_ref=resolved_base_ref` to `commit_story()`.
- ✅ Task 4: Added 5 new tests to `test_branch.py` covering all commit scenarios (agent-created, mixed, clean+base_ref_equal, backward_compat, mixed_with_base_ref). Added 2 new tests to `test_invoker.py` verifying `system_prompt` is set and contains all SCM prohibition keywords. Full suite: 932 passed (7 new tests added, 0 regressions from 925 baseline).
- ✅ `ruff check`: All checks passed
- ✅ `pytest`: 932 passed, 0 failed, 354 warnings in 13.16s
- ✅ Code review remediation: `commit_node()` now resolves the effective default branch via `_detect_default_branch(...)` before `git merge-base`, ensuring non-`main` repos correctly detect agent-created commits. Added/updated engine node test to assert `base_ref` propagation.

### File List

arcwright-ai/src/arcwright_ai/agent/invoker.py
arcwright-ai/src/arcwright_ai/scm/branch.py
arcwright-ai/src/arcwright_ai/engine/nodes.py
arcwright-ai/tests/test_agent/test_invoker.py
arcwright-ai/tests/test_scm/test_branch.py
arcwright-ai/tests/test_engine/test_nodes.py
_spec/implementation-artifacts/sprint-status.yaml
_spec/planning-artifacts/epics.md
arcwright-ai/uv.lock

### Change Log

- Story 10.4: Agent SCM guardrails & commit-node resilience (Date: 2026-03-16)
  - invoker.py: Added `_SCM_GUARDRAIL_PROMPT` constant and `system_prompt` to `ClaudeCodeOptions` — prevents agent from running git commands during dispatch
  - branch.py: Added `base_ref` parameter to `commit_story()` — detects agent-created commits and returns their hash instead of raising BranchError
  - nodes.py: Added `git` import and base_ref resolution via `git merge-base HEAD <default_branch>` in `commit_node()` — ensures push/PR/auto-merge chain always executes when agent produces code
  - 7 new tests (5 in test_branch.py, 2 in test_invoker.py)
- Story 10.4: Code review remediation pass (Date: 2026-03-16)
    - nodes.py: Updated default-branch resolution in `commit_node()` to use `_detect_default_branch(...)` before merge-base lookup
    - test_nodes.py: Strengthened commit-node test to assert resolved `base_ref` is passed to `commit_story(...)`
    - Story metadata synced: status set to `done` and File List reconciled with workspace changes
