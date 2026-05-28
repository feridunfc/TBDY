from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .models import FormulaTrace


@dataclass(frozen=True)
class EvaluationEvidence:
    evidence_type: str
    confidence: str
    source_fields: list[str]
    source_values: Mapping[str, Any]
    unit_conversion_status: str
    combo_family_status: str
    notes: list[str] = field(default_factory=list)
    missing_inputs: list[str] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class EvaluationStep:
    step_id: str
    status: str
    value: float | None
    limit: float | None
    unit: str
    ratio: float | None
    message: str
    formula_trace: FormulaTrace
    evidence: EvaluationEvidence


@dataclass(frozen=True)
class EvaluationOutput:
    output_id: str
    element_type: str
    element_label: str
    story: str
    measurements: Mapping[str, Any]
    status: str
    governing_ratio: float | None
    evidence: EvaluationEvidence
    steps: list[EvaluationStep]


@dataclass(frozen=True)
class EvaluationPackage:
    evaluation_id: str
    evaluation_type: str
    check_family: str
    category: str
    source: str
    status: str
    outputs: list[EvaluationOutput]
    summary: Mapping[str, Any]
    evidence: EvaluationEvidence
    diagnostics: list[str] = field(default_factory=list)
