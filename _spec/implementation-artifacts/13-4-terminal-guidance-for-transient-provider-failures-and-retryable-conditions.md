# Story 13.4: Terminal Guidance for Transient Provider Failures and Retryable Conditions

Status: done

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

- [x] Task 1: Add transient failure classifications (AC: #1, #3)
  - [x] 1.1: Add or refine rate-limit, network, timeout, and unknown-fallback mappings.
  - [x] 1.2: Ensure retryability metadata is preserved for downstream consumers.

- [x] Task 2: Render transient guidance in the CLI (AC: #1, #2)
  - [x] 2.1: Add concise transient/retry-later terminal messages.
  - [x] 2.2: Keep local config and platform-account advice out of transient cases.

- [x] Task 3: Add regression coverage and run quality gates (AC: #4)
  - [x] 3.1: Add tests for rate-limit, network, timeout, and unknown fallback rendering.
  - [x] 3.2: Run `ruff check src/ tests/`.
  - [x] 3.3: Run `mypy --strict src/`.
  - [x] 3.4: Run `pytest`.

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

Claude Sonnet 4.6

### Completion Notes

- Added `_TRANSIENT_CATEGORIES` frozenset (`RATE_LIMIT_ERROR`, `NETWORK_ERROR`, `TIMEOUT_ERROR`, `UNKNOWN_SDK_ERROR`) to `halt.py`, following the same module-level constant pattern used for `_PLATFORM_ACCOUNT_CATEGORIES` and `_LOCAL_RUNTIME_CATEGORIES`.
- Added two static methods to `HaltController`:
  - `_extract_transient_classification()` — mirrors `_extract_platform_classification()` and `_extract_local_classification()` but checks against `_TRANSIENT_CATEGORIES`.
  - `_format_transient_guidance()` — formats operator guidance that labels retryable failures (rate-limit, network, timeout) as transient/retryable provider issues with retry prompts (AC #1, #2). The unknown SDK fallback (`retryable=False`) is rendered as an unrecognised error without the transient label (AC #4 scope boundary). Retryability is exposed structurally via the `ClaudeErrorClassification.retryable` field already present in the taxonomy from Story 13.1 (AC #3).
- Updated `_suggested_fix_for_exception()` to check for transient classification after the existing local check.
- Updated `_suggested_fix_for_graph_state()` to add an `elif category in _TRANSIENT_CATEGORIES` branch after the existing local branch.
- Updated `handle_halt()` guidance chain to check `_extract_transient_classification()` when neither platform nor local classification is found.
- Updated `handle_graph_halt()` to add an `elif _graph_category in _TRANSIENT_CATEGORIES` branch.
- Added 15 regression tests in `tests/test_cli/test_halt.py` (3 test classes): `TestTransientSuggestedFix` (8 tests), `TestTransientTerminalOutput` (5 tests), `TestTransientGuidanceConsistency` (2 tests). All verify scope separation — transient output never references platform-account or local-setup language.
- All quality gates pass: `ruff check` clean, `mypy --strict` clean (43 files), 1095 pytest tests passing with zero regressions (+15 new).

### File List

- `arcwright-ai/src/arcwright_ai/cli/halt.py` (modified — added `_TRANSIENT_CATEGORIES`, `_extract_transient_classification()`, `_format_transient_guidance()`; wired into both halt handlers and suggested-fix helpers)
- `arcwright-ai/tests/test_cli/test_halt.py` (modified — 15 new Story 13.4 regression tests)
- `_spec/implementation-artifacts/13-4-terminal-guidance-for-transient-provider-failures-and-retryable-conditions.md` (modified — story file)
- `_spec/implementation-artifacts/sprint-status.yaml` (modified — story status)

## Change Log

- 2026-03-20: Implemented transient provider failure terminal guidance. Added `_TRANSIENT_CATEGORIES`, `_extract_transient_classification()`, and `_format_transient_guidance()` to `HaltController`. Wired into both `handle_halt()` and `handle_graph_halt()` and both suggested-fix helpers. Added 15 regression tests. All quality gates passing (ruff clean, mypy clean, 1095 pytest tests passing).