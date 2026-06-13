"""Feature-layer diagnostics for C4 FeatureSnapshot foundation.

Diagnostics are data-only. They never encode check status, pass/fail decisions,
ratios, formulas, or CheckResult objects.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from tbdy_engine.contracts.models import freeze_data


class FeatureDiagnosticSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class FeatureDiagnosticCode(StrEnum):
    FEATURE_MISSING = "FEATURE_MISSING"
    EVIDENCE_MISSING = "EVIDENCE_MISSING"
    TABLE_MISSING = "TABLE_MISSING"
    COLUMN_MISSING = "COLUMN_MISSING"
    ROW_MISSING = "ROW_MISSING"
    UNSUPPORTED_AGGREGATION = "UNSUPPORTED_AGGREGATION"
    FORBIDDEN_FEATURE_NAME = "FORBIDDEN_FEATURE_NAME"
    CHECK_RESULT_FORBIDDEN = "CHECK_RESULT_FORBIDDEN"
    FILTER_NOT_MATCHED = "FILTER_NOT_MATCHED"
    ANALYSIS_SECTION_FALLBACK = "ANALYSIS_SECTION_FALLBACK"
    COMBO_ENGINEERING_REVIEW = "COMBO_ENGINEERING_REVIEW"
    COMBO_UNKNOWN = "COMBO_UNKNOWN"
    UNIT_ASSUMED = "UNIT_ASSUMED"
    UNIT_CONTEXT_MISSING = "UNIT_CONTEXT_MISSING"
    UNIT_NORMALIZATION_UNVERIFIED = "UNIT_NORMALIZATION_UNVERIFIED"
    UNIT_NORMALIZED = "UNIT_NORMALIZED"
    SHEAR_REBAR_UNIT_SEMANTICS_REVIEW = "SHEAR_REBAR_UNIT_SEMANTICS_REVIEW"
    IDENTITY_SEEDED_FROM_DESIGN_SUMMARY = "IDENTITY_SEEDED_FROM_DESIGN_SUMMARY"
    IDENTITY_SEEDED_NOT_FRAME_CONFIRMED = "IDENTITY_SEEDED_NOT_FRAME_CONFIRMED"
    SECTION_NAME_PARSE_SUGGESTION = "SECTION_NAME_PARSE_SUGGESTION"
    ETABS_WARNING_MESSAGE = "ETABS_WARNING_MESSAGE"
    ETABS_ERROR_MESSAGE = "ETABS_ERROR_MESSAGE"
    DIRECT_API_FALLBACK_USED = "DIRECT_API_FALLBACK_USED"
    DIRECT_SECTION_GEOMETRY_UNAVAILABLE = "DIRECT_SECTION_GEOMETRY_UNAVAILABLE"
    DIRECT_FRAME_LENGTH_UNAVAILABLE = "DIRECT_FRAME_LENGTH_UNAVAILABLE"
    ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS = "ETABS_TABLEDATA_EMPTY_DESPITE_RECORDS"
    DISPLAY_SELECTION_REQUIRED = "DISPLAY_SELECTION_REQUIRED"
    MODAL_AGGREGATION_MAX_CUMULATIVE_USED = "MODAL_AGGREGATION_MAX_CUMULATIVE_USED"
    MODAL_TABLE_EMPTY = "MODAL_TABLE_EMPTY"
    MODAL_SUM_COLUMN_MISSING = "MODAL_SUM_COLUMN_MISSING"
    MODAL_MODE_COLUMN_MISSING = "MODAL_MODE_COLUMN_MISSING"
    MODAL_CUMULATIVE_VALUE_INVALID = "MODAL_CUMULATIVE_VALUE_INVALID"
    RESOLVER_ONLY_HAS_SAMPLE_ROWS = "RESOLVER_ONLY_HAS_SAMPLE_ROWS"
    RESOLVER_TABLE_PARSE_MISMATCH_WITH_PROBE = "RESOLVER_TABLE_PARSE_MISMATCH_WITH_PROBE"
    RESOLVER_SELECTOR_NO_MATCH_WITH_ROWS_PRESENT = "RESOLVER_SELECTOR_NO_MATCH_WITH_ROWS_PRESENT"


@dataclass(frozen=True, slots=True)
class FeatureDiagnostic:
    severity: FeatureDiagnosticSeverity | str
    code: FeatureDiagnosticCode | str
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "severity", FeatureDiagnosticSeverity(str(self.severity)))
        object.__setattr__(self, "code", FeatureDiagnosticCode(str(self.code)))
        object.__setattr__(self, "details", freeze_data(dict(self.details)))
        if not self.message:
            raise ValueError("FeatureDiagnostic.message is required")

    def as_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity.value,
            "code": self.code.value,
            "message": self.message,
            "details": dict(self.details),
        }


__all__ = ["FeatureDiagnostic", "FeatureDiagnosticCode", "FeatureDiagnosticSeverity"]
