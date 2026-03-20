# Story 13.2: Terminal Guidance for Claude Platform Account and Access Failures

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer running dispatch or validation,
I want billing, API-key, and model-access failures from the Claude platform to be surfaced directly in the terminal with explicit next steps,
So that I immediately know to check Claude configuration, API key validity, payment status, and model entitlements instead of chasing unrelated project issues.

## Acceptance Criteria (BDD)

### AC 1: Billing failures are labeled as Claude platform issues

**Given** Arcwright AI encounters a Claude billing or low-credit failure
**When** the CLI renders the failure
**Then** the terminal output clearly states that this is a Claude platform issue
**And** it instructs the operator to verify available credits or payment details with the Claude platform.

### AC 2: Authentication and model-access failures provide targeted remediation

**Given** Arcwright AI encounters an API-key/authentication or model-access failure
**When** the CLI renders the failure
**Then** authentication guidance instructs the operator to verify the configured API key or auth mechanism used by Arcwright AI
**And** model-access guidance instructs the operator to verify entitlement/access for the configured Claude model.

### AC 3: Platform guidance is consistent across failure surfaces

**Given** a platform-account failure occurs during dispatch or validation
**When** Arcwright AI writes terminal output, halt report, and summary content
**Then** the same classified operator guidance appears across surfaces
**And** logs retain the underlying diagnostic detail needed for debugging.

### AC 4: Regression tests cover platform failure rendering

**Given** classified `billing_error`, `auth_error`, and `model_access_error` failures
**When** the test suite runs
**Then** terminal output matches the expected operator guidance without exposing secrets
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Render platform-account failures in the CLI (AC: #1, #2)
  - [x] 1.1: Add terminal-facing messages for billing, auth, and model-access failures.
  - [x] 1.2: Ensure the language explicitly says the issue is with Claude platform/account access rather than story code.

- [x] Task 2: Propagate platform guidance into run artifacts (AC: #3)
  - [x] 2.1: Preserve the same classified guidance in halt reports and summaries.
  - [x] 2.2: Keep raw diagnostics available in logs for debugging.

- [x] Task 3: Add regression coverage and run quality gates (AC: #4)
  - [x] 3.1: Add tests for billing, auth, and model-access terminal messages.
  - [x] 3.2: Add artifact propagation tests if needed.
  - [x] 3.3: Run `ruff check src/ tests/`.
  - [x] 3.4: Run `mypy --strict src/`.
  - [x] 3.5: Run `pytest`.

## Dev Notes

### Scope Boundaries

- Do not expose raw API key values or token substrings in any rendered output.
- Do not treat platform-account failures as local Claude installation issues.
- Preserve current non-zero exit and halt semantics.

### Candidate Files

- `src/arcwright_ai/cli/halt.py`
- `src/arcwright_ai/cli/dispatch.py`
- `src/arcwright_ai/engine/nodes.py`
- `tests/test_cli/`
- `tests/test_engine/test_nodes.py`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Completion Notes

- Story created to capture explicit terminal UX for Claude platform/account failures.
- Task 1 (exception path): `HaltController` in `halt.py` extended with `_PLATFORM_ACCOUNT_CATEGORIES`, `_extract_platform_classification()`, and `_format_platform_guidance()`. Both `_suggested_fix_for_exception()` and `_emit_halt_summary()` (via `handle_halt`) use platform guidance when classification is available.
- Task 2 (graph-ESCALATED path): `StoryState` extended with `failure_category: str | None`. `agent_dispatch_node` now extracts and stores `failure_category` from the caught exception's details. `_derive_suggested_fix()` in `nodes.py` and `_suggested_fix_for_graph_state()` in `halt.py` check this field and return structured platform guidance. `handle_graph_halt` derives `operator_guidance` from `story_state.failure_category` and passes it to `_emit_halt_summary`.
- Task 3: 11 new tests in `test_halt.py` covering billing/auth/model_access terminal output and halt report consistency. All 1068 tests pass; `ruff check` and `mypy --strict` clean.

### File List

- `src/arcwright_ai/cli/halt.py`
- `src/arcwright_ai/engine/nodes.py`
- `src/arcwright_ai/engine/state.py`
- `tests/test_cli/test_halt.py`
- `_spec/implementation-artifacts/13-2-terminal-guidance-for-claude-platform-account-and-access-failures.md`
- `_spec/implementation-artifacts/sprint-status.yaml`