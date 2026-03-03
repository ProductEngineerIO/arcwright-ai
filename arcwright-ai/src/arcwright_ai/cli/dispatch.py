"""CLI dispatch — Routes CLI dispatch commands to engine operations."""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

import typer

from arcwright_ai.core.config import load_config
from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT,
    DIR_RUNS,
    EXIT_AGENT,
    EXIT_CONFIG,
    EXIT_INTERNAL,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    LOG_FILENAME,
    RUN_ID_DATETIME_FORMAT,
)
from arcwright_ai.core.exceptions import AgentError, ArcwrightError, ConfigError, ContextError, ProjectError
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import EpicId, RunId, StoryId
from arcwright_ai.engine.graph import build_story_graph
from arcwright_ai.engine.state import StoryState

__all__: list[str] = ["dispatch_command"]

logger = logging.getLogger(__name__)


class _JsonlFileHandler(logging.FileHandler):
    """Structured JSONL file handler per Decision 8.

    Captures structured log events from arcwright_ai.* loggers and writes
    them as JSON Lines to the run's log.jsonl file using the D8 envelope
    format: {ts, event, level, data}.

    Args:
        filename: Path to the JSONL log file.
    """

    def emit(self, record: logging.LogRecord) -> None:
        """Write a log record as a JSON Line to the log file.

        Args:
            record: The log record to write.
        """
        try:
            data = getattr(record, "data", {})
            entry = {
                "ts": datetime.now(UTC).isoformat(),
                "event": record.getMessage(),
                "level": record.levelname.lower(),
                "data": data if isinstance(data, dict) else {},
            }
            self.stream.write(json.dumps(entry) + "\n")
            self.flush()
        except Exception:
            self.handleError(record)


def _setup_run_logging(run_dir: Path) -> tuple[_JsonlFileHandler, int]:
    """Attach a JSONL file handler to the arcwright_ai root logger.

    Creates the handler pointing to run_dir/log.jsonl and attaches it to
    the arcwright_ai root logger so all child logger events propagate.
    Sets the logger level to DEBUG so all structured events are captured.

    Args:
        run_dir: Path to the run directory where log.jsonl will be written.

    Returns:
        Tuple of (created handler, previous logger level).
    """
    handler = _JsonlFileHandler(run_dir / LOG_FILENAME)
    handler.setLevel(logging.DEBUG)
    arcwright_logger = logging.getLogger("arcwright_ai")
    previous_level = arcwright_logger.level
    arcwright_logger.setLevel(logging.DEBUG)
    arcwright_logger.addHandler(handler)
    return handler, previous_level


def _coerce_task_state(raw_status: object) -> TaskState | None:
    """Normalize a graph result status value into TaskState.

    Args:
        raw_status: Status value from graph output.

    Returns:
        TaskState value when coercion is possible, otherwise None.
    """
    if isinstance(raw_status, TaskState):
        return raw_status
    if isinstance(raw_status, str):
        try:
            return TaskState(raw_status)
        except ValueError:
            return None
    return None


def _exit_code_for_terminal_status(status: TaskState | None) -> int:
    """Map terminal graph status to CLI exit code.

    Args:
        status: Final task status returned by graph.

    Returns:
        Exit code aligned with the CLI taxonomy.
    """
    if status == TaskState.SUCCESS:
        return EXIT_SUCCESS
    if status == TaskState.ESCALATED:
        return EXIT_AGENT
    if status == TaskState.RETRY:
        return EXIT_VALIDATION
    return EXIT_INTERNAL


def _generate_run_id() -> RunId:
    """Generate a unique run identifier.

    Format: YYYYMMDD-HHMMSS-<short-uuid> (e.g., 20260302-143052-a7f3).

    Returns:
        A unique RunId with datetime and short UUID suffix.
    """
    dt = datetime.now(UTC).strftime(RUN_ID_DATETIME_FORMAT)
    short_uuid = uuid.uuid4().hex[:4]
    return RunId(f"{dt}-{short_uuid}")


def _find_story_file(story_spec: str, artifacts_dir: Path) -> tuple[Path, StoryId, EpicId]:
    """Find a story file by story specification string.

    Parses story_spec in formats "2.7" or "2-7" to extract epic and story
    numbers, then globs for the matching story file.

    Args:
        story_spec: Story identifier string (e.g., "2.7" or "2-7").
        artifacts_dir: Directory containing implementation artifact files.

    Returns:
        Tuple of (story_path, StoryId, EpicId).

    Raises:
        ProjectError: If the story file cannot be found or spec is invalid.
    """
    normalized = story_spec.replace(".", "-")
    parts = normalized.split("-")
    if len(parts) < 2:
        raise ProjectError(f"Invalid story spec: {story_spec!r}. Expected format: '2.7' or '2-7'")
    epic_num = parts[0]
    story_num = parts[1]

    matches = list(artifacts_dir.glob(f"{epic_num}-{story_num}-*.md"))
    if not matches:
        raise ProjectError(f"No story file found for {story_spec!r} in {artifacts_dir}")
    story_path = matches[0]
    stem = story_path.stem
    return story_path, StoryId(stem), EpicId(f"epic-{epic_num}")


def _find_epic_stories(epic_spec: str, artifacts_dir: Path) -> list[tuple[Path, StoryId, EpicId]]:
    """Find all story files for an epic, sorted by story number.

    Parses epic_spec in formats "2" or "epic-2" to extract the epic number,
    then globs for all matching story files (excluding retrospectives).

    Args:
        epic_spec: Epic identifier string (e.g., "2" or "epic-2").
        artifacts_dir: Directory containing implementation artifact files.

    Returns:
        Sorted list of (story_path, StoryId, EpicId) tuples ordered by
        story number.

    Raises:
        ProjectError: If no story files are found for the epic.
    """
    epic_num = epic_spec[5:] if epic_spec.startswith("epic-") else epic_spec

    matches = [p for p in artifacts_dir.glob(f"{epic_num}-*-*.md") if "retrospective" not in p.stem]

    if not matches:
        raise ProjectError(f"No story files found for epic {epic_spec!r} in {artifacts_dir}")

    def _story_num(p: Path) -> int:
        stem_parts = p.stem.split("-")
        try:
            return int(stem_parts[1])
        except (IndexError, ValueError):
            return 0

    matches.sort(key=_story_num)

    epic_id = EpicId(f"epic-{epic_num}")
    return [(p, StoryId(p.stem), epic_id) for p in matches]


def _discover_project_root() -> Path:
    """Discover the project root from the current working directory.

    Searches cwd for .arcwright-ai/ or _spec/ markers.

    Returns:
        Path to the project root.

    Raises:
        ProjectError: If no project root markers are found in cwd.
    """
    cwd = Path.cwd()
    if (cwd / DIR_ARCWRIGHT).exists() or (cwd / "_spec").exists():
        return cwd
    raise ProjectError(
        f"Could not find project root from {cwd}. Ensure .arcwright-ai/ or _spec/ exists in the current directory."
    )


async def _dispatch_story_async(story_spec: str) -> int:
    """Dispatch a single story for agent execution.

    Discovers project root, loads config, finds the story file, sets up the
    run directory and JSONL logging, creates initial state, invokes the
    LangGraph pipeline, and reports results.

    Args:
        story_spec: Story identifier string (e.g., "2.7" or "2-7").

    Returns:
        Exit code (0 for success, non-zero for errors).
    """
    try:
        project_root = _discover_project_root()
    except ProjectError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return EXIT_CONFIG

    try:
        config = load_config(project_root)
    except ConfigError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        return EXIT_CONFIG

    artifacts_dir = project_root / config.methodology.artifacts_path / "implementation-artifacts"

    try:
        story_path, story_id, epic_id = _find_story_file(story_spec, artifacts_dir)
    except ProjectError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return EXIT_CONFIG

    run_id = _generate_run_id()
    run_dir = project_root / DIR_ARCWRIGHT / DIR_RUNS / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    handler, previous_level = _setup_run_logging(run_dir)
    try:
        root_logger = logging.getLogger("arcwright_ai")
        root_logger.info("run.start", extra={"data": {"run_id": str(run_id), "story": str(story_id)}})
        root_logger.info("story.start", extra={"data": {"story": str(story_id), "epic": str(epic_id)}})

        typer.echo(f"▶ Dispatching story {story_id}...", err=True)
        typer.echo(f"  Run: {run_id}", err=True)
        typer.echo(f"  🤖 Agent invoked ({config.model.version})", err=True)

        initial_state = StoryState(
            story_id=story_id,
            epic_id=epic_id,
            run_id=run_id,
            story_path=story_path,
            project_root=project_root,
            config=config,
        )

        graph = build_story_graph()
        result = await graph.ainvoke(initial_state)

        raw_status = result.get("status") if isinstance(result, dict) else result.status
        final_status = _coerce_task_state(raw_status)
        budget = result.get("budget") if isinstance(result, dict) else result.budget
        exit_code = _exit_code_for_terminal_status(final_status)

        typer.echo(f"✓ Story {story_id} completed (status: {final_status})", err=True)
        if budget is not None:
            typer.echo(f"  💰 Cost: ${budget.estimated_cost} | Tokens: {budget.total_tokens}", err=True)
        typer.echo(f"  📁 Run: {run_dir}", err=True)

        if exit_code != EXIT_SUCCESS:
            typer.echo(f"✗ Story {story_id} ended non-successfully (status: {final_status})", err=True)
        return exit_code

    except ContextError as exc:
        typer.echo(f"Context error: {exc}", err=True)
        return EXIT_CONFIG
    except AgentError as exc:
        typer.echo(f"Agent error: {exc}", err=True)
        return EXIT_AGENT
    except ArcwrightError as exc:
        typer.echo(f"Internal error: {exc}", err=True)
        return EXIT_INTERNAL
    except Exception as exc:
        typer.echo(f"Unexpected error: {exc}", err=True)
        return EXIT_INTERNAL
    finally:
        arcwright_logger = logging.getLogger("arcwright_ai")
        arcwright_logger.removeHandler(handler)
        arcwright_logger.setLevel(previous_level)
        handler.close()


async def _dispatch_epic_async(epic_spec: str) -> int:
    """Dispatch all stories in an epic sequentially in dependency order.

    Finds all stories for the epic, generates a shared run ID, and dispatches
    each story sorted by story number.

    Args:
        epic_spec: Epic identifier string (e.g., "2" or "epic-2").

    Returns:
        Exit code (0 for all success, non-zero on first failure).
    """
    try:
        project_root = _discover_project_root()
    except ProjectError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return EXIT_CONFIG

    try:
        config = load_config(project_root)
    except ConfigError as exc:
        typer.echo(f"Configuration error: {exc}", err=True)
        return EXIT_CONFIG

    artifacts_dir = project_root / config.methodology.artifacts_path / "implementation-artifacts"

    try:
        stories = _find_epic_stories(epic_spec, artifacts_dir)
    except ProjectError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return EXIT_CONFIG

    run_id = _generate_run_id()
    run_dir = project_root / DIR_ARCWRIGHT / DIR_RUNS / str(run_id)
    run_dir.mkdir(parents=True, exist_ok=True)

    handler, previous_level = _setup_run_logging(run_dir)
    try:
        root_logger = logging.getLogger("arcwright_ai")
        root_logger.info("run.start", extra={"data": {"run_id": str(run_id), "epic": epic_spec}})

        typer.echo(f"▶ Dispatching {len(stories)} stories from epic {epic_spec}...", err=True)
        typer.echo(f"  Run: {run_id}", err=True)

        for story_path, story_id, epic_id in stories:
            root_logger.info("story.start", extra={"data": {"story": str(story_id), "epic": str(epic_id)}})
            typer.echo(f"\n▶ Dispatching story {story_id}...", err=True)

            initial_state = StoryState(
                story_id=story_id,
                epic_id=epic_id,
                run_id=run_id,
                story_path=story_path,
                project_root=project_root,
                config=config,
            )

            graph = build_story_graph()
            try:
                result = await graph.ainvoke(initial_state)
                raw_status = result.get("status") if isinstance(result, dict) else result.status
                final_status = _coerce_task_state(raw_status)
                budget = result.get("budget") if isinstance(result, dict) else result.budget
                typer.echo(f"✓ Story {story_id} completed (status: {final_status})", err=True)
                if budget is not None:
                    typer.echo(f"  💰 Cost: ${budget.estimated_cost} | Tokens: {budget.total_tokens}", err=True)
                exit_code = _exit_code_for_terminal_status(final_status)
                if exit_code != EXIT_SUCCESS:
                    typer.echo(f"✗ Story {story_id} ended non-successfully (status: {final_status})", err=True)
                    return exit_code
            except AgentError as exc:
                typer.echo(f"✗ Story {story_id} failed (agent error): {exc}", err=True)
                return EXIT_AGENT
            except (ContextError, ConfigError) as exc:
                typer.echo(f"✗ Story {story_id} failed (config/context error): {exc}", err=True)
                return EXIT_CONFIG
            except ArcwrightError as exc:
                typer.echo(f"✗ Story {story_id} failed (internal error): {exc}", err=True)
                return EXIT_INTERNAL
            except Exception as exc:
                typer.echo(f"✗ Story {story_id} failed (unexpected): {exc}", err=True)
                return EXIT_INTERNAL

        typer.echo(f"\n✓ Epic {epic_spec} complete — {len(stories)} stories dispatched.", err=True)
        typer.echo(f"  📁 Run: {run_dir}", err=True)
        return EXIT_SUCCESS

    finally:
        arcwright_logger = logging.getLogger("arcwright_ai")
        arcwright_logger.removeHandler(handler)
        arcwright_logger.setLevel(previous_level)
        handler.close()


def dispatch_command(
    story: Annotated[str | None, typer.Option("--story", help="Story identifier (e.g., 2.7 or 2-7)")] = None,
    epic: Annotated[str | None, typer.Option("--epic", help="Epic identifier (e.g., 2 or epic-2)")] = None,
) -> None:
    """Dispatch a story or epic for AI agent execution.

    Args:
        story: Story identifier (e.g., 2.7 or 2-7).
        epic: Epic identifier (e.g., 2 or epic-2).
    """
    if story and epic:
        typer.echo("Error: specify --story or --epic, not both.", err=True)
        raise typer.Exit(code=1)
    if not story and not epic:
        typer.echo("Error: specify --story or --epic.", err=True)
        raise typer.Exit(code=1)
    if story:
        code = asyncio.run(_dispatch_story_async(story))
    else:
        assert epic is not None  # narrowing: validated above
        code = asyncio.run(_dispatch_epic_async(epic))
    raise typer.Exit(code=code)
