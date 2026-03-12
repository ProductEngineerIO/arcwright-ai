"""Core constants — Project-wide constant values and magic strings.

No magic string should appear elsewhere in the codebase — centralise everything here.
"""

from __future__ import annotations

__all__: list[str] = [
    "AGENT_OUTPUT_FILENAME",
    "BRANCH_PREFIX",
    "COMMIT_MESSAGE_TEMPLATE",
    "CONFIG_FILENAME",
    "CONTEXT_BUNDLE_FILENAME",
    "DIR_ARCWRIGHT",
    "DIR_PROVENANCE",
    "DIR_RUNS",
    "DIR_SPEC",
    "DIR_STORIES",
    "DIR_TMP",
    "DIR_WORKTREES",
    "ENV_API_CLAUDE_API_KEY",
    "ENV_LIMITS_COST_PER_RUN",
    "ENV_LIMITS_RETRY_BUDGET",
    "ENV_LIMITS_TIMEOUT_PER_STORY",
    "ENV_LIMITS_TOKENS_PER_STORY",
    "ENV_METHODOLOGY_ARTIFACTS_PATH",
    "ENV_METHODOLOGY_TYPE",
    "ENV_MODEL_GENERATE_PRICING_INPUT_RATE",
    "ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE",
    "ENV_MODEL_GENERATE_VERSION",
    "ENV_MODEL_PRICING_INPUT_RATE",
    "ENV_MODEL_PRICING_OUTPUT_RATE",
    "ENV_MODEL_REVIEW_PRICING_INPUT_RATE",
    "ENV_MODEL_REVIEW_PRICING_OUTPUT_RATE",
    "ENV_MODEL_REVIEW_VERSION",
    "ENV_MODEL_VERSION",
    "ENV_PREFIX",
    "ENV_REPRODUCIBILITY_ENABLED",
    "ENV_REPRODUCIBILITY_RETENTION",
    "ENV_SCM_BRANCH_TEMPLATE",
    "EXIT_AGENT",
    "EXIT_CONFIG",
    "EXIT_INTERNAL",
    "EXIT_SCM",
    "EXIT_SUCCESS",
    "EXIT_VALIDATION",
    "GLOBAL_CONFIG_DIR",
    "HALT_REPORT_FILENAME",
    "LOG_FILENAME",
    "MAX_RETRIES",
    "PYTHON_DIRNAME_PATTERN",
    "PYTHON_FILENAME_PATTERN",
    "RUN_ID_DATETIME_FORMAT",
    "RUN_METADATA_FILENAME",
    "STORY_COPY_FILENAME",
    "SUMMARY_FILENAME",
    "VALIDATION_FILENAME",
    "WORKTREE_DIR_TEMPLATE",
]

# ---------------------------------------------------------------------------
# Directory names
# ---------------------------------------------------------------------------

DIR_ARCWRIGHT: str = ".arcwright-ai"
DIR_SPEC: str = "_spec"
DIR_RUNS: str = "runs"
DIR_TMP: str = "tmp"
DIR_WORKTREES: str = "worktrees"
DIR_PROVENANCE: str = "provenance"
DIR_STORIES: str = "stories"

# ---------------------------------------------------------------------------
# Exit codes
# ---------------------------------------------------------------------------

EXIT_SUCCESS: int = 0
EXIT_VALIDATION: int = 1
EXIT_AGENT: int = 2
EXIT_CONFIG: int = 3
EXIT_SCM: int = 4
EXIT_INTERNAL: int = 5

# ---------------------------------------------------------------------------
# Operational defaults
# ---------------------------------------------------------------------------

MAX_RETRIES: int = 3
BRANCH_PREFIX: str = "arcwright/"

# Naming convention patterns
PYTHON_FILENAME_PATTERN: str = r"^[a-z][a-z0-9_]*\.py$"
PYTHON_DIRNAME_PATTERN: str = r"^[a-z][a-z0-9_]*$"

# ---------------------------------------------------------------------------
# Run ID and git templates
# ---------------------------------------------------------------------------

#: strftime format string for the datetime portion of a run ID.
RUN_ID_DATETIME_FORMAT: str = "%Y%m%d-%H%M%S"

COMMIT_MESSAGE_TEMPLATE: str = "[arcwright] {story_title}\n\nStory: {story_path}\nRun: {run_id}"
WORKTREE_DIR_TEMPLATE: str = ".arcwright-ai/worktrees/{story_slug}"

# ---------------------------------------------------------------------------
# File names
# ---------------------------------------------------------------------------

LOG_FILENAME: str = "log.jsonl"
RUN_METADATA_FILENAME: str = "run.yaml"
SUMMARY_FILENAME: str = "summary.md"
HALT_REPORT_FILENAME: str = "halt-report.md"

# Story lifecycle file names (under runs/<run-id>/stories/<story-slug>/)
STORY_COPY_FILENAME: str = "story.md"
CONTEXT_BUNDLE_FILENAME: str = "context-bundle.md"
AGENT_OUTPUT_FILENAME: str = "agent-output.md"
VALIDATION_FILENAME: str = "validation.md"

# ---------------------------------------------------------------------------
# Configuration file names and directories
# ---------------------------------------------------------------------------

#: Name of the YAML configuration file used at both global and project tiers.
CONFIG_FILENAME: str = "config.yaml"

#: Name of the hidden directory where Arcwright config and run data live.
GLOBAL_CONFIG_DIR: str = ".arcwright-ai"

# ---------------------------------------------------------------------------
# Environment variable names for config overrides
# ---------------------------------------------------------------------------
#
# Mapping:  ARCWRIGHT_<SECTION>_<FIELD>  →  RunConfig.<section>.<field>
#
#   ARCWRIGHT_API_CLAUDE_API_KEY                    → api.claude_api_key                       (str)
#   ARCWRIGHT_AI_MODEL_GENERATE_VERSION             → models.roles["generate"].version         (str)
#   ARCWRIGHT_AI_MODEL_REVIEW_VERSION               → models.roles["review"].version           (str)
#   ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE  → models.roles["generate"].pricing.input_rate  (Decimal)
#   ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE → models.roles["generate"].pricing.output_rate (Decimal)
#   ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE    → models.roles["review"].pricing.input_rate    (Decimal)
#   ARCWRIGHT_AI_MODEL_REVIEW_PRICING_OUTPUT_RATE   → models.roles["review"].pricing.output_rate   (Decimal)
#   ARCWRIGHT_LIMITS_TOKENS_PER_STORY               → limits.tokens_per_story                  (int)
#   ARCWRIGHT_LIMITS_COST_PER_RUN                   → limits.cost_per_run                      (float)
#   ARCWRIGHT_LIMITS_RETRY_BUDGET                   → limits.retry_budget                      (int)
#   ARCWRIGHT_LIMITS_TIMEOUT_PER_STORY              → limits.timeout_per_story                 (int)
#   ARCWRIGHT_METHODOLOGY_ARTIFACTS_PATH            → methodology.artifacts_path               (str)
#   ARCWRIGHT_METHODOLOGY_TYPE                      → methodology.type                         (str)
#   ARCWRIGHT_SCM_BRANCH_TEMPLATE                   → scm.branch_template                      (str)
#   ARCWRIGHT_REPRODUCIBILITY_ENABLED               → reproducibility.enabled                  (bool)
#   ARCWRIGHT_REPRODUCIBILITY_RETENTION             → reproducibility.retention                (int)
#
# Deprecated aliases (will be removed in a future version):
#   ARCWRIGHT_MODEL_VERSION               → alias for ARCWRIGHT_AI_MODEL_GENERATE_VERSION
#   ARCWRIGHT_MODEL_PRICING_INPUT_RATE    → alias for ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE
#   ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE   → alias for ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE

ENV_PREFIX: str = "ARCWRIGHT_"
ENV_API_CLAUDE_API_KEY: str = "ARCWRIGHT_API_CLAUDE_API_KEY"

# Role-based model env vars (preferred pattern: ARCWRIGHT_AI_MODEL_{ROLE}_{FIELD})
ENV_MODEL_GENERATE_VERSION: str = "ARCWRIGHT_AI_MODEL_GENERATE_VERSION"
ENV_MODEL_REVIEW_VERSION: str = "ARCWRIGHT_AI_MODEL_REVIEW_VERSION"
ENV_MODEL_GENERATE_PRICING_INPUT_RATE: str = "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_INPUT_RATE"
ENV_MODEL_GENERATE_PRICING_OUTPUT_RATE: str = "ARCWRIGHT_AI_MODEL_GENERATE_PRICING_OUTPUT_RATE"
ENV_MODEL_REVIEW_PRICING_INPUT_RATE: str = "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_INPUT_RATE"
ENV_MODEL_REVIEW_PRICING_OUTPUT_RATE: str = "ARCWRIGHT_AI_MODEL_REVIEW_PRICING_OUTPUT_RATE"

# Deprecated aliases — retained for backward compatibility; will be removed in a future version.
# Use ENV_MODEL_GENERATE_VERSION / ENV_MODEL_GENERATE_PRICING_* instead.
ENV_MODEL_VERSION: str = "ARCWRIGHT_MODEL_VERSION"  # deprecated alias for ARCWRIGHT_AI_MODEL_GENERATE_VERSION
ENV_MODEL_PRICING_INPUT_RATE: str = "ARCWRIGHT_MODEL_PRICING_INPUT_RATE"  # deprecated alias
ENV_MODEL_PRICING_OUTPUT_RATE: str = "ARCWRIGHT_MODEL_PRICING_OUTPUT_RATE"  # deprecated alias

ENV_LIMITS_TOKENS_PER_STORY: str = "ARCWRIGHT_LIMITS_TOKENS_PER_STORY"
ENV_LIMITS_COST_PER_RUN: str = "ARCWRIGHT_LIMITS_COST_PER_RUN"
ENV_LIMITS_RETRY_BUDGET: str = "ARCWRIGHT_LIMITS_RETRY_BUDGET"
ENV_LIMITS_TIMEOUT_PER_STORY: str = "ARCWRIGHT_LIMITS_TIMEOUT_PER_STORY"
ENV_METHODOLOGY_ARTIFACTS_PATH: str = "ARCWRIGHT_METHODOLOGY_ARTIFACTS_PATH"
ENV_METHODOLOGY_TYPE: str = "ARCWRIGHT_METHODOLOGY_TYPE"
ENV_SCM_BRANCH_TEMPLATE: str = "ARCWRIGHT_SCM_BRANCH_TEMPLATE"
ENV_REPRODUCIBILITY_ENABLED: str = "ARCWRIGHT_REPRODUCIBILITY_ENABLED"
ENV_REPRODUCIBILITY_RETENTION: str = "ARCWRIGHT_REPRODUCIBILITY_RETENTION"
