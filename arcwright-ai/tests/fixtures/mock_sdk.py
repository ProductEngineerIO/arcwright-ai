"""Mock SDK fixtures for testing agent invocation without real Claude Code SDK calls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from claude_code_sdk._errors import ClaudeSDKError
from claude_code_sdk.types import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class MockSDKClient:
    """Predictable async mock of the Claude Code SDK client.

    Mirrors the real SDK's async generator interface with configurable
    response scenarios for unit and integration testing. Returns typed
    SDK message objects (not raw dicts) matching the real API.

    Example::

        client = MockSDKClient(output_text="Done.", tokens_input=500)
        async for message in client.query(prompt="implement story"):
            ...
    """

    def __init__(
        self,
        output_text: str = "Done.",
        tokens_input: int = 100,
        tokens_output: int = 50,
        total_cost_usd: float = 0.01,
        error: type[Exception] | None = None,
        error_message: str = "Simulated error",
        tool_use_calls: list[dict[str, Any]] | None = None,
        is_rate_limit: bool = False,
        error_phase: str = "before",
        omit_result_message: bool = False,
    ) -> None:
        """Initialise the mock client with configurable response parameters.

        Args:
            output_text: Text content for the AssistantMessage TextBlock.
            tokens_input: Input token count in the ResultMessage usage.
            tokens_output: Output token count in the ResultMessage usage.
            total_cost_usd: Simulated cost in USD for the ResultMessage.
            error: Optional exception type to raise during invocation.
            error_message: Message for the raised error if ``error`` is set.
            tool_use_calls: Optional list of ToolUseBlock input dicts, each
                with ``id``, ``name``, and ``input`` keys.
            is_rate_limit: If True, raises a rate-limit ``ClaudeSDKError`` on the
                first call and succeeds on subsequent calls (tests backoff).
            error_phase: When ``error`` is set, controls raise point:
                ``"before"`` (before streaming) or ``"during"`` (mid-stream).
            omit_result_message: If True, do not yield ``ResultMessage`` to
                simulate malformed/incomplete SDK output.
        """
        self.output_text = output_text
        self.tokens_input = tokens_input
        self.tokens_output = tokens_output
        self.total_cost_usd = total_cost_usd
        self.error = error
        self.error_message = error_message
        self.tool_use_calls = tool_use_calls or []
        self.is_rate_limit = is_rate_limit
        self.error_phase = error_phase
        self.omit_result_message = omit_result_message
        self.call_count = 0

    async def query(
        self,
        *,
        prompt: str,
        options: Any = None,
        transport: Any = None,
    ) -> AsyncGenerator[Any, None]:
        """Simulate an SDK invocation, yielding typed message objects.

        Yields messages in the real SDK's sequence:
        optional ``ToolUseBlock``s (inside ``AssistantMessage``) →
        ``AssistantMessage`` with ``TextBlock`` content →
        ``ResultMessage`` with usage and cost data.

        Args:
            prompt: The prompt string (unused by the mock, accepted for
                interface compatibility).
            options: SDK options (unused by the mock, accepted for
                interface compatibility).
            transport: Transport layer (unused by the mock, accepted for
                interface compatibility).

        Yields:
            Typed SDK message objects matching the real ``query()`` sequence.

        Raises:
            ClaudeSDKError: If ``is_rate_limit`` is True on the first call.
            Exception: The configured ``error`` type if set.
        """
        self.call_count += 1

        if self.is_rate_limit and self.call_count == 1:
            raise ClaudeSDKError("rate limit exceeded (simulated 429)")

        if self.error is not None and self.error_phase == "before":
            raise self.error(self.error_message)

        # Build AssistantMessage content blocks
        content: list[Any] = []
        for tool_call in self.tool_use_calls:
            content.append(
                ToolUseBlock(
                    id=tool_call.get("id", "tool-001"),
                    name=tool_call["name"],
                    input=tool_call.get("input", {}),
                )
            )
        content.append(TextBlock(text=self.output_text))

        yield AssistantMessage(
            content=content,
            model="mock-model",
            parent_tool_use_id=None,
        )

        if self.error is not None and self.error_phase == "during":
            raise self.error(self.error_message)

        if self.omit_result_message:
            return

        yield ResultMessage(
            subtype="success",
            duration_ms=100,
            duration_api_ms=80,
            is_error=False,
            num_turns=1,
            session_id="mock-session-001",
            total_cost_usd=self.total_cost_usd,
            usage={"input_tokens": self.tokens_input, "output_tokens": self.tokens_output},
            result=self.output_text,
        )


# ---------------------------------------------------------------------------
# Backward-compatible alias
# ---------------------------------------------------------------------------

MockClaudeCodeSDK = MockSDKClient
