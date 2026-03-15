"""Unit tests for arcwright_ai.agent.sandbox — path validation layer."""

from __future__ import annotations

from pathlib import Path

import pytest

from arcwright_ai.agent.sandbox import PathValidator, validate_path, validate_temp_path
from arcwright_ai.core.exceptions import AgentError, SandboxViolation

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def project_root(tmp_path: Path) -> Path:
    """Create a temporary project root with standard subdirectories.

    Args:
        tmp_path: Pytest-provided temporary directory.

    Returns:
        Path to the created project root directory.
    """
    root = tmp_path / "my-project"
    root.mkdir()
    (root / ".arcwright-ai" / "tmp").mkdir(parents=True)
    (root / "src").mkdir()
    return root


@pytest.fixture
def arcwright_tmp(project_root: Path) -> Path:
    """Return the .arcwright-ai/tmp path within the project root.

    Args:
        project_root: The project root fixture.

    Returns:
        Path to .arcwright-ai/tmp directory.
    """
    return project_root / ".arcwright-ai" / "tmp"


# ---------------------------------------------------------------------------
# validate_path — happy path
# ---------------------------------------------------------------------------


def test_validate_path_allows_file_within_project(project_root: Path) -> None:
    """validate_path returns True for a file inside the project boundary."""
    target = project_root / "src" / "main.py"
    target.touch()
    assert validate_path(target, project_root, "write") is True


def test_validate_path_allows_nested_subdirectory(project_root: Path) -> None:
    """validate_path returns True for a deeply nested path inside the project."""
    nested = project_root / "src" / "deep" / "nested"
    nested.mkdir(parents=True)
    target = nested / "file.py"
    target.touch()
    assert validate_path(target, project_root, "read") is True


def test_validate_path_allows_relative_path_within_project(project_root: Path) -> None:
    """validate_path resolves relative paths against project_root, not process cwd."""
    target = project_root / "src" / "relative.py"
    target.touch()
    assert validate_path(Path("src/relative.py"), project_root, "write") is True


def test_validate_path_allows_arcwright_subdirectory(project_root: Path) -> None:
    """validate_path returns True for paths inside .arcwright-ai subdirectories."""
    runs_dir = project_root / ".arcwright-ai" / "runs" / "12345"
    runs_dir.mkdir(parents=True)
    target = runs_dir / "output.md"
    target.touch()
    assert validate_path(target, project_root, "read") is True


def test_validate_path_allows_symlink_within_project(project_root: Path) -> None:
    """validate_path returns True for a symlink that resolves inside the project."""
    real_dir = project_root / "src" / "real"
    real_dir.mkdir(parents=True)
    (real_dir / "file.py").touch()
    link = project_root / "src" / "link_dir"
    link.symlink_to(real_dir)
    assert validate_path(link / "file.py", project_root, "read") is True


# ---------------------------------------------------------------------------
# validate_path — rejection cases
# ---------------------------------------------------------------------------


def test_validate_path_rejects_path_traversal(project_root: Path) -> None:
    """validate_path raises SandboxViolation for paths with '..' components."""
    evil = project_root / ".." / "etc" / "passwd"
    with pytest.raises(SandboxViolation) as exc_info:
        validate_path(evil, project_root, "read")
    assert ".." in str(exc_info.value) or "traversal" in str(exc_info.value).lower()


def test_validate_path_rejects_double_dot_even_if_resolves_inside(
    project_root: Path,
) -> None:
    """Paths with '..' are rejected even if the resolved path is inside the project (defense-in-depth)."""
    # project_root/src/../src/file.py resolves inside but has '..'
    crafted = project_root / "src" / ".." / "src" / "file.py"
    with pytest.raises(SandboxViolation, match=r"traversal|\.\.."):
        validate_path(crafted, project_root, "write")


def test_validate_path_rejects_absolute_outside_project(project_root: Path) -> None:
    """validate_path raises SandboxViolation for absolute paths outside the project."""
    outside = Path("/etc/passwd")
    with pytest.raises(SandboxViolation):
        validate_path(outside, project_root, "read")


def test_validate_temp_path_allows_relative_tmp_path(project_root: Path, arcwright_tmp: Path) -> None:
    """validate_temp_path resolves relative paths against project_root."""
    target = arcwright_tmp / "relative-temp.txt"
    target.touch()
    assert validate_temp_path(Path(".arcwright-ai/tmp/relative-temp.txt"), project_root) is True


def test_validate_path_rejects_symlink_escape(project_root: Path) -> None:
    """validate_path raises SandboxViolation when a symlink resolves outside the project."""
    link = project_root / "evil_link"
    link.symlink_to(Path("/tmp"))
    target = link / "file.txt"
    with pytest.raises(SandboxViolation):
        validate_path(target, project_root, "write")


# ---------------------------------------------------------------------------
# validate_path — error message quality
# ---------------------------------------------------------------------------


def test_validate_path_operation_appears_in_error(project_root: Path) -> None:
    """The operation string appears in the SandboxViolation error message."""
    outside = Path("/etc/hosts")
    with pytest.raises(SandboxViolation) as exc_info:
        validate_path(outside, project_root, "my_special_op")
    assert "my_special_op" in str(exc_info.value)


# ---------------------------------------------------------------------------
# validate_temp_path — happy path
# ---------------------------------------------------------------------------


def test_validate_temp_path_allows_arcwright_tmp(project_root: Path, arcwright_tmp: Path) -> None:
    """validate_temp_path returns True for a file directly in .arcwright-ai/tmp."""
    target = arcwright_tmp / "scratch.txt"
    target.touch()
    assert validate_temp_path(target, project_root) is True


def test_validate_temp_path_allows_nested_tmp(project_root: Path, arcwright_tmp: Path) -> None:
    """validate_temp_path returns True for a file in a subdirectory of .arcwright-ai/tmp."""
    sub = arcwright_tmp / "sub"
    sub.mkdir()
    target = sub / "file.txt"
    target.touch()
    assert validate_temp_path(target, project_root) is True


# ---------------------------------------------------------------------------
# validate_temp_path — rejection cases
# ---------------------------------------------------------------------------


def test_validate_temp_path_rejects_non_tmp_arcwright(project_root: Path) -> None:
    """validate_temp_path raises SandboxViolation for .arcwright-ai/runs/ paths."""
    runs = project_root / ".arcwright-ai" / "runs"
    runs.mkdir(parents=True, exist_ok=True)
    target = runs / "file.txt"
    target.touch()
    with pytest.raises(SandboxViolation):
        validate_temp_path(target, project_root)


def test_validate_temp_path_rejects_project_root_file(project_root: Path) -> None:
    """validate_temp_path raises SandboxViolation for non-temp project files."""
    target = project_root / "src" / "file.py"
    target.touch()
    with pytest.raises(SandboxViolation):
        validate_temp_path(target, project_root)


def test_validate_temp_path_rejects_outside_project(project_root: Path) -> None:
    """validate_temp_path raises SandboxViolation for paths outside the project."""
    outside = Path("/tmp/file.txt")
    with pytest.raises(SandboxViolation):
        validate_temp_path(outside, project_root)


# ---------------------------------------------------------------------------
# Exception class hierarchy
# ---------------------------------------------------------------------------


def test_sandbox_violation_is_agent_error_subclass() -> None:
    """SandboxViolation must be a subclass of AgentError."""
    assert issubclass(SandboxViolation, AgentError)


def test_sandbox_violation_carries_details() -> None:
    """SandboxViolation exposes .message and .details attributes."""
    exc = SandboxViolation("bad path", details={"path": "/bad"})
    assert exc.message == "bad path"
    assert exc.details == {"path": "/bad"}


# ---------------------------------------------------------------------------
# PathValidator Protocol
# ---------------------------------------------------------------------------


def test_path_validator_protocol_satisfied() -> None:
    """validate_path satisfies the PathValidator runtime-checkable protocol."""
    assert isinstance(validate_path, PathValidator)
