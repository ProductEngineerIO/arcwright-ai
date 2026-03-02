"""Agent prompt — Prompt construction and context assembly for agent invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from arcwright_ai.core.types import ContextBundle

__all__: list[str] = ["build_prompt"]


def build_prompt(bundle: ContextBundle) -> str:
    """Assemble an SDK prompt string from a ContextBundle.

    Formats the bundle's story content, resolved requirements, architecture
    excerpts, and project conventions into a structured prompt with clearly
    delineated markdown sections. Sections are only included when the
    corresponding bundle field is non-empty.

    Args:
        bundle: The assembled context payload from the preflight node.

    Returns:
        A formatted prompt string ready for ``claude_code_sdk.query()``.
    """
    parts: list[str] = [f"## Story\n\n{bundle.story_content}"]

    if bundle.domain_requirements:
        parts.append(f"## Requirements\n\n{bundle.domain_requirements}")

    if bundle.architecture_sections:
        parts.append(f"## Architecture\n\n{bundle.architecture_sections}")

    if bundle.answerer_rules:
        parts.append(f"## Project Conventions\n\n{bundle.answerer_rules}")

    return "\n\n".join(parts)
