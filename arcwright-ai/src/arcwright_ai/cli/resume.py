"""CLI resume helpers — Functions for resuming a halted epic dispatch run."""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import typer

from arcwright_ai.core.types import BudgetState, EpicId, StoryCost, StoryId
from arcwright_ai.output.run_manager import (
    RunStatus,
    get_run_status,
    list_runs,
)

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.core.config import RunConfig

logger = logging.getLogger(__name__)

__all__: list[str] = [
    "_find_latest_run_for_epic",
    "_reconstruct_budget_from_dict",
    "_show_resume_confirmation",
]


async def _find_latest_run_for_epic(
    project_root: Path,
    epic_spec: str,
) -> tuple[str, RunStatus] | None:
    """Find the most recent run for the specified epic by scanning run directories.

    Iterates all runs sorted by start_time descending (most recent first) and
    returns the first run whose story slugs contain entries prefixed with the
    epic number.  Skips runs that cannot be loaded.

    Args:
        project_root: Absolute path to the project root.
        epic_spec: Epic identifier string (e.g., "5" or "epic-5").

    Returns:
        Tuple of ``(run_id, RunStatus)`` for the most recent matching run,
        or ``None`` if no matching run is found.
    """
    epic_num = epic_spec[5:] if epic_spec.startswith("epic-") else epic_spec
    prefix = f"{epic_num}-"
    runs = await list_runs(project_root)
    for run_summary in runs:
        try:
            run_status = await get_run_status(project_root, run_summary.run_id)
        except Exception:
            logger.debug(
                "resume.skip_run",
                extra={"data": {"run_id": run_summary.run_id, "reason": "get_run_status failed"}},
            )
            continue
        if any(slug.startswith(prefix) for slug in run_status.stories):
            return run_summary.run_id, run_status
    return None


def _reconstruct_budget_from_dict(
    budget_dict: dict[str, Any],
    config: RunConfig,
) -> BudgetState:
    """Reconstruct a BudgetState from the serialized budget dict in run.yaml.

    The budget dict from run.yaml stores Decimal fields as strings.  This
    function deserializes them back to proper Decimal values, applying sane
    defaults for missing or malformed fields.  On any error, returns a fresh
    BudgetState with a warning log.

    Args:
        budget_dict: Raw budget dict from ``RunStatus.budget`` (may have
            string-encoded Decimal values for ``estimated_cost`` and ``max_cost``).
        config: RunConfig used to set the ``max_cost`` ceiling.

    Returns:
        Reconstructed ``BudgetState`` with accumulated fields from the prior run
        and ``max_cost`` from current config.
    """
    try:
        # Reconstruct per_story dict of StoryCost from serialized data
        raw_per_story: dict[str, Any] = budget_dict.get("per_story", {}) or {}
        per_story: dict[str, StoryCost] = {}
        for slug, sc_dict in raw_per_story.items():
            if isinstance(sc_dict, dict):
                per_story[slug] = StoryCost(
                    tokens_input=sc_dict.get("tokens_input", 0),
                    tokens_output=sc_dict.get("tokens_output", 0),
                    cost=Decimal(str(sc_dict.get("cost", "0"))),
                    invocations=sc_dict.get("invocations", 0),
                )

        return BudgetState(
            invocation_count=budget_dict.get("invocation_count", 0),
            total_tokens=budget_dict.get("total_tokens", 0),
            total_tokens_input=budget_dict.get("total_tokens_input", 0),
            total_tokens_output=budget_dict.get("total_tokens_output", 0),
            estimated_cost=Decimal(str(budget_dict.get("estimated_cost", "0"))),
            max_invocations=config.limits.tokens_per_story,
            max_cost=Decimal(str(config.limits.cost_per_run)),
            per_story=per_story,
        )
    except Exception:
        logger.warning(
            "resume.budget_reconstruction_failed",
            extra={"data": {"budget_dict_keys": list(budget_dict.keys()) if budget_dict else []}},
        )
        return BudgetState(
            max_invocations=config.limits.tokens_per_story,
            max_cost=Decimal(str(config.limits.cost_per_run)),
        )


def _show_resume_confirmation(
    epic_spec: str,
    original_run_id: str,
    completed_slugs: list[str],
    remaining_stories: list[tuple[Path, StoryId, EpicId]],
    carried_budget: BudgetState,
    config: RunConfig,
    *,
    skip_confirm: bool = False,
) -> None:
    """Display a resume-specific pre-dispatch summary and prompt the user to confirm.

    Shows the original halted run ID, list of already-completed stories to be
    skipped, list of remaining stories to dispatch, carried-forward budget, and
    configured budget ceilings.  Calls :func:`typer.confirm` with ``abort=True``
    so that a rejection raises :exc:`typer.Abort` at the call site.

    Args:
        epic_spec: Epic identifier string used in the resume header.
        original_run_id: Run ID of the original halted run.
        completed_slugs: Story slugs already completed (to be skipped).
        remaining_stories: Ordered list of ``(story_path, StoryId, EpicId)``
            tuples for stories that still need to be dispatched.
        carried_budget: ``BudgetState`` reconstructed from the prior run.
        config: Fully-loaded run configuration for budget ceiling display.
        skip_confirm: When ``True`` the function returns immediately without
            prompting (equivalent to passing ``--yes``).
    """
    if skip_confirm:
        return

    typer.echo(f"\n\u23ef\ufe0f  Epic Resume Plan \u2014 {epic_spec}", err=True)
    typer.echo(f"   Resuming from halted run: {original_run_id}", err=True)
    if completed_slugs:
        typer.echo(f"   Skipping completed stories: {len(completed_slugs)}", err=True)
        for slug in completed_slugs:
            typer.echo(f"     \u2713 {slug}", err=True)
    remaining_count = len(remaining_stories)
    typer.echo(f"   Dispatching remaining stories: {remaining_count}", err=True)
    for _, story_id, _ in remaining_stories:
        typer.echo(f"     \u2022 {story_id}", err=True)
    typer.echo(
        f"\n   Carried-forward budget: ${carried_budget.estimated_cost} | "
        f"{carried_budget.total_tokens} tokens | {carried_budget.invocation_count} invocations",
        err=True,
    )
    typer.echo("\n   Budget ceilings:", err=True)
    typer.echo(f"     cost_per_run:     ${config.limits.cost_per_run}", err=True)
    typer.echo(f"     tokens_per_story: {config.limits.tokens_per_story:,}", err=True)
    typer.echo(f"     retry_budget:     {config.limits.retry_budget}", err=True)
    typer.confirm("\nProceed with resume?", abort=True)
