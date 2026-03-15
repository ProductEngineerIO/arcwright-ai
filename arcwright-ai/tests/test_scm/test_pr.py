"""Unit tests for arcwright_ai.scm.pr — PR body generator with provenance embedding."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from arcwright_ai.core.constants import STORY_COPY_FILENAME, VALIDATION_FILENAME
from arcwright_ai.core.exceptions import ScmError
from arcwright_ai.scm.pr import _detect_default_branch, generate_pr_body, open_pull_request

if TYPE_CHECKING:
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

    assert "### Decision Provenance" in body
    assert "#### Use NamedTuple for _Decision" in body
    assert "**Alternatives**" in body
    assert "**Rationale**" in body
    assert "**References**" in body
    assert "NamedTuple is immutable and lightweight." in body


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
    """generate_pr_body outputs 'No agent decisions recorded' when decisions section is empty."""
    monkeypatch.setattr(
        "arcwright_ai.scm.pr.read_text_async",
        _make_mock_read(_PROVENANCE_MINIMAL, _STORY_CONTENT),
    )

    body = await generate_pr_body(_RUN_ID, _SLUG, project_root=tmp_path)

    assert "No agent decisions recorded" in body


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
