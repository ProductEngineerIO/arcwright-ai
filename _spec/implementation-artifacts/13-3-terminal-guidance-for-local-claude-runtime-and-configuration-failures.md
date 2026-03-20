# Story 13.3: Terminal Guidance for Local Claude Runtime and Configuration Failures

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer using Arcwright AI locally,
I want local Claude installation and configuration problems to be surfaced as local runtime issues with targeted troubleshooting hints,
So that I can distinguish missing CLI/configuration problems from Claude platform account failures.

## Acceptance Criteria (BDD)

### AC 1: Local runtime/configuration failures are labeled correctly

**Given** Arcwright AI encounters a local Claude runtime/configuration failure such as missing `claude` binary, broken managed settings reference, unreadable settings file, or startup configuration error
**When** the CLI renders the failure
**Then** the terminal output explicitly labels it as a local Claude setup issue.

### AC 2: Local guidance includes the relevant troubleshooting hint

**Given** a file path or configuration target is known for the failure
**When** guidance is rendered
**Then** the terminal output includes the relevant path or filename in a concise diagnostic note
**And** it tells the operator to inspect the local Claude installation/configuration rather than billing or API credits.

### AC 3: Detailed diagnostics remain available outside the terminal summary

**Given** a local setup failure is classified
**When** halt reports and logs are written
**Then** the detailed stderr-derived diagnostic remains available for debugging
**And** the terminal output stays concise and readable.

### AC 4: Regression tests cover key local setup failures

**Given** representative local runtime/configuration failures
**When** the test suite runs
**Then** there is coverage for missing CLI executable, broken managed settings path, and generic startup/config parse failure
**And** `ruff check`, `mypy --strict`, and `pytest` pass with zero regressions.

## Tasks / Subtasks

- [x] Task 1: Add local runtime/configuration classifications (AC: #1)
  - [x] 1.1: Classify missing binary, managed settings problems, and startup/config parse failures separately from platform-account failures.
  - [x] 1.2: Preserve concise diagnostic context such as relevant filenames or paths.

- [x] Task 2: Render local troubleshooting guidance (AC: #2, #3)
  - [x] 2.1: Add terminal guidance for local Claude installation and configuration failures.
  - [x] 2.2: Keep detailed stderr-derived context in halt reports and logs.

- [x] Task 3: Add regression coverage and run quality gates (AC: #4)
  - [x] 3.1: Add tests for missing CLI, broken managed settings, and generic startup/config failures.
  - [x] 3.2: Run `ruff check src/ tests/`.
  - [x] 3.3: Run `mypy --strict src/`.
  - [x] 3.4: Run `pytest`.

## Dev Notes

### Scope Boundaries

- Do not display platform-account remediation steps for local configuration failures.
- Keep terminal messages concise; detailed stderr belongs in logs and halt artifacts.
- Reuse the shared classification contract from Story 13.1 rather than inventing a parallel path.

### Candidate Files

- `src/arcwright_ai/agent/invoker.py`
- `src/arcwright_ai/cli/halt.py`
- `src/arcwright_ai/engine/nodes.py`
- `tests/test_agent/test_invoker.py`
- `tests/test_cli/`
- `tests/test_engine/test_nodes.py`

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6

### Completion Notes

- Added `_LOCAL_RUNTIME_CATEGORIES` frozenset (`CLI_MISSING_ERROR`, `LOCAL_CONFIG_ERROR`, `MANAGED_SETTINGS_ERROR`) and `_PATH_HINT_RE` regex to `halt.py`, following the same module-level constant pattern used for `_PLATFORM_ACCOUNT_CATEGORIES` in Story 13.2.
- Added three static methods to `HaltController`:
  - `_extract_local_classification()` — mirrors `_extract_platform_classification()` but checks `_LOCAL_RUNTIME_CATEGORIES`.
  - `_extract_local_diagnostic_hint()` — scans `details["captured_stderr"]` for a plausible file path using `_PATH_HINT_RE`, returning it for use as a concise "Inspect: <path>" note in guidance output (AC #2).
  - `_format_local_guidance()` — formats operator guidance that explicitly labels the failure as a local Claude setup issue (AC #1), includes optional `diagnostic_hint` path (AC #2), and lists ordered remediation steps.
- Updated `_suggested_fix_for_exception()` to check for local classification after the existing platform check; generates structured "Local Claude Setup Issue" output with optional path hint.
- Updated `_suggested_fix_for_graph_state()` to add an `elif category in _LOCAL_RUNTIME_CATEGORIES` branch after the existing platform branch.
- Updated `handle_halt()` to check `_extract_local_classification()` when no platform classification is found, passing `diagnostic_hint` to `_format_local_guidance()` for the `operator_guidance` passed to `_emit_halt_summary()`.
- Updated `handle_graph_halt()` to add an `elif _graph_category in _LOCAL_RUNTIME_CATEGORIES` branch in the `failure_category` dispatch block.
- Added 12 regression tests in `tests/test_cli/test_halt.py` covering: `cli_missing_error`, `managed_settings_error`, and `local_config_error` cases for suggested fix content, terminal output, and halt-report consistency. Path-hint extraction and secret-safe rendering verified.
- All quality gates pass: `ruff check` clean, `mypy --strict` clean (43 files), 1080 pytest tests passing with zero regressions.

### File List

- `arcwright-ai/src/arcwright_ai/cli/halt.py`
- `arcwright-ai/tests/test_cli/test_halt.py`
- `_spec/implementation-artifacts/13-3-terminal-guidance-for-local-claude-runtime-and-configuration-failures.md`
- `_spec/implementation-artifacts/sprint-status.yaml`

## Change Log

- 2026-03-20: Implemented local Claude runtime/configuration terminal guidance. Added `_LOCAL_RUNTIME_CATEGORIES`, `_extract_local_classification()`, `_extract_local_diagnostic_hint()`, and `_format_local_guidance()` to `HaltController`. Wired into both `handle_halt()` and `handle_graph_halt()`. Added 12 regression tests. All quality gates passing (ruff clean, mypy clean, 1080 pytest tests passing).
- 2026-03-20: Code review completed with no HIGH/MEDIUM/LOW findings; targeted validation rerun passed (`pytest -q tests/test_cli/test_halt.py -k "LocalRuntime or local_"`, `ruff check src/arcwright_ai/cli/halt.py tests/test_cli/test_halt.py`, `mypy --strict src/arcwright_ai/cli/halt.py`). Story moved to `done`.