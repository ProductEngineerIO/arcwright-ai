"""CLI status — Sprint and run status display commands.

Contains: init command for scaffolding .arcwright-ai/ project directory.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer

from arcwright_ai.core.constants import (
    CONFIG_FILENAME,
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_SPEC,
    DIR_TMP,
    DIR_WORKTREES,
)

__all__: list[str] = [
    "init_command",
]

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
