"""Unit tests for arcwright_ai.agent.invoker — Claude Code SDK integration."""

from __future__ import annotations

import asyncio
import dataclasses
import logging
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import pytest
from claude_code_sdk._errors import ClaudeSDKError
from tests.fixtures.mock_sdk import MockSDKClient

from arcwright_ai.agent.invoker import InvocationResult, _patch_sdk_parser, invoke_agent
from arcwright_ai.agent.sandbox import validate_path
from arcwright_ai.core.exceptions import AgentError, SandboxViolation

if TYPE_CHECKING:
    from pathlib import Path

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
    root = tmp_path / "test-project"
    root.mkdir()
    (root / ".arcwright-ai" / "tmp").mkdir(parents=True)
    (root / "src").mkdir()
    return root


@pytest.fixture
def mock_sdk() -> MockSDKClient:
    """Return a default MockSDKClient with successful response parameters.

    Returns:
        Configured MockSDKClient instance.
    """
    return MockSDKClient(
        output_text="# Implementation\nDone.",
        tokens_input=500,
        tokens_output=200,
        total_cost_usd=0.05,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _invoke(
    mock: MockSDKClient,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    **kwargs: Any,
) -> InvocationResult:
    """Invoke invoke_agent with a monkeypatched SDK mock.

    Args:
        mock: The MockSDKClient to use as the SDK.
        project_root: Working directory and sandbox boundary.
        monkeypatch: pytest MonkeyPatch for SDK patching.
        **kwargs: Additional keyword args forwarded to invoke_agent.

    Returns:
        InvocationResult from the patched invocation.
    """
    import claude_code_sdk

    monkeypatch.setattr(claude_code_sdk, "query", mock.query)
    return await invoke_agent(
        prompt="Implement the story.",
        model="claude-test",
        cwd=project_root,
        sandbox=validate_path,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests: success path
# ---------------------------------------------------------------------------


async def test_invoke_agent_success_returns_result(
    mock_sdk: MockSDKClient,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock SDK returns text → InvocationResult with correct output, tokens, and cost."""
    result = await _invoke(mock_sdk, project_root, monkeypatch)

    assert result.output_text == "# Implementation\nDone."
    assert result.tokens_input == 500
    assert result.tokens_output == 200
    assert result.total_cost == Decimal("0.05")
    assert result.session_id == "mock-session-001"
    assert result.num_turns == 1
    assert result.is_error is False


def test_invocation_result_is_frozen_dataclass() -> None:
    """InvocationResult is a frozen dataclass that cannot be mutated."""
    assert dataclasses.is_dataclass(InvocationResult)
    result = InvocationResult(
        output_text="done",
        tokens_input=10,
        tokens_output=5,
        total_cost=Decimal("0.001"),
        duration_ms=100,
        session_id="s-1",
        num_turns=1,
        is_error=False,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.output_text = "modified"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Tests: error handling
# ---------------------------------------------------------------------------


async def test_invoke_agent_failure_raises_agent_error(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock SDK raises ProcessError → AgentError raised with details."""
    from claude_code_sdk._errors import ProcessError

    mock = MockSDKClient(error=ProcessError, error_message="Process crashed")
    with pytest.raises(AgentError, match="Process crashed"):
        await _invoke(mock, project_root, monkeypatch)


async def test_invoke_agent_malformed_response_raises_agent_error(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock SDK omits ResultMessage (malformed stream) → AgentError raised."""
    mock = MockSDKClient(omit_result_message=True)

    with pytest.raises(AgentError, match="SDK stream ended without ResultMessage"):
        await _invoke(mock, project_root, monkeypatch)


# ---------------------------------------------------------------------------
# Tests: rate limit backoff
# ---------------------------------------------------------------------------


async def test_invoke_agent_rate_limit_retries_with_backoff(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Mock raises rate limit on first call, succeeds on second → result returned
    and agent.rate_limit event is logged."""
    mock = MockSDKClient(
        output_text="Retry succeeded.",
        tokens_input=100,
        tokens_output=50,
        is_rate_limit=True,
    )

    async def instant_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    with caplog.at_level(logging.INFO, logger="arcwright_ai.agent.invoker"):
        result = await _invoke(mock, project_root, monkeypatch)

    assert result.output_text == "Retry succeeded."
    assert mock.call_count == 2  # first call failed, second succeeded
    assert any("agent.rate_limit" in record.message for record in caplog.records)


async def test_invoke_agent_rate_limit_exhausted_raises(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock always raises rate limit → AgentError after max retries exhausted."""
    import claude_code_sdk

    async def always_rate_limit(*, prompt: str, options: Any = None, **kwargs: Any) -> Any:
        raise ClaudeSDKError("rate limit always")
        yield  # makes this an async generator (unreachable statement)

    async def instant_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr(claude_code_sdk, "query", always_rate_limit)
    monkeypatch.setattr(asyncio, "sleep", instant_sleep)

    with pytest.raises(AgentError, match="max retries exhausted"):
        await invoke_agent(
            prompt="test",
            model="claude-test",
            cwd=project_root,
            sandbox=validate_path,
        )


# ---------------------------------------------------------------------------
# Tests: sandbox enforcement
# ---------------------------------------------------------------------------


async def test_invoke_agent_sandbox_violation(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock yields ToolUseBlock with path outside project → SandboxViolation raised."""
    mock = MockSDKClient(
        output_text="Writing to /etc/passwd.",
        tool_use_calls=[
            {"id": "t1", "name": "Write", "input": {"file_path": "/etc/passwd"}},
        ],
    )
    with pytest.raises(SandboxViolation):
        await _invoke(mock, project_root, monkeypatch)


async def test_invoke_agent_tool_use_within_project(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock yields ToolUseBlock with valid path inside project → no error, completes."""
    mock = MockSDKClient(
        output_text="File written.",
        tool_use_calls=[
            {"id": "t1", "name": "Write", "input": {"file_path": "src/main.py"}},
        ],
    )
    result = await _invoke(mock, project_root, monkeypatch)
    assert result.output_text == "File written."
    assert result.is_error is False


# ---------------------------------------------------------------------------
# Tests: token usage and cost
# ---------------------------------------------------------------------------


async def test_invoke_agent_captures_token_usage(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """InvocationResult.tokens_input and tokens_output match the SDK response."""
    mock = MockSDKClient(tokens_input=1200, tokens_output=800, total_cost_usd=0.123)
    result = await _invoke(mock, project_root, monkeypatch)

    assert result.tokens_input == 1200
    assert result.tokens_output == 800
    assert result.total_cost == Decimal("0.123")


# ---------------------------------------------------------------------------
# Tests: statefulness
# ---------------------------------------------------------------------------


async def test_invoke_agent_stateless(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two sequential invocations yield independent results (no shared state)."""
    import claude_code_sdk

    mock_a = MockSDKClient(output_text="Result A", tokens_input=100, tokens_output=50)
    mock_b = MockSDKClient(output_text="Result B", tokens_input=200, tokens_output=80)

    monkeypatch.setattr(claude_code_sdk, "query", mock_a.query)
    result_a = await invoke_agent(
        prompt="First invocation.",
        model="claude-test",
        cwd=project_root,
        sandbox=validate_path,
    )

    monkeypatch.setattr(claude_code_sdk, "query", mock_b.query)
    result_b = await invoke_agent(
        prompt="Second invocation.",
        model="claude-test",
        cwd=project_root,
        sandbox=validate_path,
    )

    assert result_a.output_text == "Result A"
    assert result_b.output_text == "Result B"
    assert result_a.tokens_input != result_b.tokens_input


# ---------------------------------------------------------------------------
# Tests: SDK parser monkeypatch (rate_limit_event handling)
# ---------------------------------------------------------------------------


def test_patch_sdk_parser_wraps_parse_message(monkeypatch: pytest.MonkeyPatch) -> None:
    """_patch_sdk_parser replaces parse_message in the client module with a safe wrapper."""
    import claude_code_sdk._internal.client as _client_mod
    import claude_code_sdk._internal.message_parser as _parser_mod

    import arcwright_ai.agent.invoker as _invoker_mod

    # Reset global flag so patch runs fresh
    monkeypatch.setattr(_invoker_mod, "_SDK_PARSER_PATCHED", False)
    original_fn = _parser_mod.parse_message

    _patch_sdk_parser()

    # The client module's parse_message should now be the wrapper, not the original
    assert _client_mod.parse_message is not original_fn
    # Calling the wrapper with valid data should still work
    from claude_code_sdk.types import SystemMessage

    result = _client_mod.parse_message({"type": "system", "subtype": "init", "data": {}})
    assert isinstance(result, SystemMessage)

    # Calling with an unknown type should return None instead of raising
    result = _client_mod.parse_message({"type": "rate_limit_event", "data": {}})
    assert result is None

    # Restore original to avoid polluting other tests
    _client_mod.parse_message = original_fn
    monkeypatch.setattr(_invoker_mod, "_SDK_PARSER_PATCHED", False)


async def test_invoke_agent_skips_none_messages_from_patched_parser(
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When SDK yields None messages (from patched parser), they are silently skipped."""
    import claude_code_sdk
    from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock

    messages = [
        None,  # rate_limit_event (patched → None)
        AssistantMessage(
            content=[TextBlock(text="Hello")],
            model="mock-model",
            parent_tool_use_id=None,
        ),
        None,  # another unknown type
        ResultMessage(
            subtype="success",
            duration_ms=50,
            duration_api_ms=40,
            is_error=False,
            num_turns=1,
            session_id="null-test-session",
            total_cost_usd=0.01,
            usage={"input_tokens": 10, "output_tokens": 5},
            result="Hello",
        ),
    ]

    async def mock_query(*, prompt: Any, options: Any = None, **kwargs: Any) -> Any:
        for msg in messages:
            yield msg

    monkeypatch.setattr(claude_code_sdk, "query", mock_query)

    result = await invoke_agent(
        prompt="test",
        model="claude-test",
        cwd=project_root,
        sandbox=validate_path,
    )

    assert result.output_text == "Hello"
    assert result.session_id == "null-test-session"
