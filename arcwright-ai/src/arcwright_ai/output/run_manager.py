"""Output run manager — Run directory lifecycle and state tracking.

This module is the single writer for ``run.yaml`` — no other module should read
or write that file directly.  All public functions import types from ``core/``
packages only; zero engine dependency is enforced.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from pydantic import ConfigDict
from pydantic import ValidationError as PydanticValidationError

from arcwright_ai.core.config import ModelRole
from arcwright_ai.core.constants import (
    DIR_ARCWRIGHT,
    DIR_RUNS,
    DIR_STORIES,
    RUN_ID_DATETIME_FORMAT,
    RUN_METADATA_FILENAME,
)
from arcwright_ai.core.exceptions import ConfigError, RunError
from arcwright_ai.core.io import load_yaml, save_yaml
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import ArcwrightModel, RunId

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.core.config import RunConfig
    from arcwright_ai.core.types import BudgetState

__all__: list[str] = [
    "RunStatus",
    "RunStatusValue",
    "RunSummary",
    "StoryStatusEntry",
    "create_run",
    "generate_run_id",
    "get_run_status",
    "list_runs",
    "update_run_status",
    "update_story_status",
]

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class RunStatusValue(StrEnum):
    """Lifecycle states for a run.

    Values:
        QUEUED: Run has been created but not yet started.
        RUNNING: Run is actively executing stories.
        COMPLETED: All stories finished successfully.
        HALTED: Run stopped due to unrecoverable failure.
        TIMED_OUT: Run exceeded its time budget.
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    HALTED = "halted"
    TIMED_OUT = "timed_out"


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class StoryStatusEntry(ArcwrightModel):
    """Per-story tracking entry stored inside ``run.yaml``.

    Uses ``extra="ignore"`` instead of ``extra="forbid"`` for forward
    compatibility — future stories may add fields without breaking deserialization.

    Attributes:
        status: Current lifecycle status string for this story.
        retry_count: Number of retry attempts made.
        started_at: ISO 8601 timestamp when story execution began, or None.
        completed_at: ISO 8601 timestamp when story execution finished, or None.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        str_strip_whitespace=True,
    )

    status: str
    retry_count: int = 0
    started_at: str | None = None
    completed_at: str | None = None
    pr_url: str | None = None


class RunStatus(ArcwrightModel):
    """Full run state read from ``run.yaml``.

    Attributes:
        run_id: Unique run identifier.
        status: Current run lifecycle status.
        start_time: ISO 8601 timestamp when the run was created.
        config_snapshot: Flat dict of operational config fields (no API key).
        budget: Serialized budget state (Decimal fields as strings).
        stories: Mapping of story slug to its status entry.
        last_completed_story: Slug of the most recently completed story, or None.
    """

    run_id: str
    status: RunStatusValue
    start_time: str
    config_snapshot: dict[str, Any]
    budget: dict[str, Any]
    stories: dict[str, StoryStatusEntry]
    last_completed_story: str | None = None


class RunSummary(ArcwrightModel):
    """Lightweight run summary for listing.

    Attributes:
        run_id: Unique run identifier.
        status: Current run lifecycle status.
        start_time: ISO 8601 timestamp when the run was created.
        story_count: Total number of stories in the run.
        completed_count: Number of stories with status "success".
    """

    run_id: str
    status: RunStatusValue
    start_time: str
    story_count: int
    completed_count: int


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _run_dir(project_root: Path, run_id: str) -> Path:
    """Return the run directory path for the given run ID.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Path to ``.arcwright-ai/runs/<run-id>/`` under *project_root*.
    """
    return project_root / DIR_ARCWRIGHT / DIR_RUNS / run_id


def _run_yaml_path(project_root: Path, run_id: str) -> Path:
    """Return the path to ``run.yaml`` for the given run ID.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Path to ``.arcwright-ai/runs/<run-id>/run.yaml`` under *project_root*.
    """
    return _run_dir(project_root, run_id) / RUN_METADATA_FILENAME


def _build_config_snapshot(config: RunConfig) -> dict[str, Any]:
    """Extract a flat, API-key-free snapshot of operationally-relevant config fields.

    Explicitly excludes ``api.claude_api_key`` per NFR6 (API key security).

    Args:
        config: Fully-loaded ``RunConfig`` instance.

    Returns:
        Flat dict with keys: ``model_version``, ``review_model_version``,
        ``tokens_per_story``, ``cost_per_run``, ``retry_budget``,
        ``timeout_per_story``, ``methodology_type``, ``artifacts_path``,
        ``branch_template``.
    """
    return {
        "model_version": config.models.get(ModelRole.GENERATE).version,
        "review_model_version": config.models.get(ModelRole.REVIEW).version,
        "tokens_per_story": config.limits.tokens_per_story,
        "cost_per_run": config.limits.cost_per_run,
        "retry_budget": config.limits.retry_budget,
        "timeout_per_story": config.limits.timeout_per_story,
        "methodology_type": config.methodology.type,
        "artifacts_path": config.methodology.artifacts_path,
        "branch_template": config.scm.branch_template,
    }


def _serialize_budget(budget: BudgetState) -> dict[str, Any]:
    """Serialize a ``BudgetState`` to a YAML-safe dict.

    PyYAML's ``safe_dump`` cannot handle ``Decimal`` objects, so ``estimated_cost``,
    ``max_cost``, and per-story ``cost`` fields are converted to ``str`` before
    serialization.

    Args:
        budget: ``BudgetState`` instance to serialize.

    Returns:
        Dict with all fields; ``Decimal`` values converted to strings.
    """
    data: dict[str, Any] = budget.model_dump()
    for key in ("estimated_cost", "max_cost"):
        if isinstance(data.get(key), Decimal):
            data[key] = str(data[key])
    # Serialize per_story StoryCost Decimal fields
    if "per_story" in data and isinstance(data["per_story"], dict):
        for _slug, story_cost in data["per_story"].items():
            if isinstance(story_cost, dict) and isinstance(story_cost.get("cost"), Decimal):
                story_cost["cost"] = str(story_cost["cost"])
            if isinstance(story_cost, dict) and isinstance(story_cost.get("cost_by_role"), dict):
                story_cost["cost_by_role"] = {
                    k: str(v) if isinstance(v, Decimal) else v for k, v in story_cost["cost_by_role"].items()
                }
    return data


def _load_run_yaml(project_root: Path, run_id: str) -> dict[str, Any]:
    """Synchronously load ``run.yaml`` for the given run, raising ``RunError`` on failure.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Parsed YAML content as a dict.

    Raises:
        RunError: If ``run.yaml`` does not exist or cannot be read/parsed.
    """
    path = _run_yaml_path(project_root, run_id)
    if not path.exists():
        raise RunError(
            f"run.yaml not found for run {run_id}",
            details={"path": str(path)},
        )
    try:
        return load_yaml(path)
    except ConfigError as exc:
        raise RunError(
            f"Failed to read run.yaml for run {run_id}: {exc.message}",
            details={"path": str(path), "cause": str(exc)},
        ) from exc
    except OSError as exc:
        raise RunError(
            f"I/O error reading run.yaml for run {run_id}: {exc}",
            details={"path": str(path), "cause": str(exc)},
        ) from exc


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_run_id() -> RunId:
    """Generate a unique, time-ordered run identifier.

    The format is ``YYYYMMDD-HHMMSS-<short-uuid>`` where the datetime component
    is in UTC and ``<short-uuid>`` is the first 6 hexadecimal characters of a
    ``uuid4()``.  Example: ``20260302-143022-a1b2c3``.

    Returns:
        A new ``RunId`` string.
    """
    dt_part = datetime.now(tz=UTC).strftime(RUN_ID_DATETIME_FORMAT)
    uuid_part = uuid.uuid4().hex[:6]
    return RunId(f"{dt_part}-{uuid_part}")


async def create_run(
    project_root: Path,
    run_id: RunId,
    config: RunConfig,
    story_slugs: list[str],
) -> Path:
    """Create the run directory and write the initial ``run.yaml``.

    Creates ``.arcwright-ai/runs/<run-id>/`` and ``.arcwright-ai/runs/<run-id>/stories/``
    under *project_root*, then writes a ``run.yaml`` with status ``queued`` and
    all stories initialized to ``queued``.  Parent dirs are created as needed.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Unique run identifier (from :func:`generate_run_id`).
        config: Fully-loaded ``RunConfig`` for the run.
        story_slugs: Ordered list of story slugs to include in this run.

    Returns:
        Path to the created run directory.
    """
    from arcwright_ai.core.types import BudgetState

    run_dir = _run_dir(project_root, str(run_id))
    stories_dir = run_dir / DIR_STORIES
    await asyncio.to_thread(stories_dir.mkdir, parents=True, exist_ok=True)

    run_yaml_path = run_dir / RUN_METADATA_FILENAME
    data: dict[str, Any] = {
        "run_id": str(run_id),
        "start_time": datetime.now(tz=UTC).isoformat(),
        "status": RunStatusValue.QUEUED.value,
        "config_snapshot": _build_config_snapshot(config),
        "budget": _serialize_budget(
            BudgetState(
                max_invocations=config.limits.tokens_per_story,
                max_cost=Decimal(str(config.limits.cost_per_run)),
            )
        ),
        "stories": {
            slug: {
                "status": "queued",
                "retry_count": 0,
                "started_at": None,
                "completed_at": None,
            }
            for slug in story_slugs
        },
        "last_completed_story": None,
    }
    await asyncio.to_thread(save_yaml, run_yaml_path, data)
    return run_dir


async def update_run_status(
    project_root: Path,
    run_id: str,
    *,
    status: RunStatusValue | None = None,
    last_completed_story: str | None = None,
    budget: BudgetState | None = None,
) -> None:
    """Partially update the top-level fields of ``run.yaml``.

    Only the explicitly-provided (non-``None``) arguments are modified; all
    other fields in ``run.yaml`` are preserved.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.
        status: New run lifecycle status, or ``None`` to leave unchanged.
        last_completed_story: Slug of the most recently completed story, or
            ``None`` to leave unchanged.
        budget: New ``BudgetState`` to replace the budget section, or ``None``
            to leave unchanged.

    Raises:
        RunError: If ``run.yaml`` does not exist or cannot be read/written.
    """
    path = _run_yaml_path(project_root, run_id)
    data = await asyncio.to_thread(_load_run_yaml, project_root, run_id)

    if status is not None:
        data["status"] = status.value
    if last_completed_story is not None:
        data["last_completed_story"] = last_completed_story
    if budget is not None:
        data["budget"] = _serialize_budget(budget)

    await asyncio.to_thread(save_yaml, path, data)


async def update_story_status(
    project_root: Path,
    run_id: str,
    story_slug: str,
    *,
    status: str,
    started_at: str | None = None,
    completed_at: str | None = None,
    retry_count: int | None = None,
    pr_url: str | None = None,
) -> None:
    """Update (or create) a story entry inside ``run.yaml``.

    If *story_slug* already exists in the ``stories`` section, only the
    provided non-``None`` fields are overwritten.  If the slug is absent a
    new entry is created with the provided values and sensible defaults for
    unspecified fields.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.
        story_slug: Story slug key in the ``stories`` dict.
        status: New status string for the story (always applied).
        started_at: ISO 8601 start timestamp, or ``None`` to leave unchanged.
        completed_at: ISO 8601 completion timestamp, or ``None`` to leave unchanged.
        retry_count: Retry attempt count, or ``None`` to leave unchanged.
        pr_url: Pull request URL, or ``None`` to leave unchanged.

    Raises:
        RunError: If ``run.yaml`` does not exist or cannot be read/written.
    """
    path = _run_yaml_path(project_root, run_id)
    data = await asyncio.to_thread(_load_run_yaml, project_root, run_id)

    stories: dict[str, Any] = data.setdefault("stories", {})

    if story_slug in stories:
        entry: dict[str, Any] = dict(stories[story_slug])
        entry["status"] = status
        if started_at is not None:
            entry["started_at"] = started_at
        if completed_at is not None:
            entry["completed_at"] = completed_at
        if retry_count is not None:
            entry["retry_count"] = retry_count
        if pr_url is not None:
            entry["pr_url"] = pr_url
        stories[story_slug] = entry
    else:
        stories[story_slug] = {
            "status": status,
            "retry_count": retry_count if retry_count is not None else 0,
            "started_at": started_at,
            "completed_at": completed_at,
            "pr_url": pr_url,
        }

    await asyncio.to_thread(save_yaml, path, data)


async def get_run_status(project_root: Path, run_id: str) -> RunStatus:
    """Read ``run.yaml`` and return a typed ``RunStatus`` model.

    Args:
        project_root: Absolute path to the target project root.
        run_id: Run identifier string.

    Returns:
        Fully-populated ``RunStatus`` model.

    Raises:
        RunError: If ``run.yaml`` does not exist, cannot be read, or is malformed.
    """
    path = _run_yaml_path(project_root, run_id)
    path_exists = await asyncio.to_thread(path.exists)
    if not path_exists:
        raise RunError(
            f"Run not found: {run_id}",
            details={"path": str(path)},
        )
    try:
        data = await asyncio.to_thread(load_yaml, path)
    except ConfigError as exc:
        raise RunError(
            f"Failed to read run.yaml for run {run_id}: {exc.message}",
            details={"path": str(path), "cause": str(exc)},
        ) from exc
    except OSError as exc:
        raise RunError(
            f"I/O error reading run.yaml for run {run_id}: {exc}",
            details={"path": str(path), "cause": str(exc)},
        ) from exc

    # Validate and parse stories sub-dict into typed models
    raw_stories: dict[str, Any] = data.get("stories", {})
    try:
        parsed_stories: dict[str, StoryStatusEntry] = {
            slug: StoryStatusEntry.model_validate(entry) for slug, entry in raw_stories.items()
        }
    except PydanticValidationError as exc:
        raise RunError(
            f"Malformed story entry in run.yaml for run {run_id}: {exc}",
            details={"run_id": run_id},
        ) from exc

    payload = {**data, "stories": parsed_stories}
    try:
        return RunStatus.model_validate(payload)
    except PydanticValidationError as exc:
        raise RunError(
            f"Malformed run.yaml for run {run_id}: {exc}",
            details={"run_id": run_id},
        ) from exc


async def list_runs(project_root: Path) -> list[RunSummary]:
    """Scan the runs directory and return lightweight summaries sorted by start time.

    Subdirectories that lack ``run.yaml`` or contain malformed content are
    silently skipped (logged at DEBUG level).

    Args:
        project_root: Absolute path to the target project root.

    Returns:
        List of ``RunSummary`` models sorted by ``start_time`` descending
        (most recent first).  Returns an empty list if the runs directory does
        not exist or contains no valid runs.
    """
    runs_dir = project_root / DIR_ARCWRIGHT / DIR_RUNS

    def _dir_exists() -> bool:
        return runs_dir.exists() and runs_dir.is_dir()

    if not await asyncio.to_thread(_dir_exists):
        return []

    def _list_subdirs() -> list[Any]:
        return sorted(runs_dir.iterdir())

    subdirs = await asyncio.to_thread(_list_subdirs)
    summaries: list[RunSummary] = []

    for subdir in subdirs:
        is_dir = await asyncio.to_thread(subdir.is_dir)
        if not is_dir:
            continue
        yaml_path = subdir / RUN_METADATA_FILENAME
        yaml_exists = await asyncio.to_thread(yaml_path.exists)
        if not yaml_exists:
            _log.debug("Skipping %s: no run.yaml", subdir)
            continue
        try:
            raw = await asyncio.to_thread(load_yaml, yaml_path)
        except (ConfigError, OSError) as exc:
            _log.debug("Skipping %s: failed to load run.yaml — %s", subdir, exc)
            continue

        try:
            run_id = raw["run_id"]
            status = RunStatusValue(raw["status"])
            start_time = raw["start_time"]
            stories: dict[str, Any] = raw.get("stories", {})
            story_count = len(stories)
            completed_count = sum(
                1
                for entry in stories.values()
                if isinstance(entry, dict) and entry.get("status") in {"success", TaskState.SUCCESS.value}
            )
            summaries.append(
                RunSummary(
                    run_id=run_id,
                    status=status,
                    start_time=start_time,
                    story_count=story_count,
                    completed_count=completed_count,
                )
            )
        except (KeyError, ValueError, PydanticValidationError) as exc:
            _log.debug("Skipping %s: malformed run.yaml — %s", subdir, exc)
            continue

    summaries.sort(key=lambda s: s.start_time, reverse=True)
    return summaries
