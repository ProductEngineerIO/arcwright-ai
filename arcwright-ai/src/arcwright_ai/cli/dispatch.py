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

from arcwright_ai.cli.halt import HaltController
from arcwright_ai.cli.resume import (
    _find_latest_run_for_epic,
    _reconstruct_budget_from_dict,
    _show_resume_confirmation,
)
from arcwright_ai.core.config import RunConfig, load_config
from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT,
    EXIT_AGENT,
    EXIT_CONFIG,
    EXIT_INTERNAL,
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
from arcwright_ai.output.summary import write_success_summary

__all__: list[str] = ["dispatch_command"]

logger = logging.getLogger(__name__)


def _sdk_error_types() -> tuple[type[BaseException], ...]:
    """Return exception types treated as SDK communication/response errors.

    Returns:
        Tuple of exception classes that should be wrapped into ``AgentError``
        with SDK context before routing through ``HaltController``.
    """
    error_types: tuple[type[BaseException], ...] = (
        TimeoutError,
        ConnectionError,
        json.JSONDecodeError,
    )
    try:
        import httpx

        error_types = (*error_types, httpx.HTTPStatusError)
    except ImportError:
        pass
    return error_types


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

    try:
        run_dir = await create_run(project_root, run_id, config, [str(story_id)])
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


async def _dispatch_epic_async(epic_spec: str, *, skip_confirm: bool = False, resume: bool = False) -> int:
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
        resume: When ``True`` the controller finds the most recent halted run
            for the epic, filters out already-completed stories, carries the
            accumulated budget forward, and dispatches only the remaining
            stories in a new run.

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
        all_stories = _find_epic_stories(epic_spec, artifacts_dir)
    except ProjectError as exc:
        typer.echo(f"Error: {exc}", err=True)
        return EXIT_CONFIG

    # --- Resume branch ---
    stories: list[tuple[Path, StoryId, EpicId]]
    accumulated_budget_init: BudgetState
    # original_run_id_str is set in the resume branch; None for normal dispatch.
    # It is accessible outside the branch so halt/success handlers can thread it through.
    original_run_id_str: str | None = None
    if resume:
        prior_run = await _find_latest_run_for_epic(project_root, epic_spec)
        if prior_run is None:
            epic_num = epic_spec[5:] if epic_spec.startswith("epic-") else epic_spec
            typer.echo(
                f"No previous run found for epic {epic_spec}. "
                f"Use `arcwright-ai dispatch --epic {epic_num}` without --resume.",
                err=True,
            )
            return EXIT_CONFIG

        original_run_id_str, prior_status = prior_run

        if prior_status.status == RunStatusValue.COMPLETED:
            typer.echo(
                f"Run {original_run_id_str} for epic {epic_spec} already completed. All stories passed.",
                err=True,
            )
            return EXIT_SUCCESS

        if prior_status.status != RunStatusValue.HALTED:
            typer.echo(
                f"Run {original_run_id_str} for epic {epic_spec} is {prior_status.status.value}, not halted. "
                "Only halted runs can be resumed.",
                err=True,
            )
            return EXIT_CONFIG

        completed_slugs = [slug for slug, entry in prior_status.stories.items() if entry.status == "success"]
        completed_set = set(completed_slugs)
        stories = [(p, sid, eid) for p, sid, eid in all_stories if str(sid) not in completed_set]

        if not stories:
            typer.echo(
                f"Run {original_run_id_str} for epic {epic_spec} already completed. All stories passed.",
                err=True,
            )
            return EXIT_SUCCESS

        accumulated_budget_init = _reconstruct_budget_from_dict(prior_status.budget, config)

        try:
            _show_resume_confirmation(
                epic_spec=epic_spec,
                original_run_id=original_run_id_str,
                completed_slugs=completed_slugs,
                remaining_stories=stories,
                carried_budget=accumulated_budget_init,
                config=config,
                skip_confirm=skip_confirm,
            )
        except typer.Abort:
            typer.echo("\nResume cancelled by user.", err=True)
            return EXIT_SUCCESS
    else:
        # --- Normal dispatch branch ---
        stories = all_stories
        try:
            _show_dispatch_confirmation(epic_spec, stories, config, skip_confirm=skip_confirm)
        except typer.Abort:
            typer.echo("\nDispatch cancelled by user.", err=True)
            return EXIT_SUCCESS
        accumulated_budget_init = BudgetState(
            max_invocations=0,
            max_cost=Decimal(str(config.limits.cost_per_run)),
        )

    run_id = generate_run_id()
    story_slugs = [str(story_id) for _, story_id, _ in stories]

    try:
        run_dir = await create_run(project_root, run_id, config, story_slugs)
    except Exception as exc:
        typer.echo(f"✗ Failed to create run: {exc}", err=True)
        return EXIT_CONFIG

    halt_controller = HaltController(
        project_root=project_root,
        run_id=str(run_id),
        epic_spec=epic_spec,
        previous_run_id=original_run_id_str,
    )

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
        accumulated_budget = accumulated_budget_init
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
                # NFR3: Wrap SDK-level communication failures as AgentError so they
                # route through the halt controller, not the OS exception handler.
                try:
                    result = await graph.ainvoke(initial_state)
                except _sdk_error_types() as nfr3_exc:
                    logger.debug(
                        "SDK communication failure, wrapping as AgentError",
                        exc_info=True,
                        extra={
                            "data": {
                                "original_error": type(nfr3_exc).__name__,
                                "story": str(story_id),
                                "retry_count": initial_state.retry_count,
                                "budget_invocations": initial_state.budget.invocation_count,
                                "budget_tokens": initial_state.budget.total_tokens,
                                "budget_cost": str(initial_state.budget.estimated_cost),
                            }
                        },
                    )
                    raise AgentError(
                        f"SDK communication failure: {nfr3_exc}",
                        details={
                            "error_category": "sdk",
                            "original_error": type(nfr3_exc).__name__,
                            "story": str(story_id),
                            "retry_count": initial_state.retry_count,
                            "budget": {
                                "invocation_count": initial_state.budget.invocation_count,
                                "total_tokens": initial_state.budget.total_tokens,
                                "estimated_cost": str(initial_state.budget.estimated_cost),
                            },
                        },
                    ) from nfr3_exc

                raw_status = result.get("status") if isinstance(result, dict) else result.status
                final_status = _coerce_task_state(raw_status)
                result_budget = result.get("budget") if isinstance(result, dict) else result.budget
                if result_budget is not None:
                    accumulated_budget = result_budget

                # Build final story state, extracting richer context for halt handling.
                if isinstance(result, StoryState):
                    final_story_state = result.model_copy(
                        update={"status": final_status or TaskState.ESCALATED, "budget": accumulated_budget}
                    )
                else:
                    final_story_state = initial_state.model_copy(
                        update={"status": final_status or TaskState.ESCALATED, "budget": accumulated_budget}
                    )
                project_state.stories[idx] = final_story_state

                exit_code = _exit_code_for_terminal_status(final_status)

                typer.echo(f"  ✓ Story {story_id} completed (status: {final_status})", err=True)
                typer.echo(
                    f"  💰 Cost: ${accumulated_budget.estimated_cost} | Tokens: {accumulated_budget.total_tokens}",
                    err=True,
                )

                if exit_code != EXIT_SUCCESS:
                    typer.echo(
                        f"✗ Story {story_id} ended non-successfully (status: {final_status})",
                        err=True,
                    )
                    exit_code = await halt_controller.handle_graph_halt(
                        story_state=project_state.stories[idx],
                        accumulated_budget=accumulated_budget,
                        completed_stories=completed_stories,
                        last_completed=last_completed,
                    )
                    return exit_code

                last_completed = story_slug
                completed_stories.append(story_slug)
                project_state.completed_stories = len(completed_stories)

            except Exception as exc:
                exit_code = await halt_controller.handle_halt(
                    story_id=story_id,
                    exception=exc,
                    accumulated_budget=accumulated_budget,
                    completed_stories=completed_stories,
                    last_completed=last_completed,
                )
                return exit_code

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

        # Write resume-aware success summary when in resume mode (AC#4 / Story 5.4).
        # The finalize_node already wrote per-story summaries; this overwrites the
        # run-level summary with full cross-run context (previous_run_id).
        if original_run_id_str is not None:
            try:
                await write_success_summary(
                    project_root,
                    str(run_id),
                    previous_run_id=original_run_id_str,
                )
            except Exception:
                logger.warning(
                    "run_manager.write_error",
                    extra={"data": {"operation": "write_success_summary", "previous_run_id": original_run_id_str}},
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
    resume: Annotated[
        bool, typer.Option("--resume", help="Resume a halted epic dispatch from the failure point")
    ] = False,
) -> None:
    """Dispatch a story or epic for AI agent execution.

    Args:
        story: Story identifier (e.g., 2.7 or 2-7).
        epic: Epic identifier (e.g., 2 or epic-2).
        yes: When set, skip the pre-dispatch confirmation prompt for epic
            dispatch.
        resume: When set, resume a halted epic dispatch from the failure point.
            Can only be used with ``--epic``, not ``--story``.
    """
    if story and epic:
        typer.echo("Error: specify --story or --epic, not both.", err=True)
        raise typer.Exit(code=1)
    if not story and not epic:
        typer.echo("Error: specify --story or --epic.", err=True)
        raise typer.Exit(code=1)
    if resume and story is not None:
        typer.echo("Error: --resume can only be used with --epic, not --story.", err=True)
        raise typer.Exit(code=1)
    if story:
        code = asyncio.run(_dispatch_story_async(story))
    else:
        assert epic is not None  # narrowing: validated above
        code = asyncio.run(_dispatch_epic_async(epic, skip_confirm=yes, resume=resume))
    raise typer.Exit(code=code)
