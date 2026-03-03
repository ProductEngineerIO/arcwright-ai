"""Validation package — Story output validation pipeline with V3 and V6 strategies."""

from __future__ import annotations

from arcwright_ai.validation.v6_invariant import (
    V6CheckResult,
    V6ValidationResult,
    register_v6_check,
    run_v6_validation,
)

# Planned public API — symbols implemented in future stories:
#   validate_story_output  (validation/pipeline.py — Story 3.3)
__all__: list[str] = [
    "V6CheckResult",
    "V6ValidationResult",
    "register_v6_check",
    "run_v6_validation",
]
