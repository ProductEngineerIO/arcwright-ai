# Story 10.15: Run Cost in PR Body

Status: done

## Story

As a developer reviewing an Arcwright AI–generated pull request,
I want the PR description to show the cost and token usage for the run that produced it,
so that I have full observability into execution cost without leaving the GitHub PR page.

## Acceptance Criteria

1. **Given** `generate_pr_body()` is called **When** the PR body is rendered **Then** it includes a cost metadata line near the top of the PR showing total cost in USD, total input tokens, total output tokens, and invocation count for the story run.
2. **Given** a story had multiple retry attempts **When** the PR body is rendered **Then** the cost shown is the **cumulative** total across all invocations (i.e. the value from `StoryCost.cost`, not a per-attempt value).
3. **Given** no cost data is available (e.g. `StoryCost` is the zero default) **When** the PR body is rendered **Then** the cost line is omitted gracefully — no placeholder or error text is emitted.
4. **Given** per-role cost breakdowns exist (generate vs review roles) **When** the PR body is rendered **Then** the cost line shows the overall total only (not per-role); per-role detail is already in the run `summary.md` and is not duplicated in the PR.
5. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1 — Thread `StoryCost` through the PR body call chain (AC: #1, #2, #3)
  - [x] 1.0 Add `StoryCost` to the existing import from `arcwright_ai.core.types` in `scm/pr.py` (not currently imported)
  - [x] 1.1 Add optional `story_cost: StoryCost | None = None` keyword argument to `generate_pr_body()` in `scm/pr.py`
  - [x] 1.2 Add optional `story_cost: StoryCost | None = None` keyword argument to `_render_pr_body()` in `scm/pr.py`
  - [x] 1.3 In `commit_node` (`engine/nodes.py` line ~1819), pass `state.budget.per_story.get(story_slug)` as `story_cost` to `generate_pr_body()`

- [x] Task 2 — Render the cost metadata line (AC: #1, #3, #4)
  - [x] 2.1 In `_render_pr_body()`, after the `---` separator and before `### Acceptance Criteria`, insert a `> 💰 **Run Cost:** $X.XX | **Tokens:** X,XXX in / X,XXX out | **Invocations:** N` blockquote line when `story_cost` is non-None and `story_cost.cost > 0`
  - [x] 2.2 Format cost as `f"${story_cost.cost:.4f}"` (four decimal places, consistent with CLI output)
  - [x] 2.3 Format token counts with thousands separators: `f"{story_cost.tokens_input:,}"` and `f"{story_cost.tokens_output:,}"`
  - [x] 2.4 Omit the line entirely when `story_cost is None` or `story_cost.cost == 0` (AC: #3)

- [x] Task 3 — Tests (AC: #5)
  - [x] 3.1 Unit test: `_render_pr_body()` with a real `StoryCost` → cost line present and correctly formatted
  - [x] 3.2 Unit test: `_render_pr_body()` with `story_cost=None` → no cost line emitted
  - [x] 3.3 Unit test: `_render_pr_body()` with `StoryCost()` zero-value default → no cost line emitted (AC: #3)
  - [x] 3.4 Unit test: cumulative cost with multi-invocation `StoryCost` (invocations=3) → invocation count shows `3`
  - [x] 3.5 Regression: existing `generate_pr_body()` call signature without `story_cost` still works (keyword arg is optional)

## Dev Notes

### Problem Context

Every PR currently includes Validation Results, Agent Decisions, and Pipeline Activity — but no cost. A reviewer has to open `.arcwright-ai/runs/<run-id>/summary.md` separately to find out what the story cost. Adding cost directly to the PR body closes this loop.

### Key Files

| File | Role |
|------|------|
| `arcwright-ai/src/arcwright_ai/scm/pr.py` | `generate_pr_body()`, `_render_pr_body()` — both need `story_cost` parameter |
| `arcwright-ai/src/arcwright_ai/engine/nodes.py` | Call site at line ~1819: `await generate_pr_body(run_id, story_slug, project_root=project_root)` |
| `arcwright-ai/src/arcwright_ai/core/types.py` | `StoryCost` model — read-only, no changes needed |
| `arcwright-ai/tests/test_scm/test_pr.py` | Existing PR body unit tests — extend here |

### `StoryCost` Fields Available at Call Site

```python
# In commit_node, state.budget.per_story is a dict[str, StoryCost]
story_cost: StoryCost = state.budget.per_story.get(story_slug, StoryCost())

# Fields of interest:
story_cost.cost           # Decimal — total USD across all invocations
story_cost.tokens_input   # int — total input tokens
story_cost.tokens_output  # int — total output tokens
story_cost.invocations    # int — number of agent calls
```

### Target PR Body Output

Current structure (unchanged):
```markdown
## Story: 6-4-pr-body-generator

---

### Acceptance Criteria
...
```

After this story:
```markdown
## Story: 6-4-pr-body-generator

---

> 💰 **Run Cost:** $0.1234 | **Tokens:** 45,231 in / 8,102 out | **Invocations:** 2

### Acceptance Criteria
...
```

The blockquote (`>`) keeps it visually distinct from section headings and consistent with GitHub's rendering of metadata-style lines.

### Implementation Pattern

```python
# _render_pr_body() — insert after the "---" separator block:
if story_cost is not None and story_cost.cost > 0:
    cost_str = f"${story_cost.cost:.4f}"
    tokens_in = f"{story_cost.tokens_input:,}"
    tokens_out = f"{story_cost.tokens_output:,}"
    invocations = story_cost.invocations
    parts.append(
        f"> 💰 **Run Cost:** {cost_str} | "
        f"**Tokens:** {tokens_in} in / {tokens_out} out | "
        f"**Invocations:** {invocations}"
    )
    parts.append("")
```

### Signature Changes

```python
# Before:
async def generate_pr_body(run_id: str, story_slug: str, *, project_root: Path) -> str:

# After:
async def generate_pr_body(
    run_id: str,
    story_slug: str,
    *,
    project_root: Path,
    story_cost: StoryCost | None = None,
) -> str:
```

```python
# Before:
def _render_pr_body(
    title: str,
    ac_items: list[str] | None,
    validation_table: str,
    decisions: list[_Decision],
    impl_decisions: list[_Decision] | None = None,
) -> str:

# After:
def _render_pr_body(
    title: str,
    ac_items: list[str] | None,
    validation_table: str,
    decisions: list[_Decision],
    impl_decisions: list[_Decision] | None = None,
    story_cost: StoryCost | None = None,
) -> str:
```

`StoryCost` is already imported in `scm/pr.py` — verify with `grep "StoryCost" scm/pr.py` before adding an import.

### Import Check

```bash
grep "StoryCost" arcwright-ai/src/arcwright_ai/scm/pr.py
```

If not present, add to the existing import from `arcwright_ai.core.types`.

### References

- `generate_pr_body()` public API: [Source: arcwright-ai/src/arcwright_ai/scm/pr.py#generate_pr_body]
- `_render_pr_body()` internal renderer: [Source: arcwright-ai/src/arcwright_ai/scm/pr.py#_render_pr_body]
- Call site in `commit_node`: [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py ~line 1819]
- `StoryCost` model: [Source: arcwright-ai/src/arcwright_ai/core/types.py]
- Predecessor story (PR body + decisions): [Source: _spec/implementation-artifacts/10-11-llm-extracted-agent-decisions-in-pr-body.md]
- CLI cost formatting reference (4 decimal places): [Source: arcwright-ai/src/arcwright_ai/cli/status.py]

## Dev Agent Record

### Agent Model Used

claude-sonnet-4-6

### Debug Log References

### Completion Notes List

- Added `StoryCost` to `TYPE_CHECKING` import block in `scm/pr.py` (TC001 ruff rule requires it; `from __future__ import annotations` makes it annotation-only at runtime).
- Added `story_cost: StoryCost | None = None` keyword argument to both `generate_pr_body()` and `_render_pr_body()`; threaded through call chain.
- In `_render_pr_body()`, renders `> 💰 **Run Cost:** $X.XXXX | **Tokens:** X,XXX in / X,XXX out | **Invocations:** N` blockquote immediately after the `---` separator when `story_cost is not None and story_cost.cost > 0`.
- Omits cost line silently when `story_cost is None` or `story_cost.cost == 0` (zero-value default).
- In `commit_node` (nodes.py line ~1819), passes `state.budget.per_story.get(story_slug)` as `story_cost` — returns `None` when no cost recorded, omitting the line gracefully.
- 7 new unit tests added; all 102 tests pass. `ruff check` and `mypy --strict` both clean.

### File List

- arcwright-ai/src/arcwright_ai/scm/pr.py
- arcwright-ai/src/arcwright_ai/engine/nodes.py
- arcwright-ai/tests/test_scm/test_pr.py
- _spec/implementation-artifacts/sprint-status.yaml
- _spec/implementation-artifacts/10-15-run-cost-in-pr-body.md

## Change Log

- 2026-08-08: Implemented Story 10.15 — threaded `StoryCost` through `generate_pr_body()` and `_render_pr_body()`, rendered cost metadata blockquote in PR body, added 7 unit tests. All ACs satisfied.
