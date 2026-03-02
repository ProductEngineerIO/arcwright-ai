"""Unit tests for arcwright_ai.agent.prompt — prompt builder."""

from __future__ import annotations

from arcwright_ai.agent.prompt import build_prompt
from arcwright_ai.core.types import ContextBundle

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_bundle(**kwargs: str) -> ContextBundle:
    """Construct a ContextBundle with defaults, overriding with *kwargs*."""
    defaults: dict[str, str] = {
        "story_content": "Story text.",
        "architecture_sections": "",
        "domain_requirements": "",
        "answerer_rules": "",
    }
    defaults.update(kwargs)
    return ContextBundle(**defaults)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_build_prompt_full_bundle() -> None:
    """All ContextBundle fields populated → prompt contains all four sections."""
    bundle = _make_bundle(
        story_content="Story goes here.",
        domain_requirements="FR1: The system shall...",
        architecture_sections="## Architecture overview",
        answerer_rules="Always use async.",
    )
    prompt = build_prompt(bundle)

    assert "## Story" in prompt
    assert "Story goes here." in prompt
    assert "## Requirements" in prompt
    assert "FR1: The system shall" in prompt
    assert "## Architecture" in prompt
    assert "Architecture overview" in prompt
    assert "## Project Conventions" in prompt
    assert "Always use async." in prompt


def test_build_prompt_empty_optional_sections() -> None:
    """Only story_content set → only Story section present, no empty sections."""
    bundle = _make_bundle(story_content="Just the story.")
    prompt = build_prompt(bundle)

    assert "## Story" in prompt
    assert "Just the story." in prompt
    assert "## Requirements" not in prompt
    assert "## Architecture" not in prompt
    assert "## Project Conventions" not in prompt


def test_build_prompt_includes_architecture() -> None:
    """architecture_sections populated → ## Architecture section appears."""
    bundle = _make_bundle(architecture_sections="Diagram of the system.")
    prompt = build_prompt(bundle)

    assert "## Architecture" in prompt
    assert "Diagram of the system." in prompt


def test_build_prompt_includes_requirements() -> None:
    """domain_requirements populated → ## Requirements section appears."""
    bundle = _make_bundle(domain_requirements="FR22: Rate limiting required.")
    prompt = build_prompt(bundle)

    assert "## Requirements" in prompt
    assert "FR22: Rate limiting required." in prompt


def test_build_prompt_returns_string() -> None:
    """Return type is str for any ContextBundle input."""
    bundle = _make_bundle()
    result = build_prompt(bundle)
    assert isinstance(result, str)


def test_build_prompt_sections_separated_by_blank_lines() -> None:
    """Sections are separated by double newlines."""
    bundle = _make_bundle(
        story_content="Story.",
        domain_requirements="Req.",
    )
    prompt = build_prompt(bundle)
    assert "\n\n" in prompt
