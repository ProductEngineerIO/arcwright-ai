# Story 2.2: Context Injector — BMAD Artifact Reader & Reference Resolver

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer dispatching a story,
I want the system to read BMAD planning artifacts and resolve FR/NFR/architecture references from the story file into a focused context bundle,
so that the agent receives the relevant requirements, architecture decisions, and acceptance criteria for the story it's implementing.

## Acceptance Criteria (BDD)

1. **Given** a story markdown file with FR references (e.g., `FR-1`, `NFR-5`) and architecture section references **When** `context/injector.py` processes the story **Then** the story parser extracts the story text, acceptance criteria, and all natural references (FR IDs, NFR IDs, architecture section anchors).

2. **Given** a story with FR/NFR references **When** the context resolver runs **Then** it maps FR/NFR IDs via regex (`FR-?\d+`, `NFR-?\d+`) to their definitions in the PRD document.

3. **Given** a story with architecture section references **When** the context resolver runs **Then** architecture references are resolved to the relevant section text from `architecture.md`.

4. **Given** resolved references and story content **When** the bundle builder assembles a `ContextBundle` **Then** it contains: story text, resolved requirement snippets, relevant architecture excerpts, project conventions.

5. **Given** an assembled `ContextBundle` **When** its entries are inspected **Then** every context payload entry carries a source reference (file path + section anchor) for provenance tracing.

6. **Given** a story with references that cannot be resolved **When** the context resolver runs **Then** unresolved references are logged as `context.unresolved` structured events (not errors) — the agent proceeds with available context.

7. **Given** the context resolution strategy **When** inspected **Then** no fuzzy matching or LLM fallback is used — pure regex pattern matching only per D4.

8. **Given** an assembled `ContextBundle` **When** serialized **Then** the bundle is serializable to markdown for checkpoint writing.

9. **Given** unit tests in `tests/test_context/` **When** `pytest tests/test_context/test_injector.py` is run **Then** tests cover: successful reference resolution, unresolved references (logged not errored), empty story (no refs), architecture section lookup, bundle assembly, and markdown serialization.

10. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

11. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

12. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement story parser in `context/injector.py` (AC: #1, #7, #12)
  - [x] 1.1: Add `from __future__ import annotations` as first line
  - [x] 1.2: Add imports: `asyncio`, `logging`, `re` from stdlib; `Path` from pathlib; `ContextBundle` from `arcwright_ai.core.types`; `ContextError` from `arcwright_ai.core.exceptions`; `read_text_async` from `arcwright_ai.core.io`
  - [x] 1.3: Create module-level logger: `logger = logging.getLogger(__name__)`
  - [x] 1.4: Define `@dataclass(frozen=True)` class `ParsedStory` with fields: `raw_content: str`, `acceptance_criteria: str`, `fr_references: list[str]`, `nfr_references: list[str]`, `architecture_references: list[str]`
  - [x] 1.5: Implement `async def parse_story(story_path: Path) -> ParsedStory` — reads story file via `read_text_async`, extracts full content, acceptance criteria section (between `## Acceptance Criteria` heading and next `##` heading), FR references via `re.findall(r"FR-?\d+", text, re.IGNORECASE)`, NFR references via `re.findall(r"NFR-?\d+", text, re.IGNORECASE)`, architecture section anchors via `re.findall(r"(?:Decision|D)\s*\d+|§\w+", text, re.IGNORECASE)`. Deduplicate all references.
  - [x] 1.6: Raise `ContextError` if story file does not exist or is unreadable
  - [x] 1.7: Add Google-style docstrings for `ParsedStory` and `parse_story`

- [x] Task 2: Implement reference resolver in `context/injector.py` (AC: #2, #3, #5, #6, #7, #12)
  - [x] 2.1: Define `@dataclass(frozen=True)` class `ResolvedReference` with fields: `ref_id: str`, `source_path: str`, `section_anchor: str`, `content: str`
  - [x] 2.2: Implement `async def _resolve_fr_references(fr_refs: list[str], prd_path: Path) -> list[ResolvedReference]` — loads PRD via `read_text_async`, splits into sections by `##` headings, for each FR reference uses regex to find matching section (e.g., `FR-?\d+` pattern in heading or body), extracts section text and returns `ResolvedReference` with `source_path=str(prd_path)` and `section_anchor`
  - [x] 2.3: Implement `async def _resolve_nfr_references(nfr_refs: list[str], prd_path: Path) -> list[ResolvedReference]` — same pattern as FR resolver; NFRs are in the PRD
  - [x] 2.4: Implement `async def _resolve_architecture_references(arch_refs: list[str], architecture_path: Path) -> list[ResolvedReference]` — loads architecture doc, splits by `## ` and `### ` headings, matches Decision/D references to `### Decision N:` sections, returns `ResolvedReference` with section text
  - [x] 2.5: For each resolver, log unresolved references as structured events: `logger.info("context.unresolved", extra={"data": {"ref": ref_id, "source": str(path)}})` — never raise errors for unresolved refs
  - [x] 2.6: Add Google-style docstrings for all resolver functions and `ResolvedReference`

- [x] Task 3: Implement bundle builder in `context/injector.py` (AC: #4, #5, #8, #12)
  - [x] 3.1: Implement `def _format_resolved_references(refs: list[ResolvedReference]) -> str` — formats each reference as markdown with source citation: `### {ref_id}\n\n{content}\n\n[Source: {source_path}#{section_anchor}]\n\n---\n`
  - [x] 3.2: Implement `async def build_context_bundle(story_path: Path, project_root: Path) -> ContextBundle` — the main public entry point:
    - Parse story via `parse_story()`
    - Derive artifact paths: `prd_path = project_root / config.methodology.artifacts_path / "planning-artifacts"` (use `_spec/planning-artifacts/prd.md` as default)
    - Derive `architecture_path` similarly
    - Call all three resolvers in parallel using `asyncio.gather()`
    - Assemble `ContextBundle(story_content=parsed.raw_content, architecture_sections=_format_resolved_references(arch_refs), domain_requirements=_format_resolved_references(fr_refs + nfr_refs), answerer_rules="")`
    - Log summary: `logger.info("context.resolve", extra={"data": {"story": str(story_path), "refs_found": total_found, "refs_unresolved": total_unresolved}})`
  - [x] 3.3: Handle case where PRD or architecture file doesn't exist — log `context.unresolved` for the missing doc, return `ContextBundle` with whatever is available (do NOT raise `ContextError` for missing docs — only raise for missing story file)
  - [x] 3.4: Add Google-style docstring for `build_context_bundle`

- [x] Task 4: Implement markdown serialization helper (AC: #8, #12)
  - [x] 4.1: Implement `def serialize_bundle_to_markdown(bundle: ContextBundle) -> str` — formats the `ContextBundle` as a markdown document suitable for checkpoint writing with sections: `# Context Bundle`, `## Story Content`, `## Resolved Requirements`, `## Architecture Sections`, `## Answerer Rules`
  - [x] 4.2: Add Google-style docstring

- [x] Task 5: Update `context/injector.py` and `context/__init__.py` exports (AC: #10)
  - [x] 5.1: Set `__all__` in `context/injector.py`: `["ParsedStory", "ResolvedReference", "build_context_bundle", "parse_story", "serialize_bundle_to_markdown"]` (alphabetical per RUF022)
  - [x] 5.2: Update `context/__init__.py` to import and re-export: `build_context_bundle`, `parse_story`, `serialize_bundle_to_markdown` from `context.injector`
  - [x] 5.3: Update `context/__init__.py` `__all__` in alphabetical order

- [x] Task 6: Write unit tests in `tests/test_context/test_injector.py` (AC: #9)
  - [x] 6.1: Create `tests/test_context/test_injector.py` with `from __future__ import annotations`
  - [x] 6.2: Create helper fixtures:
    - `sample_story_content` — markdown string with FR-1, FR-16, NFR-7, Decision 4 references in a realistic story format
    - `sample_prd_content` — markdown string with `## FR1:`, `## NFR7:` sections containing requirement definitions
    - `sample_architecture_content` — markdown string with `### Decision 4:` sections
    - `story_file(tmp_path)` — writes `sample_story_content` to `tmp_path / "story.md"` and returns the path
    - `project_fixture(tmp_path)` — creates `tmp_path / "_spec/planning-artifacts/prd.md"` with `sample_prd_content`, `tmp_path / "_spec/planning-artifacts/architecture.md"` with `sample_architecture_content`, returns `tmp_path`
  - [x] 6.3: Test `test_parse_story_extracts_fr_references` — parse a story with FR-1, FR-16 → verify `parsed.fr_references` contains both (deduplicated)
  - [x] 6.4: Test `test_parse_story_extracts_nfr_references` — parse a story with NFR-5, NFR-7 → verify extraction
  - [x] 6.5: Test `test_parse_story_extracts_architecture_references` — parse with Decision 4, D1 → verify extraction
  - [x] 6.6: Test `test_parse_story_extracts_acceptance_criteria` — verify AC section text extracted
  - [x] 6.7: Test `test_parse_story_empty_references` — story with no references → empty lists, no errors
  - [x] 6.8: Test `test_parse_story_raises_context_error_for_missing_file` — non-existent path → `ContextError`
  - [x] 6.9: Test `test_resolve_fr_references_finds_matching_sections` — FR-1, FR-16 → resolved with correct content from PRD
  - [x] 6.10: Test `test_resolve_fr_references_logs_unresolved` — FR-99 (not in PRD) → logged, not errored (use `caplog` fixture)
  - [x] 6.11: Test `test_resolve_architecture_references_finds_decisions` — Decision 4 → resolved with correct section text
  - [x] 6.12: Test `test_resolve_architecture_references_logs_unresolved` — Decision 99 → logged, not errored
  - [x] 6.13: Test `test_build_context_bundle_assembles_complete_bundle` — full integration: story with refs + PRD + arch → `ContextBundle` with all fields populated
  - [x] 6.14: Test `test_build_context_bundle_includes_source_references` — verify source path and section anchors appear in formatted output
  - [x] 6.15: Test `test_build_context_bundle_handles_missing_prd` — no PRD file → bundle with empty `domain_requirements`, not an error
  - [x] 6.16: Test `test_build_context_bundle_handles_missing_architecture` — no arch file → bundle with empty `architecture_sections`, not an error
  - [x] 6.17: Test `test_serialize_bundle_to_markdown_produces_valid_markdown` — serialize a populated bundle → verify markdown sections present
  - [x] 6.18: Test `test_serialize_bundle_to_markdown_empty_bundle` — serialize with empty fields → valid markdown (empty sections)

- [x] Task 7: Validate all quality gates (AC: #10, #11)
  - [x] 7.1: Run `ruff check .` — zero violations
  - [x] 7.2: Run `ruff format --check .` — no formatting diffs
  - [x] 7.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 7.4: Run `pytest tests/test_context/ -v` — all new tests pass
  - [x] 7.5: Run `pytest` — full test suite passes (no regressions)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `context/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
`context/` depends ONLY on `core/`. It must NOT import from `engine/`, `agent/`, `validation/`, `output/`, or `scm/`. The `engine/` package will wire `context/injector.py` into the preflight node (Story 2.6). This story implements the standalone context resolution logic — no engine integration.

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. When populating `context/injector.py` and `context/__init__.py`, sort all entries alphabetically.

#### Async-First I/O — `asyncio.to_thread()` for File Reads
All file reads MUST use `read_text_async()` from `core/io.py` (which wraps `asyncio.to_thread()`). Never use synchronous `path.read_text()` directly in async functions.

#### Structured Logging — Not `print()`, Not Unstructured Strings
```python
logger.info("context.resolve", extra={"data": {"story": str(story_path), "refs_found": 5, "refs_unresolved": 1}})
logger.info("context.unresolved", extra={"data": {"ref": "FR-99", "source": str(prd_path)}})
```
**Never:** `logger.info(f"Resolved {n} references for {story}")` or `print(...)`.

#### No Fuzzy Matching — Strict Regex Only (D4 Constraint)
Per Architecture Decision 4, MVP context resolution uses **pure regex pattern matching only**:
- FR/NFR IDs → regex match `FR-?\d+`, `NFR-?\d+` against document content
- Architecture refs → match against `### Decision N:` section headings
- **No fuzzy matching**, no similarity scoring, no LLM fallback
- Unresolved refs → log as `context.unresolved`, proceed with available context

#### Error Handling — `ContextError` for Story File Issues Only
- Missing/unreadable story file → raise `ContextError` (exit code 3 — user-fixable per D6)
- Missing PRD or architecture file → **do NOT raise** — log as `context.unresolved`, return bundle with available content
- Malformed sections → log and skip, never crash

#### Existing `ContextBundle` Model — Use As-Is
The `ContextBundle` model in `core/types.py` already defines the fields:
```python
class ContextBundle(ArcwrightModel):
    story_content: str
    architecture_sections: str = ""
    domain_requirements: str = ""
    answerer_rules: str = ""
```
- `story_content`: Full markdown content of the story file
- `architecture_sections`: Formatted resolved architecture excerts with source refs
- `domain_requirements`: Formatted resolved FR/NFR requirements with source refs
- `answerer_rules`: Empty string for now — populated by Story 2.3 (Context Answerer)

ContextBundle is frozen (`ArcwrightModel` base). Construct it in one shot — no mutation after creation.

#### Source Reference Format
Every resolved reference must carry provenance information. Use this format in the output strings:
```
[Source: _spec/planning-artifacts/prd.md#FR-16]
[Source: _spec/planning-artifacts/architecture.md#Decision-4]
```
This allows downstream provenance tracing (Story 4.1) to link context back to source documents.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented. `context/answerer.py` retains its empty `__all__` — we only modify `context/injector.py` and `context/__init__.py`.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. Applies to `ParsedStory` if using Pydantic (use `dataclass` instead — no Pydantic needed for internal data objects).
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. Not directly relevant here, but do NOT change RunConfig.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. `tests/test_context/__init__.py` already exists.

---

### Previous Story Intelligence (Story 2.1 Learnings)

**From Story 2.1 (LangGraph State Models & Graph Skeleton):**

- `StoryState.context_bundle` is typed as `ContextBundle | None = None`. This story's `build_context_bundle()` returns a `ContextBundle` that the preflight node (Story 2.6) will assign to this field.
- `StoryState.story_path: Path` and `StoryState.project_root: Path` are available to the preflight node and will be passed to `build_context_bundle()`.
- Graph node pattern established: all nodes return full `StoryState` via `model_copy(update={...})`. This story does NOT touch graph nodes — it provides the function that the preflight node will call.
- TCH/type-checking pattern: LangGraph resolves annotations at runtime, so node function type annotations must be available at runtime (not behind `TYPE_CHECKING`). For `context/injector.py`, this is NOT relevant — we are not defining graph nodes in this module, so standard `TYPE_CHECKING` guards are fine.
- Structured logging pattern: `logger.info("event.name", extra={"data": {...}})` — use the event name as the first argument, structured data in `extra["data"]`.
- `BudgetState` was reconciled in Story 2.1 — uses `Decimal` for cost fields, `max_invocations: int`.

**From Story 2.1 Debug Log:**
- `# type: ignore[import-untyped]` comments were NOT needed for LangGraph imports on this platform — do not preemptively add them.
- `# noqa: TC001` was needed in `engine/nodes.py` where LangGraph resolves type annotations at runtime. Not needed in `context/injector.py`.

---

### Technical Specifications

#### Story Parser — Reference Extraction Patterns

The story parser must extract three types of references using regex:

**FR references:**
```python
FR_PATTERN = re.compile(r"\bFR[-‐]?\d+\b", re.IGNORECASE)
# Matches: FR1, FR-1, FR16, FR-16, fr1 (case insensitive)
```

**NFR references:**
```python
NFR_PATTERN = re.compile(r"\bNFR[-‐]?\d+\b", re.IGNORECASE)
# Matches: NFR1, NFR-1, NFR7, NFR-7, nfr5 (case insensitive)
```

**Architecture references:**
```python
ARCH_PATTERN = re.compile(r"\b(?:Decision|D)\s*\d+\b", re.IGNORECASE)
# Matches: Decision 4, Decision4, D4, D 4, decision 1 (case insensitive)
```

Deduplicate by normalizing: `FR-1` and `FR1` → `FR1` (strip dash, uppercase).

#### PRD Section Matching Strategy

The PRD (`_spec/planning-artifacts/prd.md`) contains FR/NFR definitions. Sections typically look like:

```markdown
- FR1: Developer can dispatch all stories in an epic for sequential autonomous execution
- FR16: System reads BMAD planning artifacts and injects the story's acceptance criteria...
```

Or in tables:
```markdown
| FR | Epic | Description |
|----|------|-------------|
| FR1 | Epic 2 | Dispatch all stories in an epic for sequential execution |
```

The resolver should:
1. Split PRD content by lines
2. For each FR/NFR reference, search for lines containing the reference ID
3. Extract the line plus surrounding context (the requirement definition)
4. If the requirement appears in a section (under a `##` heading), include the heading for context

#### Architecture Section Matching Strategy

The architecture doc uses `### Decision N:` headings for key decisions. Section text extends from the heading to the next `---` horizontal rule or `### Decision` heading.

Example:
```markdown
### Decision 4: Context Injection Strategy — Dispatch-Time Assembly (Option D)
...content until next section separator...
---
```

The resolver should:
1. Split architecture content by `### Decision` headings (or `### ` headings more broadly)
2. For each architecture reference (e.g., `Decision 4`, `D4`), find the matching section
3. Extract the full section text including sub-content

#### Bundle Assembly — Parallel Resolution

Use `asyncio.gather()` to resolve FR, NFR, and architecture references in parallel:

```python
fr_results, nfr_results, arch_results = await asyncio.gather(
    _resolve_fr_references(parsed.fr_references, prd_path),
    _resolve_nfr_references(parsed.nfr_references, prd_path),
    _resolve_architecture_references(parsed.architecture_references, arch_path),
)
```

#### Artifact Path Discovery

The injector needs to locate BMAD artifacts. Use simple path derivation from `project_root`:

```python
spec_dir = project_root / "_spec" / "planning-artifacts"
prd_path = spec_dir / "prd.md"
architecture_path = spec_dir / "architecture.md"
```

Note: The `_spec` directory name comes from `core/constants.py` → `DIR_SPEC = "_spec"`. Use the constant, not a hardcoded string. The `planning-artifacts` subdirectory is a convention — for robustness, the function should accept explicit paths as optional parameters and fall back to convention-based discovery.

#### Function Signature for `build_context_bundle`

```python
async def build_context_bundle(
    story_path: Path,
    project_root: Path,
    *,
    prd_path: Path | None = None,
    architecture_path: Path | None = None,
) -> ContextBundle:
    """Resolve FR/NFR/architecture references from a story file into a context bundle.

    Args:
        story_path: Path to the BMAD story markdown file.
        project_root: Root directory of the project.
        prd_path: Optional explicit path to PRD document. If None, derived from
            project_root / _spec / planning-artifacts / prd.md.
        architecture_path: Optional explicit path to architecture document. If None,
            derived from project_root / _spec / planning-artifacts / architecture.md.

    Returns:
        Assembled context bundle with resolved references.

    Raises:
        ContextError: If story file is missing or unreadable.
    """
```

#### Markdown Serialization Format

The `serialize_bundle_to_markdown()` function produces a checkpoint-ready markdown document:

```markdown
# Context Bundle

## Story Content

{story_content}

## Resolved Requirements

{domain_requirements}

## Architecture Sections

{architecture_sections}

## Answerer Rules

{answerer_rules}
```

---

### Project Structure Notes

**Files to create/modify:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/context/injector.py` | MODIFY (was placeholder) | Story parser, reference resolvers, bundle builder, markdown serializer |
| `src/arcwright_ai/context/__init__.py` | MODIFY (was empty `__all__`) | Add real exports from `injector` |
| `tests/test_context/test_injector.py` | CREATE | Unit tests for all injector functionality |

**Files NOT touched** (no changes needed):
- `core/types.py` — `ContextBundle` already correct with all needed fields
- `core/io.py` — `read_text_async` already available
- `core/exceptions.py` — `ContextError` already defined
- `core/constants.py` — `DIR_SPEC` already defined
- `context/answerer.py` — Story 2.3 scope, leave empty `__all__`
- `engine/` — preflight node wiring is Story 2.6 scope
- `cli/` — no CLI changes in this story

**Alignment with architecture:**
- `context/injector.py` matches architecture's project tree: "Story parser + reference resolver + bundle builder"
- Package exports match architecture: `resolve_context` (we use `build_context_bundle` as the specific function name)
- Test file matches architecture: `tests/test_context/test_injector.py`

---

### Cross-Story Context (Epic 2 Stories That Build on 2.2)

| Story | Relationship to 2.2 | Impact |
|---|---|---|
| 2.3: Context Answerer | Populates `ContextBundle.answerer_rules` field | Story 2.2 leaves `answerer_rules=""` — Story 2.3 adds rule lookup |
| 2.6: Preflight Node | Calls `build_context_bundle()` and stores result in `StoryState.context_bundle` | This story provides the function; 2.6 wires it into the graph |
| 2.5: Agent Invoker | Consumes `ContextBundle` via prompt builder | `agent/prompt.py` reads bundle fields to construct SDK prompt |
| 4.1: Provenance Recorder | Uses source references from bundle | Source citations (`[Source: ...]`) enable provenance tracing |

---

### Git Intelligence

Last 5 commits:
```
70d73e6 chore(story-2.1): finalize story file, quality-gate fixes, and sprint status
51fdf4d feat(engine): implement Story 2.1 — LangGraph state models and graph skeleton
5cf30a9 retro: complete Epic 1 retrospective
03a8e08 feat(cli): implement Story 1.5 — CLI validate-setup command
e56b320 feat(cli): implement Story 1.4 — CLI init command
```

**Patterns established:**
- Commit prefix: `feat(context):` for new feature in context package
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- All core types and config are stable — no pending changes expected

**Files from Story 2.1 that are relevant:**
- `src/arcwright_ai/engine/state.py` — `StoryState.context_bundle: ContextBundle | None = None` is the field this story's output populates
- `src/arcwright_ai/core/types.py` — `ContextBundle` model definition (do not modify)
- `src/arcwright_ai/core/io.py` — `read_text_async()` is the async file read primitive to use

---

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
def test_parse_story_extracts_fr_references(): ...
async def test_build_context_bundle_assembles_complete_bundle(): ...
```

**Async tests:** Use `@pytest.mark.asyncio` decorator for all async test functions.

**File fixtures:** Use `tmp_path` fixture for creating temporary story/PRD/architecture files:
```python
@pytest.fixture
def story_file(tmp_path: Path) -> Path:
    content = "# Story 1.1: Test Story\n\nFR-1, FR-16, NFR-7\n\n## Acceptance Criteria\n\n..."
    path = tmp_path / "story.md"
    path.write_text(content, encoding="utf-8")
    return path
```

**Log capture:** Use `caplog` fixture to verify structured log events are emitted:
```python
def test_resolve_logs_unresolved(caplog):
    with caplog.at_level(logging.INFO):
        # call resolver with unknown ref
        ...
    assert any("context.unresolved" in record.message for record in caplog.records)
```

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries.

**Test isolation:** Each test creates its own state via fixtures. No shared mutable state between tests.

---

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision-4 — Context Injection Strategy]
- [Source: _spec/planning-artifacts/architecture.md#Decision-1 — LangGraph State Model (D1↔D4 binding)]
- [Source: _spec/planning-artifacts/architecture.md — Package Dependency DAG]
- [Source: _spec/planning-artifacts/architecture.md — Async Patterns, Structured Logging Patterns]
- [Source: _spec/planning-artifacts/architecture.md — Context Chain FR16→17→18→19]
- [Source: _spec/planning-artifacts/architecture.md — Boundary 4: Application ↔ File System]
- [Source: _spec/planning-artifacts/epics.md — Epic 2, Story 2.2 AC]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — Known pitfalls, Action Items]
- [Source: _spec/implementation-artifacts/2-1-langgraph-state-models-and-graph-skeleton.md — Previous story patterns, debug log]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — ContextBundle, ArtifactRef definitions]
- [Source: arcwright-ai/src/arcwright_ai/core/io.py — read_text_async, write_text_async]
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py — ContextError definition]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — DIR_SPEC constant]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

- Task 1: Implemented `ParsedStory` dataclass and `parse_story()` with DOTALL regex for AC extraction. Normalised FR/NFR/arch refs to strip dashes/spaces before deduplication.
- Task 2: Resolved FR/NFR from PRD by line-scan (window context ±1 line). Architecture resolved by `### ` section splitting with `---` trim. Both log `context.unresolved` for misses.
- Task 3: `build_context_bundle()` accepts optional explicit `prd_path`/`architecture_path` for testability; resolves to `_spec/planning-artifacts/` via `DIR_SPEC` constant when not provided.
- Task 5: `Path` moved to `TYPE_CHECKING` block per TC003 ruff rule; `ContextBundle` promoted to top-level import since used at runtime.
- Task 6: `@pytest.mark.asyncio` provided automatically by `asyncio_mode=auto` in pyproject.toml.
- Task 7: All quality gates passed — 218/218 tests, zero ruff, zero mypy.

### Completion Notes List

- Implemented `ParsedStory` and `ResolvedReference` frozen dataclasses (not Pydantic — per pitfall #3 from Epic 1 retro).
- Strict regex patterns per D4: `_FR_PATTERN`, `_NFR_PATTERN`, `_ARCH_PATTERN` as module-level compiled constants.
- Normalisation: `FR1`/`FR-1` → `FR1`; `Decision4`/`D4`/`D 4` → `Decision4` for deduplication and matching.
- `build_context_bundle()` runs FR, NFR, and architecture resolution in parallel via `asyncio.gather()`.
- Missing PRD / architecture files → `context.unresolved` log events, empty string fields in bundle. Missing story file → `ContextError` raised.
- `answerer_rules=""` left empty for Story 2.3.
- 16 new unit tests added; 218 total tests pass (no regressions).

### File List

- `arcwright-ai/src/arcwright_ai/context/injector.py` — (modified) full implementation replacing placeholder
- `arcwright-ai/src/arcwright_ai/context/__init__.py` — (modified) real exports added
- `arcwright-ai/tests/test_context/test_injector.py` — (created) 16 unit tests

### Change Log

- 2026-03-02: Implemented Story 2.2 — Context Injector, BMAD Artifact Reader & Reference Resolver. Added `ParsedStory`, `ResolvedReference`, `parse_story`, `_resolve_fr_references`, `_resolve_nfr_references`, `_resolve_architecture_references`, `_format_resolved_references`, `build_context_bundle`, `serialize_bundle_to_markdown`. Updated context package exports. Created 16 unit tests. All quality gates passed.
