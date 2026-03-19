# Story 10.9: CLI Version Command

Status: ready-for-dev

## Story

As a user of Arcwright AI,
I want to check which version I'm running from the command line,
So that I can quickly verify my installed version for debugging, support, and compatibility purposes.

## Acceptance Criteria (BDD)

1. **Given** the CLI is installed **When** the user runs `arcwright-ai version` **Then** the installed package version is printed to stdout (e.g., `arcwright-ai 0.2.0`) and the process exits with code 0

2. **Given** the CLI is installed **When** the user runs `arcwright-ai --version` **Then** the same version string is printed to stdout and the process exits with code 0, without invoking any subcommand

3. **Given** the package is installed in editable mode without a git tag **When** the user runs `arcwright-ai version` or `arcwright-ai --version` **Then** the fallback version `0.0.0.dev0` is displayed (consistent with the existing `__version__` fallback from Story 10.1)

4. **Given** the version command exists **When** `arcwright-ai --help` is inspected **Then** `version` appears in the command list with a brief description, and `--version` appears as a top-level option

5. **Given** the implementation is complete **When** `ruff check src/ tests/` and `mypy --strict src/` are run **Then** zero violations and zero type errors

6. **Given** the implementation is complete **When** `pytest` is run **Then** all existing tests pass with no regressions and new tests cover the version command and `--version` flag

## Tasks / Subtasks

- [ ] Task 1: Add `--version` callback to the Typer app (AC: #2, #4)
  - [ ] 1.1: Add a `version_callback` function in `cli/app.py` that prints the version and raises `typer.Exit()`
  - [ ] 1.2: Add `--version` option to the `app.callback()` using `typer.Option(None, "--version", callback=version_callback, is_eager=True)`

- [ ] Task 2: Add `version` subcommand (AC: #1, #3, #4)
  - [ ] 2.1: Create `version_command()` function (either in `cli/app.py` or a new `cli/version.py` — prefer `app.py` for simplicity since it's a one-liner)
  - [ ] 2.2: Register with `app.command(name="version")(version_command)`

- [ ] Task 3: Tests (AC: #5, #6)
  - [ ] 3.1: Test `arcwright-ai version` outputs version string and exits 0
  - [ ] 3.2: Test `arcwright-ai --version` outputs version string and exits 0
  - [ ] 3.3: Verify version string matches `arcwright_ai.__version__`

- [ ] Task 4: Validation (AC: #5, #6)
  - [ ] 4.1: Run `ruff check src/ tests/` — zero violations
  - [ ] 4.2: Run `mypy --strict src/` — zero errors
  - [ ] 4.3: Run `pytest` — all tests pass

## Dev Notes

**Design rationale:**
- Both `arcwright-ai version` (subcommand) and `arcwright-ai --version` (flag) are supported — this matches the convention used by tools like `docker`, `git`, `uv`, and `ruff`
- The version string is sourced from `arcwright_ai.__version__`, which is already resolved dynamically via `importlib.metadata` (Story 10.1)
- No new dependencies required
- Typer's `is_eager=True` ensures `--version` is processed before any subcommand resolution

**Output format:**
```
arcwright-ai X.Y.Z
```

## File List

- `arcwright-ai/src/arcwright_ai/cli/app.py` — Add `--version` callback to app and `version` subcommand
- `arcwright-ai/tests/test_cli/` — Tests for version command and `--version` flag

## Change Log

| Date | Change | Author |
|------|--------|--------|
| 2026-03-18 | Story created | BMad Master (AI) |
