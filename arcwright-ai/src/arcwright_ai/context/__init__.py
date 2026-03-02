"""Context package — BMAD artifact reading, reference resolution, and rule lookup."""

from __future__ import annotations

from arcwright_ai.context.answerer import (
    IndexedSection,
    RuleIndex,
)
from arcwright_ai.context.injector import (
    build_context_bundle,
    parse_story,
    serialize_bundle_to_markdown,
)

__all__: list[str] = [
    "IndexedSection",
    "RuleIndex",
    "build_context_bundle",
    "parse_story",
    "serialize_bundle_to_markdown",
]
