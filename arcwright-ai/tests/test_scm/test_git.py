"""Unit tests for arcwright_ai.scm.git — Safe subprocess wrapper."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from arcwright_ai.core.exceptions import ScmError
from arcwright_ai.scm.git import GitResult, git

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_process(
    returncode: int,
    stdout: bytes = b"",
    stderr: bytes = b"",
) -> AsyncMock:
    """Create a mock asyncio.Process with preset communicate() results.

    Args:
        returncode: The exit code the process should report.
        stdout: Raw bytes to return from communicate() as stdout.
        stderr: Raw bytes to return from communicate() as stderr.

    Returns:
        AsyncMock: A mock process object compatible with asyncio subprocess API.
    """
    proc = AsyncMock()
    proc.communicate = AsyncMock(return_value=(stdout, stderr))
    proc.returncode = returncode
    return proc


# ---------------------------------------------------------------------------
# Task 1 — GitResult model
# ---------------------------------------------------------------------------


def test_git_result_success_property() -> None:
    """GitResult.success returns True for returncode=0 and False otherwise."""
    assert GitResult(stdout="ok", stderr="", returncode=0).success is True
    assert GitResult(stdout="", stderr="err", returncode=1).success is False
    assert GitResult(stdout="", stderr="", returncode=128).success is False


def test_git_result_is_frozen() -> None:
    """GitResult is a frozen Pydantic model — field assignment raises ValidationError."""
    result = GitResult(stdout="hello", stderr="", returncode=0)
    with pytest.raises(ValidationError):
        result.stdout = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Task 2 & 3 — git() wrapper: success path and logging
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_git_successful_command_returns_git_result(monkeypatch: pytest.MonkeyPatch) -> None:
    """Successful git command returns GitResult with correct fields and success=True."""
    mock_proc = _make_mock_process(returncode=0, stdout=b"output\n", stderr=b"")
    mock_exec = AsyncMock(return_value=mock_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)

    result = await git("status", "-s")

    assert isinstance(result, GitResult)
    assert result.stdout == "output"  # trailing newline stripped
    assert result.stderr == ""
    assert result.returncode == 0
    assert result.success is True


@pytest.mark.asyncio
async def test_git_logs_successful_command(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Successful git command emits a git.command info log with args in the data dict."""
    mock_proc = _make_mock_process(returncode=0, stdout=b"abc", stderr=b"")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    with caplog.at_level(logging.DEBUG, logger="arcwright_ai.scm.git"):
        await git("log", "--oneline")

    info_records = [r for r in caplog.records if r.levelname == "INFO" and r.message == "git.command"]
    assert len(info_records) == 1
    data = info_records[0].__dict__.get("data", {})
    assert data["args"] == ["log", "--oneline"]
    assert data["returncode"] == 0


@pytest.mark.asyncio
async def test_git_logs_failed_command(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Failed git command (non-lock error) emits a git.command error log."""
    mock_proc = _make_mock_process(returncode=1, stdout=b"", stderr=b"unknown error")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    with caplog.at_level(logging.ERROR, logger="arcwright_ai.scm.git"), pytest.raises(ScmError):
        await git("status")

    error_records = [r for r in caplog.records if r.levelname == "ERROR" and r.message == "git.command"]
    assert len(error_records) >= 1
    data = error_records[0].__dict__.get("data", {})
    assert data["returncode"] == 1


@pytest.mark.asyncio
async def test_git_cwd_forwarded_to_subprocess(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The cwd argument is forwarded as str to asyncio.create_subprocess_exec."""
    mock_exec = AsyncMock(return_value=_make_mock_process(0, b"ok", b""))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)

    await git("status", cwd=tmp_path)

    mock_exec.assert_called_once()
    _, kwargs = mock_exec.call_args
    assert kwargs.get("cwd") == str(tmp_path)


# ---------------------------------------------------------------------------
# Task 4 — Error classification
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_git_nonzero_exit_raises_scm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Non-zero, non-classified exit code raises ScmError with stderr and returncode in details."""
    mock_proc = _make_mock_process(returncode=1, stdout=b"", stderr=b"error msg details")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    with pytest.raises(ScmError) as exc_info:
        await git("status")

    err = exc_info.value
    assert err.details is not None
    assert "error msg details" in err.details["stderr"]
    assert err.details["returncode"] == 1


@pytest.mark.asyncio
async def test_git_permission_denied_raises_scm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """'permission denied' stderr raises ScmError with 'Permission denied' in message."""
    mock_proc = _make_mock_process(returncode=128, stdout=b"", stderr=b"fatal: permission denied")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    with pytest.raises(ScmError, match="Permission denied"):
        await git("push", "origin", "main")


@pytest.mark.asyncio
async def test_git_not_a_repo_raises_scm_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """'not a git repository' stderr raises ScmError with 'Not a git repository' in message."""
    mock_proc = _make_mock_process(
        returncode=128,
        stdout=b"",
        stderr=b"fatal: not a git repository (or any parent up to mount point /)",
    )
    monkeypatch.setattr(asyncio, "create_subprocess_exec", AsyncMock(return_value=mock_proc))

    with pytest.raises(ScmError, match="Not a git repository"):
        await git("status", cwd=Path("/tmp/not-a-repo"))


@pytest.mark.asyncio
async def test_git_lock_contention_retries_and_succeeds(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Lock contention on attempt 1 retries; succeeds on attempt 2 without raising."""
    lock_proc = _make_mock_process(
        returncode=1,
        stdout=b"",
        stderr=b"fatal: Unable to create '.git/index.lock': File exists.",
    )
    ok_proc = _make_mock_process(returncode=0, stdout=b"all good", stderr=b"")

    mock_exec = AsyncMock(side_effect=[lock_proc, ok_proc])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.git"):
        result = await git("add", ".")

    assert isinstance(result, GitResult)
    assert result.success is True
    # Exactly one retry was logged
    retry_records = [r for r in caplog.records if r.message == "git.retry"]
    assert len(retry_records) == 1


@pytest.mark.asyncio
async def test_git_lock_contention_exhausts_retries(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """After all 3 retries on lock contention, raises ScmError with 'lock' in message."""
    lock_stderr = b"fatal: Unable to create '.git/index.lock': File exists."
    lock_proc = _make_mock_process(returncode=1, stdout=b"", stderr=lock_stderr)

    # Always return the lock error process
    mock_exec = AsyncMock(return_value=lock_proc)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", mock_exec)
    monkeypatch.setattr(asyncio, "sleep", AsyncMock())

    with caplog.at_level(logging.WARNING, logger="arcwright_ai.scm.git"), pytest.raises(ScmError, match="lock"):
        await git("commit", "-m", "test")

    retry_records = [r for r in caplog.records if r.message == "git.retry"]
    assert len(retry_records) == 3
