"""Agent invoker — Claude Code SDK integration for dispatching agent work."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from arcwright_ai.core.constants import DIR_ARCWRIGHT, DIR_TMP
from arcwright_ai.core.exceptions import AgentError, AgentTimeoutError, SandboxViolation

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator, Awaitable, Callable
    from pathlib import Path

    from claude_code_sdk.types import PermissionResultAllow, PermissionResultDeny

    from arcwright_ai.agent.sandbox import PathValidator

__all__: list[str] = ["InvocationResult", "invoke_agent"]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

_BACKOFF_BASE: float = 2.0
_BACKOFF_CAP: float = 120.0
_BACKOFF_MAX_RETRIES: int = 7
_RATE_LIMIT_RE: re.Pattern[str] = re.compile(r"rate.?limit|429|too many requests", re.IGNORECASE)
_FILE_WRITE_TOOLS: frozenset[str] = frozenset({"CreateFile", "Edit", "MultiEdit", "Write"})

# Flag prevents double-patching across multiple invoke_agent calls.
_SDK_PARSER_PATCHED: bool = False


class _SkippedMessage:
    """Sentinel returned by the patched SDK parser for unrecognised message types.

    Carrying the original ``type`` field lets the streaming loop detect whether
    a ``rate_limit_event`` was silently dropped just before the claude CLI
    exited with code 1, so we can treat that as a retryable condition.
    """

    __slots__ = ("msg_type",)

    def __init__(self, msg_type: str) -> None:
        self.msg_type = msg_type


# Flag prevents registering the asyncio exception handler more than once.
_BG_HANDLER_INSTALLED: bool = False


def _claude_meta_dir() -> Path:
    """Return the resolved ``~/.claude`` directory path (lazy, no import-time side-effects)."""
    from pathlib import Path as _Path

    return (_Path.home() / ".claude").resolve()


def _suppress_bg_cancel_scope_errors() -> None:
    """Install a one-shot asyncio exception handler to silence Python 3.14 / anyio
    ``RuntimeError: Attempted to exit cancel scope in a different task`` noise.

    Python 3.14 tightened ``asyncio`` so that ``anyio`` cancel scopes cannot be
    exited from a different task than they were entered in.  The
    ``claude_code_sdk`` internal async generator cleanup path hits this edge
    case when the iterator is abandoned (e.g. after a denied tool-use).  The
    resulting ``RuntimeError`` is surfaced only as a background
    "Task exception was never retrieved" warning and has no effect on
    correctness, so we suppress it here.
    """
    global _BG_HANDLER_INSTALLED
    if _BG_HANDLER_INSTALLED:
        return

    import asyncio

    loop = asyncio.get_running_loop()
    original_handler = loop.get_exception_handler()

    def _handler(lp: asyncio.AbstractEventLoop, context: dict) -> None:  # type: ignore[type-arg]
        exc = context.get("exception")
        if isinstance(exc, RuntimeError) and "cancel scope" in str(exc).lower():
            logger.debug(
                "agent.bg_cancel_scope_suppressed",
                extra={"data": {"error": str(exc)}},
            )
            return
        if original_handler is not None:
            original_handler(lp, context)
        else:
            lp.default_exception_handler(context)

    loop.set_exception_handler(_handler)
    _BG_HANDLER_INSTALLED = True


def _patch_sdk_parser() -> None:
    """Monkeypatch the SDK message parser to skip unknown message types.

    Claude Code SDK v0.0.25 raises ``MessageParseError`` for unrecognised
    streaming message types (e.g. ``rate_limit_event``).  This patch wraps
    ``parse_message`` so it returns ``None`` for unknown types instead of
    raising, allowing the async generator in ``client.py`` to ``yield None``
    which the invoker then filters out.
    """
    global _SDK_PARSER_PATCHED
    if _SDK_PARSER_PATCHED:
        return

    import claude_code_sdk._internal.client as _client_mod
    import claude_code_sdk._internal.message_parser as _parser_mod

    _original = _parser_mod.parse_message

    def _safe_parse_message(data: Any) -> Any:
        try:
            return _original(data)
        except Exception:
            msg_type = data.get("type", "<unknown>") if isinstance(data, dict) else "<invalid>"
            logger.debug("Skipping unrecognised SDK message type: %s", msg_type)
            return _SkippedMessage(msg_type)

    # Patch the name *in the client module* (where it was imported).
    _client_mod.parse_message = _safe_parse_message  # type: ignore[attr-defined]
    _SDK_PARSER_PATCHED = True


# ---------------------------------------------------------------------------
# InvocationResult dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InvocationResult:
    """Result of a single Claude Code SDK invocation.

    Captures the agent's output text, token consumption, cost, and
    session metadata for budget tracking and provenance.

    Attributes:
        output_text: The agent's full text output (concatenated TextBlocks).
        tokens_input: Input tokens consumed (from SDK usage report).
        tokens_output: Output tokens consumed (from SDK usage report).
        total_cost: Estimated cost in USD (Decimal for exact arithmetic).
        duration_ms: Wall-clock duration of the invocation in milliseconds.
        session_id: SDK session identifier for debugging.
        num_turns: Number of conversational turns in the session.
        is_error: Whether the SDK reported an error condition.
    """

    output_text: str
    tokens_input: int
    tokens_output: int
    total_cost: Decimal
    duration_ms: int
    session_id: str
    num_turns: int
    is_error: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _wrap_sdk_error(error: Exception) -> AgentError:
    """Wrap an SDK or generic exception into the appropriate AgentError subclass.

    Args:
        error: The original exception to wrap.

    Returns:
        An ``AgentError`` (or appropriate subclass) preserving the original
        message in ``details``.
    """
    from claude_code_sdk._errors import ClaudeSDKError

    message = str(error)
    details: dict[str, Any] = {"original_error": message}
    if isinstance(error, ClaudeSDKError):
        if re.search(r"timeout", message, re.IGNORECASE):
            return AgentTimeoutError(f"Agent session timed out: {message}", details=details)
        return AgentError(f"SDK error: {message}", details=details)
    return AgentError(f"Unexpected error during agent invocation: {message}", details=details)


def _validate_tool_use(block: Any, sandbox: PathValidator, cwd: Path) -> None:
    """Validate a ToolUseBlock file path through the sandbox (defense-in-depth).

    Called for every ToolUseBlock in the SDK stream after the primary
    ``can_use_tool`` callback. Raises ``SandboxViolation`` to abort the
    invocation if a file-writing tool targets a path outside the boundary.

    Args:
        block: A ``ToolUseBlock`` from the SDK message stream.
        sandbox: The injected path validator function.
        cwd: The working directory (sandbox boundary).

    Raises:
        SandboxViolation: If the tool targets a path outside the sandbox boundary.
    """
    from pathlib import Path as _Path

    if block.name in _FILE_WRITE_TOOLS:
        file_path_str: str | None = block.input.get("file_path") or block.input.get("path")
        if file_path_str:
            file_path = _Path(file_path_str)
            temp_dir = (cwd / DIR_ARCWRIGHT / DIR_TMP).resolve()
            candidate_path = file_path if file_path.is_absolute() else cwd.resolve() / file_path

            # Silently deny writes to ~/.claude/ (Claude's session-resume
            # scratchpad).  Arcwright never uses CLI resume, so the checkpoint
            # is worthless and we don't want files accumulating in $HOME.
            # Returning without raising lets the session continue normally.
            if candidate_path.resolve().is_relative_to(_claude_meta_dir()):
                logger.debug(
                    "agent.sandbox.deny_claude_meta",
                    extra={"data": {"tool": block.name, "path": str(file_path)}},
                )
                return

            if candidate_path.resolve().is_relative_to(temp_dir):
                temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                sandbox(file_path, cwd, block.name)
            except SandboxViolation:
                logger.info(
                    "agent.sandbox.deny",
                    extra={
                        "data": {
                            "tool": block.name,
                            "path": str(file_path),
                            "cwd": str(cwd),
                        }
                    },
                )
                raise

            if file_path.is_absolute() and file_path.resolve().is_relative_to(temp_dir):
                return

            normalized_parts = os.path.normpath(file_path_str).split(os.sep)
            if (
                normalized_parts[:3] == [".", DIR_ARCWRIGHT, DIR_TMP]
                or normalized_parts[:2] == [DIR_ARCWRIGHT, DIR_TMP]
            ) and not candidate_path.resolve().is_relative_to(temp_dir):
                raise SandboxViolation(
                    f"Temp files must target {temp_dir}, got: {candidate_path.resolve()}",
                    details={
                        "path": file_path_str,
                        "resolved": str(candidate_path.resolve()),
                        "expected_tmp": str(temp_dir),
                    },
                )


def _make_tool_validator(
    sandbox: PathValidator,
    cwd: Path,
) -> Callable[[str, dict[str, Any], Any], Awaitable[PermissionResultAllow | PermissionResultDeny]]:
    """Create a ``can_use_tool`` callback that enforces sandbox rules at the SDK level.

    Returns an async callback compatible with ``ClaudeCodeOptions.can_use_tool``
    that passes file-writing tool calls through the injected ``PathValidator``,
    returning ``PermissionResultDeny`` for sandbox violations.

    Args:
        sandbox: The injected path validator.
        cwd: The working directory (sandbox boundary).

    Returns:
        An async callback that returns ``PermissionResultAllow`` for safe paths
        and ``PermissionResultDeny`` for sandbox violations.
    """
    from pathlib import Path as _Path

    from claude_code_sdk.types import PermissionResultAllow, PermissionResultDeny

    async def can_use_tool(
        tool_name: str,
        tool_input: dict[str, Any],
        context: Any,
    ) -> PermissionResultAllow | PermissionResultDeny:
        if tool_name in _FILE_WRITE_TOOLS:
            file_path_str: str | None = tool_input.get("file_path") or tool_input.get("path")
            if file_path_str:
                file_path = _Path(file_path_str)
                temp_dir = (cwd / DIR_ARCWRIGHT / DIR_TMP).resolve()
                candidate_path = file_path if file_path.is_absolute() else cwd.resolve() / file_path

                # Silently deny writes to ~/.claude/ (Claude's session-resume
                # scratchpad).  Arcwright never uses CLI resume, so the plan
                # checkpoint is worthless and we don't want files accumulating
                # outside the project.  Deny is silent — the session continues.
                if candidate_path.resolve().is_relative_to(_claude_meta_dir()):
                    logger.debug(
                        "agent.sandbox.deny_claude_meta",
                        extra={"data": {"tool": tool_name, "path": file_path_str}},
                    )
                    return PermissionResultDeny(
                        message="~/.claude/ writes are not permitted; Arcwright does not use Claude session-resume."
                    )

                if candidate_path.resolve().is_relative_to(temp_dir):
                    temp_dir.mkdir(parents=True, exist_ok=True)

                try:
                    sandbox(file_path, cwd, tool_name)
                except SandboxViolation as exc:
                    logger.info(
                        "agent.sandbox.deny",
                        extra={
                            "data": {
                                "tool": tool_name,
                                "path": file_path_str,
                                "cwd": str(cwd),
                                "reason": str(exc),
                            }
                        },
                    )
                    return PermissionResultDeny(message=str(exc))

                if file_path.is_absolute() and file_path.resolve().is_relative_to(temp_dir):
                    return PermissionResultAllow()

                normalized_parts = os.path.normpath(file_path_str).split(os.sep)
                if (
                    normalized_parts[:3] == [".", DIR_ARCWRIGHT, DIR_TMP]
                    or normalized_parts[:2] == [DIR_ARCWRIGHT, DIR_TMP]
                ) and not candidate_path.resolve().is_relative_to(temp_dir):
                    return PermissionResultDeny(
                        message=f"Temp files must target {temp_dir}, got: {candidate_path.resolve()}"
                    )
        return PermissionResultAllow()

    return can_use_tool


async def _invoke_with_backoff(
    prompt: str,
    options: Any,
) -> AsyncGenerator[Any, None]:
    """Invoke the SDK with exponential backoff on rate limit errors.

    Calls ``claude_code_sdk.query()`` and re-yields all messages. On rate
    limit errors (detected via regex on the error message) it sleeps with
    exponential backoff and jitter before retrying, up to
    ``_BACKOFF_MAX_RETRIES`` attempts.

    When ``can_use_tool`` is set on options, the SDK requires the prompt
    to be an ``AsyncIterable`` (streaming mode).  We wrap the plain string
    into a single-message async iterable to satisfy this contract.

    Args:
        prompt: The prompt string to pass to the SDK.
        options: A ``ClaudeCodeOptions`` instance.

    Yields:
        Typed SDK message objects as yielded by ``claude_code_sdk.query()``.

    Raises:
        AgentError: On non-rate-limit SDK errors or when max retries is exhausted.
    """
    from claude_code_sdk import query as sdk_query
    from claude_code_sdk._errors import ClaudeSDKError, MessageParseError

    # Ensure the SDK parser tolerates unknown message types (e.g.
    # rate_limit_event in v0.0.25) before we start streaming.
    _patch_sdk_parser()

    # SDK requires AsyncIterable prompt when can_use_tool is configured
    needs_streaming = getattr(options, "can_use_tool", None) is not None

    for attempt in range(_BACKOFF_MAX_RETRIES):
        saw_rate_limit_event: bool = False
        try:

            async def _prompt_stream() -> AsyncGenerator[dict[str, Any], None]:
                yield {
                    "type": "user",
                    "message": {"role": "user", "content": prompt},
                }

            sdk_prompt: str | AsyncGenerator[dict[str, Any], None] = _prompt_stream() if needs_streaming else prompt
            async for message in sdk_query(prompt=sdk_prompt, options=options):
                if isinstance(message, _SkippedMessage):
                    # Patched parse_message returned a sentinel for an unknown
                    # message type. Track rate_limit_event specifically so we
                    # can retry if the process then exits with code 1.
                    if message.msg_type == "rate_limit_event":
                        saw_rate_limit_event = True
                    continue
                yield message
            return
        except MessageParseError as exc:
            # SDK v0.0.25 doesn't handle some streaming message types
            # (e.g. rate_limit_event).  These are informational — log and
            # retry so the agent can continue on the next attempt.
            error_detail = str(exc)
            logger.info(
                "agent.sdk_parse_error",
                extra={
                    "data": {
                        "attempt": attempt + 1,
                        "error": error_detail,
                    }
                },
            )
            wait = min(
                _BACKOFF_BASE * (2**attempt) + random.uniform(0, 0.5),
                _BACKOFF_CAP,
            )
            await asyncio.sleep(wait)
        except ClaudeSDKError as exc:
            sdk_error_detail: str = str(exc)
            stderr: str | None = getattr(exc, "stderr", None)
            exit_code: int | None = getattr(exc, "exit_code", None)
            if stderr:
                sdk_error_detail = f"{sdk_error_detail} | stderr={stderr}"
            is_rate_limit = _RATE_LIMIT_RE.search(sdk_error_detail) or (saw_rate_limit_event and exit_code == 1)
            if is_rate_limit:
                wait = min(
                    _BACKOFF_BASE * (2**attempt) + random.uniform(0, 0.5),
                    _BACKOFF_CAP,
                )
                logger.info(
                    "agent.rate_limit",
                    extra={
                        "data": {
                            "attempt": attempt + 1,
                            "wait_seconds": round(wait, 2),
                            "error": sdk_error_detail,
                            "exit_code": exit_code,
                            "triggered_by": "rate_limit_event" if saw_rate_limit_event else "error_pattern",
                        }
                    },
                )
                await asyncio.sleep(wait)
            else:
                raise _wrap_sdk_error(exc) from exc

    raise AgentError(
        "Rate limit: max retries exhausted",
        details={"attempts": _BACKOFF_MAX_RETRIES},
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


async def invoke_agent(
    prompt: str,
    *,
    model: str,
    cwd: Path,
    sandbox: PathValidator,
    max_turns: int | None = None,
) -> InvocationResult:
    """Invoke Claude Code SDK to execute a story implementation.

    Calls the SDK's ``query()`` async iterator, processes streaming messages,
    validates file operations through the injected sandbox, and captures
    token usage for budget tracking. Each invocation is stateless — no
    persistent agent state is shared between calls.

    Args:
        prompt: The assembled prompt string from ``build_prompt()``.
        model: Claude model version identifier
            (e.g., ``"claude-sonnet-4-20250514"``).
        cwd: Working directory for agent file operations (typically the
            worktree path). Also serves as the sandbox boundary.
        sandbox: Path validator function (``PathValidator`` protocol) for
            sandbox enforcement via dependency injection.
        max_turns: Optional maximum number of conversational turns.

    Returns:
        ``InvocationResult`` containing agent output, token usage, cost,
        and session metadata.

    Raises:
        AgentError: On SDK invocation failure (network, process crash,
            malformed response), or when rate limit max retries is exhausted.
        AgentTimeoutError: On SDK timeout.
        SandboxViolation: If the agent attempts a file operation outside
            the sandbox boundary.
    """
    from claude_code_sdk import ClaudeCodeOptions, query  # noqa: F401
    from claude_code_sdk.types import AssistantMessage, ResultMessage, TextBlock, ToolUseBlock

    # Suppress Python 3.14 / anyio cancel-scope RuntimeErrors emitted as
    # unhandled background-task warnings during async generator cleanup.
    _suppress_bg_cancel_scope_errors()

    options = ClaudeCodeOptions(
        model=model,
        cwd=str(cwd),
        permission_mode="bypassPermissions",
        max_turns=max_turns,
        can_use_tool=_make_tool_validator(sandbox, cwd),
    )

    output_parts: list[str] = []
    result_message: ResultMessage | None = None

    stream = _invoke_with_backoff(prompt, options)
    try:
        async for message in stream:
            if isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        output_parts.append(block.text)
                    elif isinstance(block, ToolUseBlock):
                        _validate_tool_use(block, sandbox, cwd)
            elif isinstance(message, ResultMessage):
                result_message = message
    except AgentError:
        raise
    except Exception as exc:
        raise _wrap_sdk_error(exc) from exc
    finally:
        await stream.aclose()

    if result_message is None:
        raise AgentError(
            "SDK stream ended without ResultMessage",
            details={"prompt_length": len(prompt)},
        )

    usage: dict[str, Any] = result_message.usage or {}
    tokens_input: int = int(usage.get("input_tokens", 0))
    tokens_output: int = int(usage.get("output_tokens", 0))
    cost_float: float = result_message.total_cost_usd or 0.0

    logger.info(
        "agent.response",
        extra={
            "data": {
                "tokens_input": tokens_input,
                "tokens_output": tokens_output,
                "cost_usd": str(round(cost_float, 6)),
                "session_id": result_message.session_id,
            }
        },
    )

    return InvocationResult(
        output_text="".join(output_parts),
        tokens_input=tokens_input,
        tokens_output=tokens_output,
        total_cost=Decimal(str(cost_float)),
        duration_ms=result_message.duration_ms,
        session_id=result_message.session_id,
        num_turns=result_message.num_turns,
        is_error=result_message.is_error,
    )
