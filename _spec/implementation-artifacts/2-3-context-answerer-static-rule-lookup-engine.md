# Story 2.3: Context Answerer — Static Rule Lookup Engine

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer whose agent needs to query BMAD conventions during implementation,
I want a static rule lookup engine that responds to agent questions about workflow steps, artifact formats, and naming conventions,
so that the agent can follow project conventions without LLM-based interpretation.

## Acceptance Criteria (BDD)

1. **Given** a `context/answerer.py` module **When** the answerer is initialized with a project's BMAD artifacts **Then** it indexes document sections by heading, building a searchable map of rules and conventions.

2. **Given** an initialized answerer **When** `lookup_answer(question_pattern: str) -> str | None` is called with a matching pattern **Then** it matches the question against indexed patterns using regex and returns the relevant section text.

3. **Given** an initialized answerer **When** `lookup_answer` is called with an unmatched pattern **Then** it returns `None` and logs a `context.answerer.no_match` structured event as a provenance note ("no answer available").

4. **Given** an initialized answerer **When** queries about naming conventions, file structure patterns, coding standards, or artifact format rules are made **Then** the answerer handles all four query categories returning appropriate answers.

5. **Given** a successful lookup result **When** the answer is inspected **Then** it includes the source document path and section heading for traceability.

6. **Given** multiple sections match a query **When** the answerer selects a result **Then** it returns the most specific match (shortest heading match or deepest nesting level).

7. **Given** unit tests in `tests/test_context/` **When** `pytest tests/test_context/test_answerer.py` is run **Then** tests cover: successful pattern match, no match (returns `None`), multiple matches (returns most specific), index building from sample BMAD artifacts.

8. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

9. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

10. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement `RuleIndex` and `IndexedSection` in `context/answerer.py` (AC: #1, #5, #10)
  - [x] 1.1: Add `from __future__ import annotations` as first line
  - [x] 1.2: Add imports: `logging`, `re` from stdlib; `Path` from pathlib (behind `TYPE_CHECKING`); `ContextError` from `arcwright_ai.core.exceptions`; `read_text_async` from `arcwright_ai.core.io`; `DIR_SPEC` from `arcwright_ai.core.constants`
  - [x] 1.3: Create module-level logger: `logger = logging.getLogger(__name__)`
  - [x] 1.4: Define `@dataclass(frozen=True)` class `IndexedSection` with fields: `heading: str`, `content: str`, `source_path: str`, `depth: int` (heading nesting level: `#` = 1, `##` = 2, `###` = 3, etc.)
  - [x] 1.5: Define class `RuleIndex` containing:
    - `_sections: list[IndexedSection]` — flat list of all indexed sections
    - `_patterns: dict[str, re.Pattern[str]]` — precompiled keyword-to-regex map for common query categories
  - [x] 1.6: Implement `async def build_index(cls, project_root: Path, *, doc_paths: list[Path] | None = None) -> RuleIndex` — class method that:
    - Discovers BMAD docs from `project_root / _spec / planning-artifacts /` (architecture.md, prd.md) and `project_root / docs /` if `doc_paths` not provided
    - For each document, calls `_index_document()` to parse all headings and their section content
    - Returns a populated `RuleIndex`
    - Logs `context.answerer.index` structured event with doc count and section count
    - Gracefully handles missing documents: log `context.unresolved` and continue — never raise for missing docs
  - [x] 1.7: Add Google-style docstrings for `IndexedSection`, `RuleIndex`, and `build_index`

- [x] Task 2: Implement document indexer in `context/answerer.py` (AC: #1, #5, #10)
  - [x] 2.1: Implement `async def _index_document(doc_path: Path) -> list[IndexedSection]` — reads document via `read_text_async`, splits by markdown heading pattern `^(#{1,6})\s+(.+)$` (multiline), extracts heading text and section content (text under heading until next heading of same or higher level), records `depth` from number of `#` characters, and returns list of `IndexedSection` with `source_path=str(doc_path)`
  - [x] 2.2: Handle section content extraction: content starts after the heading line and extends to the next heading at the same depth or higher (fewer `#` characters) or end of file
  - [x] 2.3: Strip horizontal rules (`---`) from section boundaries — sections should not include separator lines
  - [x] 2.4: Add Google-style docstring

- [x] Task 3: Implement `lookup_answer` in `context/answerer.py` (AC: #2, #3, #5, #6, #10)
  - [x] 3.1: Implement `def lookup_answer(self, question_pattern: str) -> str | None` on `RuleIndex`:
    - Compile `question_pattern` as a case-insensitive regex
    - Search all `_sections` by matching the pattern against both `heading` and `content`
    - On match: return formatted answer string including source reference: `{content}\n\n[Source: {source_path}#{heading}]`
    - On no match: log `context.answerer.no_match` structured event with the question pattern, return `None`
  - [x] 3.2: Implement specificity selection (AC: #6): when multiple sections match, prefer the one with:
    - First priority: heading match over content-only match
    - Second priority: deepest nesting level (highest `depth` value — more specific section)
    - Third priority: shortest content length (more focused answer)
  - [x] 3.3: Handle invalid regex patterns gracefully — catch `re.error`, log warning, fall back to literal string matching via `re.escape()`
  - [x] 3.4: Add Google-style docstring

- [x] Task 4: Implement convenience lookup functions (AC: #4, #10)
  - [x] 4.1: Implement `def lookup_naming_conventions(self) -> str | None` — calls `lookup_answer(r"naming\s+convention|snake.?case|PascalCase|UPPER.?SNAKE")`
  - [x] 4.2: Implement `def lookup_file_structure(self) -> str | None` — calls `lookup_answer(r"project\s+structure|file\s+structure|package.*structure|directory.*layout")`
  - [x] 4.3: Implement `def lookup_coding_standards(self) -> str | None` — calls `lookup_answer(r"coding\s+standard|code\s+style|import\s+order|docstring|type\s+hint")`
  - [x] 4.4: Implement `def lookup_artifact_format(self) -> str | None` — calls `lookup_answer(r"artifact\s+format|markdown\s+format|yaml\s+format|BMAD.*format")`
  - [x] 4.5: Add Google-style docstrings for all convenience functions

- [x] Task 5: Update `context/answerer.py` and `context/__init__.py` exports (AC: #8)
  - [x] 5.1: Set `__all__` in `context/answerer.py`: `["IndexedSection", "RuleIndex"]` (alphabetical per RUF022)
  - [x] 5.2: Update `context/__init__.py` to import and re-export: `IndexedSection`, `RuleIndex` from `context.answerer`
  - [x] 5.3: Update `context/__init__.py` `__all__` in alphabetical order — add new exports while preserving existing `build_context_bundle`, `parse_story`, `serialize_bundle_to_markdown`

- [x] Task 6: Write unit tests in `tests/test_context/test_answerer.py` (AC: #7)
  - [x] 6.1: Create `tests/test_context/test_answerer.py` with `from __future__ import annotations`
  - [x] 6.2: Create helper fixtures:
    - `sample_architecture_content` — markdown string with `## Implementation Patterns`, `### Python Code Style Patterns` (naming conventions, import ordering), `### Async Patterns`, `### Structured Logging Patterns`, `### Testing Patterns` subsections
    - `sample_prd_content` — markdown string with `## Functional Requirements`, `## NonFunctional Requirements` sections
    - `project_fixture(tmp_path)` — creates `tmp_path / "_spec/planning-artifacts/architecture.md"` and `tmp_path / "_spec/planning-artifacts/prd.md"` with sample content, returns `tmp_path`
  - [x] 6.3: Test `test_build_index_creates_sections_from_documents` — build index from project fixture, verify sections exist with correct headings, source paths, and depth values
  - [x] 6.4: Test `test_build_index_handles_missing_documents` — build index when one doc is missing → index still builds from available docs, log event emitted (use `caplog`)
  - [x] 6.5: Test `test_build_index_with_explicit_doc_paths` — pass custom `doc_paths` instead of relying on auto-discovery
  - [x] 6.6: Test `test_lookup_answer_finds_matching_section` — lookup "naming convention" → returns section with naming convention content and source reference
  - [x] 6.7: Test `test_lookup_answer_returns_none_for_no_match` — lookup "quantum computing" → returns `None`, log event emitted
  - [x] 6.8: Test `test_lookup_answer_returns_most_specific_match` — index contains both `## Implementation Patterns` (broad) and `### Python Code Style Patterns` (specific), lookup "code style" → returns the more specific `###` section
  - [x] 6.9: Test `test_lookup_answer_prefers_heading_match_over_content_match` — section A has "naming" in heading, section B has "naming" in content only → returns section A
  - [x] 6.10: Test `test_lookup_answer_handles_invalid_regex` — pass `"[invalid"` as pattern → does not raise, falls back to literal match or returns `None`
  - [x] 6.11: Test `test_lookup_answer_includes_source_reference` — verify returned string contains `[Source: ` with file path and section heading
  - [x] 6.12: Test `test_lookup_naming_conventions` — verify convenience method returns naming content
  - [x] 6.13: Test `test_lookup_file_structure` — verify convenience method returns file structure content
  - [x] 6.14: Test `test_lookup_coding_standards` — verify convenience method returns coding standards content
  - [x] 6.15: Test `test_lookup_artifact_format_returns_none_when_absent` — verify convenience method returns `None` when no artifact format section exists

- [x] Task 7: Validate all quality gates (AC: #8, #9)
  - [x] 7.1: Run `ruff check .` — zero violations
  - [x] 7.2: Run `ruff format --check .` — no formatting diffs
  - [x] 7.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 7.4: Run `pytest tests/test_context/test_answerer.py -v` — all new tests pass
  - [x] 7.5: Run `pytest` — full test suite passes (no regressions)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `context/` Position
```
cli → engine → {validation, agent, context, output, scm} → core
```
`context/` depends ONLY on `core/`. It must NOT import from `engine/`, `agent/`, `validation/`, `output/`, or `scm/`. The `engine/` package will wire `context/answerer.py` into the preflight node (Story 2.6). This story implements the standalone rule lookup logic — no engine integration.

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. When populating `context/answerer.py` and updating `context/__init__.py`, sort all entries alphabetically.

#### Async-First I/O — `asyncio.to_thread()` for File Reads
All file reads MUST use `read_text_async()` from `core/io.py` (which wraps `asyncio.to_thread()`). Never use synchronous `path.read_text()` directly in async functions. Note: `build_index()` is async because it reads document files. `lookup_answer()` is synchronous because it only operates on the in-memory index — no I/O needed after indexing.

#### Structured Logging — Not `print()`, Not Unstructured Strings
```python
logger.info("context.answerer.index", extra={"data": {"docs_loaded": 2, "sections_indexed": 45}})
logger.info("context.answerer.no_match", extra={"data": {"pattern": "quantum computing"}})
```
**Never:** `logger.info(f"No match found for {pattern}")` or `print(...)`.

#### No Fuzzy Matching — Strict Regex Only (D4 Constraint)
Per Architecture Decision 4, MVP context resolution uses **pure regex pattern matching only**:
- Question patterns are used as regex against indexed heading text and section content
- **No fuzzy matching**, no similarity scoring, no LLM fallback
- Unmatched queries → log as `context.answerer.no_match`, return `None`

#### Error Handling — Graceful Degradation
- Missing documents during indexing → log `context.unresolved`, skip, continue building index from available docs — never raise `ContextError` for missing docs
- Invalid regex in `lookup_answer` → catch `re.error`, log warning, fall back to `re.escape()` literal match
- Empty index (no docs found) → functional but returns `None` for all lookups — never crash

#### Existing `ContextBundle.answerer_rules` Field
The `ContextBundle` model already has `answerer_rules: str = ""`. Story 2.2's injector currently populates this with project conventions from `project-context.md`. Story 2.6 (Preflight Node) will wire the `RuleIndex` into the preflight flow and may append answerer lookup results to the `answerer_rules` field alongside project conventions.

**This story does NOT modify `ContextBundle` or `context/injector.py`.** It provides a standalone `RuleIndex` class that the preflight node will consume.

---

### Known Pitfalls from Epic 1 (MANDATORY — From Retro Action 1)

These pitfalls were identified during Epic 1 and MUST be applied to this story:

1. **`__all__` must be alphabetically sorted** (RUF022 — enforced by ruff). Not optional.
2. **Placeholder modules ship with empty `__all__: list[str] = []` only** — no aspirational exports for symbols not yet implemented. `context/answerer.py` currently has empty `__all__` — this story replaces it with real exports.
3. **Pydantic mutable default fields require `Field(default_factory=list)`** — never bare `= []`. For `RuleIndex._sections`, use a `dataclass` or plain class (not Pydantic) for internal data — no Pydantic overhead needed.
4. **Config sub-models must override `extra="ignore"`** (not `extra="forbid"`) for forward-compatible unknown key handling. Not directly relevant here — no config models in this story.
5. **Always use `.venv/bin/python -m mypy --strict src/`** — not bare `mypy`.
6. **Test subdirectories require `__init__.py`** for robust pytest import resolution. `tests/test_context/__init__.py` already exists.

---

### Previous Story Intelligence (Story 2.2 Learnings)

**From Story 2.2 (Context Injector — BMAD Artifact Reader & Reference Resolver):**

- `ParsedStory` and `ResolvedReference` are `@dataclass(frozen=True)` — not Pydantic. Use the same pattern for `IndexedSection`. No Pydantic overhead for internal data objects.
- `Path` is guarded behind `TYPE_CHECKING` per TC003 ruff rule. Runtime-needed imports (like `ContextBundle`) stay top-level.
- `_FR_PATTERN`, `_NFR_PATTERN`, `_ARCH_PATTERN` are module-level compiled regex constants. Follow same pattern for any patterns in the answerer.
- `asyncio.gather()` is used for parallel I/O in the injector. Use it for loading multiple documents during indexing if beneficial.
- Structured logging pattern: `logger.info("event.name", extra={"data": {...}})` — event name as first arg, structured data in `extra["data"]`.
- `build_context_bundle()` accepts optional explicit paths with fallback to convention-based discovery. Follow same pattern in `build_index()` with optional `doc_paths`.
- Normalisation helpers (`_normalise_fr`, `_normalise_arch`) are private module-level functions. Follow same pattern for heading normalisation.
- Test fixtures use `tmp_path` for creating temporary files. Story 2.2's `project_fixture` creates `_spec/planning-artifacts/` structure — reuse the pattern.
- `@pytest.mark.asyncio` is provided automatically by `asyncio_mode=auto` in `pyproject.toml` — no need for explicit decorator on async tests.

**From Story 2.2 Debug Log:**
- `Path` moved to `TYPE_CHECKING` block per TC003 ruff rule. Do the same in `answerer.py`.
- `ContextBundle` promoted to top-level import since used at runtime. `IndexedSection` is a local dataclass — no import-path concern.
- No `# type: ignore` comments were needed for core/io imports.

---

### Technical Specifications

#### `IndexedSection` Data Class

```python
@dataclass(frozen=True)
class IndexedSection:
    """A single indexed section from a BMAD document.

    Attributes:
        heading: The section heading text (e.g. 'Python Code Style Patterns').
        content: Full text content under this heading.
        source_path: Path of the source document.
        depth: Heading nesting level (# = 1, ## = 2, ### = 3, etc.).
    """
    heading: str
    content: str
    source_path: str
    depth: int
```

#### `RuleIndex` Class

```python
class RuleIndex:
    """Static rule lookup index built from BMAD project documents.

    Indexes all markdown sections by heading, enabling regex-based lookup
    of project rules, conventions, and standards. No fuzzy matching — pure
    regex per D4.

    Attributes:
        sections: List of all indexed sections from loaded documents.
    """

    def __init__(self, sections: list[IndexedSection]) -> None:
        self._sections = sections

    @classmethod
    async def build_index(
        cls,
        project_root: Path,
        *,
        doc_paths: list[Path] | None = None,
    ) -> RuleIndex:
        ...

    def lookup_answer(self, question_pattern: str) -> str | None:
        ...

    # Convenience methods
    def lookup_naming_conventions(self) -> str | None: ...
    def lookup_file_structure(self) -> str | None: ...
    def lookup_coding_standards(self) -> str | None: ...
    def lookup_artifact_format(self) -> str | None: ...
```

#### Document Indexing Strategy

The indexer parses markdown documents by heading hierarchy:

```markdown
# Top Level (depth=1)
Content under top level...

## Second Level (depth=2)
Content under second level...

### Third Level (depth=3)
Content under third level...
```

Each heading creates an `IndexedSection`. Content extends from the heading line to the next heading at the same depth or shallower, or end of file.

**Heading regex:**
```python
_HEADING_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
```

#### Lookup Specificity Algorithm

When multiple sections match a query pattern:

1. **Heading match > content-only match**: A section whose heading matches the pattern is preferred over one where only the body content matches.
2. **Deeper nesting > shallower nesting**: `### Python Code Style Patterns` (depth=3) beats `## Implementation Patterns` (depth=2) for a query about "code style".
3. **Shorter heading > longer heading**: Among equally deep heading matches, prefer the shorter heading.
4. **Shorter content > longer content**: Among otherwise equal sections, prefer the more focused (shorter) section.

```python
def _score_match(section: IndexedSection, pattern: re.Pattern[str]) -> tuple[int, int, int, int]:
    """Score a section match for specificity ranking.

    Returns:
        Tuple of (heading_match, depth, -heading_length, -content_length) for sorting.
        Higher values = better match.
    """
    heading_match = 1 if pattern.search(section.heading) else 0
      return (heading_match, section.depth, -len(section.heading), -len(section.content))
```

#### Auto-Discovery Document Paths

When `doc_paths` is not provided, the indexer discovers documents from:

```python
spec_dir = project_root / DIR_SPEC / "planning-artifacts"
docs_dir = project_root / "docs"

candidates = [
    spec_dir / "architecture.md",
    spec_dir / "prd.md",
]
# Also glob for any other .md files in docs/
if docs_dir.is_dir():
    candidates.extend(docs_dir.glob("*.md"))
```

Documents that don't exist are silently skipped with a `context.unresolved` log event.

#### Answer Format

Successful lookups return a formatted string:

```
{section content}

[Source: _spec/planning-artifacts/architecture.md#Python-Code-Style-Patterns]
```

The source reference format matches the convention established in Story 2.2's `ResolvedReference` — `[Source: {path}#{anchor}]`.

---

### Project Structure Notes

**Files to create/modify:**

| File | Action | Content |
|---|---|---|
| `src/arcwright_ai/context/answerer.py` | MODIFY (was placeholder) | `IndexedSection`, `RuleIndex` with indexer, lookup, and convenience methods |
| `src/arcwright_ai/context/__init__.py` | MODIFY | Add `IndexedSection`, `RuleIndex` to exports |
| `tests/test_context/test_answerer.py` | CREATE | Unit tests for all answerer functionality |

**Files NOT touched** (no changes needed):
- `core/types.py` — `ContextBundle` already correct; `answerer_rules` field exists
- `core/io.py` — `read_text_async` already available
- `core/exceptions.py` — `ContextError` already defined (but this story doesn't raise it)
- `core/constants.py` — `DIR_SPEC` already defined
- `context/injector.py` — Story 2.2 implementation is complete; no modifications needed
- `engine/` — preflight node wiring is Story 2.6 scope
- `cli/` — no CLI changes in this story

**Alignment with architecture:**
- `context/answerer.py` matches architecture's project tree: "Static rule lookup engine"
- FR17 mapping: `context/answerer.py` — "Regex-based pattern matcher against indexed document sections"
- Package exports follow the `__init__.py` re-export convention from Story 2.2

---

### Cross-Story Context (Epic 2 Stories That Interact with 2.3)

| Story | Relationship to 2.3 | Impact |
|---|---|---|
| 2.2: Context Injector | Sibling in `context/` package; 2.2 populates `answerer_rules` with project-context.md | This story adds rule lookup capability alongside 2.2's reference resolution |
| 2.6: Preflight Node | Calls `RuleIndex.build_index()` and uses it during context assembly | Preflight will build index, potentially call lookup methods, append results to `ContextBundle.answerer_rules` |
| 2.5: Agent Invoker | Agent may use answerer results from context bundle | Answerer rules in the bundle inform the agent about project conventions |
| 4.1: Provenance Recorder | Unanswered questions logged as provenance notes | `context.answerer.no_match` events feed into provenance trail |

---

### Git Intelligence

Last 5 commits:
```
f91e3a5 chore(story-2.2): post-format fixes, finalize story file, and sprint status
bcdbba7 feat(context): implement Story 2.2 — Context Injector, BMAD Artifact Reader & Reference Resolver
70d73e6 chore(story-2.1): finalize story file, quality-gate fixes, and sprint status
51fdf4d feat(engine): implement Story 2.1 — LangGraph state models and graph skeleton
5cf30a9 retro: complete Epic 1 retrospective
```

**Patterns established:**
- Commit prefix: `feat(context):` for new feature in context package — use same prefix for this story
- Test files co-committed with source files
- Quality gates (ruff, mypy, pytest) verified before commit
- `context/__init__.py` already has real exports from 2.2 — extend, don't replace

**Files from Story 2.2 that are relevant:**
- `src/arcwright_ai/context/injector.py` — established patterns for dataclass definitions, async I/O, structured logging, and regex matching in `context/` package
- `src/arcwright_ai/context/__init__.py` — current exports to extend
- `src/arcwright_ai/core/io.py` — `read_text_async()` is the async file read primitive to use
- `src/arcwright_ai/core/constants.py` — `DIR_SPEC` constant for path derivation

---

### Testing Patterns

**Test naming convention:** `test_<function_name>_<scenario>`:
```python
async def test_build_index_creates_sections_from_documents(): ...
def test_lookup_answer_finds_matching_section(): ...
def test_lookup_answer_returns_none_for_no_match(): ...
```

**Async tests:** `build_index` is async — test functions calling it must be `async def`. `lookup_answer` is synchronous — tests can be plain `def`.

**Note:** `asyncio_mode=auto` is configured in `pyproject.toml`, so `@pytest.mark.asyncio` is not needed on async test functions.

**File fixtures:** Use `tmp_path` fixture for creating temporary BMAD documents:
```python
@pytest.fixture
def project_fixture(tmp_path: Path) -> Path:
    spec_dir = tmp_path / "_spec" / "planning-artifacts"
    spec_dir.mkdir(parents=True)
    (spec_dir / "architecture.md").write_text(SAMPLE_ARCHITECTURE, encoding="utf-8")
    (spec_dir / "prd.md").write_text(SAMPLE_PRD, encoding="utf-8")
    return tmp_path
```

**Log capture:** Use `caplog` fixture to verify structured log events are emitted:
```python
def test_lookup_answer_returns_none_for_no_match(caplog, rule_index):
    with caplog.at_level(logging.INFO):
        result = rule_index.lookup_answer("quantum computing")
    assert result is None
    assert any("context.answerer.no_match" in record.message for record in caplog.records)
```

**Assertion style:** Plain `assert` + `pytest.raises` only. No assertion libraries.

**Test isolation:** Each test creates its own state via fixtures. No shared mutable state between tests.

---

### References

- [Source: _spec/planning-artifacts/architecture.md#Decision-4 — Context Injection Strategy, Answerer strategy]
- [Source: _spec/planning-artifacts/architecture.md#Context-Chain — FR16→17→18→19 mapping]
- [Source: _spec/planning-artifacts/architecture.md#Implementation-Patterns — Python Code Style, Async, Structured Logging, Testing patterns]
- [Source: _spec/planning-artifacts/architecture.md#Package-Dependency-DAG — context/ depends only on core/]
- [Source: _spec/planning-artifacts/architecture.md#Boundary-4 — All _spec/ reads go through context/injector.py]
- [Source: _spec/planning-artifacts/epics.md#Story-2.3 — Acceptance criteria, story definition]
- [Source: _spec/implementation-artifacts/epic-1-retro-2026-03-02.md — Known pitfalls, Action Items 1-3]
- [Source: _spec/implementation-artifacts/2-2-context-injector-bmad-artifact-reader-and-reference-resolver.md — Previous story patterns, dataclass conventions, structured logging patterns]
- [Source: arcwright-ai/src/arcwright_ai/context/answerer.py — Current empty placeholder]
- [Source: arcwright-ai/src/arcwright_ai/context/injector.py — Sibling module patterns]
- [Source: arcwright-ai/src/arcwright_ai/context/__init__.py — Current exports to extend]
- [Source: arcwright-ai/src/arcwright_ai/core/types.py — ContextBundle.answerer_rules field]
- [Source: arcwright-ai/src/arcwright_ai/core/io.py — read_text_async primitive]
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py — DIR_SPEC constant]

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Debug Log References

No debug issues encountered. All tests passed on second run after two fixes:
1. Added "naming convention" phrase to sample architecture fixture content
2. Updated `lookup_answer` output format to prepend heading (`**{heading}**\n\n{content}\n\n[Source: ...]`) so heading text appears in result — enabling test assertions on heading identity and satisfying AC #5 (traceability).

### Completion Notes List

- Implemented `IndexedSection` as a `@dataclass(frozen=True)` — same pattern as `ParsedStory` from Story 2.2
- Implemented `RuleIndex` with `build_index()` (async classmethod), `lookup_answer()` (sync), and 4 convenience methods
- `_index_document()` private async function parses markdown headings into `IndexedSection` objects with correct depth, content, and source path
- Specificity scoring: heading match > depth > shorter content, implemented via `_score_match()` helper and `max()` with key
- Invalid regex gracefully falls back to `re.escape()` literal match — no exception propagated
- `asyncio.gather()` used for parallel document loading in `build_index()`
- Answer format: `**{heading}**\n\n{content}\n\n[Source: {path}#{anchor}]` — heading prepended for traceability (AC #5)
- All 19 new tests pass; 241/241 full suite green; ruff check, ruff format, mypy --strict all pass
- `context/__init__.py` extended with `IndexedSection`, `RuleIndex` exports, `__all__` alphabetically ordered (RUF022)
- Senior code review fixes applied:
  - Added `ContextError` import and usage for resilient document read failures (logged as `context.unresolved` without raising)
  - Implemented required `RuleIndex._patterns` precompiled regex map for common query categories and routed convenience lookups through it
  - Refined specificity tie-breaker to include shorter heading preference when depth ties
  - Added regression test for heading-length tie-break behavior

### File List

- `arcwright-ai/src/arcwright_ai/context/answerer.py` (modified — was placeholder, now fully implemented)
- `arcwright-ai/src/arcwright_ai/context/__init__.py` (modified — added IndexedSection, RuleIndex exports)
- `arcwright-ai/tests/test_context/test_answerer.py` (created — 19 unit tests)
- `_spec/implementation-artifacts/2-3-context-answerer-static-rule-lookup-engine.md` (modified — review remediation + status update)
- `_spec/implementation-artifacts/sprint-status.yaml` (modified — synced story status)

### Senior Developer Review (AI)

- Outcome: Changes requested issues resolved.
- High severity findings fixed:
  - Missing `ContextError` import/usage in `context/answerer.py`
  - Missing required `_patterns` precompiled regex map on `RuleIndex`
- Medium severity findings fixed:
  - Story documentation/file list reconciled with actual modified files
  - Specificity behavior aligned to include shortest-heading tie-break alongside depth
- Verification: target tests, lint, and strict typing pass after fixes.

### Change Log

- 2026-03-02: Applied AI code-review remediation, updated story status to `done`, and synced sprint tracking.
