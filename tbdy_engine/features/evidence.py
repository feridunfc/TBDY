"""Feature evidence records for C4.

Evidence is traceability data only. It does not carry CheckResult objects or any
check pass/fail decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping

from tbdy_engine.contracts.models import freeze_data


class FeatureEvidenceStatus(StrEnum):
    FULL = "FULL"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"


@dataclass(frozen=True, slots=True)
class FeatureEvidence:
    evidence_status: FeatureEvidenceStatus | str
    source_table: str | None = None
    actual_table_name: str | None = None
    source_column: str | None = None
    source_row: Mapping[str, Any] | None = None
    output_case: str | None = None
    combo_family: str | None = None
    governing_combo: str | None = None
    section_state: str | None = None
    ductility_class: str | None = None
    raw_value: Any = None
    normalized_value: Any = None
    unit: str = ""
    resolver: str = "generic_table_resolver"
    reason: str | None = None

    def __post_init__(self) -> None:
        status = FeatureEvidenceStatus(str(self.evidence_status))
        object.__setattr__(self, "evidence_status", status)
        object.__setattr__(self, "source_row", freeze_data(dict(self.source_row or {})))
        if status in {FeatureEvidenceStatus.PARTIAL, FeatureEvidenceStatus.MISSING} and not self.reason:
            raise ValueError("PARTIAL or MISSING feature evidence requires reason")
        if status == FeatureEvidenceStatus.FULL:
            missing = [
                name
                for name, value in (
                    ("source_table", self.source_table),
                    ("actual_table_name", self.actual_table_name),
                    ("source_column", self.source_column),
                )
                if value in (None, "")
            ]
            if missing:
                raise ValueError(f"FULL feature evidence missing required fields: {', '.join(missing)}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "evidence_status": self.evidence_status.value,
            "source_table": self.source_table,
            "actual_table_name": self.actual_table_name,
            "source_column": self.source_column,
            "source_row": dict(self.source_row or {}),
            "output_case": self.output_case,
            "combo_family": self.combo_family,
            "governing_combo": self.governing_combo,
            "section_state": self.section_state,
            "ductility_class": self.ductility_class,
            "raw_value": self.raw_value,
            "normalized_value": self.normalized_value,
            "unit": self.unit,
            "resolver": self.resolver,
            "reason": self.reason,
        }


__all__ = ["FeatureEvidence", "FeatureEvidenceStatus"]
