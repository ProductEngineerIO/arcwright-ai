"""Core errors — Structured Claude error taxonomy and remediation contract.

Defines a stable error classification taxonomy for Claude SDK / CLI failures.
Each category carries operator-facing guidance metadata (title, summary,
retryability, and ordered remediation steps) consumable by CLI, engine, and
output surfaces without ad hoc string parsing.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING

from pydantic import ConfigDict

from arcwright_ai.core.types import ArcwrightModel

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__: list[str] = [
    "CLAUDE_ERROR_REGISTRY",
    "ClaudeErrorCategory",
    "ClaudeErrorClassification",
    "classify_claude_error",
]

# ---------------------------------------------------------------------------
# Error category enum
# ---------------------------------------------------------------------------


class ClaudeErrorCategory(StrEnum):
    """Stable error codes for Claude-related failures.

    Platform / account failures:
        BILLING_ERROR, AUTH_ERROR, MODEL_ACCESS_ERROR, RATE_LIMIT_ERROR

    Local runtime / configuration failures:
        LOCAL_CONFIG_ERROR, MANAGED_SETTINGS_ERROR, CLI_MISSING_ERROR

    Transient provider failures:
        NETWORK_ERROR, TIMEOUT_ERROR

    Catch-all:
        UNKNOWN_SDK_ERROR
    """

    BILLING_ERROR = "billing_error"
    AUTH_ERROR = "auth_error"
    MODEL_ACCESS_ERROR = "model_access_error"
    RATE_LIMIT_ERROR = "rate_limit_error"
    NETWORK_ERROR = "network_error"
    TIMEOUT_ERROR = "timeout_error"
    LOCAL_CONFIG_ERROR = "local_config_error"
    MANAGED_SETTINGS_ERROR = "managed_settings_error"
    CLI_MISSING_ERROR = "cli_missing_error"
    UNKNOWN_SDK_ERROR = "unknown_sdk_error"


# ---------------------------------------------------------------------------
# Classification model
# ---------------------------------------------------------------------------


class ClaudeErrorClassification(ArcwrightModel):
    """Structured classification of a Claude-related failure.

    Attributes:
        error_code: Stable category from the taxonomy enum.
        title: Short user-facing label (e.g. "API Billing Error").
        summary: Concise terminal-safe description of the failure.
        retryable: Whether the failure may resolve on retry.
        remediation_steps: Ordered operator guidance steps.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", str_strip_whitespace=True)

    error_code: ClaudeErrorCategory
    title: str
    summary: str
    retryable: bool
    remediation_steps: list[str]


# ---------------------------------------------------------------------------
# Static registry — one entry per category
# ---------------------------------------------------------------------------

CLAUDE_ERROR_REGISTRY: Mapping[ClaudeErrorCategory, ClaudeErrorClassification] = {
    ClaudeErrorCategory.BILLING_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.BILLING_ERROR,
        title="API Billing Error",
        summary="The configured Anthropic API key has insufficient credit balance.",
        retryable=False,
        remediation_steps=[
            "Check your Anthropic billing dashboard for remaining credits.",
            "Add credits or upgrade your plan at console.anthropic.com.",
            "If using an API key override, remove it so Claude Code can use CLI/OAuth auth.",
        ],
    ),
    ClaudeErrorCategory.AUTH_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.AUTH_ERROR,
        title="API Authentication Error",
        summary="The configured Anthropic API key was rejected.",
        retryable=False,
        remediation_steps=[
            "Verify the ANTHROPIC_API_KEY value is correct and not expired.",
            "Regenerate the key at console.anthropic.com if needed.",
            "Remove the Arcwright API-key override to use CLI/OAuth auth instead.",
        ],
    ),
    ClaudeErrorCategory.MODEL_ACCESS_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.MODEL_ACCESS_ERROR,
        title="Model Access Denied",
        summary="The configured account or API key does not have access to the requested model.",
        retryable=False,
        remediation_steps=[
            "Check which models your API key is authorised for.",
            "Choose a model your account can use in arcwright config.",
            "Upgrade your Anthropic plan if the model requires a higher tier.",
        ],
    ),
    ClaudeErrorCategory.RATE_LIMIT_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.RATE_LIMIT_ERROR,
        title="Rate Limit Exceeded",
        summary="Anthropic API rate limit reached. The request may succeed after a cooldown.",
        retryable=True,
        remediation_steps=[
            "Wait and retry — Arcwright applies exponential backoff automatically.",
            "If persistent, check your Anthropic rate-limit tier and usage.",
            "Consider reducing concurrency or request frequency.",
        ],
    ),
    ClaudeErrorCategory.NETWORK_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.NETWORK_ERROR,
        title="Network Connectivity Error",
        summary="Cannot reach Anthropic API servers. Check network connectivity.",
        retryable=True,
        remediation_steps=[
            "Verify internet connectivity and DNS resolution.",
            "Check if api.anthropic.com is reachable from your network.",
            "Check proxy/firewall settings if operating behind a corporate network.",
        ],
    ),
    ClaudeErrorCategory.TIMEOUT_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.TIMEOUT_ERROR,
        title="Request Timeout",
        summary="The Claude API request timed out before completing.",
        retryable=True,
        remediation_steps=[
            "Retry — transient network congestion may have caused the timeout.",
            "If persistent, check network latency to Anthropic endpoints.",
            "Consider increasing the timeout configuration if available.",
        ],
    ),
    ClaudeErrorCategory.LOCAL_CONFIG_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.LOCAL_CONFIG_ERROR,
        title="Local Configuration Error",
        summary="A required local configuration value is missing or invalid.",
        retryable=False,
        remediation_steps=[
            "Ensure ANTHROPIC_API_KEY is set in your environment or .env file.",
            "Run 'arcwright init' to regenerate configuration if needed.",
            "Check arcwright config file for missing or malformed values.",
        ],
    ),
    ClaudeErrorCategory.MANAGED_SETTINGS_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.MANAGED_SETTINGS_ERROR,
        title="Managed Settings Error",
        summary="Claude managed settings file is invalid or could not be loaded.",
        retryable=False,
        remediation_steps=[
            "Check ~/.claude/remote-settings.json for valid JSON syntax.",
            "Delete the file and let Arcwright recreate it on next run.",
            "Verify file permissions allow read/write access.",
        ],
    ),
    ClaudeErrorCategory.CLI_MISSING_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.CLI_MISSING_ERROR,
        title="Claude CLI Not Found",
        summary="The 'claude' command-line tool is not installed or not on PATH.",
        retryable=False,
        remediation_steps=[
            "Install Claude Code CLI: npm install -g @anthropic-ai/claude-code",
            "Verify 'claude' is on your PATH by running 'which claude'.",
            "If installed via a version manager, ensure the correct Node environment is active.",
        ],
    ),
    ClaudeErrorCategory.UNKNOWN_SDK_ERROR: ClaudeErrorClassification(
        error_code=ClaudeErrorCategory.UNKNOWN_SDK_ERROR,
        title="Unknown Claude SDK Error",
        summary="An unrecognised Claude SDK or CLI error occurred.",
        retryable=False,
        remediation_steps=[
            "Check the full error output in the Arcwright run log for details.",
            "Search the Anthropic status page (status.anthropic.com) for incidents.",
            "If reproducible, file an issue with the full error log attached.",
        ],
    ),
}

# ---------------------------------------------------------------------------
# Credential redaction
# ---------------------------------------------------------------------------

_REDACTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"sk-ant-[a-zA-Z0-9\-_]{10,}"),
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"Bearer\s+[a-zA-Z0-9\-_\.]+"),
    re.compile(r"api[_\-]?key[=: ]+\S+", re.IGNORECASE),
]


def _redact_secrets(text: str) -> str:
    """Strip API keys, bearer tokens, and other credential patterns from *text*."""
    for pattern in _REDACTION_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


# ---------------------------------------------------------------------------
# Classification patterns (order matters — first match wins)
# ---------------------------------------------------------------------------

_BILLING_RE = re.compile(
    r"credit balance is too low|plans?\s*&\s*billing|billing_error|insufficient credit",
    re.IGNORECASE,
)
_AUTH_RE = re.compile(
    r"authentication_error|invalid.api.key|api.key[^\n]*invalid|incorrect.api.key|401\b|unauthorized|forbidden",
    re.IGNORECASE,
)
_MODEL_ACCESS_RE = re.compile(
    (
        r"model access denied|does not have access to (?:the )?model|"
        r"not authorized to use (?:the )?model|model[^\n]*not available for this key"
    ),
    re.IGNORECASE,
)
_RATE_LIMIT_RE = re.compile(
    r"rate.?limit|429|too many requests",
    re.IGNORECASE,
)
_TIMEOUT_RE = re.compile(
    r"timeout|timed?\s*out",
    re.IGNORECASE,
)
_NETWORK_RE = re.compile(
    r"connection refused|connection reset|ECONNREFUSED|dns resolution|name resolution|"
    r"network (?:is )?unreachable|no route to host|socket.gaierror",
    re.IGNORECASE,
)
_CLI_MISSING_RE = re.compile(
    r"command not found.*claude|claude.*command not found|"
    r"No such file or directory.*claude|claude.*No such file or directory|"
    r"ENOENT.*claude",
    re.IGNORECASE,
)
_LOCAL_CONFIG_RE = re.compile(
    r"ANTHROPIC_API_KEY.*not set|environment variable.*not set|" r"missing.*api.key|api.key.*missing|config.*not found",
    re.IGNORECASE,
)
_MANAGED_SETTINGS_RE = re.compile(
    r"managed.settings|remote-settings\.json",
    re.IGNORECASE,
)

_CLASSIFICATION_CHAIN: list[tuple[re.Pattern[str], ClaudeErrorCategory]] = [
    (_BILLING_RE, ClaudeErrorCategory.BILLING_ERROR),
    (_AUTH_RE, ClaudeErrorCategory.AUTH_ERROR),
    (_MODEL_ACCESS_RE, ClaudeErrorCategory.MODEL_ACCESS_ERROR),
    (_CLI_MISSING_RE, ClaudeErrorCategory.CLI_MISSING_ERROR),
    (_LOCAL_CONFIG_RE, ClaudeErrorCategory.LOCAL_CONFIG_ERROR),
    (_MANAGED_SETTINGS_RE, ClaudeErrorCategory.MANAGED_SETTINGS_ERROR),
    (_RATE_LIMIT_RE, ClaudeErrorCategory.RATE_LIMIT_ERROR),
    (_TIMEOUT_RE, ClaudeErrorCategory.TIMEOUT_ERROR),
    (_NETWORK_RE, ClaudeErrorCategory.NETWORK_ERROR),
]


# ---------------------------------------------------------------------------
# Public classifier
# ---------------------------------------------------------------------------


def classify_claude_error(
    *,
    message: str,
    stderr: str | None = None,
    exit_code: int | None = None,
) -> ClaudeErrorClassification:
    """Classify a Claude SDK / CLI failure into the structured taxonomy.

    Combines *message* and *stderr* and matches against the ordered pattern
    chain.  The first matching category wins; unrecognised failures fall back
    to ``UNKNOWN_SDK_ERROR``.

    All credential patterns are redacted from the returned summary so the
    result is safe for terminal / artifact rendering.

    Args:
        message: Primary error message (from exception or SDK).
        stderr: Optional captured stderr from the Claude CLI process.
        exit_code: Optional process exit code for additional context.

    Returns:
        A ``ClaudeErrorClassification`` drawn from the static registry,
        potentially with a redacted summary for dynamic context.
    """
    combined = "\n".join(part for part in (message, stderr or "") if part)
    if not combined:
        return CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.UNKNOWN_SDK_ERROR]

    for pattern, category in _CLASSIFICATION_CHAIN:
        if pattern.search(combined):
            entry = CLAUDE_ERROR_REGISTRY[category]
            # Return the static entry — summary is already secret-safe.
            return (
                entry.model_copy(
                    update={"summary": _redact_secrets(entry.summary)},
                )
                if _has_secrets(combined)
                else entry
            )

    # Fallback: unknown_sdk_error with a redacted diagnostic summary.
    fallback = CLAUDE_ERROR_REGISTRY[ClaudeErrorCategory.UNKNOWN_SDK_ERROR]
    safe_snippet = _redact_secrets(combined[:240])
    return fallback.model_copy(
        update={"summary": f"An unrecognised Claude error occurred. Diagnostic: {safe_snippet}"},
    )


def _has_secrets(text: str) -> bool:
    """Return True if *text* matches any credential pattern."""
    return any(p.search(text) for p in _REDACTION_PATTERNS)
