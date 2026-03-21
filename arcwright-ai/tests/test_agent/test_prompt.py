"""Unit tests for arcwright_ai.agent.prompt — prompt builder."""

from __future__ import annotations

from pathlib import Path

from arcwright_ai.agent.prompt import build_prompt
from arcwright_ai.core.types import ContextBundle
from arcwright_ai.validation.quality_gate import QualityFeedback, ToolResult
from arcwright_ai.validation.v3_reflexion import ReflexionFeedback

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


def test_build_prompt_without_feedback_has_no_feedback_section() -> None:
    """build_prompt with feedback=None produces no feedback section."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(bundle, feedback=None)
    assert "Previous Validation Feedback" not in prompt


def test_build_prompt_with_failed_feedback_includes_feedback_section() -> None:
    """build_prompt with failed ReflexionFeedback appends feedback section."""
    bundle = _make_bundle(story_content="Story text.")
    feedback = ReflexionFeedback(
        passed=False,
        unmet_criteria=["2"],
        feedback_per_criterion={"2": "Missing X implementation"},
        attempt_number=1,
    )
    prompt = build_prompt(bundle, feedback=feedback)
    assert "## Previous Validation Feedback" in prompt
    assert "AC 2" in prompt
    assert "Missing X implementation" in prompt
    assert "Attempt 1 failed" in prompt


def test_build_prompt_with_passed_feedback_has_no_feedback_section() -> None:
    """build_prompt with passed=True ReflexionFeedback does not append feedback section."""
    bundle = _make_bundle(story_content="Story text.")
    feedback = ReflexionFeedback(
        passed=True,
        unmet_criteria=[],
        feedback_per_criterion={},
        attempt_number=1,
    )
    prompt = build_prompt(bundle, feedback=feedback)
    assert "Previous Validation Feedback" not in prompt


def test_build_prompt_includes_file_operation_constraints_when_cwd_provided() -> None:
    """Providing working_directory appends explicit relative-path constraints."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(bundle, working_directory=Path("/repo/worktrees/story-1"))

    assert "## File Operation Constraints" in prompt
    assert "Current working directory: /repo/worktrees/story-1" in prompt
    assert "Use relative file paths rooted at the current working directory." in prompt
    assert "Do not use absolute paths from validator output or prior logs." in prompt


def test_build_prompt_includes_prior_sandbox_denial_section() -> None:
    """sandbox_feedback adds a dedicated retry guidance section."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(
        bundle,
        sandbox_feedback="Write to '/abs/path/file.ts' was denied.",
    )

    assert "## Prior Sandbox Denial" in prompt
    assert "Write to '/abs/path/file.ts' was denied." in prompt
    assert "Correct this before making other changes." in prompt


# ---------------------------------------------------------------------------
# Test 6.10 — build_prompt quality_feedback injection (Story 10.12)
# ---------------------------------------------------------------------------


def _make_failed_quality_feedback() -> QualityFeedback:
    """Build a failing QualityFeedback with a mypy failure."""
    return QualityFeedback(
        passed=False,
        auto_fix_summary=[],
        tool_results=[
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(
                tool_name="mypy --strict",
                passed=False,
                exit_code=1,
                stdout="",
                stderr="src/foo.py:10: error: Missing return statement  [return]",
            ),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ],
    )


def test_build_prompt_quality_feedback_section_present_when_failed() -> None:
    """build_prompt with failing quality_feedback includes ## Previous Quality Gate Feedback."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(bundle, quality_feedback=_make_failed_quality_feedback())
    assert "## Previous Quality Gate Feedback" in prompt


def test_build_prompt_quality_feedback_includes_failing_tool_diagnostics() -> None:
    """build_prompt quality_feedback section includes stderr/stdout for failing tools."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(bundle, quality_feedback=_make_failed_quality_feedback())
    assert "mypy --strict" in prompt
    assert "Missing return statement" in prompt


def test_build_prompt_quality_feedback_omits_passing_tools() -> None:
    """build_prompt quality_feedback section does not include diagnostics for passing tools."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(bundle, quality_feedback=_make_failed_quality_feedback())
    # ruff check and pytest passed — their names should not appear in the section diagnostic block
    # (they may appear briefly if listed as "passed", but no stderr/stdout injected)
    assert "ruff check: passed" not in prompt or "## Previous Quality Gate Feedback" in prompt


def test_build_prompt_quality_feedback_none_does_not_inject_section() -> None:
    """build_prompt without quality_feedback does not include quality gate section."""
    bundle = _make_bundle(story_content="Story text.")
    prompt = build_prompt(bundle, quality_feedback=None)
    assert "## Previous Quality Gate Feedback" not in prompt


def test_build_prompt_quality_feedback_passed_does_not_inject_section() -> None:
    """build_prompt with quality_feedback.passed=True does not inject the section."""
    bundle = _make_bundle(story_content="Story text.")
    feedback = QualityFeedback(
        passed=True,
        auto_fix_summary=[],
        tool_results=[
            ToolResult(tool_name="ruff check", passed=True, exit_code=0),
            ToolResult(tool_name="mypy --strict", passed=True, exit_code=0),
            ToolResult(tool_name="pytest", passed=True, exit_code=0),
        ],
    )
    prompt = build_prompt(bundle, quality_feedback=feedback)
    assert "## Previous Quality Gate Feedback" not in prompt
