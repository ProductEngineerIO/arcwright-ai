"""Unit tests for arcwright_ai.scm.pr — PR body generator with provenance embedding."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcwright_ai.core.constants import STORY_COPY_FILENAME, VALIDATION_FILENAME
from arcwright_ai.core.exceptions import ScmError
from arcwright_ai.scm.pr import (
    MergeOutcome,
    _detect_default_branch,
    _extract_decisions,
    _extract_implementation_decisions,
    _render_pr_body,
    generate_pr_body,
    get_pull_request_merge_sha,
    merge_pull_request,
    open_pull_request,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable
    from pathlib import Path

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

_RUN_ID = "20260101-120000-abc123"
_SLUG = "6-4-pr-body-generator"

_PROVENANCE_MINIMAL = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | All criteria satisfied |\n\n"
    "## Context Provided\n\n"
    "- AC-1\n"
)

_PROVENANCE_WITH_DECISION = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Use NamedTuple for _Decision\n\n"
    "- **Timestamp**: 2026-01-01T00:00:00Z\n"
    "- **Alternatives**: dataclass, TypedDict, Pydantic model\n"
    "- **Rationale**: NamedTuple is immutable and lightweight.\n"
    "- **References**: AC-2, D7\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | All criteria satisfied |\n\n"
    "## Context Provided\n\n"
    "- AC-2\n"
    "- D7\n"
)

_LONG_RATIONALE = "A" * 501

_PROVENANCE_LONG_RATIONALE = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Long rationale decision\n\n"
    "- **Timestamp**: 2026-01-01T00:00:00Z\n"
    "- **Alternatives**: option-a, option-b\n"
    f"- **Rationale**: {_LONG_RATIONALE}\n"
    "- **References**: None\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | ok |\n\n"
    "## Context Provided\n\n"
    "- None\n"
)

_PROVENANCE_MANY_ALTERNATIVES = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Many alternatives decision\n\n"
    "- **Timestamp**: 2026-01-01T00:00:00Z\n"
    "- **Alternatives**: opt-a, opt-b, opt-c, opt-d, opt-e, opt-f\n"
    "- **Rationale**: Chose the simplest option.\n"
    "- **References**: None\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | ok |\n\n"
    "## Context Provided\n\n"
    "- None\n"
)

_STORY_CONTENT = (
    "# Story 6.4: PR Body Generator\n\n"
    "Status: ready-for-dev\n\n"
    "## Acceptance Criteria (BDD)\n\n"
    "1. **Given** `scm/pr.py` **When** called **Then** returns PR body string.\n"
    "2. **Given** provenance exists **When** parsed **Then** includes decisions.\n\n"
    "## Tasks / Subtasks\n\n"
    "- [ ] Task 1\n"
)

_PROVENANCE_WITH_CROSS_REFS = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Architecture choice\n\n"
    "- **Timestamp**: 2026-01-01T00:00:00Z\n"
    "- **Alternatives**: option-a\n"
    "- **Rationale**: Best fit.\n"
    "- **References**: AC-2, D7\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | ok |\n\n"
    "## Context Provided\n\n"
    "- AC-2\n"
    "- D7\n"
)

_PROVENANCE_NO_HEADER = (
    "## Agent Decisions\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | ok |\n"
)

_STORY_CONTENT_UNNUMBERED_BDD = (
    "# Story 6.4: PR Body Generator\n\n"
    "Status: ready-for-dev\n\n"
    "## Acceptance Criteria (BDD)\n\n"
    "**Given** the story copy exists **When** parsed **Then** checklist entries are generated.\n"
    "- **Given** an unnumbered BDD line **When** parsed **Then** it is included.\n\n"
    "## Tasks / Subtasks\n\n"
    "- [ ] Task 1\n"
)

_LONG_DIFF_BODY = "\n".join(f"+ line {idx}" for idx in range(1, 61))
_PROVENANCE_WITH_LONG_DIFF_RATIONALE = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Include generated diff\n\n"
    "- **Timestamp**: 2026-01-01T00:00:00Z\n"
    "- **Alternatives**: None considered\n"
    f"- **Rationale**: ```diff\n{_LONG_DIFF_BODY}\n```\n"
    "- **References**: AC-2\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | ok |\n\n"
    "## Context Provided\n\n"
    "- AC-2\n"
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_mock_read(
    provenance: str,
    story: str | None = None,
) -> AsyncMock:
    """Return an AsyncMock for read_text_async dispatching by filename."""

    async def _side_effect(path: Path) -> str:
        if path.name == VALIDATION_FILENAME:
            return provenance
        if path.name == STORY_COPY_FILENAME:
            if story is None:
                raise FileNotFoundError(path)
            return story
        raise FileNotFoundError(path)

    return AsyncMock(side_effect=_side_effect)


# ---------------------------------------------------------------------------
# Task 8.1 — test_generate_pr_body_includes_story_title (AC: #14a)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_includes_story_title(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body returns markdown containing the story title from the provenance header."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert _SLUG in body
    assert "## Story:" in body


# ---------------------------------------------------------------------------
# Task 8.2 — test_generate_pr_body_includes_ac_checklist (AC: #14b)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_includes_ac_checklist(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body includes acceptance criteria as checkbox items from story.md."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Acceptance Criteria" in body
    assert "- [ ] **Given**" in body


# ---------------------------------------------------------------------------
# Task 8.3 — test_generate_pr_body_includes_validation_table (AC: #14c)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_includes_validation_table(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body includes the validation history table from provenance."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Validation Results" in body
    assert "All criteria satisfied" in body


# ---------------------------------------------------------------------------
# Task 8.4 — test_generate_pr_body_includes_decision_sections (AC: #14d)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_includes_decision_sections(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body includes decision subsections with alternatives/rationale/references."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_WITH_DECISION, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Pipeline Activity" in body
    assert "#### Use NamedTuple for _Decision" in body
    assert "**Alternatives**" in body
    assert "**Rationale**" in body
    assert "**References**" in body
    assert "NamedTuple is immutable and lightweight." in body
    assert "### Decision Provenance" not in body


# ---------------------------------------------------------------------------
# Task 8.5 — test_generate_pr_body_wraps_long_rationale_in_details (AC: #14e)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_wraps_long_rationale_in_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body wraps rationale >500 chars in <details> block."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_LONG_RATIONALE, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "<details>" in body
    assert "Rationale (click to expand)" in body


# ---------------------------------------------------------------------------
# Task 8.6 — test_generate_pr_body_wraps_many_alternatives_in_details (AC: #14f)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_wraps_many_alternatives_in_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body wraps alternatives list >5 items in <details> block."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MANY_ALTERNATIVES, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "<details>" in body
    assert "Alternatives (click to expand)" in body


# ---------------------------------------------------------------------------
# Task 8.7 — test_generate_pr_body_raises_scm_error_no_provenance (AC: #14g)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_raises_scm_error_no_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body raises ScmError when provenance file is missing."""

    async def _missing(path: Path) -> str:
        raise FileNotFoundError(path)

    monkeypatch.setattr("arcwright_ai.scm.pr.read_text_async", AsyncMock(side_effect=_missing))

    with pytest.raises(ScmError) as exc_info:
        await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert exc_info.value.details is not None
    assert exc_info.value.details["run_id"] == _RUN_ID
    assert exc_info.value.details["story_slug"] == _SLUG


# ---------------------------------------------------------------------------
# Task 8.8 — test_generate_pr_body_omits_ac_when_no_story_copy (AC: #14h)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_omits_ac_when_no_story_copy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """generate_pr_body omits AC section gracefully when story.md is missing."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, story=None),
    )

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"):
        body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Acceptance Criteria" not in body
    assert any("scm.pr.story_copy_missing" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task 8.9 — test_generate_pr_body_no_decisions_shows_note (AC: #14i)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_no_decisions_shows_note(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body outputs pipeline activity note when pipeline decisions section is empty."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "No pipeline activity recorded" in body


# ---------------------------------------------------------------------------
# Task 8.10 — test_generate_pr_body_preserves_cross_references (AC: #14j)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_preserves_cross_references(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body preserves AC/architecture cross-references (e.g. 'AC-2', 'D7') as-is."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_WITH_CROSS_REFS, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "AC-2" in body
    assert "D7" in body


# ---------------------------------------------------------------------------
# Task 8.11 — test_generate_pr_body_logs_structured_event (AC: #14k)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_logs_structured_event(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """generate_pr_body emits 'scm.pr.generate' structured log event on success."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_WITH_DECISION, _STORY_CONTENT),
    )

    with caplog.at_level(logging.INFO, logger="arcwright_ai.scm.pr"):
        await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert any("scm.pr.generate" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Task 8.12 — test_generate_pr_body_logs_warning_missing_story (AC: #14l)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_pr_body_logs_warning_missing_story(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """generate_pr_body emits 'scm.pr.story_copy_missing' warning when story.md is absent."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, story=None),
    )

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"):
        await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert any("scm.pr.story_copy_missing" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_generate_pr_body_falls_back_to_story_title_when_provenance_header_missing(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body falls back to story title from story.md when provenance header is absent."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_NO_HEADER, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "## Story: 6.4: PR Body Generator" in body


@pytest.mark.asyncio
async def test_generate_pr_body_extracts_unnumbered_bdd_acceptance_criteria(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body includes unnumbered BDD AC lines under Acceptance Criteria."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, _STORY_CONTENT_UNNUMBERED_BDD),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "- [ ] **Given** the story copy exists" in body
    assert "- [ ] **Given** an unnumbered BDD line" in body


@pytest.mark.asyncio
async def test_generate_pr_body_wraps_large_diff_fenced_blocks_in_details(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body wraps fenced diff blocks over 50 lines in details."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_WITH_LONG_DIFF_RATIONALE, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "<details><summary>Diff (60 lines)</summary>" in body


# ---------------------------------------------------------------------------
# Story 6.7 — _detect_default_branch tests (Task 5.4)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_default_branch_returns_main_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_detect_default_branch returns 'main' when all detection methods fail."""
    from arcwright_ai.core.exceptions import ScmError as _ScmError

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: None)

    async def _git_fail(*args: object, **kwargs: object) -> object:
        raise _ScmError("failed", details={})

    monkeypatch.setattr("arcwright_ai.scm.pr.git", AsyncMock(side_effect=_git_fail))

    result = await _detect_default_branch(tmp_path, "6-7-story")

    assert result == "main"


@pytest.mark.asyncio
async def test_detect_default_branch_strips_origin_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_detect_default_branch prefers parsing git remote show origin output."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="* remote origin\n  HEAD branch: main\n", stderr="", returncode=0)),
    )

    result = await _detect_default_branch(tmp_path, "6-7-story")

    assert result == "main"


@pytest.mark.asyncio
async def test_detect_default_branch_returns_branch_without_prefix(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_detect_default_branch returns parsed HEAD branch from git remote show output."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="* remote origin\n  HEAD branch: develop\n", stderr="", returncode=0)),
    )

    result = await _detect_default_branch(tmp_path, "6-7-story")

    assert result == "develop"


# ---------------------------------------------------------------------------
# Story 9.1 — _detect_default_branch config override tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_detect_default_branch_config_override(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_detect_default_branch returns override immediately when non-empty string provided."""
    from arcwright_ai.core.exceptions import ScmError as _ScmError

    # Make all git calls fail to prove override short-circuits
    async def _git_fail(*args: object, **kwargs: object) -> object:
        raise _ScmError("should not be called", details={})

    monkeypatch.setattr("arcwright_ai.scm.pr.git", AsyncMock(side_effect=_git_fail))
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: None)

    result = await _detect_default_branch(tmp_path, "9-1-story", default_branch_override="develop")

    assert result == "develop"


@pytest.mark.asyncio
async def test_detect_default_branch_empty_override_uses_cascade(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_detect_default_branch runs the existing cascade when override is empty string."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="* remote origin\n  HEAD branch: main\n", stderr="", returncode=0)),
    )

    result = await _detect_default_branch(tmp_path, "9-1-story", default_branch_override="")

    assert result == "main"


@pytest.mark.asyncio
async def test_detect_default_branch_strips_whitespace_before_return(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """_detect_default_branch returns stripped branch name when override has surrounding whitespace."""
    from arcwright_ai.core.exceptions import ScmError as _ScmError

    async def _git_fail(*args: object, **kwargs: object) -> object:
        raise _ScmError("should not be called", details={})

    monkeypatch.setattr("arcwright_ai.scm.pr.git", AsyncMock(side_effect=_git_fail))
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: None)

    result = await _detect_default_branch(tmp_path, "9-1-story", default_branch_override="  develop  ")

    assert result == "develop"


# ---------------------------------------------------------------------------
# Story 6.7 — open_pull_request tests (Task 5.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_pull_request_returns_none_when_gh_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """open_pull_request returns None when gh CLI is not on PATH."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: None)

    result = await open_pull_request(
        "arcwright-ai/my-story",
        "6-7-push-branch",
        "PR body",
        project_root=tmp_path,
    )

    assert result is None


@pytest.mark.asyncio
async def test_open_pull_request_logs_skipped_when_gh_not_found(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """open_pull_request logs scm.pr.create.skipped with reason=gh_not_found."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: None)
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="https://github.com/owner/repo.git", stderr="", returncode=0)),
    )

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"):
        await open_pull_request(
            "arcwright-ai/my-story",
            "6-7-push-branch",
            "PR body",
            project_root=tmp_path,
        )

    assert any("scm.pr.create.skipped" in r.message for r in caplog.records)
    manual_url_logs = [r for r in caplog.records if r.message == "scm.pr.create.skipped"]
    assert manual_url_logs
    data = getattr(manual_url_logs[-1], "data", {})
    assert data.get("manual_pr_url") == "https://github.com/owner/repo/pull/new/arcwright-ai/my-story"


@pytest.mark.asyncio
async def test_open_pull_request_returns_pr_url_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """open_pull_request returns the PR URL extracted from gh stdout."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="origin/main", stderr="", returncode=0)),
    )

    pr_url = "https://github.com/owner/repo/pull/42"

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(pr_url.encode(), b""))

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await open_pull_request(
            "arcwright-ai/my-story",
            "6-7-push-branch",
            "PR body",
            project_root=tmp_path,
        )

    assert result == pr_url


@pytest.mark.asyncio
async def test_open_pull_request_logs_create_event_on_success(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """open_pull_request logs scm.pr.create on success."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="origin/main", stderr="", returncode=0)),
    )

    pr_url = "https://github.com/owner/repo/pull/42"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(pr_url.encode(), b""))

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
        caplog.at_level(logging.INFO, logger="arcwright_ai.scm.pr"),
    ):
        await open_pull_request(
            "arcwright-ai/my-story",
            "6-7-push-branch",
            "PR body",
            project_root=tmp_path,
        )

    assert any("scm.pr.create" in r.message for r in caplog.records)


@pytest.mark.asyncio
async def test_open_pull_request_returns_none_on_gh_auth_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """open_pull_request returns None when gh exits with non-zero (auth failure)."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="origin/main", stderr="", returncode=0)),
    )

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"not authenticated"))

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await open_pull_request(
            "arcwright-ai/my-story",
            "6-7-push-branch",
            "PR body",
            project_root=tmp_path,
        )

    assert result is None


@pytest.mark.asyncio
async def test_open_pull_request_returns_none_when_pr_already_exists(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """open_pull_request returns None and logs pr_already_exists when PR exists."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="origin/main", stderr="", returncode=0)),
    )

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(
        return_value=(b"", b"a pull request for branch 'arcwright-ai/my-story' already exists")
    )

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await open_pull_request(
            "arcwright-ai/my-story",
            "6-7-push-branch",
            "PR body",
            project_root=tmp_path,
        )

    assert result is None


@pytest.mark.asyncio
async def test_open_pull_request_pr_title_humanized_from_slug(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """open_pull_request passes a humanized title derived from the story slug."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="origin/main", stderr="", returncode=0)),
    )

    pr_url = "https://github.com/owner/repo/pull/42"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(pr_url.encode(), b""))

    captured_args: list[tuple[str, ...]] = []

    async def mock_exec(*args: str, **kwargs: object) -> MagicMock:
        captured_args.append(args)
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", mock_exec):
        await open_pull_request(
            "arcwright-ai/6-7-push-branch",
            "6-7-push-branch",
            "PR body",
            project_root=tmp_path,
        )

    assert captured_args, "create_subprocess_exec was not called"
    pr_create_call = next((args for args in captured_args if "--title" in args), None)
    assert pr_create_call is not None
    title_idx = list(pr_create_call).index("--title")
    assert pr_create_call[title_idx + 1] == "[arcwright-ai] Push Branch"


# ---------------------------------------------------------------------------
# Story 9.1 — open_pull_request default_branch passthrough test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_open_pull_request_passes_default_branch(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """open_pull_request forwards default_branch to _detect_default_branch."""
    from arcwright_ai.scm.git import GitResult

    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.git",
        AsyncMock(return_value=GitResult(stdout="origin/main", stderr="", returncode=0)),
    )

    pr_url = "https://github.com/owner/repo/pull/99"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(pr_url.encode(), b""))

    captured_base: list[str] = []

    async def mock_exec(*args: str, **kwargs: object) -> MagicMock:
        args_list = list(args)
        if "--base" in args_list:
            base_idx = args_list.index("--base")
            captured_base.append(args_list[base_idx + 1])
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", mock_exec):
        result = await open_pull_request(
            "arcwright-ai/my-story",
            "9-1-story",
            "PR body",
            project_root=tmp_path,
            default_branch="develop",
        )

    assert result == pr_url
    # The --base argument should be "develop" (from the config override)
    assert captured_base == ["develop"]


# ---------------------------------------------------------------------------
# Story 9.3 — merge_pull_request unit tests (AC: #15)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_pull_request_calls_gh_merge_squash(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request calls gh pr merge <number> --squash --delete-branch."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"Squashed and merged pull request #42", b""))

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        captured_args.append(args)
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    assert len(captured_args) == 1
    args = captured_args[0]
    assert args[0] == "gh"
    assert args[1] == "pr"
    assert args[2] == "merge"
    assert args[3] == "42"
    assert "--squash" in args
    assert "--delete-branch" in args


@pytest.mark.asyncio
async def test_merge_pull_request_returns_true_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request returns MergeOutcome.MERGED when gh exits with returncode 0."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"Merged", b""))

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    assert result is MergeOutcome.MERGED


@pytest.mark.asyncio
async def test_merge_pull_request_returns_false_on_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request returns MergeOutcome.ERROR on non-zero returncode without raising."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"merge conflict"))

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    assert result is MergeOutcome.ERROR


@pytest.mark.asyncio
async def test_merge_pull_request_extracts_pr_number_from_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request correctly parses PR number from a full GitHub URL."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"Merged", b""))

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        captured_args.append(args)
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    assert captured_args[0][3] == "42"


@pytest.mark.asyncio
async def test_merge_pull_request_returns_false_gh_not_found(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request returns MergeOutcome.ERROR immediately when gh CLI is not on PATH."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: None)

    result = await merge_pull_request(
        "https://github.com/owner/repo/pull/42",
        project_root=tmp_path,
    )

    assert result is MergeOutcome.ERROR


@pytest.mark.asyncio
async def test_merge_pull_request_passes_merge_strategy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request passes --merge flag when strategy='merge'."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"Merged", b""))

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        captured_args.append(args)
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            "merge",
            project_root=tmp_path,
        )

    assert "--merge" in captured_args[0]
    assert "--squash" not in captured_args[0]


@pytest.mark.asyncio
async def test_merge_pull_request_passes_rebase_strategy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request passes --rebase flag when strategy='rebase'."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"Rebased", b""))

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        captured_args.append(args)
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            "rebase",
            project_root=tmp_path,
        )

    assert "--rebase" in captured_args[0]
    assert "--squash" not in captured_args[0]


@pytest.mark.asyncio
async def test_merge_pull_request_logs_success_event(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """merge_pull_request logs scm.pr.merge info event with metadata on success."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"abc1234 Squashed and merged", b""))

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
        caplog.at_level(logging.INFO, logger="arcwright_ai.scm.pr"),
    ):
        await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    merge_records = [r for r in caplog.records if r.message == "scm.pr.merge"]
    assert merge_records, "Expected scm.pr.merge info event"
    data = getattr(merge_records[0], "data", {})
    assert data.get("pr_number") == "42"
    assert data.get("strategy") == "squash"
    assert data.get("merge_sha") != ""


@pytest.mark.asyncio
async def test_merge_pull_request_logs_failure_warning(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """merge_pull_request logs scm.pr.merge.failed warning on non-zero returncode."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", b"required review"))

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)),
        caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"),
    ):
        await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    fail_records = [r for r in caplog.records if r.message == "scm.pr.merge.failed"]
    assert fail_records, "Expected scm.pr.merge.failed warning"
    data = getattr(fail_records[0], "data", {})
    assert data.get("returncode") == 1


@pytest.mark.asyncio
async def test_merge_pull_request_returns_false_on_invalid_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request returns MergeOutcome.ERROR when PR URL has no /pull/<number>."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    result = await merge_pull_request(
        "https://github.com/owner/repo/issues/42",
        project_root=tmp_path,
    )

    assert result is MergeOutcome.ERROR


@pytest.mark.asyncio
async def test_merge_pull_request_returns_false_on_subprocess_exception(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request returns MergeOutcome.ERROR when subprocess raises an exception."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    async def _raise(*args: object, **kwargs: object) -> None:
        raise OSError("file not found")

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _raise):
        result = await merge_pull_request(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    assert result is MergeOutcome.ERROR


@pytest.mark.asyncio
async def test_get_pull_request_merge_sha_returns_sha_on_success(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """get_pull_request_merge_sha returns merge commit SHA from gh pr view."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"abc1234def5678", b""))

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await get_pull_request_merge_sha(
            "https://github.com/owner/repo/pull/42",
            project_root=tmp_path,
        )

    assert result == "abc1234def5678"


@pytest.mark.asyncio
async def test_get_pull_request_merge_sha_returns_none_on_invalid_url(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """get_pull_request_merge_sha returns None for non-PR URLs."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    result = await get_pull_request_merge_sha(
        "https://github.com/owner/repo/issues/42",
        project_root=tmp_path,
    )

    assert result is None


# ---------------------------------------------------------------------------
# Story 12.1 — MergeOutcome StrEnum
# ---------------------------------------------------------------------------


def test_merge_outcome_enum_values() -> None:
    """MergeOutcome StrEnum has the expected string values."""
    from arcwright_ai.scm.pr import MergeOutcome

    assert set(MergeOutcome) == {"merged", "skipped", "ci_failed", "timeout", "error"}
    assert MergeOutcome.MERGED == "merged"
    assert MergeOutcome.SKIPPED == "skipped"
    assert MergeOutcome.CI_FAILED == "ci_failed"
    assert MergeOutcome.TIMEOUT == "timeout"
    assert MergeOutcome.ERROR == "error"


def test_merge_outcome_exported_from_scm_package() -> None:
    """MergeOutcome is accessible via the scm package __init__."""
    from arcwright_ai.scm import MergeOutcome

    assert MergeOutcome.MERGED == "merged"


# ---------------------------------------------------------------------------
# Story 12.2 — CI-wait merge_pull_request unit tests
# ---------------------------------------------------------------------------

_PR_URL = "https://github.com/owner/repo/pull/42"


def _make_mock_proc(
    returncode: int = 0,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> MagicMock:
    """Create a mock subprocess with configurable returncode/stdout/stderr."""
    proc = MagicMock()
    proc.returncode = returncode
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.wait = AsyncMock(return_value=returncode)
    proc.terminate = MagicMock()
    proc.kill = MagicMock()
    return proc


@pytest.mark.asyncio
async def test_merge_pr_auto_flag_when_wait_timeout_positive(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When wait_timeout > 0, gh pr merge is called with --auto flag."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = _make_mock_proc()
    view_proc = _make_mock_proc(stdout=b"MERGED")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        captured_args.append(args)
        call_count += 1
        if call_count == 1:
            return merge_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    # First call should be gh pr merge with --auto
    assert "--auto" in captured_args[0]
    assert "merge" in captured_args[0]


@pytest.mark.asyncio
async def test_merge_pr_checks_watch_called_after_auto(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """After gh pr merge --auto, gh pr checks --watch --fail-fast is called."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = _make_mock_proc()
    view_proc = _make_mock_proc(stdout=b"MERGED")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        captured_args.append(args)
        call_count += 1
        if call_count == 1:
            return merge_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    # First call: gh pr merge --auto
    assert captured_args[0][1] == "pr"
    assert captured_args[0][2] == "merge"
    assert "--auto" in captured_args[0]

    # Second call: gh pr checks --watch --fail-fast
    assert captured_args[1][1] == "pr"
    assert captured_args[1][2] == "checks"
    assert "--watch" in captured_args[1]
    assert "--fail-fast" in captured_args[1]


@pytest.mark.asyncio
async def test_merge_pr_returns_merged_on_ci_pass(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CI passes → verify merge → MergeOutcome.MERGED."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = _make_mock_proc()  # exit 0 = CI passed
    view_proc = _make_mock_proc(stdout=b"MERGED")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    assert result is MergeOutcome.MERGED


@pytest.mark.asyncio
async def test_merge_pr_returns_ci_failed_on_check_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """CI fails (exit 1) → MergeOutcome.CI_FAILED."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = _make_mock_proc(returncode=1)

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        return checks_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    assert result is MergeOutcome.CI_FAILED


@pytest.mark.asyncio
async def test_merge_pr_returns_error_on_non_ci_check_failure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Non-CI gh checks failures (exit != 1) return MergeOutcome.ERROR."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = _make_mock_proc(returncode=2, stderr=b"network/auth failure")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        return checks_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    assert result is MergeOutcome.ERROR


@pytest.mark.asyncio
async def test_merge_pr_returns_timeout_on_asyncio_timeout(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """TimeoutError during gh pr checks → subprocess terminated → MergeOutcome.TIMEOUT."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = MagicMock()
    checks_proc.returncode = None
    checks_proc.communicate = AsyncMock(side_effect=TimeoutError)
    checks_proc.wait = AsyncMock(return_value=0)
    checks_proc.terminate = MagicMock()
    checks_proc.kill = MagicMock()
    # PR view shows OPEN (not merged)
    view_proc = _make_mock_proc(stdout=b"OPEN")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    wait_for_calls: list[float] = []

    async def _selective_wait_for(coro: Awaitable[Any], *, timeout: float) -> Any:  # type: ignore[override]
        wait_for_calls.append(timeout)
        if len(wait_for_calls) == 1:
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            raise TimeoutError
        return await coro

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec),
        patch("arcwright_ai.scm.pr.asyncio.wait_for", _selective_wait_for),
    ):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=2)

    assert result is MergeOutcome.TIMEOUT
    checks_proc.terminate.assert_called_once()


@pytest.mark.asyncio
async def test_merge_pr_no_wait_when_timeout_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """wait_timeout=0 → no --auto flag, no gh pr checks call, immediate merge."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    captured_args: list[tuple[str, ...]] = []
    mock_proc = _make_mock_proc(stdout=b"Squashed and merged")

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        captured_args.append(args)
        return mock_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=0)

    assert result is MergeOutcome.MERGED
    # Only one subprocess call — the immediate merge
    assert len(captured_args) == 1
    assert "--auto" not in captured_args[0]
    # No checks call
    assert all("checks" not in str(args) for args in captured_args)


@pytest.mark.asyncio
async def test_merge_pr_returns_skipped_never(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request() never returns MergeOutcome.SKIPPED (only commit_node sets that)."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    # Success path
    mock_proc = _make_mock_proc(stdout=b"Merged")
    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc)):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path)
    assert result is not MergeOutcome.SKIPPED

    # Failure path
    mock_proc_fail = _make_mock_proc(returncode=1, stderr=b"error")
    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=mock_proc_fail)):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path)
    assert result is not MergeOutcome.SKIPPED


@pytest.mark.asyncio
async def test_merge_pr_timeout_verify_actually_merged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Timeout fires but PR was already merged → MergeOutcome.MERGED (not TIMEOUT)."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = MagicMock()
    checks_proc.returncode = None
    checks_proc.communicate = AsyncMock(side_effect=TimeoutError)
    checks_proc.wait = AsyncMock(return_value=0)
    checks_proc.terminate = MagicMock()
    checks_proc.kill = MagicMock()
    # PR view shows MERGED (race window)
    view_proc = _make_mock_proc(stdout=b"MERGED")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    wait_for_calls: list[float] = []

    async def _selective_wait_for(coro: Awaitable[Any], *, timeout: float) -> Any:  # type: ignore[override]
        wait_for_calls.append(timeout)
        if len(wait_for_calls) == 1:
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            raise TimeoutError
        return await coro

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec),
        patch("arcwright_ai.scm.pr.asyncio.wait_for", _selective_wait_for),
    ):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=2)

    assert result is MergeOutcome.MERGED


@pytest.mark.asyncio
async def test_merge_pr_timeout_subprocess_sigterm(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """On timeout, proc.terminate() is called; proc.kill() is NOT called if wait completes."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(stdout=b"Auto-merge enabled")
    checks_proc = MagicMock()
    checks_proc.returncode = None
    checks_proc.communicate = AsyncMock(side_effect=TimeoutError)
    # proc.wait completes within grace period (no SIGKILL needed)
    checks_proc.wait = AsyncMock(return_value=0)
    checks_proc.terminate = MagicMock()
    checks_proc.kill = MagicMock()
    view_proc = _make_mock_proc(stdout=b"OPEN")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    wait_for_calls: list[float] = []

    async def _selective_wait_for(coro: Awaitable[Any], *, timeout: float) -> Any:  # type: ignore[override]
        wait_for_calls.append(timeout)
        if len(wait_for_calls) == 1:
            # First call: proc.communicate — raise TimeoutError
            close = getattr(coro, "close", None)
            if callable(close):
                close()
            raise TimeoutError
        # Second call: proc.wait (5s grace period) — let it succeed
        return await coro

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec),
        patch("arcwright_ai.scm.pr.asyncio.wait_for", _selective_wait_for),
    ):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=2)

    checks_proc.terminate.assert_called_once()
    checks_proc.kill.assert_not_called()
    assert result is MergeOutcome.TIMEOUT


@pytest.mark.asyncio
async def test_merge_pr_auto_merge_not_allowed_stderr(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Stderr 'auto-merge is not allowed' → MergeOutcome.ERROR with actionable log."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(
        returncode=1,
        stderr=b"auto-merge is not allowed for this repository",
    )

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        return merge_proc

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec),
        caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"),
    ):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    assert result is MergeOutcome.ERROR
    # Verify log mentions how to enable auto-merge
    fail_records = [r for r in caplog.records if "auto_merge_not_allowed" in str(getattr(r, "data", {}))]
    assert fail_records, "Expected log with auto_merge_not_allowed reason"
    data = getattr(fail_records[0], "data", {})
    assert "Settings" in data.get("hint", "") and "Allow auto-merge" in data.get("hint", "")


# ---------------------------------------------------------------------------
# Story 10.7 — PR body includes decisions from post-fix provenance format (AC: #2, #3)
# ---------------------------------------------------------------------------

_PROVENANCE_POST_FIX = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Agent invoked for story 6-4-pr-body-generator (attempt 1)\n\n"
    "- **Timestamp**: 2026-03-01T00:00:00Z\n"
    "- **Alternatives**: claude-sonnet-4-5\n"
    "- **Rationale**: Dispatch decision for attempt 1\n"
    "- **References**: AC1\n\n"
    "### Decision: Validation attempt 1: pass\n\n"
    "- **Timestamp**: 2026-03-01T00:01:00Z\n"
    "- **Alternatives**: claude-sonnet-4-5\n"
    "- **Rationale**: All checks passed (V6: 3 checks)\nValidation row: | 1 | pass | All checks passed |\n"
    "- **References**: \n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | All checks passed |\n\n"
    "## Context Provided\n\n"
    "- AC1\n"
)


@pytest.mark.asyncio
async def test_generate_pr_body_includes_decisions_from_post_fix_provenance(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body returns populated Pipeline Activity section from post-fix provenance.

    AC #2 and #3: after validate_node preserves ## Agent Decisions,
    _extract_decisions() finds them and _render_pr_body() includes them.
    """
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_POST_FIX, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Pipeline Activity" in body
    assert "Agent invoked for story 6-4-pr-body-generator" in body
    assert "Validation attempt 1: pass" in body
    assert "No pipeline activity recorded" not in body


# ---------------------------------------------------------------------------
# Story 10.6 — split merge/cleanup outcome tests (AC: #1, #2, #3, #5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_merge_immediate_merge_succeeds_cleanup_fails_returns_merged(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """merge_pull_request (immediate) returns MERGED when PR merged but local branch cleanup failed."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    # gh pr merge exits non-zero because local branch is checked out in a worktree
    merge_proc = _make_mock_proc(
        returncode=1,
        stderr=b"error: Cannot delete branch 'arcwright-ai/my-story' checked out at '/path/to/worktree'",
    )
    # gh pr view confirms PR was actually merged
    view_proc = _make_mock_proc(stdout=b"MERGED")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        return view_proc

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec),
        caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"),
    ):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path)

    assert result is MergeOutcome.MERGED
    cleanup_records = [r for r in caplog.records if r.message == "scm.pr.post_merge_cleanup.failed"]
    assert cleanup_records, "Expected scm.pr.post_merge_cleanup.failed warning event"
    data = getattr(cleanup_records[0], "data", {})
    assert data.get("pr_number") == "42"
    assert "pr_merged_but_local_cleanup_failed" in data.get("note", "")


@pytest.mark.asyncio
async def test_merge_immediate_real_failure_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request (immediate) returns ERROR when PR was not actually merged."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    merge_proc = _make_mock_proc(returncode=1, stderr=b"error: merge conflict")
    # gh pr view shows PR is still OPEN (not merged)
    view_proc = _make_mock_proc(stdout=b"OPEN")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return merge_proc
        return view_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path)

    assert result is MergeOutcome.ERROR


@pytest.mark.asyncio
async def test_merge_immediate_success_and_cleanup_success_returns_merged(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """merge_pull_request (immediate) returns MERGED on clean success (no cleanup failure)."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    proc = _make_mock_proc(returncode=0, stdout=b"abc1234 Squashed and merged pull request #42")

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", AsyncMock(return_value=proc)):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path)

    assert result is MergeOutcome.MERGED


@pytest.mark.asyncio
async def test_merge_auto_queue_cleanup_failure_continues_to_ci_wait(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
) -> None:
    """Auto-merge path: branch-checkout cleanup error in step A is non-blocking; CI-wait continues."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    # Step A: gh pr merge --auto exits non-zero due to local branch checkout error
    queue_proc = _make_mock_proc(
        returncode=1,
        stderr=b"error: Cannot delete branch 'arcwright-ai/my-story' checked out at '/wt'",
    )
    # Step B: gh pr checks passes
    checks_proc = _make_mock_proc(returncode=0)
    # Step C: gh pr view confirms MERGED
    view_proc = _make_mock_proc(stdout=b"MERGED")

    call_count = 0

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return queue_proc
        if call_count == 2:
            return checks_proc
        return view_proc

    with (
        patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec),
        caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.pr"),
    ):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    assert result is MergeOutcome.MERGED
    cleanup_records = [r for r in caplog.records if r.message == "scm.pr.post_merge_cleanup.failed"]
    assert cleanup_records, "Expected scm.pr.post_merge_cleanup.failed warning for auto-merge path"
    data = getattr(cleanup_records[0], "data", {})
    assert "auto_merge_queued_but_local_cleanup_failed" in data.get("note", "")


@pytest.mark.asyncio
async def test_merge_auto_queue_real_failure_returns_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """Auto-merge path: non-cleanup step-A failure still returns ERROR."""
    monkeypatch.setattr("arcwright_ai.scm.pr.shutil.which", lambda _: "/usr/local/bin/gh")

    # Step A fails with an unrelated error (e.g. network issue)
    queue_proc = _make_mock_proc(returncode=1, stderr=b"error: could not resolve host github.com")

    async def _mock_exec(*args: str, **kwargs: object) -> MagicMock:
        return queue_proc

    with patch("arcwright_ai.scm.pr.asyncio.create_subprocess_exec", _mock_exec):
        result = await merge_pull_request(_PR_URL, project_root=tmp_path, wait_timeout=300)

    assert result is MergeOutcome.ERROR


# ---------------------------------------------------------------------------
# Fixture: provenance with ## Implementation Decisions section
# ---------------------------------------------------------------------------

_PROVENANCE_WITH_IMPL_DECISIONS = (
    f"# Provenance: {_SLUG}\n\n"
    "## Agent Decisions\n\n"
    "### Decision: Low-level pipeline choice\n\n"
    "- **Timestamp**: 2026-01-01T00:00:00Z\n"
    "- **Alternatives**: option-x\n"
    "- **Rationale**: Pipeline metadata reason.\n"
    "- **References**: None\n\n"
    "## Implementation Decisions\n\n"
    "### Decision: Used Strategy pattern for dispatch\n\n"
    "- **Timestamp**: 2026-01-02T00:00:00Z\n"
    "- **Alternatives**: if/else chain, registry dict\n"
    "- **Rationale**: Extensibility without modifying existing code.\n"
    "- **References**: AC-1, FR-9\n\n"
    "## Validation History\n\n"
    "| Attempt | Result | Feedback |\n"
    "|---------|--------|----------|\n"
    "| 1 | pass | All criteria satisfied |\n\n"
    "## Context Provided\n\n"
    "- AC-1\n"
    "- FR-9\n"
)

_PROVENANCE_NO_IMPL_DECISIONS = _PROVENANCE_WITH_DECISION  # no ## Implementation Decisions section


# ---------------------------------------------------------------------------
# 5.3 — _render_pr_body() produces ### Agent Decisions and ### Pipeline Activity
# ---------------------------------------------------------------------------


def test_render_pr_body_has_agent_decisions_section_with_impl() -> None:
    """_render_pr_body renders ### Agent Decisions when impl_decisions is provided."""
    from arcwright_ai.scm.pr import _Decision

    impl = [_Decision(title="Strategy pattern", timestamp="t", rationale="r", alternatives=["x"], references=["AC-1"])]
    body = _render_pr_body("title", [], "", [], impl_decisions=impl)

    assert "### Agent Decisions" in body
    assert "Strategy pattern" in body


def test_render_pr_body_agent_decisions_unavailable_when_none() -> None:
    """_render_pr_body renders 'Decision extraction unavailable' when impl_decisions is None."""
    body = _render_pr_body("title", [], "", [], impl_decisions=None)

    assert "### Agent Decisions" in body
    assert "Decision extraction unavailable" in body


def test_render_pr_body_agent_decisions_unavailable_when_empty() -> None:
    """_render_pr_body renders 'Decision extraction unavailable' when impl_decisions is []."""
    body = _render_pr_body("title", [], "", [], impl_decisions=[])

    assert "### Agent Decisions" in body
    assert "Decision extraction unavailable" in body


def test_render_pr_body_has_pipeline_activity_section() -> None:
    """_render_pr_body includes ### Pipeline Activity (not ### Decision Provenance)."""
    body = _render_pr_body("title", [], "", [], impl_decisions=None)

    assert "### Pipeline Activity" in body
    assert "### Decision Provenance" not in body


def test_render_pr_body_pipeline_activity_renders_decisions() -> None:
    """_render_pr_body renders pipeline decisions under ### Pipeline Activity."""
    from arcwright_ai.scm.pr import _Decision

    decisions = [_Decision(title="Some pipeline choice", timestamp="t", rationale="r", alternatives=[], references=[])]
    body = _render_pr_body("title", [], "", decisions, impl_decisions=None)

    assert "### Pipeline Activity" in body
    assert "Some pipeline choice" in body


@pytest.mark.asyncio
async def test_generate_pr_body_agent_decisions_section_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body includes ### Agent Decisions with LLM-extracted content."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_WITH_IMPL_DECISIONS, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Agent Decisions" in body
    assert "Used Strategy pattern for dispatch" in body


@pytest.mark.asyncio
async def test_generate_pr_body_pipeline_activity_section_present(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body includes ### Pipeline Activity for ## Agent Decisions content."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_WITH_IMPL_DECISIONS, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Pipeline Activity" in body
    assert "Low-level pipeline choice" in body


@pytest.mark.asyncio
async def test_generate_pr_body_decision_extraction_unavailable_fallback(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """generate_pr_body shows 'Decision extraction unavailable' when no ## Implementation Decisions."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_NO_IMPL_DECISIONS, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "### Agent Decisions" in body
    assert "Decision extraction unavailable" in body


# ---------------------------------------------------------------------------
# 5.4 — _extract_implementation_decisions() and _extract_decisions() boundaries
# ---------------------------------------------------------------------------


def test_extract_implementation_decisions_parses_correctly() -> None:
    """_extract_implementation_decisions parses ## Implementation Decisions section."""
    decisions = _extract_implementation_decisions(_PROVENANCE_WITH_IMPL_DECISIONS)

    assert len(decisions) == 1
    d = decisions[0]
    assert d.title == "Used Strategy pattern for dispatch"
    assert "if/else chain" in d.alternatives
    assert d.rationale == "Extensibility without modifying existing code."
    assert "AC-1" in d.references


def test_extract_implementation_decisions_returns_empty_when_absent() -> None:
    """_extract_implementation_decisions returns [] when section is not in provenance."""
    decisions = _extract_implementation_decisions(_PROVENANCE_WITH_DECISION)

    assert decisions == []


def test_extract_implementation_decisions_does_not_bleed_into_validation_history() -> None:
    """_extract_implementation_decisions boundary stops at ## Validation History."""
    decisions = _extract_implementation_decisions(_PROVENANCE_WITH_IMPL_DECISIONS)

    # Should only find the one decision in ## Implementation Decisions
    assert len(decisions) == 1
    assert all("Validation" not in d.title for d in decisions)


def test_extract_decisions_excludes_implementation_section() -> None:
    """_extract_decisions() stops at ## Implementation Decisions and excludes its content."""
    decisions = _extract_decisions(_PROVENANCE_WITH_IMPL_DECISIONS)

    # Only the ## Agent Decisions entry should be found
    assert len(decisions) == 1
    assert decisions[0].title == "Low-level pipeline choice"
    assert not any(d.title == "Used Strategy pattern for dispatch" for d in decisions)
