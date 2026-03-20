# Story 13.3: Terminal Guidance for Local Claude Runtime and Configuration Failures

Status: ready-for-dev

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

- [ ] Task 1: Add local runtime/configuration classifications (AC: #1)
  - [ ] 1.1: Classify missing binary, managed settings problems, and startup/config parse failures separately from platform-account failures.
  - [ ] 1.2: Preserve concise diagnostic context such as relevant filenames or paths.

- [ ] Task 2: Render local troubleshooting guidance (AC: #2, #3)
  - [ ] 2.1: Add terminal guidance for local Claude installation and configuration failures.
  - [ ] 2.2: Keep detailed stderr-derived context in halt reports and logs.

- [ ] Task 3: Add regression coverage and run quality gates (AC: #4)
  - [ ] 3.1: Add tests for missing CLI, broken managed settings, and generic startup/config failures.
  - [ ] 3.2: Run `ruff check src/ tests/`.
  - [ ] 3.3: Run `mypy --strict src/`.
  - [ ] 3.4: Run `pytest`.

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

GPT-5.4

### Completion Notes

- Story created to cover local Claude setup/runtime error UX separately from Claude platform failures.

### File List

- `_spec/implementation-artifacts/13-3-terminal-guidance-for-local-claude-runtime-and-configuration-failures.md`
- `_spec/implementation-artifacts/sprint-status.yaml`
- `_spec/planning-artifacts/epics.md`