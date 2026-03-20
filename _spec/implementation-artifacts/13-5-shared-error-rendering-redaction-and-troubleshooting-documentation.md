# Story 13.5: Shared Error Rendering, Redaction, and Troubleshooting Documentation

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As the maintainer of Arcwright AI,
I want terminal output, halt reports, summaries, and logs to use a shared Claude error rendering path with documented troubleshooting guidance,
So that operator messaging stays consistent across surfaces and future error categories can be added without drift.

## Acceptance Criteria (BDD)

### AC 1: Shared rendering path is used across user-facing surfaces

**Given** a Claude-related failure is classified
**When** Arcwright AI renders terminal output, halt reports, summaries, and structured logs
**Then** all surfaces derive guidance from a shared renderer or shared message contract rather than bespoke string assembly in multiple locations.

### AC 2: Secret redaction is enforced centrally

**Given** any Claude-related failure is rendered
**When** the output is inspected across terminal, halt report, summary, and logs
**Then** secret redaction behavior is applied consistently across all surfaces.

### AC 3: Troubleshooting documentation covers the major categories

**Given** the user needs to diagnose a Claude-related Arcwright AI failure
**When** they consult the documentation
**Then** there is a troubleshooting matrix covering platform/account failures, local runtime/configuration failures, transient provider failures, and unknown fallback cases
**And** the documentation explains which actions are local versus Claude-platform follow-up.

### AC 4: Cross-surface regression tests prevent message drift

**Given** one representative failure from each major category
**When** the test suite runs
**Then** the rendered guidance remains aligned across terminal, halt report, summary, and logs
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Introduce a shared render path (AC: #1)
  - [x] 1.1: Replace bespoke string assembly with a shared renderer or shared message contract.
  - [x] 1.2: Ensure the same render path can produce concise terminal text and richer artifact/log output.

- [x] Task 2: Centralize redaction (AC: #2)
  - [x] 2.1: Apply redaction in one shared location.
  - [x] 2.2: Verify all major failure surfaces consume the redacted form.

- [x] Task 3: Document troubleshooting guidance (AC: #3)
  - [x] 3.1: Add or update documentation with a Claude error troubleshooting matrix.
  - [x] 3.2: Distinguish local operator actions from Claude platform/account actions.

- [x] Task 4: Add cross-surface regression coverage and run quality gates (AC: #4)
  - [x] 4.1: Add tests proving guidance alignment across terminal, halt report, summary, and logs.
  - [x] 4.2: Run `ruff check src/ tests/`.
  - [x] 4.3: Run `mypy --strict src/`.
  - [x] 4.4: Run `pytest`.

## Dev Notes

### Scope Boundaries

- Do not introduce a second independent render path for Claude errors.
- Keep documentation implementation-focused and operator-actionable.
- Redaction rules must be applied before any message is emitted.

### Candidate Files

- `src/arcwright_ai/cli/halt.py`
- `src/arcwright_ai/engine/nodes.py`
- `src/arcwright_ai/output/summary.py`
- `README.md`
- `docs/validation-pipeline.md`
- `tests/test_cli/`
- `tests/test_engine/`
- `tests/test_output/`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Completion Notes

- **Task 1 (Shared render path):** Added `render_claude_guidance(classification, *, diagnostic_hint=None) -> str` to `core/errors.py` as the single authoritative renderer for all 10 error categories. `cli/halt.py` `_format_platform_guidance`, `_format_local_guidance`, `_format_transient_guidance` now delegate to it; `_suggested_fix_for_exception` and `_suggested_fix_for_graph_state` call it directly. `engine/nodes.py` `_derive_suggested_fix` extended from 3-category to full 10-category coverage via the same shared function.
- **Task 2 (Centralized redaction):** `_redact_secrets` exposed as public `redact_secrets` in `core/errors.py`. `render_claude_guidance` applies `_redact_secrets` to `diagnostic_hint` before inclusion. All three rendering surfaces (terminal, halt report, summary) consume redacted content through the shared function.
- **Task 3 (Documentation):** Created `docs/troubleshooting-claude-errors.md` with a full troubleshooting matrix covering all 4 categories (platform/account, local runtime/config, transient provider, unknown fallback), distinguishing local actions from Claude-platform actions.
- **Task 4 (Regression tests):** Added 21 new tests in `tests/test_core/test_errors.py`: `TestRenderClaudeGuidanceSharedRenderer` (13 tests), `TestRedactSecretsPublicAPI` (4 tests), `TestCrossSurfaceGuidanceAlignment` (4 tests). All 1116 tests pass; ruff and mypy --strict are clean.

### File List

- `_spec/implementation-artifacts/13-5-shared-error-rendering-redaction-and-troubleshooting-documentation.md`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `arcwright-ai/src/arcwright_ai/core/errors.py`
- `arcwright-ai/src/arcwright_ai/cli/halt.py`
- `arcwright-ai/src/arcwright_ai/engine/nodes.py`
- `arcwright-ai/tests/test_core/test_errors.py`
- `arcwright-ai/docs/troubleshooting-claude-errors.md`

## Change Log

- 2026-03-20: Implemented shared `render_claude_guidance` in `core/errors.py`; refactored `cli/halt.py` and `engine/nodes.py` to use shared renderer; added public `redact_secrets`; added `docs/troubleshooting-claude-errors.md`; added 21 cross-surface regression tests (1116 total passing).
- 2026-03-20: Code review completed with no HIGH/MEDIUM/LOW findings; verification passed (`ruff check src/ tests/`, `mypy --strict src/`, `pytest -q`, targeted cross-surface guidance tests). Story moved to `done`.