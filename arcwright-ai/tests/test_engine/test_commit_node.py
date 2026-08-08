"""Tests for _update_sprint_status_done() and its call site in commit_node."""

from __future__ import annotations

import logging
from datetime import date
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import SecretStr

from arcwright_ai.core.config import ApiConfig, LimitsConfig, RunConfig
from arcwright_ai.core.lifecycle import TaskState
from arcwright_ai.core.types import EpicId, RunId, StoryId
from arcwright_ai.engine.nodes import _update_sprint_status_done, commit_node
from arcwright_ai.engine.state import StoryState

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SPRINT_STATUS_TEMPLATE = """\
# STATUS DEFINITIONS:
# ==================
# Story Status:
#   - ready-for-dev: Story file created
#   - in-progress: Developer actively working
#   - done: Story completed

generated: 2026-03-02
last_updated: 2026-03-02

development_status:
  # Epic 10: Ad-Hoc Improvements & Housekeeping
  epic-10: in-progress
  10-15-run-cost-in-pr-body: done
  {target_slug}: {target_status}
"""


def _make_sprint_status(
    target_slug: str = "10-16-mark-story-done-in-sprint-status-before-pr-creation",
    target_status: str = "in-progress",
) -> str:
    return _SPRINT_STATUS_TEMPLATE.format(
        target_slug=target_slug,
        target_status=target_status,
    )


def _write_sprint_status(
    tmp_path: Path,
    content: str,
    artifacts_path: str = "_spec",
) -> Path:
    impl_dir = tmp_path / artifacts_path / "implementation-artifacts"
    impl_dir.mkdir(parents=True, exist_ok=True)
    sprint_file = impl_dir / "sprint-status.yaml"
    sprint_file.write_text(content, encoding="utf-8")
    return sprint_file


def _make_run_config() -> RunConfig:
    return RunConfig(
        api=ApiConfig(claude_api_key=SecretStr("test-key-not-real")),
        limits=LimitsConfig(retry_budget=3),
    )


# ---------------------------------------------------------------------------
# Unit tests: _update_sprint_status_done()
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_sprint_status_changes_status_to_done(tmp_path: Path) -> None:
    """Target story status is changed to done, last_updated updated, comments preserved."""
    slug = "10-16-mark-story-done-in-sprint-status-before-pr-creation"
    content = _make_sprint_status(target_slug=slug, target_status="in-progress")
    sprint_file = _write_sprint_status(tmp_path, content)

    await _update_sprint_status_done(slug, tmp_path, "_spec")

    result = sprint_file.read_text(encoding="utf-8")
    assert f"{slug}: done" in result
    # Comments are preserved
    assert "# STATUS DEFINITIONS:" in result
    assert "# Epic 10: Ad-Hoc Improvements & Housekeeping" in result
    # last_updated changed
    assert "last_updated: 2026-03-02" not in result
    assert f"last_updated: {date.today().isoformat()}" in result


@pytest.mark.asyncio
async def test_update_sprint_status_file_not_found_logs_warning(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """When sprint-status.yaml does not exist, warning is logged and no exception raised."""
    with caplog.at_level(logging.WARNING, logger="arcwright_ai.engine.nodes"):
        await _update_sprint_status_done("some-slug", tmp_path, "_spec")

    assert "scm.sprint_status.not_found" in caplog.text


@pytest.mark.asyncio
async def test_update_sprint_status_slug_not_found_logs_debug(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    """When story_slug is absent from file, debug log emitted, file left unchanged."""
    content = _make_sprint_status(
        target_slug="10-15-run-cost-in-pr-body",
        target_status="done",
    )
    sprint_file = _write_sprint_status(tmp_path, content)
    original = sprint_file.read_text(encoding="utf-8")

    with caplog.at_level(logging.DEBUG, logger="arcwright_ai.engine.nodes"):
        await _update_sprint_status_done("nonexistent-slug", tmp_path, "_spec")

    assert sprint_file.read_text(encoding="utf-8") == original
    assert "scm.sprint_status.key_not_found" in caplog.text


@pytest.mark.asyncio
async def test_update_sprint_status_idempotent_when_already_done(tmp_path: Path) -> None:
    """When status is already done, file is rewritten with same done value and updated last_updated."""
    slug = "10-16-mark-story-done-in-sprint-status-before-pr-creation"
    content = _make_sprint_status(target_slug=slug, target_status="done")
    sprint_file = _write_sprint_status(tmp_path, content)

    await _update_sprint_status_done(slug, tmp_path, "_spec")

    result = sprint_file.read_text(encoding="utf-8")
    assert f"{slug}: done" in result
    assert f"last_updated: {date.today().isoformat()}" in result


@pytest.mark.asyncio
async def test_update_sprint_status_from_ready_for_dev(tmp_path: Path) -> None:
    """Status ready-for-dev is correctly replaced with done."""
    slug = "10-16-mark-story-done-in-sprint-status-before-pr-creation"
    content = _make_sprint_status(target_slug=slug, target_status="ready-for-dev")
    sprint_file = _write_sprint_status(tmp_path, content)

    await _update_sprint_status_done(slug, tmp_path, "_spec")

    result = sprint_file.read_text(encoding="utf-8")
    assert f"{slug}: done" in result
    assert f"{slug}: ready-for-dev" not in result


@pytest.mark.asyncio
async def test_update_sprint_status_io_error_logs_warning_no_propagation(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """OSError during write is caught and logged as warning; no exception propagated."""
    slug = "10-16-mark-story-done-in-sprint-status-before-pr-creation"
    content = _make_sprint_status(target_slug=slug, target_status="in-progress")
    _write_sprint_status(tmp_path, content)

    with (
        patch("arcwright_ai.engine.nodes.write_text_async", AsyncMock(side_effect=OSError("disk full"))),
        caplog.at_level(logging.WARNING, logger="arcwright_ai.engine.nodes"),
    ):
        # Must not raise
        await _update_sprint_status_done(slug, tmp_path, "_spec")

    assert "scm.sprint_status.update_error" in caplog.text


@pytest.mark.asyncio
async def test_update_sprint_status_targets_worktree_not_project_root(tmp_path: Path) -> None:
    """Regression test (Story 10.18): only the repo_root passed in is updated.

    _update_sprint_status_done() is agnostic to whether its repo_root argument is a
    project root or a worktree root — it updates whatever directory it is given.
    This proves that when called with a worktree path, the project root's own copy
    of sprint-status.yaml (a completely separate directory) is left untouched.
    """
    slug = "10-16-mark-story-done-in-sprint-status-before-pr-creation"
    project_root = tmp_path / "project"
    worktree_dir = tmp_path / "worktree"
    project_root.mkdir()
    worktree_dir.mkdir()

    content = _make_sprint_status(target_slug=slug, target_status="in-progress")
    project_sprint_file = _write_sprint_status(project_root, content)
    worktree_sprint_file = _write_sprint_status(worktree_dir, content)

    await _update_sprint_status_done(slug, worktree_dir, "_spec")

    assert f"{slug}: done" in worktree_sprint_file.read_text(encoding="utf-8")
    assert f"{slug}: in-progress" in project_sprint_file.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Integration test: commit_node calls _update_sprint_status_done before commit_story()
# ---------------------------------------------------------------------------


def _make_commit_node_state(tmp_path: Path, slug: str, project_root: Path, worktree_path: Path) -> StoryState:
    return StoryState(
        story_id=StoryId(slug),
        epic_id=EpicId("epic-10"),
        run_id=RunId("20260808-120000-a7f3"),
        story_path=tmp_path / "_spec" / f"{slug}.md",
        project_root=project_root,
        status=TaskState.SUCCESS,
        worktree_path=worktree_path,
        config=_make_run_config(),
    )


def _patch_commit_node_collaborators(monkeypatch: pytest.MonkeyPatch, *, push_succeeded: bool) -> AsyncMock:
    """Patch all of commit_node's collaborators and return the sprint-status mock."""
    mock_update = AsyncMock()
    monkeypatch.setattr("arcwright_ai.engine.nodes._update_sprint_status_done", mock_update)
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", AsyncMock(return_value="abc1234"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=push_succeeded))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=None))
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.delete_remote_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_success_summary", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.extract_agent_decisions", AsyncMock(return_value=None))
    monkeypatch.setattr("arcwright_ai.engine.nodes._detect_default_branch", AsyncMock(return_value="main"))
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.git",
        AsyncMock(return_value=MagicMock(stdout="abc1234567890", returncode=0)),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.merge_pull_request",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.get_pull_request_merge_sha",
        AsyncMock(return_value=None),
    )
    return mock_update


@pytest.mark.asyncio
async def test_commit_node_calls_update_sprint_status_with_worktree_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """commit_node awaits _update_sprint_status_done with state.worktree_path, not project_root (AC: #1)."""
    slug = "10-16-mark-story-done"
    project_root = tmp_path / "project"
    worktree_path = tmp_path / "worktree"
    project_root.mkdir()
    worktree_path.mkdir()
    state = _make_commit_node_state(tmp_path, slug, project_root, worktree_path)

    mock_update = _patch_commit_node_collaborators(monkeypatch, push_succeeded=True)

    await commit_node(state)

    mock_update.assert_awaited_once_with(slug, state.worktree_path, state.config.methodology.artifacts_path)


@pytest.mark.asyncio
async def test_commit_node_updates_sprint_status_even_when_push_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """commit_node calls _update_sprint_status_done even when push_branch fails (AC: #5).

    The sprint-status update now happens before push_branch() is even attempted, so a
    failed push has no bearing on whether the update runs.
    """
    slug = "10-16-mark-story-done"
    project_root = tmp_path / "project"
    worktree_path = tmp_path / "worktree"
    project_root.mkdir()
    worktree_path.mkdir()
    state = _make_commit_node_state(tmp_path, slug, project_root, worktree_path)

    mock_update = _patch_commit_node_collaborators(monkeypatch, push_succeeded=False)

    await commit_node(state)

    mock_update.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_node_updates_sprint_status_before_commit_story(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_update_sprint_status_done is awaited before commit_story() (AC: #3)."""
    slug = "10-16-mark-story-done"
    project_root = tmp_path / "project"
    worktree_path = tmp_path / "worktree"
    project_root.mkdir()
    worktree_path.mkdir()
    state = _make_commit_node_state(tmp_path, slug, project_root, worktree_path)

    call_order: list[str] = []

    async def _record_update(*_args: object, **_kwargs: object) -> None:
        call_order.append("update_sprint_status")

    async def _record_commit(*_args: object, **_kwargs: object) -> str:
        call_order.append("commit_story")
        return "abc1234"

    monkeypatch.setattr("arcwright_ai.engine.nodes._update_sprint_status_done", _record_update)
    monkeypatch.setattr("arcwright_ai.engine.nodes.commit_story", _record_commit)
    monkeypatch.setattr("arcwright_ai.engine.nodes.push_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.generate_pr_body", AsyncMock(return_value="body"))
    monkeypatch.setattr("arcwright_ai.engine.nodes.open_pull_request", AsyncMock(return_value=None))
    monkeypatch.setattr("arcwright_ai.engine.nodes.remove_worktree", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.delete_remote_branch", AsyncMock(return_value=True))
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_story_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.update_run_status", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.write_success_summary", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.append_entry", AsyncMock())
    monkeypatch.setattr("arcwright_ai.engine.nodes.extract_agent_decisions", AsyncMock(return_value=None))
    monkeypatch.setattr("arcwright_ai.engine.nodes._detect_default_branch", AsyncMock(return_value="main"))
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.git",
        AsyncMock(return_value=MagicMock(stdout="abc1234567890", returncode=0)),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.merge_pull_request",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "arcwright_ai.engine.nodes.get_pull_request_merge_sha",
        AsyncMock(return_value=None),
    )

    await commit_node(state)

    assert call_order == ["update_sprint_status", "commit_story"]
