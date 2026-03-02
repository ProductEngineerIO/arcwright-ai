"""Tests for core/exceptions.py — Full exception hierarchy."""

from __future__ import annotations

from arcwright_ai.core.exceptions import (
    AgentBudgetError,
    AgentError,
    AgentTimeoutError,
    ArcwrightError,
    BranchError,
    ConfigError,
    ContextError,
    ProjectError,
    RunError,
    ScmError,
    ValidationError,
    WorktreeError,
)

# ---------------------------------------------------------------------------
# ArcwrightError base
# ---------------------------------------------------------------------------


def test_arcwright_error_message_attribute() -> None:
    exc = ArcwrightError("something failed")
    assert exc.message == "something failed"


def test_arcwright_error_details_defaults_to_none() -> None:
    exc = ArcwrightError("msg")
    assert exc.details is None


def test_arcwright_error_details_can_be_set() -> None:
    exc = ArcwrightError("msg", details={"key": "value"})
    assert exc.details == {"key": "value"}


def test_arcwright_error_str_representation() -> None:
    exc = ArcwrightError("msg")
    assert str(exc) == "msg"


def test_arcwright_error_is_exception() -> None:
    exc = ArcwrightError("msg")
    assert isinstance(exc, Exception)


# ---------------------------------------------------------------------------
# Direct subclasses
# ---------------------------------------------------------------------------


def test_config_error_is_arcwright_error() -> None:
    exc = ConfigError("bad config")
    assert isinstance(exc, ArcwrightError)
    assert exc.message == "bad config"


def test_project_error_is_arcwright_error() -> None:
    exc = ProjectError("not initialised")
    assert isinstance(exc, ArcwrightError)


def test_context_error_is_arcwright_error() -> None:
    exc = ContextError("cannot read artifact")
    assert isinstance(exc, ArcwrightError)


def test_validation_error_is_arcwright_error() -> None:
    exc = ValidationError("invariant failed")
    assert isinstance(exc, ArcwrightError)


def test_run_error_is_arcwright_error() -> None:
    exc = RunError("state corrupted")
    assert isinstance(exc, ArcwrightError)


# ---------------------------------------------------------------------------
# AgentError hierarchy
# ---------------------------------------------------------------------------


def test_agent_error_is_arcwright_error() -> None:
    exc = AgentError("sdk failed")
    assert isinstance(exc, ArcwrightError)


def test_agent_timeout_error_is_agent_error() -> None:
    exc = AgentTimeoutError("timed out")
    assert isinstance(exc, AgentError)
    assert isinstance(exc, ArcwrightError)


def test_agent_budget_error_is_agent_error() -> None:
    exc = AgentBudgetError("budget exceeded")
    assert isinstance(exc, AgentError)
    assert isinstance(exc, ArcwrightError)


# ---------------------------------------------------------------------------
# ScmError hierarchy
# ---------------------------------------------------------------------------


def test_scm_error_is_arcwright_error() -> None:
    exc = ScmError("git failed")
    assert isinstance(exc, ArcwrightError)


def test_worktree_error_is_scm_error() -> None:
    exc = WorktreeError("worktree add failed")
    assert isinstance(exc, ScmError)
    assert isinstance(exc, ArcwrightError)


def test_branch_error_is_scm_error() -> None:
    exc = BranchError("branch exists")
    assert isinstance(exc, ScmError)
    assert isinstance(exc, ArcwrightError)


# ---------------------------------------------------------------------------
# Details attribute on subclasses
# ---------------------------------------------------------------------------


def test_config_error_with_details() -> None:
    exc = ConfigError("bad config", details={"path": "/etc/pyproject.toml"})
    assert exc.details == {"path": "/etc/pyproject.toml"}


def test_worktree_error_with_details() -> None:
    exc = WorktreeError("failed", details={"branch": "arcwright/story-1-2"})
    assert exc.details == {"branch": "arcwright/story-1-2"}


# ---------------------------------------------------------------------------
# Exception can be raised and caught
# ---------------------------------------------------------------------------


def test_config_error_can_be_raised_and_caught() -> None:
    import pytest

    with pytest.raises(ConfigError, match="bad"):
        raise ConfigError("bad config")


def test_agent_timeout_caught_as_agent_error() -> None:
    import pytest

    with pytest.raises(AgentError):
        raise AgentTimeoutError("timeout")


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


def test_all_symbols_exported() -> None:
    import arcwright_ai.core.exceptions as mod

    expected = {
        "AgentBudgetError",
        "AgentError",
        "AgentTimeoutError",
        "ArcwrightError",
        "BranchError",
        "ConfigError",
        "ContextError",
        "ProjectError",
        "RunError",
        "SandboxViolation",
        "ScmError",
        "ValidationError",
        "WorktreeError",
    }
    assert set(mod.__all__) == expected
