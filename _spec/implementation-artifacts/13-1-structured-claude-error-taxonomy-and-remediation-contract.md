# Story 13.1: Structured Claude Error Taxonomy and Remediation Contract

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a maintainer of Arcwright AI,
I want Claude SDK and Claude CLI failures to map into a structured taxonomy with operator guidance metadata,
So that downstream terminal, halt, and summary surfaces can render clear, consistent, and secret-safe remediation steps for each error family.

## Acceptance Criteria (BDD)

### AC 1: Structured taxonomy exists for Claude-related failures

**Given** the agent invoker captures Claude subprocess stderr or SDK exceptions
**When** the failure is classified
**Then** the result includes a stable error code, user-facing title, concise terminal summary, retryability flag, and ordered remediation steps.

### AC 2: Platform and local runtime issues are distinct categories

**Given** Arcwright AI classifies Claude-related failures
**When** the taxonomy is inspected
**Then** it includes at minimum `billing_error`, `auth_error`, `model_access_error`, `local_config_error`, `managed_settings_error`, `cli_missing_error`, `network_error`, `rate_limit_error`, `timeout_error`, and `unknown_sdk_error`
**And** platform/account failures are distinct from local runtime/configuration failures.

### AC 3: Secret-safe rendering contract

**Given** the classification metadata is used by terminal or artifact renderers
**When** guidance is generated
**Then** raw API keys, bearer tokens, and other credential values are never included in user-facing output.

### AC 4: Classification tests cover supported categories

**Given** representative stderr/process-error samples for each category
**When** the unit tests run
**Then** each sample maps to the expected structured category
**And** unknown samples fall back to `unknown_sdk_error`
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Define the shared Claude error contract (AC: #1, #2)
  - [x] 1.1: Choose a shared model or typed mapping for Claude error code, title, summary, retryability, and remediation steps.
  - [x] 1.2: Ensure the contract can be consumed by CLI, engine, and output layers without ad hoc string parsing.

- [x] Task 2: Expand classification coverage in the invoker (AC: #1, #2)
  - [x] 2.1: Add explicit mappings for platform, local runtime/configuration, transient, and unknown failures.
  - [x] 2.2: Preserve stderr summaries for diagnostics while keeping the user-facing contract concise.

- [x] Task 3: Enforce secret-safe guidance (AC: #3)
  - [x] 3.1: Verify raw credentials are redacted before any guidance object is rendered.
  - [x] 3.2: Confirm unknown fallback paths also respect redaction.

- [x] Task 4: Add unit coverage and run quality gates (AC: #4)
  - [x] 4.1: Add representative classification tests for each supported category and fallback.
  - [x] 4.2: Run `ruff check src/ tests/`.
  - [x] 4.3: Run `mypy --strict src/`.
  - [x] 4.4: Run `pytest`.

## Dev Notes

### Scope Boundaries

- Do not change retry policy behavior in this story.
- Do not remove raw stderr capture from logs; wrap it in a safer shared contract.
- Keep the taxonomy extensible so new Claude failure modes can be added without rewriting all renderers.

### Candidate Files

- `src/arcwright_ai/agent/invoker.py`
- `src/arcwright_ai/core/errors.py`
- `src/arcwright_ai/core/types.py`
- `tests/test_agent/test_invoker.py`

## Dev Agent Record

### Agent Model Used

Claude Opus 4.6

### Completion Notes

- Created `core/errors.py` with `ClaudeErrorCategory` (StrEnum), `ClaudeErrorClassification` (frozen Pydantic model), and `CLAUDE_ERROR_REGISTRY` (static mapping with 10 categories).
- Implemented `classify_claude_error()` public classifier with ordered regex chain, fallback to `unknown_sdk_error`, and credential redaction via `_redact_secrets()`.
- Refactored `agent/invoker.py` to delegate `_classify_sdk_failure()` to the shared taxonomy, eliminating duplicated regex patterns and ad hoc tuple returns.
- Updated `_enrich_error_with_stderr` and `_wrap_sdk_error` to populate `details["classification"]` with the full `ClaudeErrorClassification` object.
- Exported new types from `core/__init__.py`.
- Added 27 unit tests covering all 10 categories, registry structure, frozen model, secret-safe rendering, and credential redaction.
- All quality gates pass: `ruff check` clean, `mypy --strict` clean, 1056 pytest tests passing with zero regressions.

### File List

- `arcwright-ai/src/arcwright_ai/core/errors.py` (new — taxonomy, registry, classifier)
- `arcwright-ai/src/arcwright_ai/core/__init__.py` (modified — export new types)
- `arcwright-ai/src/arcwright_ai/agent/invoker.py` (modified — delegate to shared contract)
- `arcwright-ai/tests/test_core/test_errors.py` (new — 27 taxonomy tests)
- `arcwright-ai/tests/test_agent/test_invoker.py` (modified — updated assertions for new summaries)
- `_spec/implementation-artifacts/sprint-status.yaml` (modified — story status)
- `_spec/implementation-artifacts/13-1-structured-claude-error-taxonomy-and-remediation-contract.md` (modified — story file)

### Out-of-Scope Carryover Working-Tree Changes (Observed During CR)

- `.gitignore` (modified outside Story 13.1 scope)
- `_spec/planning-artifacts/epics.md` (modified outside Story 13.1 scope)
- `_spec/implementation-artifacts/13-2-terminal-guidance-for-claude-platform-account-and-access-failures.md` (new, not part of 13.1 implementation)
- `_spec/implementation-artifacts/13-3-terminal-guidance-for-local-claude-runtime-and-configuration-failures.md` (new, not part of 13.1 implementation)
- `_spec/implementation-artifacts/13-4-terminal-guidance-for-transient-provider-failures-and-retryable-conditions.md` (new, not part of 13.1 implementation)
- `_spec/implementation-artifacts/13-5-shared-error-rendering-redaction-and-troubleshooting-documentation.md` (new, not part of 13.1 implementation)

## Change Log

- 2026-03-20: Implemented structured Claude error taxonomy and remediation contract. Created `core/errors.py` with 10-category taxonomy, refactored invoker to use shared contract, added 27 tests, all quality gates passing.
- 2026-03-20: CR remediation applied. `_wrap_sdk_error()` now always records taxonomy metadata (including `unknown_sdk_error`) and no longer appends raw `stderr` to user-facing messages; added regression test to verify unknown-category metadata and credential-safe rendering.