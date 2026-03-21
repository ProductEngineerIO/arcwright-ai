"""Agent prompt — Prompt construction and context assembly for agent invocation."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from arcwright_ai.core.types import ContextBundle
    from arcwright_ai.validation.quality_gate import QualityFeedback
    from arcwright_ai.validation.v3_reflexion import ReflexionFeedback

__all__: list[str] = ["build_prompt"]


def build_prompt(
    bundle: ContextBundle,
    *,
    feedback: ReflexionFeedback | None = None,
    quality_feedback: QualityFeedback | None = None,
    working_directory: Path | None = None,
    sandbox_feedback: str | None = None,
) -> str:
    """Assemble an SDK prompt string from a ContextBundle.

    Formats the bundle's story content, resolved requirements, architecture
    excerpts, and project conventions into a structured prompt with clearly
    delineated markdown sections. Sections are only included when the
    corresponding bundle field is non-empty. When ``feedback`` is provided and
    the feedback indicates failure, a ``## Previous Validation Feedback``
    section is appended with the failing criteria and suggested fixes.

    When ``quality_feedback`` is provided and the gate failed, a
    ``## Previous Quality Gate Feedback`` section is appended with the auto-fix
    summary and per-tool diagnostics so the agent can see exactly what to fix.

    Args:
        bundle: The assembled context payload from the preflight node.
        feedback: Optional reflexion feedback from a previous validation
            attempt. Appended to the prompt only when feedback is not None
            and feedback.passed is False.
        quality_feedback: Optional Quality Gate feedback from a previous
            attempt. Appended to the prompt only when the gate failed.
        working_directory: Optional agent working directory used to anchor
            file edits.
        sandbox_feedback: Optional feedback describing a sandbox-denied write
            from a prior attempt.

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

    if working_directory is not None:
        parts.append(
            "\n".join(
                [
                    "## File Operation Constraints",
                    "",
                    f"- Current working directory: {working_directory}",
                    "- Use relative file paths rooted at the current working directory.",
                    "- Do not use absolute paths from validator output or prior logs.",
                    (
                        "- If a validator references an absolute path like "
                        "'/.../src/app/file.ts', rewrite it as 'src/app/file.ts'."
                    ),
                ]
            )
        )

    if sandbox_feedback:
        parts.append(
            "\n".join(
                [
                    "## Prior Sandbox Denial",
                    "",
                    sandbox_feedback,
                    "",
                    "Correct this before making other changes.",
                ]
            )
        )

    if feedback is not None and not feedback.passed:
        feedback_lines: list[str] = [
            "## Previous Validation Feedback",
            "",
            f"**Attempt {feedback.attempt_number} failed.** The following acceptance criteria were NOT met:",
            "",
        ]
        for ac_id in feedback.unmet_criteria:
            detail = feedback.feedback_per_criterion.get(ac_id, "No details provided")
            feedback_lines.append(f"### AC {ac_id}")
            feedback_lines.append(detail)
            feedback_lines.append("")
        feedback_lines.append("**Fix all unmet criteria above before completing this story.**")
        parts.append("\n".join(feedback_lines))

    if quality_feedback is not None and not quality_feedback.passed:
        qf_lines: list[str] = ["## Previous Quality Gate Feedback", ""]

        if quality_feedback.auto_fix_summary:
            qf_lines.append("**Auto-fixes applied (informational):**")
            for fix in quality_feedback.auto_fix_summary:
                qf_lines.append(f"- `{fix.file_path}`: {fix.rule_id} ({fix.description})")
            qf_lines.append("")

        failing_tools = [r for r in quality_feedback.tool_results if not r.passed]
        if failing_tools:
            qf_lines.append("**Failing checks — fix these issues:**")
            qf_lines.append("")
            for tool in failing_tools:
                if tool.timed_out:
                    qf_lines.append(f"### {tool.tool_name} (timed out)")
                    qf_lines.append("")
                    qf_lines.append(f"```\n{tool.stderr}\n```")
                else:
                    qf_lines.append(f"### {tool.tool_name} (exit code {tool.exit_code})")
                    qf_lines.append("")
                    diagnostic = (tool.stdout or tool.stderr).strip()
                    if diagnostic:
                        qf_lines.append(f"```\n{diagnostic}\n```")
                qf_lines.append("")

        qf_lines.append("**Fix all failing checks above before completing this story.**")
        parts.append("\n".join(qf_lines))

    return "\n\n".join(parts)
