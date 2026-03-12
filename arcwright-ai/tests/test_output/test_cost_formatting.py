"""Unit tests for cost/token formatting functions in arcwright_ai.output.summary.

Covers: format_cost, format_tokens, format_budget_remaining, format_retry_overhead.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from arcwright_ai.output.summary import (
    format_budget_remaining,
    format_cost,
    format_retry_overhead,
    format_tokens,
)

# ---------------------------------------------------------------------------
# format_cost (AC: #9a)
# ---------------------------------------------------------------------------


def test_format_cost_normal_value() -> None:
    """(9a) format_cost returns '$1.17' for Decimal('1.17')."""
    assert format_cost(Decimal("1.17")) == "$1.17"


def test_format_cost_zero_decimal() -> None:
    """(9a) format_cost returns '$0.00' for zero Decimal."""
    assert format_cost(Decimal("0")) == "$0.00"


def test_format_cost_none() -> None:
    """(9a) format_cost returns '$0.00' for None."""
    assert format_cost(None) == "$0.00"


def test_format_cost_string_input() -> None:
    """(9a) format_cost parses string input to Decimal before formatting."""
    assert format_cost("3.42") == "$3.42"


def test_format_cost_high_precision_rounds_half_up() -> None:
    """(9a) format_cost rounds high-precision Decimal to 2 decimal places."""
    assert format_cost(Decimal("0.005")) == "$0.01"
    assert format_cost(Decimal("0.123456789")) == "$0.12"


def test_format_cost_large_value() -> None:
    """(9a) format_cost formats large values with comma thousands separator."""
    assert format_cost(Decimal("1234.56")) == "$1,234.56"


def test_format_cost_int_input() -> None:
    """(9a) format_cost handles integer input."""
    assert format_cost(5) == "$5.00"


def test_format_cost_float_input() -> None:
    """(9a) format_cost handles float input by converting via str."""
    result = format_cost(1.0)
    assert result == "$1.00"


def test_format_cost_zero_string() -> None:
    """(9a) format_cost returns '$0.00' for '0' string input."""
    assert format_cost("0") == "$0.00"


# ---------------------------------------------------------------------------
# format_tokens (AC: #9b)
# ---------------------------------------------------------------------------


def test_format_tokens_normal_int() -> None:
    """(9b) format_tokens returns '12,450' for 12450."""
    assert format_tokens(12450) == "12,450"


def test_format_tokens_zero() -> None:
    """(9b) format_tokens returns '0' for 0."""
    assert format_tokens(0) == "0"


def test_format_tokens_none() -> None:
    """(9b) format_tokens returns '0' for None."""
    assert format_tokens(None) == "0"


def test_format_tokens_string_input() -> None:
    """(9b) format_tokens parses string input to int before formatting."""
    assert format_tokens("12450") == "12,450"


def test_format_tokens_large_value() -> None:
    """(9b) format_tokens formats values in the millions correctly."""
    assert format_tokens(1000000) == "1,000,000"
    assert format_tokens(5000000) == "5,000,000"


def test_format_tokens_small_value() -> None:
    """(9b) format_tokens handles values under 1000 without commas."""
    assert format_tokens(999) == "999"


# ---------------------------------------------------------------------------
# format_budget_remaining (AC: #9c)
# ---------------------------------------------------------------------------


def test_format_budget_remaining_normal_case() -> None:
    """(9c) format_budget_remaining returns percentage and absolute for normal case."""
    result = format_budget_remaining("2.70", "10.00")
    assert result == "73% ($7.30 of $10.00)"


def test_format_budget_remaining_zero_ceiling_unlimited() -> None:
    """(9c) format_budget_remaining returns 'unlimited' when ceiling is 0."""
    assert format_budget_remaining("0", "0") == "unlimited"
    assert format_budget_remaining("5.00", "0") == "unlimited"


def test_format_budget_remaining_zero_max_invocations_unlimited() -> None:
    """(9c) format_budget_remaining returns 'unlimited' when max_invocations is 0."""
    assert format_budget_remaining("2.70", "10.00", 0) == "unlimited"
    assert format_budget_remaining("2.70", "10.00", "0") == "unlimited"


def test_format_budget_remaining_exact_ceiling_zero_percent() -> None:
    """(9c) format_budget_remaining returns 0% when fully spent."""
    result = format_budget_remaining("10.00", "10.00")
    assert result == "0% ($0.00 of $10.00)"


def test_format_budget_remaining_decimal_inputs() -> None:
    """(9c) format_budget_remaining handles Decimal type inputs."""
    result = format_budget_remaining(Decimal("2.70"), Decimal("10.00"))
    assert result == "73% ($7.30 of $10.00)"


def test_format_budget_remaining_percentage_rounding() -> None:
    """(9c) format_budget_remaining rounds percentage to nearest integer."""
    # 7.33 / 10.0 * 100 = 73.3 → rounds to 73
    result = format_budget_remaining("2.67", "10.00")
    assert "73%" in result


# ---------------------------------------------------------------------------
# format_retry_overhead (AC: #9d)
# ---------------------------------------------------------------------------


def test_format_retry_overhead_empty_dict() -> None:
    """(9d) format_retry_overhead returns '$0.00 (no retries)' for empty dict."""
    assert format_retry_overhead({}) == "$0.00 (no retries)"


def test_format_retry_overhead_no_retries_single_invocation() -> None:
    """(9d) format_retry_overhead returns '$0.00 (no retries)' when all invocations == 1."""
    per_story: dict[str, Any] = {
        "7-1-story": {"cost": "0.50", "invocations": 1},
        "7-2-story": {"cost": "0.75", "invocations": 1},
    }
    assert format_retry_overhead(per_story) == "$0.00 (no retries)"


def test_format_retry_overhead_single_story_three_invocations() -> None:
    """(9d) Story with 3 invocations at $0.50 each → $1.00 (200% overhead)."""
    per_story: dict[str, Any] = {
        "4-3-run-summary": {"cost": "1.50", "invocations": 3},
    }
    result = format_retry_overhead(per_story)
    assert result == "$1.00 (200% overhead)"


def test_format_retry_overhead_multiple_stories_mixed_retries() -> None:
    """(9d) format_retry_overhead computes overhead across multiple stories."""
    per_story: dict[str, Any] = {
        "7-1-story": {"cost": "0.50", "invocations": 1},  # no retry
        "7-2-story": {"cost": "1.50", "invocations": 3},  # 2 retries at $0.50 each
    }
    # first_pass = 0.50 + 0.50 = 1.00
    # total = 0.50 + 1.50 = 2.00
    # retry_cost = 2.00 - 1.00 = 1.00
    # overhead% = 1.00 / 1.00 * 100 = 100%
    result = format_retry_overhead(per_story)
    assert "$1.00" in result
    assert "100% overhead" in result


def test_format_retry_overhead_string_cost_values() -> None:
    """(9d) format_retry_overhead handles string cost values from run.yaml deserialization."""
    per_story: dict[str, Any] = {
        "7-1-story": {"cost": "0.39", "invocations": 2},
    }
    # first_pass = 0.195 (half of 0.39), total = 0.39, retry_cost = 0.195
    # overhead% = 0.195 / 0.195 * 100 = 100%
    result = format_retry_overhead(per_story)
    assert "100% overhead" in result
