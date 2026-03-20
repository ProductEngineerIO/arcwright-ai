# Story 13.5: Shared Error Rendering, Redaction, and Troubleshooting Documentation

Status: ready-for-dev

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

- [ ] Task 1: Introduce a shared render path (AC: #1)
  - [ ] 1.1: Replace bespoke string assembly with a shared renderer or shared message contract.
  - [ ] 1.2: Ensure the same render path can produce concise terminal text and richer artifact/log output.

- [ ] Task 2: Centralize redaction (AC: #2)
  - [ ] 2.1: Apply redaction in one shared location.
  - [ ] 2.2: Verify all major failure surfaces consume the redacted form.

- [ ] Task 3: Document troubleshooting guidance (AC: #3)
  - [ ] 3.1: Add or update documentation with a Claude error troubleshooting matrix.
  - [ ] 3.2: Distinguish local operator actions from Claude platform/account actions.

- [ ] Task 4: Add cross-surface regression coverage and run quality gates (AC: #4)
  - [ ] 4.1: Add tests proving guidance alignment across terminal, halt report, summary, and logs.
  - [ ] 4.2: Run `ruff check src/ tests/`.
  - [ ] 4.3: Run `mypy --strict src/`.
  - [ ] 4.4: Run `pytest`.

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

GPT-5.4

### Completion Notes

- Story created to lock down shared rendering, redaction, documentation, and regression coverage for Epic 13.

### File List

- `_spec/implementation-artifacts/13-5-shared-error-rendering-redaction-and-troubleshooting-documentation.md`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/planning-artifacts/epics.md`