# Story 1.4: CLI Init Command

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a developer starting a new Arcwright AI project,
I want to run `arcwright-ai init` to scaffold the `.arcwright-ai/` directory with default config and `.gitignore` entries,
so that my project is ready for dispatching runs with minimal manual setup.

## Acceptance Criteria (BDD)

1. **Given** a project directory with an existing `_spec/` directory containing BMAD artifacts **When** I run `arcwright-ai init` **Then** `.arcwright-ai/` directory is created with `config.yaml` (default values), `runs/` (empty), `worktrees/` (empty), `tmp/` (empty).

2. **Given** a project directory with a `.gitignore` file that does not contain `.arcwright-ai/tmp/` or `.arcwright-ai/runs/` **When** I run `arcwright-ai init` **Then** `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` are appended to the project `.gitignore`.

3. **Given** a project directory without a `.gitignore` file **When** I run `arcwright-ai init` **Then** a `.gitignore` file is created containing `.arcwright-ai/tmp/` and `.arcwright-ai/runs/`.

4. **Given** `_spec/` exists and contains BMAD artifacts (PRD, architecture, epics, stories) **When** `arcwright-ai init` runs **Then** the command detects and reports which BMAD artifacts were found in `_spec/` (e.g., "Found: PRD, Architecture, Epics, 12 stories").

5. **Given** an already-initialized project (`.arcwright-ai/` exists with `config.yaml`) **When** I run `arcwright-ai init` again **Then** the operation is idempotent — existing `config.yaml` is preserved, missing subdirectories are created, `.gitignore` entries are not duplicated.

6. **Given** `arcwright-ai init` completes successfully **When** the output is inspected **Then** output is formatted using Rich/Typer to stderr per D8.

7. **Given** `arcwright-ai init` completes successfully **When** the exit code is inspected **Then** exit code is 0.

8. **Given** unit tests for the init command **When** `pytest tests/test_cli/test_init.py` is run **Then** all tests pass, covering: fresh init, idempotent re-init, BMAD artifact detection, `.gitignore` creation, `.gitignore` append without duplication, `.gitignore` already-has-entries behavior.

9. **Given** story implementation is complete **When** `ruff check .` is run **Then** zero violations.

10. **Given** story implementation is complete **When** `mypy --strict src/` (via `.venv/bin/python -m mypy --strict src/`) is run **Then** zero errors.

11. **Given** all public classes and functions **When** every docstring is inspected **Then** each conforms to Google-style (Args, Returns, Raises sections where appropriate).

## Tasks / Subtasks

- [x] Task 1: Implement `init` command in `cli/status.py` (AC: #1, #2, #3, #4, #5, #6, #7, #11)
  - [x] 1.1: Import required modules: `typer`, `Path`, `sys`, and constants from `core.constants` (`DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_TMP`, `DIR_WORKTREES`, `DIR_SPEC`, `CONFIG_FILENAME`)
  - [x] 1.2: Implement `init` command function registered on the Typer app from `cli/app.py` (either via direct `@app.command()` in `status.py` with the app imported, or via a callback registration pattern in `app.py` that imports from `status.py`)
    - [x] 1.3: Accept optional `--path` / `-p` argument (default: current directory) for specifying the project root — `typer.Option(".", "--path", "-p", help="Project root directory")`
  - [x] 1.4: Implement `_scaffold_directories(project_root: Path) -> list[str]` — creates `.arcwright-ai/`, `runs/`, `worktrees/`, `tmp/` using `path.mkdir(parents=True, exist_ok=True)`. Returns a list of directory names that were newly created (for reporting).
  - [x] 1.5: Implement `_write_default_config(project_root: Path) -> bool` — writes a default `config.yaml` to `.arcwright-ai/config.yaml` with commented-out sections for `model`, `limits`, `methodology`, `scm`, `reproducibility` (NOT `api` — API key is global-only per NFR6). Returns `True` if created, `False` if already exists.
  - [x] 1.6: Implement `_update_gitignore(project_root: Path) -> list[str]` — reads existing `.gitignore` (or creates new), appends `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` if they are not already present. Returns a list of lines added. Handles: missing file (create), existing file without entries (append), existing file with entries (no-op), existing file with partial entries (append missing only).
  - [x] 1.7: Implement `_detect_bmad_artifacts(project_root: Path) -> dict[str, Any]` — scans `_spec/` for BMAD artifacts. Returns a dict with keys: `prd` (bool or filename), `architecture` (bool or filename), `epics` (bool or filename), `stories` (list of filenames or count). Uses glob patterns: `*prd*`, `*architecture*`, `*epic*`, plus `implementation-artifacts/*.md` for stories.
  - [x] 1.8: Compose the `init` command function: call scaffolding, default config, gitignore, artifact detection in sequence; format and display results using `typer.echo()` to stderr; exit 0 on success.

- [x] Task 2: Register the `init` command on the CLI app (AC: #7)
  - [x] 2.1: In `cli/app.py`, import and register the init command so `arcwright-ai init` works from the CLI entry point.
  - [x] 2.2: Ensure `arcwright-ai --help` lists the `init` command.

- [x] Task 3: Write the default config YAML content (AC: #1, #5)
  - [x] 3.1: Define the default config content as a string constant or dict. Must include: `model` section with `version: "claude-opus-4-5"`, `limits` section with defaults, `methodology` section with `artifacts_path: "_spec"` and `type: "bmad"`, `scm` section with `branch_template: "arcwright/{story_slug}"`, `reproducibility` section with defaults. Must NOT include `api` section (NFR6).
  - [x] 3.2: Include comments in the generated YAML explaining each section and noting that `api.claude_api_key` must be set via environment variable or `~/.arcwright-ai/config.yaml`.

- [x] Task 4: Write unit tests in `tests/test_cli/test_init.py` (AC: #8)
  - [x] 4.1: Create `tests/test_cli/test_init.py` with fixtures: `project_dir` (tmp_path with `_spec/` pre-created), `initialized_project` (tmp_path with `.arcwright-ai/` already scaffolded)
  - [x] 4.2: Test `test_init_fresh_project`: assert `.arcwright-ai/` created with `config.yaml`, `runs/`, `worktrees/`, `tmp/`
  - [x] 4.3: Test `test_init_creates_gitignore`: no `.gitignore` exists → created with `.arcwright-ai/tmp/` and `.arcwright-ai/runs/`
  - [x] 4.4: Test `test_init_appends_gitignore`: existing `.gitignore` with unrelated content → entries appended, original content preserved
  - [x] 4.5: Test `test_init_gitignore_no_duplicates`: `.gitignore` already has `.arcwright-ai/tmp/` and `.arcwright-ai/runs/` → no duplicate lines added
  - [x] 4.6: Test `test_init_gitignore_partial_entries`: `.gitignore` has `.arcwright-ai/tmp/` but not `.arcwright-ai/runs/` → only `.arcwright-ai/runs/` appended
  - [x] 4.7: Test `test_init_idempotent_preserves_config`: existing `config.yaml` with custom values → re-init does NOT overwrite config
  - [x] 4.8: Test `test_init_idempotent_creates_missing_dirs`: `.arcwright-ai/` exists but `tmp/` missing → only `tmp/` created
  - [x] 4.9: Test `test_init_detects_bmad_artifacts`: `_spec/` has prd.md, architecture.md, epics.md, stories → all detected and reported
  - [x] 4.10: Test `test_init_no_spec_directory`: no `_spec/` directory → report "No BMAD artifacts found" (not an error)
  - [x] 4.11: Test `test_init_exit_code_zero`: `result.exit_code == 0` using `typer.testing.CliRunner`
  - [x] 4.12: Test `test_init_default_config_has_no_api_section`: generated `config.yaml` must not contain `api:` or `claude_api_key`

- [x] Task 5: Validate all quality gates (AC: #9, #10)
  - [x] 5.1: Run `ruff check .` — zero violations
  - [x] 5.2: Run `ruff format --check .` — no formatting diffs
  - [x] 5.3: Run `.venv/bin/python -m mypy --strict src/` — zero errors
  - [x] 5.4: Run `pytest tests/test_cli/test_init.py -v` — all tests pass
  - [x] 5.5: Run full test suite `pytest` — all tests pass (no regressions)

## Dev Notes

### Critical Architecture Constraints

#### Package Dependency DAG — `cli/` Depends on `core/` Only (Not `engine/`)
```
cli → engine → {validation, agent, context, output, scm} → core
```
For the `init` command, `cli/status.py` can only import from `core/` (constants, io, config, exceptions). The init command does NOT need engine, validation, agent, context, output, or scm. Keep it minimal.

#### `from __future__ import annotations` — Required First Line
Every `.py` file must begin with `from __future__ import annotations`. This is enforced and was established in Story 1.1.

#### `__all__` Must Be Alphabetically Sorted (RUF022)
`ruff` enforces RUF022 — `__all__` lists must be in alphabetical order. Learned the hard way in Story 1.2.

#### `asyncio_mode = "auto"` — No `@pytest.mark.asyncio` Decorator
`pyproject.toml` sets `asyncio_mode = "auto"` — async test functions are discovered automatically. The init command is synchronous (startup-time action), so this is informational only.

#### Output Goes to stderr (D8)
Per Decision 8 (Logging & Observability), user output uses Rich/Typer formatted text to stderr. Typer's `echo()` writes to stdout by default. Use `typer.echo(..., err=True)` or use `rich.print()` to stderr. The pattern: use `typer.echo(message, err=True)` for status output.

#### No `print()` — Use `typer.echo()` or Rich
Architecture anti-patterns explicitly forbid `print()`. All output must go through Typer echo or Rich console.

---

### Technical Specifications

#### Command Registration Pattern

The init command should be registered in `cli/app.py`. Looking at the existing code, `app.py` creates the Typer app. The pattern is:

```python
# cli/status.py — implements the init function
def init_command(path: str = typer.Argument(default=".", help="Project root directory")) -> None:
    """Initialize a new Arcwright AI project."""
    ...

# cli/app.py — registers it
from arcwright_ai.cli.status import init_command

app.command(name="init")(init_command)
```

Or alternatively, define the `@app.command()` directly in `status.py` by importing `app` from `app.py`. **Check which pattern avoids circular imports.** Typer supports registering commands from other modules via `app.command()`.

#### Directory Scaffolding

```python
from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_RUNS, DIR_TMP, DIR_WORKTREES

def _scaffold_directories(project_root: Path) -> list[str]:
    """Create .arcwright-ai/ directory structure.

    Args:
        project_root: Project root directory.

    Returns:
        List of directory names that were newly created.
    """
    created: list[str] = []
    arcwright_dir = project_root / DIR_ARCWRIGHT

    for subdir_name in (DIR_RUNS, DIR_TMP, DIR_WORKTREES):
        subdir = arcwright_dir / subdir_name
        if not subdir.exists():
            subdir.mkdir(parents=True, exist_ok=True)
            created.append(subdir_name)
        # If parent .arcwright-ai/ itself was newly created, note it
    
    return created
```

Use `path.mkdir(parents=True, exist_ok=True)` for all directory creation — idempotent by design.

#### Default Config YAML Content

The generated `config.yaml` must NOT include an `api` section (NFR6: API keys never in project-level files). The file should include helpful comments:

```yaml
# Arcwright AI Project Configuration
# 
# API keys must be set via environment variable:
#   export ARCWRIGHT_API_CLAUDE_API_KEY="sk-ant-..."
# Or in the global config file: ~/.arcwright-ai/config.yaml

model:
  version: "claude-opus-4-5"

limits:
  tokens_per_story: 200000
  cost_per_run: 10.0
  retry_budget: 3
  timeout_per_story: 300

methodology:
  artifacts_path: "_spec"
  type: "bmad"

scm:
  branch_template: "arcwright/{story_slug}"

reproducibility:
  enabled: false
  retention: 30
```

**Do NOT use `save_yaml()` for this.** `save_yaml()` uses `yaml.safe_dump()` which strips comments. Write the config as a raw string to preserve the human-readable comments. Use `path.write_text(content, encoding="utf-8")`.

#### `.gitignore` Update Logic

```python
GITIGNORE_ENTRIES: list[str] = [
    ".arcwright-ai/tmp/",
    ".arcwright-ai/runs/",
]

def _update_gitignore(project_root: Path) -> list[str]:
    """Add Arcwright AI entries to .gitignore.

    Args:
        project_root: Project root directory.

    Returns:
        List of entries that were added.
    """
    gitignore_path = project_root / ".gitignore"
    existing_content = ""
    if gitignore_path.exists():
        existing_content = gitignore_path.read_text(encoding="utf-8")

    existing_lines = set(existing_content.splitlines())
    added: list[str] = []

    for entry in GITIGNORE_ENTRIES:
        if entry not in existing_lines:
            added.append(entry)

    if added:
        # Ensure existing content ends with newline before appending
        if existing_content and not existing_content.endswith("\n"):
            existing_content += "\n"
        # Add a comment header if we're adding new entries
        if not any("arcwright" in line.lower() for line in existing_lines):
            existing_content += "\n# Arcwright AI\n"
        existing_content += "\n".join(added) + "\n"
        gitignore_path.write_text(existing_content, encoding="utf-8")

    return added
```

**Edge cases:**
- File doesn't exist → create with entries
- File exists, empty → append with header comment
- File exists, has unrelated rules → append with header comment
- File exists, has some entries → only add missing
- File exists, has all entries → no-op, return empty list

#### BMAD Artifact Detection

```python
def _detect_bmad_artifacts(project_root: Path) -> dict[str, Any]:
    """Scan _spec/ for BMAD planning artifacts.

    Args:
        project_root: Project root directory.

    Returns:
        Dict with found artifacts by type.
    """
    spec_dir = project_root / DIR_SPEC
    if not spec_dir.exists():
        return {}

    results: dict[str, Any] = {}

    # Planning artifacts in _spec/planning-artifacts/
    planning_dir = spec_dir / "planning-artifacts"
    if planning_dir.exists():
        prd_files = list(planning_dir.glob("*prd*"))
        if prd_files:
            results["prd"] = [f.name for f in prd_files]

        arch_files = list(planning_dir.glob("*architecture*"))
        if arch_files:
            results["architecture"] = [f.name for f in arch_files]

        epic_files = list(planning_dir.glob("*epic*"))
        if epic_files:
            results["epics"] = [f.name for f in epic_files]

    # Stories in _spec/implementation-artifacts/
    impl_dir = spec_dir / "implementation-artifacts"
    if impl_dir.exists():
        story_files = [f for f in impl_dir.glob("*.md") if f.stem[0].isdigit()]
        if story_files:
            results["stories"] = len(story_files)

    return results
```

#### Typer CLI Testing Pattern

Use `typer.testing.CliRunner` for testing CLI commands:

```python
from typer.testing import CliRunner
from arcwright_ai.cli.app import app

runner = CliRunner()

def test_init_fresh_project(tmp_path: Path) -> None:
    (tmp_path / "_spec").mkdir()
    result = runner.invoke(app, ["init", str(tmp_path)])
    assert result.exit_code == 0
    assert (tmp_path / ".arcwright-ai" / "config.yaml").exists()
    assert (tmp_path / ".arcwright-ai" / "runs").is_dir()
    assert (tmp_path / ".arcwright-ai" / "tmp").is_dir()
    assert (tmp_path / ".arcwright-ai" / "worktrees").is_dir()
```

**Important:** The `CliRunner` captures stdout by default. Since we're writing to stderr per D8, use `runner.invoke(app, ["init", ...])` and check `result.output` for stderr content. Typer's CliRunner may need `catch_exceptions=False` for debugging.

**Alternative path argument approach:** If using `typer.Argument(default=".")`, the command accepts the path as a positional argument. `runner.invoke(app, ["init", str(tmp_path)])` passes the path.

---

### Previous Story Intelligence (Stories 1.1, 1.2, 1.3)

Key learnings from prior stories that directly affect this story:

1. **`__all__` sorted alphabetically** — `ruff` RUF022 enforces this. All `__all__` lists in every file must be in alphabetical order. This applies to updates to `cli/status.py` and `cli/app.py`.

2. **All test subdirectories have `__init__.py`** — `tests/test_cli/__init__.py` exists from Story 1.1. No new test directories needed.

3. **`ArcwrightModel` is frozen** — Config models are read-only. The init command doesn't construct config models; it writes a raw YAML file.

4. **`from __future__ import annotations` as first line** — Required in every `.py` file for PEP 604 `X | None` syntax.

5. **Import ordering: stdlib → third-party → local** — Enforced by Ruff isort.

6. **`save_yaml()` strips comments** — `save_yaml()` uses `yaml.safe_dump()` which does not preserve comments. Write the default config as a raw string instead.

7. **Constants already defined**: `DIR_ARCWRIGHT`, `DIR_RUNS`, `DIR_TMP`, `DIR_WORKTREES`, `DIR_SPEC`, `CONFIG_FILENAME` — all in `core/constants.py`. Import and use these. **No magic strings.**

8. **Existing `cli/status.py` is a stub** — Currently only has `from __future__ import annotations` and an empty `__all__`. Ready to implement.

9. **Existing `cli/app.py` creates the Typer app** — Has `app = typer.Typer(...)` and a `main()` callback. Commands should be registered here or imported from other modules.

10. **Fixture `tmp_project` in conftest.py** — Creates `tmp_path / ".arcwright-ai"` and `tmp_path / "_spec"`. Useful for some tests, but init tests need to test WITHOUT `.arcwright-ai/` existing (fresh init), so create test-specific fixtures.

11. **Story 1.3: Pydantic `ValidationError` name collision** — Not relevant for init command (no Pydantic validation in the init path).

12. **Story 1.3: `_check_no_api_keys_in_project()` enforcement** — The default config generated by `init` must NOT include an `api` section. This is validated by `test_init_default_config_has_no_api_section`.

---

### Architecture Compliance Notes

1. **`cli/` depends on `core/` only** — The init command imports constants from `core.constants`. It does NOT import from `engine/`, `agent/`, `validation/`, `context/`, `output/`, or `scm/`. Keep it clean.

2. **Init is synchronous** — Unlike dispatch or status, the init command performs no async I/O. It creates directories and writes files synchronously at startup time. This is intentional — init runs before any event loop.

3. **`typer.echo(..., err=True)` for output** — All user-facing output goes to stderr per D8. Do not use `print()`.

4. **No `os.path` — use `pathlib.Path`** — All path operations must use `pathlib.Path`. Never string concatenation.

5. **FR26 mapping** — Per the architecture FR mapping table, FR26 maps to `cli/status.py`. This is the canonical location for the init command.

6. **Idempotency (NFR19)** — Re-running `arcwright-ai init` on an already-initialized project must be safe. Existing config must not be overwritten. Missing directories must be created. `.gitignore` entries must not be duplicated.

7. **Config.yaml is project-level** — The init-generated config lives at `.arcwright-ai/config.yaml` (project tier). It contains only non-sensitive defaults. API keys belong in `~/.arcwright-ai/config.yaml` (global tier) or env vars.

---

### Git Intelligence (Recent Commits)

```
9295f8a fix(story-1.3): address review findings and finalize config system
54d2269 feat(core): implement Story 1.2 core foundation and tests
12444ff feat(arcwright-ai): implement Story 1.1 — project scaffold and package structure
```

**Patterns observed:**
- Commit convention: `feat(scope): description` for new features, `fix(scope): description` for fixes
- All stories are fully implemented in single commits (or commit + fix pair)
- Story 1.3's most recent commit was a review-fix follow-up
- Files modified follow the expected pattern: source → tests → story doc → sprint-status

**Convention for this story:**
- `feat(cli): implement Story 1.4 — CLI init command`

---

### Testing Architecture Notes

File to create: `tests/test_cli/test_init.py`

`tests/test_cli/__init__.py` already exists from Story 1.1. Directory is ready.

**Recommended test approach using `typer.testing.CliRunner`:**

```python
from pathlib import Path
from typer.testing import CliRunner
from arcwright_ai.cli.app import app

runner = CliRunner()

@pytest.fixture
def fresh_project(tmp_path: Path) -> Path:
    """Project directory with _spec/ but no .arcwright-ai/."""
    (tmp_path / "_spec" / "planning-artifacts").mkdir(parents=True)
    return tmp_path

@pytest.fixture
def initialized_project(fresh_project: Path) -> Path:
    """Already-initialized project with .arcwright-ai/ structure."""
    runner.invoke(app, ["init", str(fresh_project)])
    return fresh_project
```

**Test isolation:** Each test gets its own `tmp_path`. No shared mutable state. No reads from real filesystem.

**Testing `.gitignore` behavior:**
- Read `.gitignore` after init, check for entries using `in` on lines
- For duplicate checks: pre-write `.gitignore` with entries, invoke init, assert line count unchanged

**Testing BMAD detection:**
- Create dummy files in `_spec/planning-artifacts/`: `prd.md`, `architecture.md`, `epics.md`
- Create dummy stories in `_spec/implementation-artifacts/`: `1-1-foo.md`, `1-2-bar.md`
- Assert detection output mentions all found artifacts

---

### Project Structure Notes

Files to create or modify:
- `arcwright-ai/src/arcwright_ai/cli/status.py` — **replace stub** with init command implementation
- `arcwright-ai/src/arcwright_ai/cli/app.py` — **update** to register the init command
- `arcwright-ai/tests/test_cli/test_init.py` — **new file**

No new directories needed. `tests/test_cli/` already exists with `__init__.py`.

Working directory for all commands: `arcwright-ai/`

### References

- [Source: _spec/planning-artifacts/epics.md#Story-1.4] — story requirements and acceptance criteria
- [Source: _spec/planning-artifacts/architecture.md#Architectural-Subsystem-Map] — Subsystem #10: CLI Surface, Subsystem #8: Configuration System
- [Source: _spec/planning-artifacts/architecture.md#Complete-Project-Tree] — `cli/status.py` is canonical location for init, validate-setup, status, clean
- [Source: _spec/planning-artifacts/architecture.md#Boundary-1-CLI-Engine] — CLI calls single function per command, all user output stays in `cli/`
- [Source: _spec/planning-artifacts/architecture.md#Decision-8] — Output to stderr, Rich/Typer formatting
- [Source: _spec/planning-artifacts/architecture.md#Python-Code-Style-Patterns] — naming, `__all__`, docstrings, import ordering
- [Source: _spec/planning-artifacts/architecture.md#File-Path-Patterns] — pathlib.Path, encoding, mkdir(parents=True, exist_ok=True)
- [Source: _spec/planning-artifacts/architecture.md#Testing-Patterns] — naming, isolation, `tmp_path`, `pytest.raises`, no assertion libraries
- [Source: _spec/planning-artifacts/prd.md#FR26] — `arcwright-ai init` scaffolds .arcwright-ai/, detects BMAD artifacts
- [Source: _spec/planning-artifacts/prd.md#NFR5] — Config validation catches all invalid states at startup
- [Source: _spec/planning-artifacts/prd.md#NFR6] — API keys never written to project-level files
- [Source: _spec/planning-artifacts/prd.md#NFR8] — .arcwright-ai/tmp/ and .arcwright-ai/runs/ added to .gitignore automatically on init
- [Source: _spec/planning-artifacts/prd.md#NFR19] — All operations idempotent
- [Source: _spec/planning-artifacts/prd.md#Journey-3] — Marcus Evaluator journey: init + validate-setup flow
- [Source: _spec/implementation-artifacts/1-3-configuration-system-with-two-tier-loading.md#Dev-Notes] — previous story patterns: `__all__` sorting, import aliasing, `save_yaml()` strips comments
- [Source: arcwright-ai/src/arcwright_ai/core/constants.py] — DIR_ARCWRIGHT, DIR_RUNS, DIR_TMP, DIR_WORKTREES, DIR_SPEC, CONFIG_FILENAME
- [Source: arcwright-ai/src/arcwright_ai/core/io.py] — save_yaml() (note: strips comments, use raw string write instead)
- [Source: arcwright-ai/src/arcwright_ai/cli/app.py] — Typer app instance and command registration
- [Source: arcwright-ai/src/arcwright_ai/cli/status.py] — current stub, target for implementation

## Dev Agent Record

### Agent Model Used

Claude Sonnet 4.6 (GitHub Copilot)

### Debug Log References

No issues encountered. Implementation proceeded without halts.

### Completion Notes List

- ✅ Implemented `_scaffold_directories`, `_write_default_config`, `_update_gitignore`, `_detect_bmad_artifacts` helper functions in `cli/status.py`
- ✅ `init_command` registered on Typer app via `app.command(name="init")(init_command)` pattern in `app.py` to avoid circular imports
- ✅ All output goes to stderr via `typer.echo(..., err=True)` per D8
- ✅ Default config uses raw string write (not `save_yaml()`) to preserve comments; contains no `api:` section per NFR6
- ✅ `.gitignore` update logic handles all 5 edge cases: create, append with header, append partial, no-op full, no-op partial
- ✅ BMAD artifact detection scans `_spec/planning-artifacts/` and `_spec/implementation-artifacts/` using glob patterns
- ✅ Idempotency verified: re-running init preserves config, creates only missing dirs, adds no duplicate gitignore entries
- ✅ 11 new tests, all passing; 155 total tests (0 regressions)
- ✅ `ruff check`: 0 violations; `ruff format --check`: 0 diffs; `mypy --strict src/`: 0 errors
- ✅ All public functions have Google-style docstrings with Args and Returns sections
- ✅ `Path` import uses TYPE_CHECKING block per TCH002 ruff rule
- ✅ Review fixes applied: `init` now supports `--path` / `-p` as specified in Task 1.3
- ✅ Added CLI contract tests: `init --help` exposes `--path`/`-p`, root `--help` includes `init` command
- ✅ Re-verified quality gates after review fixes: `pytest tests/test_cli/test_init.py`, `ruff check .`, `mypy --strict src/`, and full `pytest`

### File List

- arcwright-ai/src/arcwright_ai/cli/status.py (modified — full implementation replacing stub)
- arcwright-ai/src/arcwright_ai/cli/app.py (modified — registered init command)
- arcwright-ai/tests/test_cli/test_init.py (new — 13 unit tests)
- _spec/implementation-artifacts/1-4-cli-init-command.md (modified — story metadata)
- _spec/implementation-artifacts/sprint-status.yaml (modified — status updates)

## Senior Developer Review (AI)

### Reviewer

Ed (AI-assisted review)

### Outcome

Changes Requested → Addressed → Approved

### Findings Resolved

- HIGH: Task 1.3 marked complete but `--path` / `-p` option was not implemented (positional arg used instead). Fixed in `cli/status.py`.
- MEDIUM: CLI contract for `init --help` option visibility was not validated. Added test coverage.
- MEDIUM: CLI root help exposure for `init` command was not validated. Added test coverage.

### Verification

- `pytest tests/test_cli/test_init.py -q` → 13 passed
- `ruff check .` → all checks passed
- `.venv/bin/python -m mypy --strict src/` → success
- `pytest -q` → all tests passed

## Change Log

- 2026-03-02: Story created by SM (create-story workflow) — comprehensive context engine analysis completed. Status → ready-for-dev.
- 2026-03-02: Story implemented by Dev (dev-story workflow) — CLI init command complete. Status → review.
- 2026-03-02: Code review fixes applied — implemented `--path`/`-p`, expanded CLI help tests, reran quality gates. Status → done.
