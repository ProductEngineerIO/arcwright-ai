# Story 1.5: CLI Validate-Setup Command

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer about to dispatch my first run,
I want to run `arcwright-ai validate-setup` to verify my configuration, API key, and project structure with clear pass/fail per check,
so that I catch configuration problems before they become mid-run failures.

## Acceptance Criteria (BDD)

1. **Given** an initialized Arcwright AI project **When** I run `arcwright-ai validate-setup` **Then** the command checks and reports pass/fail for each: (1) Claude API key present and non-empty, (2) BMAD project structure detected at configured artifacts path, (3) planning artifacts found (PRD, architecture, epics), (4) story artifacts found with acceptance criteria, (5) Arcwright AI config valid per schema.

2. **Given** a check fails **When** the result is displayed **Then** each failed check includes a specific fix instruction (e.g., "Expected: `./_spec/` — check config.yaml → methodology.artifacts_path").

3. **Given** a critical check fails (API key or project structure) **When** subsequent dependent checks are evaluated **Then** they are skipped with a "Cannot validate — requires [failed check]" message instead of running.

4. **Given** all checks pass **When** the exit code is inspected **Then** exit code is 0.

5. **Given** any critical check fails **When** the exit code is inspected **Then** exit code is 3 (`EXIT_CONFIG`).

6. **Given** `arcwright-ai validate-setup` runs **When** the output is inspected **Then** output uses Rich/Typer formatting to stderr per D8.

7. **Given** unit tests for the validate-setup command **When** `pytest tests/test_cli/test_validate_setup.py` is run **Then** all tests pass, covering: all-pass scenario, missing API key, wrong artifacts path, missing planning artifacts, invalid config, dependent check skipping.

8. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

9. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

10. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement `validate_setup_command` and helper functions in `cli/status.py` (AC: #1, #2, #3, #6, #10)
  - [x] 1.1: Import required modules: `os` from stdlib; `typer`, `Path`; constants from `core.constants` (`CONFIG_FILENAME`, `DIR_ARCWRIGHT`, `DIR_SPEC`, `ENV_API_CLAUDE_API_KEY`, `EXIT_CONFIG`, `EXIT_SUCCESS`, `GLOBAL_CONFIG_DIR`); `load_yaml` from `core.io`; `load_config` from `core.config`; `ConfigError` from `core.exceptions`
  - [x] 1.2: Implement `_check_api_key() -> tuple[bool, str]` — checks `os.environ.get(ENV_API_CLAUDE_API_KEY)` first; if not set, loads `~/.arcwright-ai/config.yaml` via `load_yaml()` and checks `data.get("api", {}).get("claude_api_key", "")`. Returns `(True, "present (env)" | "present (global config)")` on success, `(False, "NOT FOUND\n   Fix: Set ARCWRIGHT_API_CLAUDE_API_KEY environment variable or add claude_api_key to ~/.arcwright-ai/config.yaml")` on failure.
  - [x] 1.3: Implement `_check_project_structure(project_root: Path, artifacts_path: str) -> tuple[bool, str]` — resolves `project_root / artifacts_path` to check if the BMAD artifacts directory exists. Returns `(True, f"detected at ./{artifacts_path}/")` on success, `(False, f"NOT FOUND at ./{artifacts_path}/\n   Expected: ./{artifacts_path}/ — check config.yaml → methodology.artifacts_path\n   Fix: Update .arcwright-ai/config.yaml artifacts_path or move artifacts to ./{artifacts_path}/")` on failure.
  - [x] 1.4: Implement `_check_planning_artifacts(project_root: Path, artifacts_path: str) -> tuple[bool, str]` — scans `project_root / artifacts_path / "planning-artifacts"` using glob patterns `*prd*`, `*architecture*`, `*epic*` (same patterns as `_detect_bmad_artifacts` from init). Returns `(True, "PRD, architecture, epics found")` listing found artifacts, `(False, "Missing: [list of missing]\n   Fix: Create missing planning artifacts in {artifacts_path}/planning-artifacts/")` with specifics on what's missing.
  - [x] 1.5: Implement `_check_story_artifacts(project_root: Path, artifacts_path: str) -> tuple[bool, str]` — scans `project_root / artifacts_path / "implementation-artifacts"` for story `.md` files (names starting with a digit). For each found story, does a basic check that it contains "Acceptance Criteria" text. Returns `(True, f"{count} stories with acceptance criteria")` on success, `(False, "No story artifacts found\n   Fix: Create stories in {artifacts_path}/implementation-artifacts/")` if none found, or a warning listing stories missing acceptance criteria.
  - [x] 1.6: Implement `_check_config_valid(project_root: Path) -> tuple[bool, str]` — wraps `load_config(project_root)` in try/except `ConfigError`. Returns `(True, "valid")` on success, `(False, f"INVALID: {error.message}\n   Fix: {error.details.get('fix', 'Check .arcwright-ai/config.yaml')}")` on failure.
  - [x] 1.7: Implement `validate_setup_command(path: str = typer.Option(".", "--path", "-p", help="Project root directory")) -> None` composing all checks. Uses `_resolve_artifacts_path(project_root)` to determine the artifacts path from project config or default `"_spec"`. Executes checks in order, tracks critical failures, skips dependent checks when critical checks fail. Outputs results to stderr via `typer.echo(..., err=True)`. Exit 0 if all pass, exit 3 (`EXIT_CONFIG`) if any fail.
  - [x] 1.8: Implement `_resolve_artifacts_path(project_root: Path) -> str` — reads `.arcwright-ai/config.yaml` from project root (if exists) to get `methodology.artifacts_path`, falling back to `"_spec"` default. Uses `load_yaml()` with try/except (config may be malformed). Does NOT use `load_config()` since that requires API key.

- [x] Task 2: Register the `validate-setup` command on the CLI app (AC: #4, #5)
  - [x] 2.1: In `cli/app.py`, import `validate_setup_command` from `cli.status` and register via `app.command(name="validate-setup")(validate_setup_command)`.
  - [x] 2.2: Ensure `arcwright-ai --help` lists the `validate-setup` command.
  - [x] 2.3: Update `__all__` in `cli/status.py` to include `"validate_setup_command"` (alphabetical order per RUF022).

- [x] Task 3: Write unit tests in `tests/test_cli/test_validate_setup.py` (AC: #7)
  - [x] 3.1: Create `tests/test_cli/test_validate_setup.py` with fixtures:
    - `valid_project(tmp_path)` — fully initialized project with `.arcwright-ai/config.yaml`, `_spec/planning-artifacts/` containing `prd.md`, `architecture.md`, `epics.md`, and `_spec/implementation-artifacts/` with at least one story file containing "Acceptance Criteria"
    - `mock_api_key(monkeypatch)` — sets `ARCWRIGHT_API_CLAUDE_API_KEY` env var to `"sk-ant-test-key"`
  - [x] 3.2: Test `test_validate_setup_all_pass` — fully valid project + API key env var → exit code 0, output contains "✅" for each check
  - [x] 3.3: Test `test_validate_setup_missing_api_key` — valid project, no API key env var, no global config → output contains "❌" and "Claude API key", exit code 3
  - [x] 3.4: Test `test_validate_setup_wrong_artifacts_path` — project config has `methodology.artifacts_path: "wrong-dir"`, `wrong-dir/` does not exist → output shows "NOT FOUND", exit code 3
  - [x] 3.5: Test `test_validate_setup_missing_planning_artifacts` — `_spec/planning-artifacts/` exists but is empty → output shows "Missing" with specific file types, exit code 3
  - [x] 3.6: Test `test_validate_setup_missing_story_artifacts` — planning artifacts exist but `_spec/implementation-artifacts/` is empty → output reports no stories found
  - [x] 3.7: Test `test_validate_setup_invalid_config` — malformed `config.yaml` (e.g., `limits.tokens_per_story: "not-a-number"`) → config check fails with specific error
  - [x] 3.8: Test `test_validate_setup_dependent_check_skipping_api` — no API key → check 5 (config valid) shows "Cannot validate" skip message since full config validation requires API key
  - [x] 3.9: Test `test_validate_setup_dependent_check_skipping_structure` — artifacts path does not exist → checks 3 and 4 (planning/story artifacts) show "Cannot validate — requires BMAD project structure" skip message
  - [x] 3.10: Test `test_validate_setup_exit_code_three_on_failure` — any failing check → `result.exit_code == 3`
  - [x] 3.11: Test `test_validate_setup_help_lists_path_option` — `validate-setup --help` shows `--path`/`-p`
  - [x] 3.12: Test `test_root_help_lists_validate_setup_command` — CLI root `--help` includes `validate-setup`
  - [x] 3.13: Test `test_validate_setup_uninitialized_project` — no `.arcwright-ai/` directory → config check reports the issue, artifacts still checked at default path

- [x] Task 4: Validate all quality gates (AC: #8, #9)
  - [x] 4.1: Run `ruff check .` — zero violations
  - [x] 4.2: Run `ruff format --check .` — no formatting diffs
  - [x] 4.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 4.4: Run `pytest tests/test_cli/test_validate_setup.py -v` — all tests pass
  - [x] 4.5: Run full test suite `pytest` — all tests pass (no regressions from 157 existing tests)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `cli/` Depends on `core/` Only
```
cli → engine → {validation, agent, context, output, scm} → core
```
The `validate-setup` command in `cli/status.py` can import from `core/` only: `core.constants`, `core.config` (`load_config`), `core.io` (`load_yaml`), `core.exceptions` (`ConfigError`). No imports from `engine/`, `validation/`, `agent/`, `context/`, `output/`, or `scm/`.

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. Enforced since Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. When adding `"validate_setup_command"` to `cli/status.py`'s `__all__`, maintain sort order.

#### Output Goes to stderr (D8)
Per Decision 8, all user-facing output goes to stderr. Use `typer.echo(message, err=True)`. Never use `print()`.

#### No `print()` — Use `typer.echo()` or Rich
Architecture anti-patterns explicitly forbid `print()`. All output through Typer echo or Rich console.

#### `asyncio_mode = "auto"` — No `@pytest.mark.asyncio` Decorator Needed
`pyproject.toml` sets `asyncio_mode = "auto"`. The validate-setup command is synchronous (startup-time action), so this is informational only.

---

### Technical Specifications

#### Command Registration Pattern (Established in Story 1.4)

Follow the exact pattern from `init_command`:

```python
# cli/status.py — implements the validate_setup function
def validate_setup_command(
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
) -> None:
    """Validate Arcwright AI project setup."""
    ...

# cli/app.py — registers it
from arcwright_ai.cli.status import init_command, validate_setup_command

app.command(name="init")(init_command)
app.command(name="validate-setup")(validate_setup_command)
```

#### Artifacts Path Resolution

The validate-setup command needs to know where BMAD artifacts live BEFORE loading full config (since full config requires API key). Read the project config directly for `methodology.artifacts_path`:

```python
def _resolve_artifacts_path(project_root: Path) -> str:
    """Determine BMAD artifacts path from project config or default.

    Args:
        project_root: Project root directory.

    Returns:
        Artifacts directory relative path (e.g. "_spec").
    """
    config_path = project_root / DIR_ARCWRIGHT / CONFIG_FILENAME
    if config_path.exists():
        try:
            data = load_yaml(config_path)
            methodology = data.get("methodology", {})
            if isinstance(methodology, dict):
                return str(methodology.get("artifacts_path", DIR_SPEC))
        except ConfigError:
            pass  # Malformed config — use default
    return DIR_SPEC
```

#### Check Dependency Structure

The 5 checks have a dependency structure that governs skipping:

```
Check 1: API key          ─── independent (always runs)
Check 2: Project structure ─── independent (always runs, uses artifacts_path from config or default)
Check 3: Planning artifacts ─── depends on Check 2 (needs project structure directory)
Check 4: Story artifacts    ─── depends on Check 2 (needs project structure directory)
Check 5: Config valid       ─── depends on Check 1 (load_config requires API key to succeed)
```

When a check is skipped, output: `⚠️  [Check name]: Cannot validate — requires [dependency]`

#### API Key Check Implementation

The API key check must look in two places (same logic as `load_config` tier 1 + tier 3):

```python
def _check_api_key() -> tuple[bool, str]:
    """Check if Claude API key is available.

    Returns:
        Tuple of (passed, detail_message).
    """
    # Check env var first (highest precedence)
    env_key = os.environ.get(ENV_API_CLAUDE_API_KEY, "").strip()
    if env_key:
        return True, "present (environment variable)"

    # Check global config (~/.arcwright-ai/config.yaml)
    global_cfg_path = Path.home() / GLOBAL_CONFIG_DIR / CONFIG_FILENAME
    if global_cfg_path.exists():
        try:
            data = load_yaml(global_cfg_path)
            api_section = data.get("api", {})
            if isinstance(api_section, dict):
                key = str(api_section.get("claude_api_key", "")).strip()
                if key:
                    return True, "present (global config)"
        except ConfigError:
            pass  # Malformed global config — key not found

    return (
        False,
        "NOT FOUND\n"
        "   Fix: Set ARCWRIGHT_API_CLAUDE_API_KEY environment variable\n"
        "   or add claude_api_key to ~/.arcwright-ai/config.yaml",
    )
```

**Do NOT check project-level config for API key** — project config must never hold API keys (NFR6).

#### Planning Artifacts Check

Reuse the same glob patterns from `_detect_bmad_artifacts()` (Story 1.4):

```python
def _check_planning_artifacts(
    project_root: Path, artifacts_path: str
) -> tuple[bool, str]:
    """Check for required BMAD planning artifacts.

    Args:
        project_root: Project root directory.
        artifacts_path: Relative path to artifacts (e.g. "_spec").

    Returns:
        Tuple of (passed, detail_message).
    """
    planning_dir = project_root / artifacts_path / "planning-artifacts"
    if not planning_dir.is_dir():
        return (
            False,
            f"planning-artifacts directory not found at {artifacts_path}/planning-artifacts/\n"
            f"   Fix: Create {artifacts_path}/planning-artifacts/ with PRD, architecture, and epics files",
        )

    found: list[str] = []
    missing: list[str] = []

    for artifact_name, pattern in [("PRD", "*prd*"), ("architecture", "*architecture*"), ("epics", "*epic*")]:
        matches = list(planning_dir.glob(pattern))
        if matches:
            found.append(artifact_name)
        else:
            missing.append(artifact_name)

    if missing:
        return (
            False,
            f"Found: {', '.join(found) or 'none'} | Missing: {', '.join(missing)}\n"
            f"   Fix: Create missing planning artifacts in {artifacts_path}/planning-artifacts/",
        )

    return True, f"{', '.join(found)} found"
```

#### Story Artifacts Check with Acceptance Criteria Validation

```python
def _check_story_artifacts(
    project_root: Path, artifacts_path: str
) -> tuple[bool, str]:
    """Check for story artifacts with acceptance criteria.

    Args:
        project_root: Project root directory.
        artifacts_path: Relative path to artifacts (e.g. "_spec").

    Returns:
        Tuple of (passed, detail_message).
    """
    impl_dir = project_root / artifacts_path / "implementation-artifacts"
    if not impl_dir.is_dir():
        return (
            False,
            f"No implementation-artifacts directory at {artifacts_path}/implementation-artifacts/\n"
            f"   Fix: Run sprint-planning to create stories, or create story files manually",
        )

    story_files = [f for f in impl_dir.glob("*.md") if f.stem[0:1].isdigit()]
    if not story_files:
        return (
            False,
            f"No story files found in {artifacts_path}/implementation-artifacts/\n"
            f"   Fix: Create story markdown files (e.g. 1-1-my-story.md)",
        )

    with_ac = 0
    for sf in story_files:
        content = sf.read_text(encoding="utf-8")
        if "acceptance criteria" in content.lower():
            with_ac += 1

    total = len(story_files)
    if with_ac == 0:
        return False, f"{total} stories found but none contain acceptance criteria"

    return True, f"{with_ac} of {total} stories with acceptance criteria"
```

#### Config Validation Check

```python
def _check_config_valid(project_root: Path) -> tuple[bool, str]:
    """Validate full Arcwright AI configuration against schema.

    Args:
        project_root: Project root directory.

    Returns:
        Tuple of (passed, detail_message).
    """
    try:
        load_config(project_root)
        return True, "valid"
    except ConfigError as exc:
        fix = ""
        if exc.details and "fix" in exc.details:
            fix = f"\n   Fix: {exc.details['fix']}"
        return False, f"INVALID: {exc.message}{fix}"
```

#### Output Format

Per the PRD Journey 3 examples, use these symbols:
- `✅` for passing checks
- `❌` for failing checks
- `⚠️` for skipped checks

```
Arcwright AI — Validate Setup
──────────────────────────────

✅ Claude API key: present (environment variable)
✅ BMAD project structure: detected at ./_spec/
✅ Planning artifacts: PRD, architecture, epics found
✅ Story artifacts: 4 of 4 stories with acceptance criteria
✅ Arcwright AI config: valid

All checks passed. Ready for dispatch.
```

Failure example:
```
Arcwright AI — Validate Setup
──────────────────────────────

❌ Claude API key: NOT FOUND
   Fix: Set ARCWRIGHT_API_CLAUDE_API_KEY environment variable
   or add claude_api_key to ~/.arcwright-ai/config.yaml
✅ BMAD project structure: detected at ./_spec/
✅ Planning artifacts: PRD, architecture, epics found
✅ Story artifacts: 4 of 4 stories with acceptance criteria
⚠️  Arcwright AI config: Cannot validate — requires Claude API key

Setup validation failed. Fix the issues above and re-run.
```

#### Exit Code Mapping

- Exit 0 (`EXIT_SUCCESS`): All 5 checks pass
- Exit 3 (`EXIT_CONFIG`): Any check fails — ConfigError maps to exit code 3 per D6

Use `raise typer.Exit(code=EXIT_CONFIG)` or `raise typer.Exit(code=EXIT_SUCCESS)`. Do NOT use `sys.exit()`.

---

### Previous Story Intelligence (Stories 1.1–1.4)

Key learnings from prior stories that directly affect this story:

1. **`__all__` sorted alphabetically** — `ruff` RUF022 enforces this. After adding `"validate_setup_command"` to `cli/status.py`'s `__all__`, ensure sort ordering: `["init_command", "validate_setup_command"]`.

2. **`from __future__ import annotations` as first line** — Required in every `.py` file for PEP 604 `X | None` syntax.

3. **Import ordering: stdlib → third-party → local** — Enforced by Ruff isort.

4. **`save_yaml()` strips comments** — If you need to read config for artifacts path, use `load_yaml()`. Don't write config from validate-setup.

5. **Constants already defined**: `DIR_ARCWRIGHT`, `DIR_SPEC`, `CONFIG_FILENAME`, `GLOBAL_CONFIG_DIR`, `ENV_API_CLAUDE_API_KEY`, `EXIT_SUCCESS`, `EXIT_CONFIG` — all in `core/constants.py`. Import and use. **No magic strings.**

6. **Existing `cli/status.py` has init_command** — Add validate-setup alongside it. The file already imports the required constants. Add new imports as needed.

7. **Existing `cli/app.py` registers init** — Add validate-setup registration in the same pattern: `app.command(name="validate-setup")(validate_setup_command)`.

8. **`load_config()` requires API key** — `load_config(project_root)` will raise `ConfigError` if no API key is available in any tier. The validate-setup command must handle this gracefully — it's an expected "check 5 failure", not an unhandled exception.

9. **`load_yaml()` raises `ConfigError`** — Both for file read errors and YAML parse errors. Handle gracefully when reading partial config for artifacts path resolution.

10. **`Path` import uses TYPE_CHECKING block** — In the existing `status.py`, `Path` is imported directly (not under TYPE_CHECKING) because it's used at runtime. Continue this pattern for validate-setup.

11. **Fixture `tmp_project` in conftest.py** — Creates `tmp_path / ".arcwright-ai"` and `tmp_path / "_spec"`. Useful as base for some validate-setup tests but may need enhancement.

12. **CliRunner mixes stderr+stdout** — `typer.testing.CliRunner` captures both stderr and stdout into `result.output`. Since we write to stderr per D8, all our output will be in `result.output`.

13. **Story 1.4: `_detect_bmad_artifacts()` patterns** — The glob patterns `*prd*`, `*architecture*`, `*epic*` are already proven in Story 1.4. Reuse the same patterns in validate-setup. Consider extracting shared logic or at minimum keeping patterns consistent.

14. **Test count baseline: 157 tests** — Full suite must pass with zero regressions after this story.

---

### Architecture Compliance Notes

1. **`cli/` depends on `core/` only** — validate-setup imports `load_config` from `core.config`, `load_yaml` from `core.io`, constants from `core.constants`, and `ConfigError` from `core.exceptions`. No other package imports.

2. **Validate-setup is synchronous** — Like init, this is a startup-time validation command. No async needed. No event loop.

3. **`typer.echo(..., err=True)` for all output** — Per D8. No `print()`.

4. **No `os.path` — use `pathlib.Path`** — All path operations via `pathlib.Path`.

5. **FR27 mapping** — Per architecture, FR27 maps to `cli/status.py` + `core/config.py`. The validate-setup command in `status.py` is the CLI surface; config validation logic lives in `core/config.py` (already implemented in Story 1.3).

6. **Exit code 3** — `EXIT_CONFIG` from `core/constants.py`. Per D6 exit code mapping, ConfigError/ProjectError/ContextError all map to exit 3. Missing artifacts, missing API key, invalid config are all exit 3 conditions.

7. **NFR5 enforcement** — Config validation catches all invalid states at startup. The validate-setup command IS the user-facing implementation of NFR5 — it surfaces config problems before any run.

8. **PRD Journey 3 alignment** — The output format must match the examples from Journey 3 (Marcus the Evaluator): pass/fail per check, specific fix instructions, clear success/failure summary.

---

### Git Intelligence (Recent Commits)

```
e56b320 feat(cli): implement Story 1.4 — CLI init command
9295f8a fix(story-1.3): address review findings and finalize config system
54d2269 feat(core): implement Story 1.2 core foundation and tests
12444ff feat(arcwright-ai): implement Story 1.1 — project scaffold and package structure
```

**Patterns observed:**
- Commit convention: `feat(scope): description` for new features, `fix(scope): description` for fixes
- Scope for CLI features: `cli` (as in Story 1.4)
- All stories fully implemented in single commits (or commit + fix pair)

**Convention for this story:**
- `feat(cli): implement Story 1.5 — CLI validate-setup command`

---

### Testing Architecture Notes

File to create: `tests/test_cli/test_validate_setup.py`

`tests/test_cli/__init__.py` already exists from Story 1.1. Directory is ready.

**Recommended test approach using `typer.testing.CliRunner`:**

```python
from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner

if TYPE_CHECKING:
    from pathlib import Path

from arcwright_ai.cli.app import app
from arcwright_ai.core.constants import DIR_ARCWRIGHT, CONFIG_FILENAME

runner = CliRunner()


@pytest.fixture()
def valid_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Fully initialized project that passes all validate-setup checks."""
    # Set API key
    monkeypatch.setenv("ARCWRIGHT_API_CLAUDE_API_KEY", "sk-ant-test-key")

    # Create .arcwright-ai/config.yaml (no api section per NFR6)
    arcwright = tmp_path / ".arcwright-ai"
    arcwright.mkdir()
    config_content = 'model:\n  version: "claude-opus-4-5"\nmethodology:\n  artifacts_path: "_spec"\n'
    (arcwright / "config.yaml").write_text(config_content, encoding="utf-8")

    # Create planning artifacts
    planning = tmp_path / "_spec" / "planning-artifacts"
    planning.mkdir(parents=True)
    (planning / "prd.md").write_text("# PRD\n", encoding="utf-8")
    (planning / "architecture.md").write_text("# Architecture\n", encoding="utf-8")
    (planning / "epics.md").write_text("# Epics\n", encoding="utf-8")

    # Create story artifacts with acceptance criteria
    impl = tmp_path / "_spec" / "implementation-artifacts"
    impl.mkdir(parents=True)
    (impl / "1-1-scaffold.md").write_text(
        "# Story 1.1\n\n## Acceptance Criteria\n\n1. Given...\n", encoding="utf-8"
    )

    return tmp_path
```

**Test isolation:** Each test gets its own `tmp_path`. Use `monkeypatch` for env vars (auto-restored). No shared mutable state.

**Testing the skip behavior:** Create a project without API key → assert checks 5 shows skip message. Create a project with non-existent artifacts path → assert checks 3, 4 show skip message.

**Edge case: no `.arcwright-ai/` directory** — The command should still work (just report config issues). The artifacts path falls back to default `"_spec"`.

---

### Project Structure Notes

Files to modify:
- `arcwright-ai/src/arcwright_ai/cli/status.py` — add `validate_setup_command` and helper functions
- `arcwright-ai/src/arcwright_ai/cli/app.py` — register `validate-setup` command

Files to create:
- `arcwright-ai/tests/test_cli/test_validate_setup.py` — new test file

No new directories needed. `tests/test_cli/` already has `__init__.py`.

Working directory for all commands: `arcwright-ai/`

### References

- [Source: _spec/planning-artifacts/epics.md#Story-1.5] — story requirements and acceptance criteria
- [Source: _spec/planning-artifacts/architecture.md#Architectural-Subsystem-Map] — Subsystem #10: CLI Surface, Subsystem #8: Configuration System
- [Source: _spec/planning-artifacts/architecture.md#Complete-Project-Tree] — `cli/status.py` is canonical location for init, validate-setup, status, clean
- [Source: _spec/planning-artifacts/architecture.md#Boundary-1-CLI-Engine] — CLI calls single function per command, all user output stays in `cli/`
- [Source: _spec/planning-artifacts/architecture.md#Decision-6] — exit code 3 for ConfigError/ProjectError/ContextError
- [Source: _spec/planning-artifacts/architecture.md#Decision-8] — Output to stderr, Rich/Typer formatting
- [Source: _spec/planning-artifacts/architecture.md#Python-Code-Style-Patterns] — naming, `__all__`, docstrings, import ordering
- [Source: _spec/planning-artifacts/architecture.md#File-Path-Patterns] — pathlib.Path, encoding, mkdir(parents=True, exist_ok=True)
- [Source: _spec/planning-artifacts/architecture.md#Testing-Patterns] — naming, isolation, `tmp_path`, `pytest.raises`, no assertion libraries
- [Source: _spec/planning-artifacts/prd.md#FR27] — `arcwright-ai validate-setup` with pass/fail checks and fix instructions
- [Source: _spec/planning-artifacts/prd.md#NFR5] — Config validation catches all invalid states at startup — never fails mid-run due to bad config
- [Source: _spec/planning-artifacts/prd.md#NFR6] — API keys never written to project-level files or committed to git
- [Source: _spec/planning-artifacts/prd.md#Journey-3] — Marcus Evaluator journey: validate-setup success/failure output examples
- [Source: _spec/implementation-artifacts/1-4-cli-init-command.md#Dev-Notes] — init command patterns, `_detect_bmad_artifacts()` glob patterns, `-p`/`--path` option, CliRunner testing, `typer.echo(..., err=True)`
- [Source: _spec/implementation-artifacts/1-3-configuration-system-with-two-tier-loading.md] — `load_config()` API, `ConfigError` handling, env var constants, `_check_no_api_keys_in_project()`, unknown key warnings
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py] — DIR_ARCWRIGHT, DIR_SPEC, CONFIG_FILENAME, ENV_API_CLAUDE_API_KEY, EXIT_SUCCESS, EXIT_CONFIG, GLOBAL_CONFIG_DIR
- [Source: arcwright-ai/src/arcwright_ai/core/config.py] — load_config(), RunConfig, ConfigError translation, tier loading order
- [Source: arcwright-ai/src/arcwright_ai/core/io.py] — load_yaml() for reading config files safely
- [Source: arcwright-ai/src/arcwright_ai/core/exceptions.py] — ConfigError with message + details dict
- [Source: arcwright-ai/src/arcwright_ai/cli/app.py] — Typer app, command registration pattern
- [Source: arcwright-ai/src/arcwright_ai/cli/status.py] — init_command, _detect_bmad_artifacts(), _GITIGNORE_ENTRIES, existing helper pattern

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No debug issues encountered. Implementation straightforward following story spec exactly.

### Completion Notes List

- Implemented 6 helper functions: `_resolve_artifacts_path`, `_check_api_key`, `_check_project_structure`, `_check_planning_artifacts`, `_check_story_artifacts`, `_check_config_valid`
- Implemented `validate_setup_command` composing all 5 checks with correct dependency-based skip logic
- Registered `validate-setup` command in `cli/app.py` following established init pattern
- Created 14 comprehensive tests covering all ACs (3.2–3.13) plus review follow-up hardening for fix guidance and artifacts path safety
- All output routed to stderr via `typer.echo(..., err=True)` per D8
- Exit codes: 0 (EXIT_SUCCESS) for all-pass, 3 (EXIT_CONFIG) for any failure
- 171 tests total pass (157 baseline + 14 new), zero regressions
- ruff lint: 0 violations, ruff format: clean, mypy --strict: 0 errors

### File List

- `arcwright-ai/src/arcwright_ai/cli/status.py` — modified: added imports (`os`, `load_config`, `ConfigError`, `load_yaml`, `ENV_API_CLAUDE_API_KEY`, `EXIT_CONFIG`, `EXIT_SUCCESS`, `GLOBAL_CONFIG_DIR`); updated `__all__`; added `_resolve_artifacts_path`, `_check_api_key`, `_check_project_structure`, `_check_planning_artifacts`, `_check_story_artifacts`, `_check_config_valid`, `validate_setup_command`
- `arcwright-ai/src/arcwright_ai/cli/app.py` — modified: added `validate_setup_command` import and `app.command(name="validate-setup")` registration
- `arcwright-ai/tests/test_cli/test_validate_setup.py` — created and expanded to 14 tests covering all ACs and review follow-up edge cases

## Senior Developer Review (AI)

### Outcome

Changes Requested → Resolved (all HIGH and MEDIUM issues fixed in this review pass)

### Findings

1. **HIGH** — Story-artifact failure path lacked actionable fix guidance when stories existed but had no Acceptance Criteria section.
2. **MEDIUM** — Artifacts path resolution accepted invalid/absolute values from project config without fallback hardening.
3. **MEDIUM** — Config validation failure messaging could omit explicit fix instructions.
4. **MEDIUM** — Test expectation for uninitialized project exit code was too permissive and could hide regressions.
5. **MEDIUM** — Git/story discrepancy: `_spec/implementation-artifacts/sprint-status.yaml` was changed but not recorded in this story's File List.

### Fixes Applied

- Hardened `_resolve_artifacts_path()` in `arcwright-ai/src/arcwright_ai/cli/status.py` to reject empty/absolute paths and fall back to `"_spec"`.
- Improved `_check_story_artifacts()` to:
    - return actionable `Fix:` guidance when no stories include Acceptance Criteria,
    - gracefully handle unreadable story files with explicit remediation,
    - report partial AC coverage details.
- Updated `_check_config_valid()` to always include a `Fix:` line.
- Expanded `arcwright-ai/tests/test_cli/test_validate_setup.py` with review follow-up tests and tightened the uninitialized-project assertion to require exit code `3`.
- Re-ran quality gates: `ruff check .`, `ruff format --check .`, `.venv/bin/python -m mypy --strict src/`, `pytest tests/test_cli/test_validate_setup.py`, and full `pytest`.

### Validation Summary

- Targeted validate-setup tests: **14 passed**
- Full test suite: **171 passed**
- Ruff lint/format: **clean**
- Mypy strict: **0 errors**

### Git vs Story Notes

- Added this review note to close documentation gaps discovered during git/story cross-check.

## Change Log

- 2026-03-02: Story 1.5 implemented — CLI validate-setup command with 5-check suite, dependency-based skip logic, and 12 unit tests. All quality gates pass.
- 2026-03-02: Senior Developer Review completed — resolved HIGH/MEDIUM findings, hardened validate-setup edge cases, expanded test coverage to 14 tests, and revalidated full suite (171 passing).
