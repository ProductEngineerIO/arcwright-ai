"""Tests for core/constants.py — All magic strings and numeric constants."""

from __future__ import annotations

from arcwright_ai.core.constants import (
    AGENT_OUTPUT_FILENAME,
    BRANCH_PREFIX,
    COMMIT_MESSAGE_TEMPLATE,
    CONTEXT_BUNDLE_FILENAME,
    DIR_ARCWRIGHT,
    DIR_PROVENANCE,
    DIR_RUNS,
    DIR_SPEC,
    DIR_STORIES,
    DIR_TMP,
    DIR_WORKTREES,
    EXIT_AGENT,
    EXIT_CONFIG,
    EXIT_INTERNAL,
    EXIT_SCM,
    EXIT_SUCCESS,
    EXIT_VALIDATION,
    HALT_REPORT_FILENAME,
    LOG_FILENAME,
    MAX_RETRIES,
    RUN_ID_DATETIME_FORMAT,
    RUN_METADATA_FILENAME,
    STORY_COPY_FILENAME,
    SUMMARY_FILENAME,
    VALIDATION_FILENAME,
    WORKTREE_DIR_TEMPLATE,
)

# ---------------------------------------------------------------------------
# Directory constants
# ---------------------------------------------------------------------------


def test_dir_arcwright() -> None:
    assert DIR_ARCWRIGHT == ".arcwright-ai"


def test_dir_spec() -> None:
    assert DIR_SPEC == "_spec"


def test_dir_runs() -> None:
    assert DIR_RUNS == "runs"


def test_dir_tmp() -> None:
    assert DIR_TMP == "tmp"


def test_dir_worktrees() -> None:
    assert DIR_WORKTREES == "worktrees"


def test_dir_provenance() -> None:
    assert DIR_PROVENANCE == "provenance"


def test_dir_stories() -> None:
    assert DIR_STORIES == "stories"


# ---------------------------------------------------------------------------
# Exit codes — sequential 0-5
# ---------------------------------------------------------------------------


def test_exit_success_is_zero() -> None:
    assert EXIT_SUCCESS == 0


def test_exit_validation_is_one() -> None:
    assert EXIT_VALIDATION == 1


def test_exit_agent_is_two() -> None:
    assert EXIT_AGENT == 2


def test_exit_config_is_three() -> None:
    assert EXIT_CONFIG == 3


def test_exit_scm_is_four() -> None:
    assert EXIT_SCM == 4


def test_exit_internal_is_five() -> None:
    assert EXIT_INTERNAL == 5


def test_exit_codes_are_sequential() -> None:
    codes = [EXIT_SUCCESS, EXIT_VALIDATION, EXIT_AGENT, EXIT_CONFIG, EXIT_SCM, EXIT_INTERNAL]
    assert codes == list(range(6))


# ---------------------------------------------------------------------------
# Operational constants
# ---------------------------------------------------------------------------


def test_max_retries() -> None:
    assert MAX_RETRIES == 3


def test_branch_prefix() -> None:
    assert BRANCH_PREFIX == "arcwright/"


def test_run_id_datetime_format() -> None:
    assert RUN_ID_DATETIME_FORMAT == "%Y%m%d-%H%M%S"


# ---------------------------------------------------------------------------
# File names
# ---------------------------------------------------------------------------


def test_log_filename() -> None:
    assert LOG_FILENAME == "log.jsonl"


def test_run_metadata_filename() -> None:
    assert RUN_METADATA_FILENAME == "run.yaml"


def test_summary_filename() -> None:
    assert SUMMARY_FILENAME == "summary.md"


def test_halt_report_filename() -> None:
    assert HALT_REPORT_FILENAME == "halt-report.md"


def test_story_copy_filename() -> None:
    assert STORY_COPY_FILENAME == "story.md"


def test_context_bundle_filename() -> None:
    assert CONTEXT_BUNDLE_FILENAME == "context-bundle.md"


def test_agent_output_filename() -> None:
    assert AGENT_OUTPUT_FILENAME == "agent-output.md"


def test_validation_filename() -> None:
    assert VALIDATION_FILENAME == "validation.md"


# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------


def test_commit_message_template_contains_placeholders() -> None:
    assert "{story_title}" in COMMIT_MESSAGE_TEMPLATE
    assert "{story_path}" in COMMIT_MESSAGE_TEMPLATE
    assert "{run_id}" in COMMIT_MESSAGE_TEMPLATE


def test_worktree_dir_template_contains_placeholder() -> None:
    assert "{story_slug}" in WORKTREE_DIR_TEMPLATE


# ---------------------------------------------------------------------------
# __all__ completeness
# ---------------------------------------------------------------------------


def test_all_symbols_exported() -> None:
    import arcwright_ai.core.constants as mod

    expected = {
        "AGENT_OUTPUT_FILENAME",
        "BRANCH_PREFIX",
        "COMMIT_MESSAGE_TEMPLATE",
        "CONTEXT_BUNDLE_FILENAME",
        "DIR_ARCWRIGHT",
        "DIR_PROVENANCE",
        "DIR_RUNS",
        "DIR_SPEC",
        "DIR_STORIES",
        "DIR_TMP",
        "DIR_WORKTREES",
        "EXIT_AGENT",
        "EXIT_CONFIG",
        "EXIT_INTERNAL",
        "EXIT_SCM",
        "EXIT_SUCCESS",
        "EXIT_VALIDATION",
        "HALT_REPORT_FILENAME",
        "LOG_FILENAME",
        "MAX_RETRIES",
        "RUN_ID_DATETIME_FORMAT",
        "RUN_METADATA_FILENAME",
        "STORY_COPY_FILENAME",
        "SUMMARY_FILENAME",
        "VALIDATION_FILENAME",
        "WORKTREE_DIR_TEMPLATE",
    }
    assert set(mod.__all__) == expected
