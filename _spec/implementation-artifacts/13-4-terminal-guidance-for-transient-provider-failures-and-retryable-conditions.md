# Story 13.4: Terminal Guidance for Transient Provider Failures and Retryable Conditions

Status: ready-for-dev

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As an operator running Arcwright AI over longer sessions,
I want transient Claude/provider failures to be identified as retryable conditions with appropriate guidance,
So that I know when to retry later versus when to fix configuration or account issues.

## Acceptance Criteria (BDD)

### AC 1: Retryable provider failures are surfaced as transient issues

**Given** Arcwright AI encounters rate limiting, network interruption, provider timeout, or similar transient Claude/provider failure
**When** the CLI renders the failure
**Then** the terminal output identifies it as a retryable/transient Claude issue.

### AC 2: Guidance matches the transient failure type

**Given** a transient Claude/provider failure is classified
**When** operator guidance is rendered
**Then** rate-limit failures instruct the user to wait and retry
**And** timeout/network failures instruct the user to retry after checking connectivity or provider status.

### AC 3: Retryability is available programmatically

**Given** a transient failure classification exists
**When** engine or CLI code consumes it
**Then** retryability is exposed as structured metadata rather than inferred from free-form strings.

### AC 4: Regression tests cover transient and unknown fallback behavior

**Given** classified `rate_limit_error`, `network_error`, `timeout_error`, and `unknown_sdk_error` samples
**When** the test suite runs
**Then** the terminal output and classification behavior match the expected guidance
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [ ] Task 1: Add transient failure classifications (AC: #1, #3)
  - [ ] 1.1: Add or refine rate-limit, network, timeout, and unknown-fallback mappings.
  - [ ] 1.2: Ensure retryability metadata is preserved for downstream consumers.

- [ ] Task 2: Render transient guidance in the CLI (AC: #1, #2)
  - [ ] 2.1: Add concise transient/retry-later terminal messages.
  - [ ] 2.2: Keep local config and platform-account advice out of transient cases.

- [ ] Task 3: Add regression coverage and run quality gates (AC: #4)
  - [ ] 3.1: Add tests for rate-limit, network, timeout, and unknown fallback rendering.
  - [ ] 3.2: Run `ruff check src/ tests/`.
  - [ ] 3.3: Run `mypy --strict src/`.
  - [ ] 3.4: Run `pytest`.

## Dev Notes

### Scope Boundaries

- Do not change the engine retry loop itself in this story.
- Unknown failures must still be rendered even when no explicit transient category matches.
- Reuse the shared taxonomy from Story 13.1.

### Candidate Files

- `src/arcwright_ai/agent/invoker.py`
- `src/arcwright_ai/cli/halt.py`
- `src/arcwright_ai/engine/nodes.py`
- `tests/test_agent/test_invoker.py`
- `tests/test_cli/`

## Dev Agent Record

### Agent Model Used

GPT-5.4

### Completion Notes

- Story created for retryable/transient Claude failure guidance and structured retryability metadata.

### File List

- `_spec/implementation-artifacts/13-4-terminal-guidance-for-transient-provider-failures-and-retryable-conditions.md`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/planning-artifacts/epics.md`