"""Resolved feature value DTO for C4.

A FeatureValue is not a check result. It never emits OK/FAIL and does not carry
ratios, formulas, or pass rules.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Sequence

from tbdy_engine.features.diagnostics import FeatureDiagnostic, FeatureDiagnosticCode, FeatureDiagnosticSeverity
from tbdy_engine.features.evidence import FeatureEvidence, FeatureEvidenceStatus

_FORBIDDEN_FEATURE_NAME_TERMS = ("ratio", "status", "pass", "fail", "ok")
_FORBIDDEN_TEXT_TOKENS = ("CheckResult", "pass_rule")


class FeatureValueStatus(StrEnum):
    RESOLVED = "RESOLVED"
    MISSING = "MISSING"
    PARTIAL = "PARTIAL"


def validate_feature_name(feature_name: str) -> None:
    lowered = feature_name.casefold()
    if any(term in lowered for term in _FORBIDDEN_FEATURE_NAME_TERMS):
        raise ValueError("Feature names must not contain check-result or decision semantics")
    if any(token.casefold() in lowered for token in _FORBIDDEN_TEXT_TOKENS):
        raise ValueError("Feature names must remain data-only")


@dataclass(frozen=True, slots=True)
class FeatureValue:
    feature_name: str
    value: Any
    unit: str
    semantic_role: str
    status: FeatureValueStatus | str
    evidence: tuple[FeatureEvidence, ...] = field(default_factory=tuple)
    diagnostics: tuple[FeatureDiagnostic, ...] = field(default_factory=tuple)

    def __init__(
        self,
        *,
        feature_name: str,
        value: Any,
        unit: str = "",
        semantic_role: str = "UNKNOWN",
        status: FeatureValueStatus | str = FeatureValueStatus.RESOLVED,
        evidence: Sequence[FeatureEvidence] | None = None,
        diagnostics: Sequence[FeatureDiagnostic] | None = None,
    ) -> None:
        if not feature_name:
            raise ValueError("FeatureValue.feature_name is required")
        validate_feature_name(feature_name)
        normalized_status = FeatureValueStatus(str(status))
        normalized_evidence = tuple(evidence or ())
        normalized_diagnostics = tuple(diagnostics or ())
        if normalized_status == FeatureValueStatus.RESOLVED:
            if not normalized_evidence:
                raise ValueError("RESOLVED FeatureValue requires evidence")
            if any(ev.evidence_status == FeatureEvidenceStatus.MISSING for ev in normalized_evidence):
                raise ValueError("RESOLVED FeatureValue cannot be backed only by missing evidence")
        if normalized_status in {FeatureValueStatus.PARTIAL, FeatureValueStatus.MISSING} and not normalized_evidence:
            normalized_diagnostics = normalized_diagnostics + (
                FeatureDiagnostic(
                    severity=FeatureDiagnosticSeverity.WARNING,
                    code=FeatureDiagnosticCode.EVIDENCE_MISSING,
                    message="Feature evidence is not complete",
                    details={"feature_name": feature_name, "feature_status": normalized_status.value},
                ),
            )
        object.__setattr__(self, "feature_name", feature_name)
        object.__setattr__(self, "value", value)
        object.__setattr__(self, "unit", unit)
        object.__setattr__(self, "semantic_role", semantic_role)
        object.__setattr__(self, "status", normalized_status)
        object.__setattr__(self, "evidence", normalized_evidence)
        object.__setattr__(self, "diagnostics", normalized_diagnostics)

    def as_dict(self) -> dict[str, Any]:
        return {
            "feature_name": self.feature_name,
            "value": self.value,
            "unit": self.unit,
            "semantic_role": self.semantic_role,
            "status": self.status.value,
            "evidence": [ev.as_dict() for ev in self.evidence],
            "diagnostics": [diag.as_dict() for diag in self.diagnostics],
        }


__all__ = ["FeatureValue", "FeatureValueStatus", "validate_feature_name"]
