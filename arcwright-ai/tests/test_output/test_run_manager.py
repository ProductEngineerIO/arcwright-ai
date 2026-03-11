"""Unit tests for arcwright_ai.output.run_manager — Run directory lifecycle."""

from __future__ import annotations

import re
from decimal import Decimal
from typing import TYPE_CHECKING

import pytest

from arcwright_ai.core.config import ApiConfig, RunConfig
from arcwright_ai.core.exceptions import RunError
from arcwright_ai.core.types import BudgetState, RunId
from arcwright_ai.output.run_manager import (
    RunStatus,
    RunStatusValue,
    StoryStatusEntry,
    create_run,
    generate_run_id,
    get_run_status,
    list_runs,
    update_run_status,
    update_story_status,
)

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers / Fixtures
# ---------------------------------------------------------------------------

RUN_ID_PATTERN = re.compile(r"^\d{8}-\d{6}-[0-9a-f]{6}$")


def _make_config() -> RunConfig:
    """Return a minimal RunConfig suitable for tests.

    Returns:
        RunConfig with a known API key and default values for all other fields.
    """
    return RunConfig(api=ApiConfig(claude_api_key="test-key-123"))


def _make_run_id() -> RunId:
    """Return a stable run ID for tests.

    Returns:
        RunId string.
    """
    return RunId("20260302-143022-a1b2c3")


STORY_SLUGS = ["2-1-state-models", "2-2-context-injector"]


@pytest.fixture
async def created_run(tmp_path: Path) -> Path:
    """Create a real run directory and return its path.

    Args:
        tmp_path: Pytest temporary directory fixture.

    Returns:
        Path to the created run directory.
    """
    run_id = _make_run_id()
    config = _make_config()
    return await create_run(tmp_path, run_id, config, STORY_SLUGS)


# ---------------------------------------------------------------------------
# Task 1 coverage: generate_run_id
# ---------------------------------------------------------------------------


def test_generate_run_id_pattern() -> None:
    """(a) generate_run_id produces a string matching YYYYMMDD-HHMMSS-xxxxxx."""
    run_id = generate_run_id()
    assert RUN_ID_PATTERN.match(run_id), f"run_id {run_id!r} does not match pattern"


def test_generate_run_id_uniqueness() -> None:
    """(a) Two sequential calls produce different IDs."""
    id1 = generate_run_id()
    id2 = generate_run_id()
    assert id1 != id2


# ---------------------------------------------------------------------------
# Task 2 coverage: create_run — directory structure
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_run_directory_structure(tmp_path: Path) -> None:
    """(b) create_run creates run directory, stories subdir, and run.yaml."""
    run_id = _make_run_id()
    run_dir = await create_run(tmp_path, run_id, _make_config(), STORY_SLUGS)

    assert run_dir.is_dir(), "run directory was not created"
    assert (run_dir / "stories").is_dir(), "stories subdirectory was not created"
    assert (run_dir / "run.yaml").is_file(), "run.yaml was not created"


# ---------------------------------------------------------------------------
# Task 3 coverage: create_run — run.yaml content
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_run_yaml_content(tmp_path: Path) -> None:
    """(c) create_run writes valid run.yaml with all required keys and initial values."""
    import yaml

    run_id = _make_run_id()
    run_dir = await create_run(tmp_path, run_id, _make_config(), STORY_SLUGS)
    raw = yaml.safe_load((run_dir / "run.yaml").read_text())

    assert raw["run_id"] == str(run_id)
    assert raw["status"] == "queued"
    assert raw["last_completed_story"] is None
    assert "start_time" in raw
    assert "config_snapshot" in raw
    assert "budget" in raw

    for slug in STORY_SLUGS:
        assert slug in raw["stories"]
        entry = raw["stories"][slug]
        assert entry["status"] == "queued"
        assert entry["retry_count"] == 0
        assert entry["started_at"] is None
        assert entry["completed_at"] is None


@pytest.mark.asyncio
async def test_create_run_config_snapshot_excludes_api_key(tmp_path: Path) -> None:
    """(d) create_run config_snapshot does NOT contain the API key (NFR6)."""
    import yaml

    run_id = _make_run_id()
    run_dir = await create_run(tmp_path, run_id, _make_config(), STORY_SLUGS)
    raw = yaml.safe_load((run_dir / "run.yaml").read_text())
    snapshot = raw["config_snapshot"]

    assert "claude_api_key" not in snapshot
    assert "api_key" not in snapshot
    assert "test-key-123" not in str(snapshot)

    # Expected operational fields are present
    for field in (
        "model_version",
        "tokens_per_story",
        "cost_per_run",
        "retry_budget",
        "timeout_per_story",
        "methodology_type",
        "artifacts_path",
        "branch_template",
    ):
        assert field in snapshot, f"Expected field {field!r} missing from config_snapshot"


@pytest.mark.asyncio
async def test_create_run_decimal_budget_serialized_as_strings(tmp_path: Path) -> None:
    """(e) create_run Decimal fields in budget are serialized as strings in YAML."""
    import yaml

    run_id = _make_run_id()
    run_dir = await create_run(tmp_path, run_id, _make_config(), STORY_SLUGS)
    raw = yaml.safe_load((run_dir / "run.yaml").read_text())
    budget = raw["budget"]

    assert isinstance(budget["estimated_cost"], str), "estimated_cost must be a string"
    assert isinstance(budget["max_cost"], str), "max_cost must be a string"


# ---------------------------------------------------------------------------
# Task 4 coverage: update_run_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_run_status_partial_update(tmp_path: Path, created_run: Path) -> None:
    """(f) update_run_status partial update — only specified fields change, others preserved."""
    import yaml

    run_id = _make_run_id()
    await update_run_status(tmp_path, str(run_id), status=RunStatusValue.RUNNING)

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    assert raw["status"] == "running"
    # Other fields preserved
    assert raw["run_id"] == str(run_id)
    assert raw["last_completed_story"] is None
    assert "stories" in raw


@pytest.mark.asyncio
async def test_update_run_status_budget_replacement(tmp_path: Path, created_run: Path) -> None:
    """(g) update_run_status with budget — full budget section updated."""
    import yaml

    run_id = _make_run_id()
    new_budget = BudgetState(
        invocation_count=5,
        total_tokens=12000,
        estimated_cost=Decimal("0.42"),
        max_invocations=100,
        max_cost=Decimal("10.00"),
    )
    await update_run_status(tmp_path, str(run_id), budget=new_budget)

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    budget = raw["budget"]
    assert budget["invocation_count"] == 5
    assert budget["total_tokens"] == 12000
    assert budget["estimated_cost"] == "0.42"
    assert budget["max_cost"] == "10.00"


@pytest.mark.asyncio
async def test_update_run_status_missing_yaml_raises(tmp_path: Path) -> None:
    """(h) update_run_status on missing run.yaml raises RunError."""
    with pytest.raises(RunError, match=r"run\.yaml not found"):
        await update_run_status(tmp_path, "nonexistent-run-id", status=RunStatusValue.HALTED)


# ---------------------------------------------------------------------------
# Task 5 coverage: update_story_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_story_status_existing_entry(tmp_path: Path, created_run: Path) -> None:
    """(i) update_story_status updates existing story entry correctly."""
    import yaml

    run_id = _make_run_id()
    slug = STORY_SLUGS[0]
    await update_story_status(
        tmp_path,
        str(run_id),
        slug,
        status="running",
        started_at="2026-03-02T14:31:00+00:00",
    )

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    entry = raw["stories"][slug]
    assert entry["status"] == "running"
    assert entry["started_at"] == "2026-03-02T14:31:00+00:00"
    assert entry["retry_count"] == 0  # preserved from initial value


@pytest.mark.asyncio
async def test_update_story_status_new_entry(tmp_path: Path, created_run: Path) -> None:
    """(j) update_story_status creates new story entry if slug not found."""
    import yaml

    run_id = _make_run_id()
    new_slug = "3-1-brand-new-story"
    await update_story_status(tmp_path, str(run_id), new_slug, status="running")

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    assert new_slug in raw["stories"]
    entry = raw["stories"][new_slug]
    assert entry["status"] == "running"
    assert entry["retry_count"] == 0
    assert entry["started_at"] is None
    assert entry["completed_at"] is None


@pytest.mark.asyncio
async def test_update_story_status_missing_yaml_raises(tmp_path: Path) -> None:
    """(k) update_story_status on missing run.yaml raises RunError."""
    with pytest.raises(RunError, match=r"run\.yaml not found"):
        await update_story_status(tmp_path, "no-such-run", "some-slug", status="running")


@pytest.mark.asyncio
async def test_update_story_status_partial_update_preserves_fields(tmp_path: Path, created_run: Path) -> None:
    """(q) update_story_status partial update — only specified fields change, others preserved."""
    import yaml

    run_id = _make_run_id()
    slug = STORY_SLUGS[0]

    # First: set retry_count to 2
    await update_story_status(tmp_path, str(run_id), slug, status="running", retry_count=2)

    # Second: update status only — retry_count should be preserved
    await update_story_status(tmp_path, str(run_id), slug, status="success")

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    entry = raw["stories"][slug]
    assert entry["status"] == "success"
    assert entry["retry_count"] == 2  # preserved, not reset


# ---------------------------------------------------------------------------
# Task 6 coverage: get_run_status
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_run_status_returns_correct_model(tmp_path: Path, created_run: Path) -> None:
    """(l) get_run_status returns correct typed RunStatus model."""
    run_id = _make_run_id()
    status = await get_run_status(tmp_path, str(run_id))

    assert isinstance(status, RunStatus)
    assert status.run_id == str(run_id)
    assert status.status == RunStatusValue.QUEUED
    assert status.last_completed_story is None
    assert len(status.stories) == len(STORY_SLUGS)
    for slug in STORY_SLUGS:
        assert slug in status.stories
        assert isinstance(status.stories[slug], StoryStatusEntry)
        assert status.stories[slug].status == "queued"


@pytest.mark.asyncio
async def test_get_run_status_missing_run_raises(tmp_path: Path) -> None:
    """(m) get_run_status on missing run raises RunError with correct message."""
    with pytest.raises(RunError, match="Run not found"):
        await get_run_status(tmp_path, "missing-run-id")


# ---------------------------------------------------------------------------
# Task 7 coverage: list_runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_runs_sorted_by_start_time(tmp_path: Path) -> None:
    """(n) list_runs returns summaries sorted by start_time descending (most recent first)."""
    import yaml

    config = _make_config()

    # Create two runs with known, distinct start_times by patching run.yaml after creation
    run_id_a = RunId("20260301-100000-aaaaaa")
    run_id_b = RunId("20260302-100000-bbbbbb")

    dir_a = await create_run(tmp_path, run_id_a, config, ["s1"])
    dir_b = await create_run(tmp_path, run_id_b, config, ["s1"])

    # Fix start_times so they are deterministic
    for run_dir, ts in ((dir_a, "2026-03-01T10:00:00+00:00"), (dir_b, "2026-03-02T10:00:00+00:00")):
        raw = yaml.safe_load((run_dir / "run.yaml").read_text())
        raw["start_time"] = ts
        import yaml as yaml2

        (run_dir / "run.yaml").write_text(yaml2.safe_dump(raw, default_flow_style=False, allow_unicode=True))

    summaries = await list_runs(tmp_path)
    assert len(summaries) == 2
    assert summaries[0].run_id == str(run_id_b)  # more recent first
    assert summaries[1].run_id == str(run_id_a)


@pytest.mark.asyncio
async def test_list_runs_empty_directory(tmp_path: Path) -> None:
    """(o) list_runs on empty/missing runs directory returns empty list."""
    result = await list_runs(tmp_path)
    assert result == []


@pytest.mark.asyncio
async def test_list_runs_skips_directories_without_yaml(tmp_path: Path) -> None:
    """(p) list_runs skips subdirectories without run.yaml."""
    config = _make_config()
    run_id = _make_run_id()
    await create_run(tmp_path, run_id, config, STORY_SLUGS)

    # Create a subdir without run.yaml
    orphan_dir = tmp_path / ".arcwright-ai" / "runs" / "not-a-run"
    orphan_dir.mkdir(parents=True, exist_ok=True)

    summaries = await list_runs(tmp_path)
    assert len(summaries) == 1
    assert summaries[0].run_id == str(run_id)


@pytest.mark.asyncio
async def test_list_runs_story_count_and_completed_count(tmp_path: Path) -> None:
    """list_runs RunSummary has correct story_count and completed_count."""
    config = _make_config()
    run_id = _make_run_id()
    await create_run(tmp_path, run_id, config, STORY_SLUGS)

    # Mark first story as success
    await update_story_status(tmp_path, str(run_id), STORY_SLUGS[0], status="success")

    summaries = await list_runs(tmp_path)
    assert len(summaries) == 1
    summary = summaries[0]
    assert summary.story_count == len(STORY_SLUGS)
    assert summary.completed_count == 1


# ---------------------------------------------------------------------------
# Additional coverage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_run_status_halted_persisted(tmp_path: Path, created_run: Path) -> None:
    """(r) update_run_status with RunStatusValue.HALTED — status correctly persisted and readable."""
    import yaml

    run_id = _make_run_id()
    await update_run_status(tmp_path, str(run_id), status=RunStatusValue.HALTED)

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    assert raw["status"] == "halted"

    # Also verify round-trip via get_run_status
    status_model = await get_run_status(tmp_path, str(run_id))
    assert status_model.status == RunStatusValue.HALTED


@pytest.mark.asyncio
async def test_update_run_status_last_completed_story(tmp_path: Path, created_run: Path) -> None:
    """update_run_status with last_completed_story — field is persisted."""
    import yaml

    run_id = _make_run_id()
    slug = STORY_SLUGS[0]
    await update_run_status(tmp_path, str(run_id), last_completed_story=slug)

    raw = yaml.safe_load((created_run / "run.yaml").read_text())
    assert raw["last_completed_story"] == slug


@pytest.mark.asyncio
async def test_create_run_returns_run_dir_path(tmp_path: Path) -> None:
    """create_run returns the run directory Path."""
    run_id = _make_run_id()
    run_dir = await create_run(tmp_path, run_id, _make_config(), STORY_SLUGS)

    expected = tmp_path / ".arcwright-ai" / "runs" / str(run_id)
    assert run_dir == expected


@pytest.mark.asyncio
async def test_create_run_idempotent(tmp_path: Path) -> None:
    """create_run with exist_ok — calling twice with same run_id does not raise."""
    run_id = _make_run_id()
    config = _make_config()
    await create_run(tmp_path, run_id, config, STORY_SLUGS)
    # Should not raise
    await create_run(tmp_path, run_id, config, STORY_SLUGS)


# ---------------------------------------------------------------------------
# _serialize_budget — per_story and Decimal handling
# ---------------------------------------------------------------------------


def test_serialize_budget_converts_decimals_to_strings() -> None:
    """_serialize_budget converts all Decimal fields to strings for YAML safety."""
    from arcwright_ai.output.run_manager import _serialize_budget

    budget = BudgetState(
        invocation_count=2,
        total_tokens=1400,
        total_tokens_input=1000,
        total_tokens_output=400,
        estimated_cost=Decimal("0.0225"),
        max_cost=Decimal("100.0"),
    )
    data = _serialize_budget(budget)
    assert data["estimated_cost"] == "0.0225"
    assert data["max_cost"] == "100.0"
    assert data["invocation_count"] == 2
    assert data["total_tokens_input"] == 1000
    assert data["total_tokens_output"] == 400


def test_serialize_budget_per_story_decimal_conversion() -> None:
    """_serialize_budget converts per_story StoryCost.cost Decimal to string."""
    from arcwright_ai.core.types import StoryCost
    from arcwright_ai.output.run_manager import _serialize_budget

    budget = BudgetState(
        invocation_count=1,
        estimated_cost=Decimal("0.01"),
        per_story={
            "2-1-slug": StoryCost(
                tokens_input=500,
                tokens_output=200,
                cost=Decimal("0.01"),
                invocations=1,
            ),
        },
    )
    data = _serialize_budget(budget)
    assert "per_story" in data
    assert "2-1-slug" in data["per_story"]
    sc = data["per_story"]["2-1-slug"]
    assert sc["cost"] == "0.01"
    assert sc["tokens_input"] == 500
    assert sc["tokens_output"] == 200
    assert sc["invocations"] == 1


def test_serialize_budget_empty_per_story() -> None:
    """_serialize_budget handles empty per_story dict."""
    from arcwright_ai.output.run_manager import _serialize_budget

    budget = BudgetState()
    data = _serialize_budget(budget)
    assert data["per_story"] == {}


def test_serialize_budget_yaml_safe_dump() -> None:
    """Serialized budget can be passed to yaml.safe_dump without error."""
    import yaml

    from arcwright_ai.core.types import StoryCost
    from arcwright_ai.output.run_manager import _serialize_budget

    budget = BudgetState(
        invocation_count=3,
        total_tokens=2100,
        total_tokens_input=1500,
        total_tokens_output=600,
        estimated_cost=Decimal("0.0525"),
        max_cost=Decimal("50.0"),
        per_story={
            "3-1-a": StoryCost(tokens_input=500, tokens_output=200, cost=Decimal("0.0175"), invocations=1),
            "3-2-b": StoryCost(tokens_input=1000, tokens_output=400, cost=Decimal("0.035"), invocations=2),
        },
    )
    data = _serialize_budget(budget)
    # Should not raise — all Decimals are strings
    yaml_str = yaml.safe_dump(data, default_flow_style=False)
    assert "estimated_cost" in yaml_str
