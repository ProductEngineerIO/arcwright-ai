"""CLI status — Sprint and run status display commands.

Contains: init command for scaffolding .arcwright-ai/ project directory,
validate-setup command for configuration verification, and status command
for live and historical run visibility.
"""

from __future__ import annotations

import asyncio
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any

import typer

from arcwright_ai.core.config import load_config
from arcwright_ai.core.constants import (
    CONFIG_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_SPEC,
    DIR_TMP,
    DIR_WORKTREES,
    ENV_API_CLAUDE_API_KEY,
    EXIT_CONFIG,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    GLOBAL_CONFIG_DIR,
)
from arcwright_ai.core.exceptions import ConfigError, RunError
from arcwright_ai.core.io import load_yaml
from arcwright_ai.output.run_manager import RunStatusValue, get_run_status, list_runs

__all__: list[str] = [
    "init_command",
    "status_command",
    "validate_setup_command",
]

# ---------------------------------------------------------------------------
# Status command constants
# ---------------------------------------------------------------------------

_COMPLETED_STATUSES: frozenset[str] = frozenset({"success", "completed", "done"})
_FAILED_STATUSES: frozenset[str] = frozenset({"failed", "halted", "escalated"})

# ---------------------------------------------------------------------------
# Gitignore entries managed by arcwright-ai
# ---------------------------------------------------------------------------

_GITIGNORE_ENTRIES: list[str] = [
    ".arcwright-ai/tmp/",
    ".arcwright-ai/runs/",
]

# ---------------------------------------------------------------------------
# Default project-level config content
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG_YAML: str = """# Arcwright AI Project Configuration
#
# API keys must be set via environment variable:
#   export ARCWRIGHT_API_CLAUDE_API_KEY="sk-ant-..."
# Or in the global config file: ~/.arcwright-ai/config.yaml
# The api section must NEVER appear in project-level config files.

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
"""


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _scaffold_directories(project_root: Path) -> list[str]:
    """Create .arcwright-ai/ directory structure.

    Args:
        project_root: Project root directory.

    Returns:
        List of subdirectory names that were newly created (not including
        the base .arcwright-ai/ itself).
    """
    created: list[str] = []
    arcwright_dir = project_root / DIR_ARCWRIGHT

    for subdir_name in (DIR_RUNS, DIR_TMP, DIR_WORKTREES):
        subdir = arcwright_dir / subdir_name
        if not subdir.exists():
            subdir.mkdir(parents=True, exist_ok=True)
            created.append(subdir_name)
        else:
            # Ensure parent was created even if subdir pre-existed
            arcwright_dir.mkdir(parents=True, exist_ok=True)

    # Ensure base dir exists even if all subdirs already existed
    arcwright_dir.mkdir(parents=True, exist_ok=True)

    return created


def _write_default_config(project_root: Path) -> bool:
    """Write default config.yaml to .arcwright-ai/.

    Uses raw string write to preserve human-readable comments.
    save_yaml() strips comments via yaml.safe_dump — do NOT use it here.

    Args:
        project_root: Project root directory.

    Returns:
        True if the config was created, False if it already existed.
    """
    config_path = project_root / DIR_ARCWRIGHT / CONFIG_FILENAME
    if config_path.exists():
        return False
    config_path.write_text(_DEFAULT_CONFIG_YAML, encoding="utf-8")
    return True


def _update_gitignore(project_root: Path) -> list[str]:
    """Add Arcwright AI entries to .gitignore.

    Handles: missing file (create), existing without entries (append),
    existing with all entries (no-op), existing with partial entries
    (append missing only).

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

    for entry in _GITIGNORE_ENTRIES:
        if entry not in existing_lines:
            added.append(entry)

    if added:
        if existing_content and not existing_content.endswith("\n"):
            existing_content += "\n"
        # Add comment header only if no arcwright entries exist yet
        if not any("arcwright" in line.lower() for line in existing_lines):
            existing_content += "\n# Arcwright AI\n"
        existing_content += "\n".join(added) + "\n"
        gitignore_path.write_text(existing_content, encoding="utf-8")

    return added


def _detect_bmad_artifacts(project_root: Path) -> dict[str, Any]:
    """Scan _spec/ for BMAD planning and implementation artifacts.

    Args:
        project_root: Project root directory.

    Returns:
        Dict with found artifacts by type.  Empty dict if _spec/ missing.
    """
    spec_dir = project_root / DIR_SPEC
    if not spec_dir.exists():
        return {}

    results: dict[str, Any] = {}

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

    impl_dir = spec_dir / "implementation-artifacts"
    if impl_dir.exists():
        story_files = [f for f in impl_dir.glob("*.md") if f.stem[0].isdigit()]
        if story_files:
            results["stories"] = len(story_files)

    return results


# ---------------------------------------------------------------------------
# Init command
# ---------------------------------------------------------------------------


def init_command(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Project root directory",
    ),
) -> None:
    """Initialize a new Arcwright AI project.

    Scaffolds .arcwright-ai/<runs|worktrees|tmp>, writes default
    config.yaml, updates .gitignore, and reports detected BMAD artifacts.

    Args:
        path: Path to the project root directory. Defaults to cwd.
    """
    project_root = Path(path).resolve()

    typer.echo(f"Initializing Arcwright AI in: {project_root}", err=True)

    # Task 1.4 — scaffold directories
    created_dirs = _scaffold_directories(project_root)

    # Task 1.5 — write default config
    config_created = _write_default_config(project_root)

    # Task 1.6 — update .gitignore
    added_gitignore = _update_gitignore(project_root)

    # Task 1.7 — detect BMAD artifacts
    artifacts = _detect_bmad_artifacts(project_root)

    # Task 1.8 — format and display results to stderr (D8)
    typer.echo("", err=True)
    typer.echo(".arcwright-ai/ scaffolded:", err=True)
    if created_dirs:
        for d in created_dirs:
            typer.echo(f"  ✓ Created: {d}/", err=True)
    else:
        typer.echo("  ✓ All directories already exist (idempotent)", err=True)

    if config_created:
        typer.echo(f"  ✓ Created: {CONFIG_FILENAME}", err=True)
    else:
        typer.echo(f"  ✓ Preserved existing: {CONFIG_FILENAME}", err=True)

    typer.echo("", err=True)
    typer.echo(".gitignore:", err=True)
    if added_gitignore:
        for entry in added_gitignore:
            typer.echo(f"  ✓ Added: {entry}", err=True)
    else:
        typer.echo("  ✓ Entries already present (no duplicates added)", err=True)

    typer.echo("", err=True)
    typer.echo("BMAD artifacts detected:", err=True)
    if artifacts:
        if "prd" in artifacts:
            typer.echo(f"  ✓ PRD: {', '.join(artifacts['prd'])}", err=True)
        if "architecture" in artifacts:
            typer.echo(f"  ✓ Architecture: {', '.join(artifacts['architecture'])}", err=True)
        if "epics" in artifacts:
            typer.echo(f"  ✓ Epics: {', '.join(artifacts['epics'])}", err=True)
        if "stories" in artifacts:
            story_count = artifacts["stories"]
            typer.echo(f"  ✓ Stories: {story_count}", err=True)
    else:
        typer.echo("  No BMAD artifacts found in _spec/", err=True)

    typer.echo("", err=True)
    typer.echo("✅ arcwright-ai init complete.", err=True)
    raise typer.Exit(0)


# ---------------------------------------------------------------------------
# Validate-setup helpers
# ---------------------------------------------------------------------------


def _resolve_artifacts_path(project_root: Path) -> str:
    """Determine BMAD artifacts path from project config or default.

    Reads .arcwright-ai/config.yaml for methodology.artifacts_path without
    invoking load_config() (which requires an API key).  Falls back to the
    DIR_SPEC default when the file is absent or malformed.

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
                raw_artifacts_path = methodology.get("artifacts_path", DIR_SPEC)
                if isinstance(raw_artifacts_path, str):
                    artifacts_path = raw_artifacts_path.strip()
                    if artifacts_path and not Path(artifacts_path).is_absolute():
                        return artifacts_path
        except ConfigError:
            pass  # Malformed config — use default
    return DIR_SPEC


def _check_api_key() -> tuple[bool, str]:
    """Check if Claude API key is available.

    Looks for the key in the environment variable first, then in the global
    config file (~/.arcwright-ai/config.yaml).  Never reads project-level
    config (NFR6).

    Returns:
        Tuple of (passed, detail_message).
    """
    env_key = os.environ.get(ENV_API_CLAUDE_API_KEY, "").strip()
    if env_key:
        return True, "present (environment variable)"

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


def _check_project_structure(project_root: Path, artifacts_path: str) -> tuple[bool, str]:
    """Check that the BMAD artifacts directory exists.

    Args:
        project_root: Project root directory.
        artifacts_path: Relative path to the artifacts directory (e.g. "_spec").

    Returns:
        Tuple of (passed, detail_message).
    """
    artifacts_dir = project_root / artifacts_path
    if artifacts_dir.is_dir():
        return True, f"detected at ./{artifacts_path}/"
    return (
        False,
        f"NOT FOUND at ./{artifacts_path}/\n"
        f"   Expected: ./{artifacts_path}/ \u2014 check config.yaml \u2192 methodology.artifacts_path\n"
        f"   Fix: Update .arcwright-ai/config.yaml artifacts_path or move artifacts to ./{artifacts_path}/",
    )


def _check_planning_artifacts(project_root: Path, artifacts_path: str) -> tuple[bool, str]:
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

    for artifact_name, pattern in [
        ("PRD", "*prd*"),
        ("architecture", "*architecture*"),
        ("epics", "*epic*"),
    ]:
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


def _check_story_artifacts(project_root: Path, artifacts_path: str) -> tuple[bool, str]:
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
    missing_ac: list[str] = []
    for sf in story_files:
        try:
            content = sf.read_text(encoding="utf-8")
        except OSError:
            return (
                False,
                f"Could not read story file: {sf.name}\n"
                f"   Fix: Ensure file is readable and valid UTF-8 in {artifacts_path}/implementation-artifacts/",
            )
        if "acceptance criteria" in content.lower():
            with_ac += 1
        else:
            missing_ac.append(sf.name)

    total = len(story_files)
    if with_ac == 0:
        return (
            False,
            f"{total} stories found but none contain acceptance criteria\n"
            "   Fix: Add an 'Acceptance Criteria' section to each story file",
        )

    if missing_ac:
        return (
            True,
            f"{with_ac} of {total} stories with acceptance criteria (missing in: {', '.join(missing_ac)})",
        )

    return True, f"{with_ac} of {total} stories with acceptance criteria"


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
        fix = "Check .arcwright-ai/config.yaml"
        if exc.details and "fix" in exc.details:
            fix = str(exc.details["fix"])
        return False, f"INVALID: {exc.message}\n   Fix: {fix}"


# ---------------------------------------------------------------------------
# Validate-setup command
# ---------------------------------------------------------------------------


def validate_setup_command(
    path: str = typer.Option(
        ".",
        "--path",
        "-p",
        help="Project root directory",
    ),
) -> None:
    """Validate Arcwright AI project setup.

    Runs five checks and reports pass/fail for each: Claude API key,
    BMAD project structure, planning artifacts, story artifacts, and
    config schema validity.  Dependent checks are skipped when their
    prerequisites fail.  Exits 0 if all checks pass, exits 3 if any fail.

    Args:
        path: Path to the project root directory. Defaults to cwd.
    """
    project_root = Path(path).resolve()
    artifacts_path = _resolve_artifacts_path(project_root)

    any_failed = False

    typer.echo("Arcwright AI \u2014 Validate Setup", err=True)
    typer.echo("\u2500" * 38, err=True)
    typer.echo("", err=True)

    # Check 1: API key (independent)
    api_passed, api_detail = _check_api_key()
    if api_passed:
        typer.echo(f"\u2705 Claude API key: {api_detail}", err=True)
    else:
        typer.echo(f"\u274c Claude API key: {api_detail}", err=True)
        any_failed = True

    # Check 2: Project structure (independent)
    struct_passed, struct_detail = _check_project_structure(project_root, artifacts_path)
    if struct_passed:
        typer.echo(f"\u2705 BMAD project structure: {struct_detail}", err=True)
    else:
        typer.echo(f"\u274c BMAD project structure: {struct_detail}", err=True)
        any_failed = True

    # Check 3: Planning artifacts (depends on Check 2)
    if struct_passed:
        plan_passed, plan_detail = _check_planning_artifacts(project_root, artifacts_path)
        if plan_passed:
            typer.echo(f"\u2705 Planning artifacts: {plan_detail}", err=True)
        else:
            typer.echo(f"\u274c Planning artifacts: {plan_detail}", err=True)
            any_failed = True
    else:
        typer.echo(
            "\u26a0\ufe0f  Planning artifacts: Cannot validate \u2014 requires BMAD project structure",
            err=True,
        )

    # Check 4: Story artifacts (depends on Check 2)
    if struct_passed:
        story_passed, story_detail = _check_story_artifacts(project_root, artifacts_path)
        if story_passed:
            typer.echo(f"\u2705 Story artifacts: {story_detail}", err=True)
        else:
            typer.echo(f"\u274c Story artifacts: {story_detail}", err=True)
            any_failed = True
    else:
        typer.echo(
            "\u26a0\ufe0f  Story artifacts: Cannot validate \u2014 requires BMAD project structure",
            err=True,
        )

    # Check 5: Config valid (depends on Check 1 — load_config requires API key)
    if api_passed:
        cfg_passed, cfg_detail = _check_config_valid(project_root)
        if cfg_passed:
            typer.echo(f"\u2705 Arcwright AI config: {cfg_detail}", err=True)
        else:
            typer.echo(f"\u274c Arcwright AI config: {cfg_detail}", err=True)
            any_failed = True
    else:
        typer.echo(
            "\u26a0\ufe0f  Arcwright AI config: Cannot validate \u2014 requires Claude API key",
            err=True,
        )

    typer.echo("", err=True)
    if any_failed:
        typer.echo("Setup validation failed. Fix the issues above and re-run.", err=True)
        raise typer.Exit(code=EXIT_CONFIG)
    else:
        typer.echo("All checks passed. Ready for dispatch.", err=True)
        raise typer.Exit(code=EXIT_SUCCESS)


# ---------------------------------------------------------------------------
# Status command helpers
# ---------------------------------------------------------------------------


def _format_cost_value(value: Any) -> str:
    """Format a budget/cost value for display.

    Returns ``"N/A"`` for zero or empty values; otherwise returns the string
    representation.

    Args:
        value: Raw budget field value (may be None, int, str, Decimal, etc.).

    Returns:
        Human-readable string or ``"N/A"``.
    """
    if value is None or value == 0 or value == "0" or value == "":
        return "N/A"
    return str(value)


def _format_elapsed(start_iso: str, end_iso: str | None = None) -> str:
    """Compute elapsed time between two ISO 8601 timestamps.

    If ``end_iso`` is None the current UTC time is used as the end point.

    Args:
        start_iso: ISO 8601 start timestamp string.
        end_iso: ISO 8601 end timestamp string, or None for "now".

    Returns:
        Human-readable elapsed string in the form ``"Xh Ym Zs"``.
    """
    try:
        start_dt = datetime.fromisoformat(start_iso)
    except ValueError:
        return "unknown"

    if end_iso is not None:
        try:
            end_dt = datetime.fromisoformat(end_iso)
        except ValueError:
            end_dt = datetime.now(tz=UTC)
    else:
        end_dt = datetime.now(tz=UTC)

    # Ensure both are timezone-aware for comparison
    if start_dt.tzinfo is None:
        start_dt = start_dt.replace(tzinfo=UTC)
    if end_dt.tzinfo is None:
        end_dt = end_dt.replace(tzinfo=UTC)

    total_seconds = max(0, int((end_dt - start_dt).total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}h {minutes}m {seconds}s"


def _parse_iso_datetime(timestamp: str) -> datetime | None:
    """Parse an ISO 8601 timestamp into a timezone-aware datetime.

    Args:
        timestamp: ISO 8601 timestamp string.

    Returns:
        Parsed timezone-aware datetime, or None when parsing fails.
    """
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


async def _status_async(project_root: Path, run_id: str | None) -> None:
    """Async implementation of the status command.

    Reads run state from ``run.yaml`` via ``get_run_status()`` and ``list_runs()``,
    then formats and emits run status to stderr.

    Args:
        project_root: Resolved project root directory.
        run_id: Specific run ID to inspect, or None for the latest run.

    Raises:
        typer.Exit: With code 0 on success or when no runs exist; with code 1
            when run_id is not found.
    """
    if run_id is None:
        runs = await list_runs(project_root)
        if not runs:
            typer.echo(
                "No runs found. Use 'arcwright-ai dispatch' to start a run.",
                err=True,
            )
            raise typer.Exit(code=EXIT_SUCCESS)
        resolved_run_id = runs[0].run_id
    else:
        resolved_run_id = run_id

    try:
        run_status = await get_run_status(project_root, resolved_run_id)
    except RunError:
        typer.echo(
            f"Run not found: {resolved_run_id}. Use 'arcwright-ai status' to list recent runs.",
            err=True,
        )
        raise typer.Exit(code=EXIT_VALIDATION) from None

    # Categorize stories
    completed_stories: list[str] = []
    failed_stories: list[str] = []
    pending_stories: list[str] = []
    latest_completed_at: datetime | None = None

    for slug, entry in run_status.stories.items():
        st = entry.status
        if entry.completed_at:
            completed_at_dt = _parse_iso_datetime(entry.completed_at)
            if completed_at_dt and (latest_completed_at is None or completed_at_dt > latest_completed_at):
                latest_completed_at = completed_at_dt

        if st in _COMPLETED_STATUSES:
            completed_stories.append(slug)
        elif st in _FAILED_STATUSES:
            failed_stories.append(slug)
        else:
            pending_stories.append(slug)

    # Compute elapsed time
    is_terminal = run_status.status in (
        RunStatusValue.COMPLETED,
        RunStatusValue.HALTED,
        RunStatusValue.TIMED_OUT,
    )
    elapsed = _format_elapsed(
        run_status.start_time,
        latest_completed_at.isoformat() if is_terminal and latest_completed_at is not None else None,
    )

    # Format budget/cost fields
    budget = run_status.budget
    invocation_count = _format_cost_value(budget.get("invocation_count"))
    total_tokens = _format_cost_value(budget.get("total_tokens"))
    estimated_cost = _format_cost_value(budget.get("estimated_cost"))

    # Build output
    separator = "\u2500" * 38
    total_stories = len(run_status.stories)

    typer.echo("Arcwright AI \u2014 Run Status", err=True)
    typer.echo(separator, err=True)
    typer.echo("", err=True)
    typer.echo(f"  Run ID:    {run_status.run_id}", err=True)
    typer.echo(f"  Status:    {run_status.status.value}", err=True)
    typer.echo(f"  Started:   {run_status.start_time}", err=True)
    typer.echo(f"  Elapsed:   {elapsed}", err=True)
    typer.echo("", err=True)
    typer.echo(f"Stories ({total_stories} total):", err=True)
    if completed_stories:
        typer.echo(f"  \u2713 {len(completed_stories)} completed: {', '.join(completed_stories)}", err=True)
    else:
        typer.echo("  \u2713 0 completed", err=True)
    if failed_stories:
        typer.echo(f"  \u2717 {len(failed_stories)} failed: {', '.join(failed_stories)}", err=True)
    else:
        typer.echo("  \u2717 0 failed", err=True)
    if pending_stories:
        typer.echo(f"  \u25e6 {len(pending_stories)} pending: {', '.join(pending_stories)}", err=True)
    else:
        typer.echo("  \u25e6 0 pending", err=True)
    typer.echo("", err=True)
    typer.echo("Cost:", err=True)
    typer.echo(f"  Invocations: {invocation_count}", err=True)
    typer.echo(f"  Tokens:      {total_tokens}", err=True)
    typer.echo(f"  Est. Cost:   {estimated_cost}", err=True)
    typer.echo("", err=True)


# ---------------------------------------------------------------------------
# Status command
# ---------------------------------------------------------------------------


def status_command(
    run_id: Annotated[
        str | None,
        typer.Argument(help="Run ID to inspect. Shows latest run if omitted."),
    ] = None,
    path: str = typer.Option(".", "--path", "-p", help="Project root directory"),
) -> None:
    """Display status for a live or historical run.

    Without a run-id, shows the most recent run. With a run-id, shows that
    specific run. All output goes to stderr per D8.

    Args:
        run_id: Run identifier to inspect. If omitted, the latest run is shown.
        path: Path to the project root directory. Defaults to cwd.
    """
    project_root = Path(path).resolve()
    asyncio.run(_status_async(project_root, run_id))
