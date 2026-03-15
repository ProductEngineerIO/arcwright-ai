# Epic 6 Retrospective: SCM Integration & PR Generation

**Date**: 2026-03-10
**Epic**: SCM Integration & PR Generation (29 planned pts → 34 actual pts with 6.7 addition)
**Stories**: 7 (6 originally planned + 1 added mid-epic)
**Status**: All stories done

---

## Summary

Epic 6 delivered the complete SCM layer — git subprocess wrapping, worktree isolation, branch/commit management, PR body generation with embedded provenance, a cleanup CLI command, engine node integration, and push/PR automation. All 7 stories shipped clean with zero regressions.

---

## Metrics

| Metric | Value |
|--------|-------|
| Stories completed | 7/7 |
| Source LOC (scm package) | 1,806 |
| Source LOC (cli/clean.py) | 226 |
| Total source LOC added | ~2,032 |
| Test functions (epic 6) | 108 |
| Test LOC (epic 6) | ~3,079 |
| Test:Source ratio | 1.52:1 |
| Full suite tests | 728 passed |
| Ruff violations | 0 |
| Mypy (--strict) errors | 0 |

---

## What Went Well

### 1. Layered Architecture Held Up
The single-gateway contract (Boundary 4 — all git through `scm/git.py`) was easy to enforce and made error handling consistent. Every SCM module delegates to `git()` and gets logging, retry, and error classification for free. The only intentional exception is `gh` CLI calls in `pr.py`, which is correctly scoped to a non-git binary.

### 2. Best-Effort / Non-Fatal Pattern
The architectural decision to make push, PR creation, and worktree cleanup all non-fatal proved excellent. Story execution never halts due to network issues or missing `gh` CLI. This pattern was applied consistently across `branch.py` (`push_branch`), `pr.py` (`open_pull_request`), and `nodes.py` (`commit_node`).

### 3. Idempotency Discipline (NFR19)
Every delete operation (`remove_worktree`, `delete_branch`, `clean`) is a no-op when the target doesn't exist. This eliminates an entire class of "retry after partial failure" bugs and made the cleanup command trivial to implement correctly.

### 4. Atomic Recovery in Worktree Creation
The `_cleanup_partial_worktree` helper in `worktree.py` handles mid-operation failures (disk full, permission denied, branch conflicts) by best-effort cleanup that never raises. Combined with the stale worktree auto-recovery added in `preflight_node`, the system self-heals common developer workflow friction.

### 5. Test Pyramid Execution
108 tests split across unit (monkeypatch-based, fast) and integration (real git, `@pytest.mark.slow`) provide both rapid feedback and end-to-end confidence. The 1.52:1 test-to-source ratio reflects thorough coverage of error paths, edge cases, and idempotency guarantees.

### 6. PR Body Generator Quality
The read → parse → render pipeline in `pr.py` produces GitHub-flavored markdown with collapsible `<details>` blocks for large content, AC checklists, validation history tables, and provenance cross-references. Graceful degradation when `story.md` is missing avoids hard failures.

---

## What Could Be Improved

### 1. Story 6.7 Was Unplanned
Push branch and open PR functionality (Story 6.7) was not in the original epic breakdown. It was added mid-epic after recognizing that local-only branches (the D7 "no push in MVP" decision) would create significant manual overhead for overnight dispatch workflows. While the addition was natural and well-scoped (5 pts), it signals that the original epic planning underestimated the end-to-end SCM workflow. Future epics should trace the full user journey from dispatch through code review visibility when planning SCM-adjacent features.

### 2. `pr.py` Is the Largest Single File (708 Lines)
The provenance parser, story copy reader, PR body renderer, and PR creation logic all live in one module. The internal factoring into private functions is clean, but if PR templates or provenance formats evolve, this file will grow further. Consider splitting into `pr_body.py` (generation) and `pr_create.py` (GitHub interaction) if it exceeds ~800 lines.

### 3. Integration Tests Don't Cover Push/PR
The real-git integration tests cover worktree lifecycle, branch operations, and cleanup, but not the push/PR flow (since it requires a remote and `gh` CLI). This is a reasonable constraint, but means the push→PR pipeline is only unit-tested with mocks. A future growth-phase story could add a lightweight integration test using a bare local remote.

### 4. `gh` CLI Dependency
PR creation depends on GitHub CLI (`gh`) being installed and authenticated. While the graceful fallback (manual PR URL in logs) works, it means CI/CD environments or non-GitHub forges get no automated PR creation. This is documented as Growth phase scope but worth noting for users who adopt early.

---

## Risks Identified

| Risk | Severity | Mitigation |
|------|----------|------------|
| `gh` not installed in user environments | Low | Graceful fallback with manual PR URL logged |
| Large repos may slow `git add .` in worktrees | Low | Worktrees are isolated — only story changes staged |
| Lock file contention on parallel runs | Low | 3-retry exponential backoff in `git.py` |
| Stale worktrees accumulating disk space | Low | `arcwright-ai clean` command + auto-recovery in preflight |

---

## Architecture Decisions Validated

- **D7 (Git Operations Strategy)**: No force operations, no push in original MVP, user-initiated cleanup only — all enforced. The "no push" constraint was relaxed in Story 6.7 with best-effort semantics, preserving the spirit of D7 (never lose work).
- **NFR4 (Agent Sandbox)**: Worktree path is the sandbox boundary, set in `preflight_node`, consumed by `agent_dispatch_node`.
- **NFR14 (Git 2.25+ Compatibility)**: No post-2.25 features used. `--porcelain` output parsing is stable across versions.
- **NFR19 (Idempotency)**: All cleanup and delete operations are safe to retry.
- **NFR20 (Offline Operation)**: All operations except push/PR are local-only. Push/PR failures are non-fatal.

---

## Recommendations for Next Epic (Epic 7: Cost Tracking)

1. **Budget state touches the same engine nodes** — `agent_dispatch_node` and `commit_node` were both modified in Epic 6. Story 7.4 (cost integration) will modify them again. Recommend reviewing the node modification pattern established here (best-effort wrapping, structured logging, state updates) before starting.
2. **Test fixture reuse** — The `make_story_state` fixture was extended with `worktree_path` and `pr_url` in Epic 6. Budget fields will extend it further. Keep the fixture kwargs-based with backward-compatible defaults.
3. **Keep the "non-fatal enhancement" pattern** — Cost display (Story 7.3) should follow the same best-effort approach: missing cost data degrades gracefully rather than failing the run.

---

## Final Assessment

Epic 6 delivered a production-quality SCM layer with clean architecture, thorough testing, and consistent adherence to project conventions. The unplanned Story 6.7 was the right call — it closes the gap between local execution and code review visibility. The codebase is in strong shape entering Epic 7.
