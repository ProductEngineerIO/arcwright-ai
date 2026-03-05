"""CLI dispatch — Routes CLI dispatch commands to engine operations."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Annotated

import typer

from arcwright_ai.core.config import RunConfig, load_config
from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT,
    DIR_RUNS,
    EXIT_AGENT,
    EXIT_CONFIG,
    EXIT_INTERNAL,
    EXIT_SCM,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    LOG_FILENAME,
)
from arcwright_ai.core.exceptions import (
    AgentError,
    ArcwrightError,
    ConfigError,
    ContextError,
    ProjectError,
    ScmError,
    ValidationError,
)
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import BudgetState, EpicId, StoryId
from arcwright_ai.engine.graph import build_story_graph
from arcwright_ai.engine.state import ProjectState, StoryState
from arcwright_ai.output.run_manager import (
    RunStatusValue,
    create_run,
    generate_run_id,
    update_run_status,
    update_story_status,
)

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


def _halt_reason_from_exit_code(exit_code: int) -> str:
    """Map an exit code to a human-readable halt reason string.

    Args:
        exit_code: CLI exit code from dispatch execution.

    Returns:
        Human-readable halt reason.
    """
    if exit_code == EXIT_VALIDATION:
        return "validation failure"
    if exit_code == EXIT_AGENT:
        return "agent/budget failure"
    if exit_code == EXIT_CONFIG:
        return "config/context failure"
    if exit_code == EXIT_SCM:
        return "SCM failure"
    return "internal failure"


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
    """Discover the project root by walking up from the current working directory.

    Searches cwd and each parent for .arcwright-ai/ or _spec/ markers.
    Stops at the filesystem root.

    Returns:
        Path to the project root.

    Raises:
        ProjectError: If no project root markers are found in cwd or any parent.
    """
    candidate = Path.cwd().resolve()
    while True:
        if (candidate / DIR_ARCWRIGHT).exists() or (candidate / "_spec").exists():
            return candidate
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent
    raise ProjectError(
        f"Could not find project root from {Path.cwd()}. "
        "Ensure .arcwright-ai/ or _spec/ exists in the current directory or a parent directory."
    )


def _show_dispatch_confirmation(
    epic_spec: str,
    stories: list[tuple[Path, StoryId, EpicId]],
    config: RunConfig,
    *,
    skip_confirm: bool = False,
) -> None:
    """Display a pre-dispatch summary and prompt the user to confirm.

    Shows story count, execution order, configured budget ceilings, and an
    estimated cost range.  Calls :func:`typer.confirm` with ``abort=True`` so
    that a rejection raises :exc:`typer.Abort` at the call site.

    Args:
        epic_spec: Epic identifier string used in the confirmation header.
        stories: Ordered list of ``(story_path, StoryId, EpicId)`` tuples.
        config: Fully-loaded run configuration for budget ceiling display.
        skip_confirm: When ``True`` the function returns immediately without
            prompting (equivalent to passing ``--yes``).
    """
    if skip_confirm:
        return

    story_count = len(stories)
    typer.echo(f"\n\U0001f4cb Epic Dispatch Plan \u2014 {epic_spec}", err=True)
    typer.echo(f"   Stories to dispatch: {story_count}", err=True)
    typer.echo("   Execution order:", err=True)
    for _, story_id, _ in stories:
        typer.echo(f"     \u2022 {story_id}", err=True)
    typer.echo("\n   Budget ceilings:", err=True)
    typer.echo(f"     cost_per_run:     ${config.limits.cost_per_run}", err=True)
    typer.echo(f"     tokens_per_story: {config.limits.tokens_per_story:,}", err=True)
    typer.echo(f"     retry_budget:     {config.limits.retry_budget}", err=True)
    typer.echo(
        "\n   Estimated cost range: $?.?? - $?.?? (no historical data available)",
        err=True,
    )
    typer.confirm("\nProceed with dispatch?", abort=True)


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

    run_id = generate_run_id()
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


async def _dispatch_epic_async(epic_spec: str, *, skip_confirm: bool = False) -> int:
    """Dispatch all stories in an epic sequentially with full run lifecycle management.

    Validates the epic scope, shows a pre-dispatch confirmation (unless
    ``skip_confirm`` is set), creates a run directory via
    :func:`~arcwright_ai.output.run_manager.create_run`, then dispatches each
    story in dependency order.  Budget state is accumulated across stories so
    run-level cost ceilings are enforced by the ``budget_check`` node.  On any
    non-SUCCESS terminal status the loop halts and the run is marked HALTED.

    Args:
        epic_spec: Epic identifier string (e.g., "2" or "epic-2").
        skip_confirm: When ``True`` the pre-dispatch confirmation prompt is
            skipped entirely (equivalent to the ``--yes`` CLI flag).

    Returns:
        Exit code (0 for all stories succeeded, non-zero on first failure or
        user cancellation).
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

    try:
        _show_dispatch_confirmation(epic_spec, stories, config, skip_confirm=skip_confirm)
    except typer.Abort:
        typer.echo("\nDispatch cancelled by user.", err=True)
        return EXIT_SUCCESS

    run_id = generate_run_id()
    story_slugs = [str(story_id) for _, story_id, _ in stories]

    try:
        run_dir = await create_run(project_root, run_id, config, story_slugs)
    except Exception as exc:
        typer.echo(f"✗ Failed to create run: {exc}", err=True)
        return EXIT_CONFIG

    try:
        await update_run_status(project_root, str(run_id), status=RunStatusValue.RUNNING)
    except Exception:
        logger.warning(
            "run_manager.write_error",
            extra={"data": {"operation": "update_run_status", "status": "RUNNING"}},
        )

    handler, previous_level = _setup_run_logging(run_dir)
    try:
        root_logger = logging.getLogger("arcwright_ai")
        root_logger.info("run.start", extra={"data": {"run_id": str(run_id), "epic": epic_spec}})

        typer.echo(f"▶ Dispatching {len(stories)} stories from epic {epic_spec}...", err=True)
        typer.echo(f"  Run: {run_id}", err=True)

        initial_story_states = [
            StoryState(
                story_id=story_id,
                epic_id=epic_id,
                run_id=run_id,
                story_path=story_path,
                project_root=project_root,
                status=TaskState.QUEUED,
                config=config,
                budget=BudgetState(
                    max_invocations=0,
                    max_cost=Decimal(str(config.limits.cost_per_run)),
                ),
            )
            for story_path, story_id, epic_id in stories
        ]
        project_state = ProjectState(
            epic_id=initial_story_states[0].epic_id,
            run_id=run_id,
            stories=initial_story_states,
            config=config,
        )
        accumulated_budget = project_state.stories[0].budget
        last_completed: str | None = None
        completed_stories: list[str] = []

        for idx, story_state in enumerate(project_state.stories):
            project_state.current_story_index = idx
            story_id = story_state.story_id
            epic_id = story_state.epic_id
            story_slug = str(story_id)

            try:
                await update_story_status(
                    project_root,
                    str(run_id),
                    story_slug,
                    status="running",
                    started_at=datetime.now(tz=UTC).isoformat(),
                )
            except Exception:
                logger.warning(
                    "run_manager.write_error",
                    extra={"data": {"operation": "update_story_status", "story": story_slug}},
                )

            root_logger.info("story.start", extra={"data": {"story": story_slug, "epic": str(epic_id)}})
            typer.echo(f"\n▶ [{idx + 1}/{len(stories)}] Dispatching story {story_id}...", err=True)

            initial_state = story_state.model_copy(update={"budget": accumulated_budget})

            try:
                graph = build_story_graph()
                result = await graph.ainvoke(initial_state)

                raw_status = result.get("status") if isinstance(result, dict) else result.status
                final_status = _coerce_task_state(raw_status)
                result_budget = result.get("budget") if isinstance(result, dict) else result.budget
                if result_budget is not None:
                    accumulated_budget = result_budget
                project_state.stories[idx] = initial_state.model_copy(
                    update={"status": final_status or TaskState.ESCALATED, "budget": accumulated_budget}
                )

                exit_code = _exit_code_for_terminal_status(final_status)

                typer.echo(f"  ✓ Story {story_id} completed (status: {final_status})", err=True)
                typer.echo(
                    f"  💰 Cost: ${accumulated_budget.estimated_cost} | Tokens: {accumulated_budget.total_tokens}",
                    err=True,
                )

                if exit_code != EXIT_SUCCESS:
                    halt_reason = _halt_reason_from_exit_code(exit_code)
                    typer.echo(
                        f"✗ Story {story_id} ended non-successfully (status: {final_status})",
                        err=True,
                    )
                    try:
                        await update_run_status(
                            project_root,
                            str(run_id),
                            status=RunStatusValue.HALTED,
                            last_completed_story=last_completed,
                            budget=accumulated_budget,
                        )
                    except Exception:
                        logger.warning(
                            "run_manager.write_error",
                            extra={"data": {"operation": "update_run_status", "status": "HALTED"}},
                        )
                    root_logger.info(
                        "run.halt",
                        extra={"data": {"halted_story": story_slug, "reason": halt_reason}},
                    )
                    typer.echo(f"\n✗ Epic {epic_spec} halted at story {story_id}.", err=True)
                    typer.echo(f"  Stories completed ({len(completed_stories)}): {completed_stories}", err=True)
                    typer.echo(f"  Halt reason: {halt_reason}", err=True)
                    typer.echo(
                        f"  💰 Total cost: ${accumulated_budget.estimated_cost}"
                        f" | Total tokens: {accumulated_budget.total_tokens}",
                        err=True,
                    )
                    typer.echo(
                        f"  🔁 Resume with: arcwright-ai dispatch --epic {epic_spec} --resume",
                        err=True,
                    )
                    return exit_code

                last_completed = story_slug
                completed_stories.append(story_slug)
                project_state.completed_stories = len(completed_stories)

            except ScmError as exc:
                typer.echo(f"✗ Story {story_id} failed (SCM error): {exc}", err=True)
                try:
                    await update_run_status(
                        project_root,
                        str(run_id),
                        status=RunStatusValue.HALTED,
                        last_completed_story=last_completed,
                        budget=accumulated_budget,
                    )
                except Exception:
                    logger.warning(
                        "run_manager.write_error",
                        extra={"data": {"operation": "update_run_status"}},
                    )
                root_logger.info(
                    "run.halt",
                    extra={"data": {"halted_story": story_slug, "reason": str(exc)}},
                )
                return EXIT_SCM

            except ValidationError as exc:
                typer.echo(f"✗ Story {story_id} failed (validation error): {exc}", err=True)
                try:
                    await update_run_status(
                        project_root,
                        str(run_id),
                        status=RunStatusValue.HALTED,
                        last_completed_story=last_completed,
                        budget=accumulated_budget,
                    )
                except Exception:
                    logger.warning(
                        "run_manager.write_error",
                        extra={"data": {"operation": "update_run_status"}},
                    )
                root_logger.info(
                    "run.halt",
                    extra={"data": {"halted_story": story_slug, "reason": str(exc)}},
                )
                return EXIT_VALIDATION

            except AgentError as exc:
                typer.echo(f"✗ Story {story_id} failed (agent error): {exc}", err=True)
                try:
                    await update_run_status(
                        project_root,
                        str(run_id),
                        status=RunStatusValue.HALTED,
                        last_completed_story=last_completed,
                        budget=accumulated_budget,
                    )
                except Exception:
                    logger.warning(
                        "run_manager.write_error",
                        extra={"data": {"operation": "update_run_status"}},
                    )
                root_logger.info(
                    "run.halt",
                    extra={"data": {"halted_story": story_slug, "reason": str(exc)}},
                )
                return EXIT_AGENT

            except (ContextError, ConfigError, ProjectError) as exc:
                typer.echo(f"✗ Story {story_id} failed (config/context error): {exc}", err=True)
                try:
                    await update_run_status(
                        project_root,
                        str(run_id),
                        status=RunStatusValue.HALTED,
                        last_completed_story=last_completed,
                        budget=accumulated_budget,
                    )
                except Exception:
                    logger.warning(
                        "run_manager.write_error",
                        extra={"data": {"operation": "update_run_status"}},
                    )
                root_logger.info(
                    "run.halt",
                    extra={"data": {"halted_story": story_slug, "reason": str(exc)}},
                )
                return EXIT_CONFIG

            except ArcwrightError as exc:
                typer.echo(f"✗ Story {story_id} failed (internal error): {exc}", err=True)
                try:
                    await update_run_status(
                        project_root,
                        str(run_id),
                        status=RunStatusValue.HALTED,
                        last_completed_story=last_completed,
                        budget=accumulated_budget,
                    )
                except Exception:
                    logger.warning(
                        "run_manager.write_error",
                        extra={"data": {"operation": "update_run_status"}},
                    )
                root_logger.info(
                    "run.halt",
                    extra={"data": {"halted_story": story_slug, "reason": str(exc)}},
                )
                return EXIT_INTERNAL

            except Exception as exc:
                typer.echo(f"✗ Story {story_id} failed (unexpected): {exc}", err=True)
                try:
                    await update_run_status(
                        project_root,
                        str(run_id),
                        status=RunStatusValue.HALTED,
                        last_completed_story=last_completed,
                        budget=accumulated_budget,
                    )
                except Exception:
                    logger.warning(
                        "run_manager.write_error",
                        extra={"data": {"operation": "update_run_status"}},
                    )
                root_logger.info(
                    "run.halt",
                    extra={"data": {"halted_story": story_slug, "reason": str(exc)}},
                )
                return EXIT_INTERNAL

        # All stories completed successfully
        try:
            await update_run_status(
                project_root,
                str(run_id),
                status=RunStatusValue.COMPLETED,
                last_completed_story=last_completed,
                budget=accumulated_budget,
            )
        except Exception:
            logger.warning(
                "run_manager.write_error",
                extra={"data": {"operation": "update_run_status", "status": "COMPLETED"}},
            )

        root_logger.info(
            "run.complete",
            extra={
                "data": {
                    "story_count": len(stories),
                    "total_cost": str(accumulated_budget.estimated_cost),
                }
            },
        )

        typer.echo(f"\n✓ Epic {epic_spec} complete — {len(stories)} stories dispatched.", err=True)
        typer.echo(
            f"  💰 Total cost: ${accumulated_budget.estimated_cost} | Total tokens: {accumulated_budget.total_tokens}",
            err=True,
        )
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
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip pre-dispatch confirmation")] = False,
) -> None:
    """Dispatch a story or epic for AI agent execution.

    Args:
        story: Story identifier (e.g., 2.7 or 2-7).
        epic: Epic identifier (e.g., 2 or epic-2).
        yes: When set, skip the pre-dispatch confirmation prompt for epic
            dispatch.
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
        code = asyncio.run(_dispatch_epic_async(epic, skip_confirm=yes))
    raise typer.Exit(code=code)
