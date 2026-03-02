"""Context package — BMAD artifact reading, reference resolution, and rule lookup."""

from __future__ import annotations

from arcwright_ai.context.injector import (
    build_context_bundle,
    parse_story,
    serialize_bundle_to_markdown,
)

# lookup_answer  (context/answerer.py  — Story 2.3)
__all__: list[str] = [
    "build_context_bundle",
    "parse_story",
    "serialize_bundle_to_markdown",
]
