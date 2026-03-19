# Story 10.11: LLM-Extracted Agent Decisions in PR Body

Status: done

## Story

As a code reviewer using Arcwright AI,
I want pull requests to contain a section with the agent's actual implementation decisions extracted by a review model from the diff and conversation output,
so that I can understand the reasoning behind code changes — not just pipeline execution metadata.

## Acceptance Criteria

1. **Given** `agent_dispatch_node` has completed and saved agent output to `agent-output.md` **When** the extraction step runs **Then** it invokes the `review` role model with the git diff and agent output text as input
2. **Given** the review model returns structured decisions **When** decisions are recorded **Then** they are written to `## Implementation Decisions` in the provenance file as `### Decision:` subsections following the existing `ProvenanceEntry` format
3. **Given** `commit_node` calls `generate_pr_body()` **When** the PR body is rendered **Then** the existing pipeline metadata entries appear under `### Pipeline Activity` (renamed from `### Decision Provenance`) and the extracted decisions appear under a new `### Agent Decisions` heading
4. **Given** the extraction step encounters an error (model timeout, invalid response) **When** the PR body is rendered **Then** pipeline activity is still shown and `### Agent Decisions` displays "Decision extraction unavailable" — the PR is created regardless
5. **Given** a retry cycle occurs (validate → retry → dispatch → extract → validate) **When** the final PR is generated **Then** extracted decisions from ALL attempts are present in the `### Agent Decisions` section
6. **And** `ruff check`, `mypy --strict`, and `pytest` all pass with zero regressions

## Tasks / Subtasks

- [x] Task 1 — Extract decisions via review model (AC: #1, #2)
  - [x] 1.1 Create `_extract_agent_decisions()` async function in `engine/nodes.py` (or new module `output/decisions.py`)
  - [x] 1.2 Build extraction prompt: include git diff (from worktree vs base ref) + agent-output.md content
  - [x] 1.3 Invoke review model via `invoke_agent()` with structured output prompt
  - [x] 1.4 Parse review model response into list of `ProvenanceEntry` objects
  - [x] 1.5 Write entries to `## Implementation Decisions` section in provenance file
  - [x] 1.6 Call extraction in `commit_node` **before** `generate_pr_body()` call

- [x] Task 2 — Update provenance file format (AC: #2, #5)
  - [x] 2.1 Add `## Implementation Decisions` section support in `output/provenance.py`
  - [x] 2.2 Ensure `merge_validation_checkpoint()` preserves `## Implementation Decisions` alongside `## Agent Decisions`
  - [x] 2.3 Ensure `append_entry()` can target either section by parameter
  - [x] 2.4 Handle retry accumulation: extraction appends, does not overwrite

- [x] Task 3 — Rename and restructure PR body sections (AC: #3)
  - [x] 3.1 Rename `### Decision Provenance` → `### Pipeline Activity` in `_render_pr_body()`
  - [x] 3.2 Add new `### Agent Decisions` section in `_render_pr_body()` above `### Pipeline Activity`
  - [x] 3.3 Create `_extract_implementation_decisions()` parser in `scm/pr.py` for `## Implementation Decisions` section
  - [x] 3.4 Wire new section into `generate_pr_body()` pipeline

- [x] Task 4 — Error handling and graceful fallback (AC: #4)
  - [x] 4.1 Wrap extraction in try/except — log warning, do not halt pipeline
  - [x] 4.2 On extraction failure: `### Agent Decisions` renders "Decision extraction unavailable"
  - [x] 4.3 Budget: account for extraction model cost in budget tracking

- [x] Task 5 — Tests (AC: #6)
  - [x] 5.1 Unit tests for extraction prompt construction
  - [x] 5.2 Unit tests for response parsing into `ProvenanceEntry` list
  - [x] 5.3 Unit tests for `_render_pr_body()` with new section layout
  - [x] 5.4 Unit tests for `_extract_implementation_decisions()` parser
  - [x] 5.5 Integration test: dispatch → extract → validate → commit → PR body has both sections
  - [x] 5.6 Regression test: extraction failure does not break PR creation
  - [x] 5.7 Retry accumulation test: decisions from all attempts present

## Dev Notes

### Problem Context

The current `### Decision Provenance` section in PR bodies contains pipeline execution metadata:
- "Agent invoked for story X (attempt 1)" — which model, prompt length, retry count
- "Validation attempt 1: pass" — V6/V3 check results
- "Auto-merge PR after creation" — merge strategy, outcome

These describe **what the pipeline did**, not **what the agent decided** during implementation. A code reviewer wants to see things like: "chose Strategy pattern over if/else chain", "added index on user_id for query performance", "split module into two files for separation of concerns".

### Architecture: Where Extraction Fits

**Pipeline flow (current):**
```
preflight → budget_check → agent_dispatch → validate → commit → finalize
                                               ↑ retry ↩
```

**The extraction step runs inside `commit_node`**, after the worktree is committed but before `generate_pr_body()` is called. This is the optimal position because:
1. The git diff is available (worktree has been committed)
2. The agent-output.md is available (written by `agent_dispatch_node`)
3. It's after all retries are complete (no wasted extraction on intermediate attempts)
4. It runs once per story, not per-attempt

**Alternative considered (per-attempt extraction):** Would provide decisions from each retry attempt, but costs an extra LLM call per retry. For retry scenarios, the extraction at commit time can still access all `agent-output.md` checkpoints from all attempts. The current approach is simpler and cheaper.

### Extraction Approach

1. **Read git diff**: Run `git diff {base_ref}..HEAD` in the worktree to get the full change set
2. **Read agent output**: Load `agent-output.md` from the run checkpoint directory
3. **Prompt the review model**: Send diff + agent output with a structured extraction prompt asking for implementation decisions
4. **Parse response**: Extract decisions into `ProvenanceEntry` objects with:
   - `decision`: Short title (e.g., "Added retry logic for flaky API calls")
   - `alternatives`: What else could have been done
   - `rationale`: Why this approach was chosen
   - `ac_references`: Which ACs this relates to
5. **Write to provenance**: Append to `## Implementation Decisions` section

### Model Configuration

Use the existing `review` role model from the model registry:
```python
review_spec = state.config.models.get(ModelRole.REVIEW)
```
This is the same model used for V3 reflexion validation — it's already configured and budget-tracked.

### Provenance File Format — Updated 4-Section Structure

```markdown
# Provenance: {story-slug}

## Agent Decisions

### Decision: Agent invoked for story X (attempt 1)
- **Timestamp**: ...
- **Alternatives**: claude-opus-4-1
- **Rationale**: Prompt length: 8472 chars, ...
- **References**: FR-8, FR-12

### Decision: Validation attempt 1: pass
- **Timestamp**: ...
- **Alternatives**: claude-sonnet-3-8
- **Rationale**: All checks passed ...
- **References**: None

## Implementation Decisions

### Decision: Chose Strategy pattern for validation routing
- **Timestamp**: ...
- **Alternatives**: if/else chain, registry dict, match statement
- **Rationale**: Strategy pattern allows adding new validation types without modifying existing code ...
- **References**: AC-1, FR-9

### Decision: Added database index on user_id column
- **Timestamp**: ...
- **Alternatives**: No index (sequential scan), composite index
- **Rationale**: Query profiling showed O(n) scans on user_id lookups ...
- **References**: NFR-3

## Validation History

| Attempt | Result | Feedback |
|---------|--------|----------|
| 1 | pass | All checks passed |

## Context Provided

- FR-8
- FR-12
```

### PR Body Format — Updated Section Layout

```markdown
## Story: {title}

---

### Acceptance Criteria
- [ ] AC 1 text
- [ ] AC 2 text

### Validation Results
| Attempt | Result | Feedback |
|---------|--------|----------|
| 1 | pass | All checks passed |

### Agent Decisions       ← NEW (extracted by review model)
#### Chose Strategy pattern for validation routing
- **Alternatives**: if/else chain, registry dict, match statement
- **Rationale**: Strategy pattern allows adding new validation types ...
- **References**: AC-1, FR-9

### Pipeline Activity      ← RENAMED from "Decision Provenance"
#### Agent invoked for story X (attempt 1)
- **Timestamp**: ...
- **Alternatives**: claude-opus-4-1
- **Rationale**: Prompt length: 8472 chars, ...
- **References**: FR-8, FR-12
```

### Key Code Locations

| Component | File | Key Functions |
|-----------|------|---------------|
| Agent invoker | `src/arcwright_ai/agent/invoker.py` | `invoke_agent()` — reuse for extraction call |
| Engine nodes | `src/arcwright_ai/engine/nodes.py` | `commit_node()` — add extraction before PR gen |
| Provenance | `src/arcwright_ai/output/provenance.py` | `append_entry()`, `merge_validation_checkpoint()` — extend for new section |
| PR body | `src/arcwright_ai/scm/pr.py` | `_render_pr_body()`, `_extract_decisions()`, `generate_pr_body()` |
| Constants | `src/arcwright_ai/core/constants.py` | `AGENT_OUTPUT_FILENAME = "agent-output.md"` |
| Types | `src/arcwright_ai/core/types.py` | `ProvenanceEntry` model |
| State | `src/arcwright_ai/engine/state.py` | `StoryState` — `worktree_path`, `agent_output`, `config.models` |

### Existing Patterns to Follow

**Provenance entry recording** (from `agent_dispatch_node`):
```python
provenance_entry = ProvenanceEntry(
    decision=f"Agent invoked for story {state.story_id} (attempt {state.retry_count + 1})",
    alternatives=[gen_spec.version],
    rationale=f"Prompt length: {len(prompt)} chars, ...",
    ac_references=refs,
    timestamp=datetime.now(tz=UTC).isoformat(),
)
await append_entry(provenance_path, provenance_entry)
```

**Review model invocation** (from `validate_node` — uses `invoke_agent` with review role):
```python
review_spec = state.config.models.get(ModelRole.REVIEW)
# invoke_agent() takes: prompt, model, cwd, sandbox, api_key
```

**API key access** (Story 10.10 pattern):
```python
api_key = state.config.api.claude_api_key.get_secret_value()
```

**Git diff from worktree** (existing pattern in `commit_node`):
```python
from arcwright_ai.scm.git import git
diff_result = await git("diff", f"{base_ref}..HEAD", cwd=state.worktree_path)
diff_text = diff_result.stdout
```

**Best-effort pattern** (existing pattern in `commit_node` for non-fatal operations):
```python
try:
    # extraction logic
except Exception as exc:
    logger.warning("decisions.extraction_error", extra={"data": {"story": story_slug, "error": str(exc)}})
```

**Budget tracking for extraction call**: The extraction uses the review model. Cost must be accumulated in the budget via the same pattern `agent_dispatch_node` uses — update `BudgetState` tokens and cost after invocation.

### Previous Story Intelligence

**Story 10.10** (most recent): Changed `claude_api_key` to `SecretStr`. Any new code accessing the API key must use `.get_secret_value()`.

**Story 10.7**: Fixed provenance preservation. `merge_validation_checkpoint()` now preserves `## Agent Decisions`. The new `## Implementation Decisions` section must ALSO be preserved by this function. This is the most critical integration point.

**Story 10.4**: Added SCM guardrail system prompt. The extraction call does NOT need SCM guardrails (it's read-only analysis) — but the `invoke_agent()` function already injects `_SCM_GUARDRAIL_PROMPT`. The extraction prompt should be a different invocation path, or the extraction should use the review model's LLM directly (not `invoke_agent` which is designed for code-writing agents with tool use). Consider using a simpler LLM call (e.g., direct Anthropic API call through the SDK) rather than `invoke_agent()` which grants tool permissions.

### Critical Design Decision: invoke_agent vs. direct LLM call

`invoke_agent()` grants tool use (file read/write, shell commands) with sandbox enforcement. For decision extraction, the model only needs to READ the diff and agent output — it should NOT write files or use tools. Two options:

1. **Use `invoke_agent()` with a no-op sandbox**: Simplest reuse, but grants unnecessary capabilities
2. **Create a lighter `invoke_review()` function**: Direct `claude_code_sdk.query()` call with read-only permissions or no tools at all

Option 2 is cleaner and safer. However, the claude_code_sdk may not support tool-free invocation easily. Investigate the SDK API. If not feasible, use option 1 with proper prompt guardrails (instruct model to only analyze, not modify files).

**IMPORTANT**: Whichever approach, the extraction cost (tokens in/out, USD) must be tracked and added to the story's `BudgetState` to maintain accurate cost reporting.

### Project Structure Notes

- All source in `arcwright-ai/src/arcwright_ai/` — standard Python package layout
- Tests mirror source structure: `tests/test_engine/`, `tests/test_scm/`, `tests/test_output/`
- Constants in `core/constants.py`, types in `core/types.py`
- Async file I/O via `output/fs.py` (`write_text_async`, `read_text_async`)
- Git operations via `scm/git.py` (`git()` async wrapper)

### References

- [Source: _spec/planning-artifacts/architecture.md — Decision 3 (Provenance), Decision 5 (Run Schema), Decision 9 (Model Registry)]
- [Source: _spec/planning-artifacts/epics.md — Epic 10 stories]
- [Source: arcwright-ai/src/arcwright_ai/scm/pr.py — PR body generation pipeline]
- [Source: arcwright-ai/src/arcwright_ai/output/provenance.py — Provenance recording]
- [Source: arcwright-ai/src/arcwright_ai/engine/nodes.py — commit_node, agent_dispatch_node]
- [Source: arcwright-ai/src/arcwright_ai/agent/invoker.py — invoke_agent(), InvocationResult]
- [Source: _spec/implementation-artifacts/10-7-validate-node-overwrites-provenance-decision-provenance-missing-from-prs.md — Prior provenance fix]
- [Source: _spec/implementation-artifacts/10-10-redact-api-key-from-langsmith-traces-via-secretstr.md — SecretStr pattern]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Template `{...}` brace escaping in `_EXTRACTION_PROMPT_TEMPLATE` required `{{...}}` for literal braces
- `git` and `invoke_agent` are local imports inside `extract_agent_decisions`; patching must target `arcwright_ai.scm.git.git` and `arcwright_ai.agent.invoker.invoke_agent`, not `arcwright_ai.output.decisions.git`
- `### Decision Provenance` renamed to `### Pipeline Activity`; existing tests updated accordingly
- Accidental drop of `run_manager`/`summary` imports during ruff sort fix; restored

### Completion Notes List

- New module `output/decisions.py` created with `build_extraction_prompt`, `parse_extraction_response`, `extract_agent_decisions`
- `output/provenance.py` extended with `## Implementation Decisions` section and `append_entry_to_section()` function
- `scm/pr.py` restructured: `### Decision Provenance` → `### Pipeline Activity`; new `### Agent Decisions` section; `_extract_implementation_decisions()` parser; `_parse_decisions_from_section()` generic helper
- `engine/nodes.py` calls `extract_agent_decisions()` in `commit_node` before `generate_pr_body()` with full budget accumulation
- All 1023 tests pass; ruff and mypy --strict clean
- AC #5 (retry accumulation): `append_entry_to_section` appends rather than overwrites, so multi-attempt extractions accumulate
- Review follow-up: unparseable extraction responses now return no decisions so PR body fallback shows "Decision extraction unavailable"
- Review follow-up: `agent_dispatch_node` now writes `agent-output.attempt-{n}.md`; extraction aggregates attempt outputs to satisfy AC #5

### File List

- `arcwright-ai/src/arcwright_ai/output/decisions.py` (NEW)
- `arcwright-ai/src/arcwright_ai/output/provenance.py` (MODIFIED)
- `arcwright-ai/src/arcwright_ai/scm/pr.py` (MODIFIED)
- `arcwright-ai/src/arcwright_ai/engine/nodes.py` (MODIFIED)
- `arcwright-ai/tests/test_output/test_decisions.py` (NEW)
- `arcwright-ai/tests/test_output/test_provenance.py` (MODIFIED — added 5.7 tests)
- `arcwright-ai/tests/test_scm/test_pr.py` (MODIFIED — added 5.3/5.4 tests, updated renamed sections)
- `arcwright-ai/tests/test_engine/test_nodes.py` (MODIFIED — added retry attempt checkpoint coverage)
- `_spec/implementation-artifacts/sprint-status.yaml` (MODIFIED — story status synced during review follow-up)
- `_spec/planning-artifacts/epics.md` (MODIFIED — epic tracking text updates present in working tree)
