"""Mock SDK fixtures for testing agent invocation without real Claude Code SDK calls."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


class MockClaudeCodeSDK:
    """Predictable async mock of the Claude Code SDK client.

    Mirrors the real SDK's async generator interface with configurable
    response scenarios for unit and integration testing.

    Scenarios:
        success:    Yields a single assistant message and exits cleanly.
        failure:    Yields partial output then raises RuntimeError.
        rate_limit: Raises RuntimeError immediately (simulates 429).
        malformed:  Yields a message with missing/invalid structure.

    Example::

        sdk = MockClaudeCodeSDK(scenario="success", content="Done.")
        async for message in sdk.run(prompt="implement story"):
            assert message["type"] == "assistant"
    """

    def __init__(self, scenario: str = "success", content: str = "Done.") -> None:
        self.scenario = scenario
        self.content = content
        self.call_count = 0

    async def run(self, prompt: str, **kwargs: Any) -> AsyncGenerator[dict[str, Any], None]:
        """Simulate an SDK invocation, yielding messages per the configured scenario."""
        self.call_count += 1
        if self.scenario == "success":
            yield {"type": "assistant", "content": self.content}
        elif self.scenario == "failure":
            yield {"type": "assistant", "content": "partial output"}
            raise RuntimeError("Simulated SDK agent failure")
        elif self.scenario == "rate_limit":
            raise RuntimeError("Rate limit exceeded (simulated 429)")
        elif self.scenario == "malformed":
            yield {"unexpected_key": "no type field"}
        else:
            raise ValueError(f"Unknown MockClaudeCodeSDK scenario: {self.scenario!r}")
