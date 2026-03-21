"""Validation package — Story output validation pipeline with V3 and V6 strategies."""

from __future__ import annotations

from arcwright_ai.validation.pipeline import (
    PipelineOutcome,
    PipelineResult,
    run_validation_pipeline,
)
from arcwright_ai.validation.quality_gate import (
    AutoFixEntry,
    QualityFeedback,
    QualityGateResult,
    ToolResult,
    run_quality_gate,
)
from arcwright_ai.validation.v3_reflexion import (
    ACResult,
    ReflexionFeedback,
    V3ReflexionResult,
    ValidationResult,
    run_v3_reflexion,
)
from arcwright_ai.validation.v6_invariant import (
    V6CheckResult,
    V6ValidationResult,
    register_v6_check,
    run_v6_validation,
)

__all__: list[str] = [
    "ACResult",
    "AutoFixEntry",
    "PipelineOutcome",
    "PipelineResult",
    "QualityFeedback",
    "QualityGateResult",
    "ReflexionFeedback",
    "ToolResult",
    "V3ReflexionResult",
    "V6CheckResult",
    "V6ValidationResult",
    "ValidationResult",
    "register_v6_check",
    "run_quality_gate",
    "run_v3_reflexion",
    "run_v6_validation",
    "run_validation_pipeline",
]
