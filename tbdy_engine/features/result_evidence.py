"""Factual raw ETABS result-row evidence bundles.

This module preserves complete live result identity only. It never selects Vt,
Ndm, envelopes, signs, governing locations, or engineering verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from tbdy_engine.canonical_tables.table import CanonicalTable

BASE_REACTION_IDENTITY_FIELDS = (
    "OutputCase", "CaseType", "StepType", "StepNumber", "FX", "FY", "FZ",
    "MX", "MY", "MZ", "X", "Y", "Z",
)
PIER_FORCE_IDENTITY_FIELDS = (
    "Story", "Pier", "OutputCase", "CaseType", "StepType", "StepNumber",
    "Location", "P", "V2", "V3", "T", "M2", "M3",
)
STORY_FORCE_IDENTITY_FIELDS = (
    "Story", "OutputCase", "CaseType", "StepType", "StepNumber", "Location",
    "P", "VX", "VY", "T", "MX", "MY",
)
RESULT_SOURCE_FIELDS = MappingProxyType({
    "base_reactions": BASE_REACTION_IDENTITY_FIELDS,
    "pier_forces": PIER_FORCE_IDENTITY_FIELDS,
    "story_forces": STORY_FORCE_IDENTITY_FIELDS,
})


@dataclass(frozen=True, slots=True)
class ResultRowEvidenceBundle:
    table_key: str
    actual_table_name: str
    identity_fields: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    source_contract_status: str
    units: Mapping[str, Any]

    def __post_init__(self) -> None:
        if self.table_key not in RESULT_SOURCE_FIELDS:
            raise ValueError(f"Unsupported Pack B raw result table: {self.table_key}")
        expected = RESULT_SOURCE_FIELDS[self.table_key]
        if tuple(self.identity_fields) != expected:
            raise ValueError("Raw result identity must match the frozen live-proven field set")
        if self.source_contract_status != "VERIFIED_LIVE":
            raise ValueError("Pack B result evidence bundle requires VERIFIED_LIVE raw source contract")
        frozen_rows = []
        for index, row in enumerate(self.rows):
            missing = [field for field in expected if field not in row]
            if missing:
                raise ValueError(f"Raw result row {index} missing identity field(s): {', '.join(missing)}")
            frozen_rows.append(MappingProxyType(dict(row)))
        object.__setattr__(self, "rows", tuple(frozen_rows))
        object.__setattr__(self, "units", MappingProxyType(dict(self.units or {})))

    @classmethod
    def from_canonical_table(cls, table: CanonicalTable, *, source_contract_status: str) -> "ResultRowEvidenceBundle":
        key = str(table.table_key)
        if key not in RESULT_SOURCE_FIELDS:
            raise ValueError(f"CanonicalTable is not a Pack B raw result source: {key}")
        return cls(
            table_key=key,
            actual_table_name=str(table.actual_table_name or key),
            identity_fields=RESULT_SOURCE_FIELDS[key],
            rows=tuple(dict(row) for row in table.rows),
            source_contract_status=source_contract_status,
            units=dict(table.units or {}),
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_key": self.table_key,
            "actual_table_name": self.actual_table_name,
            "identity_fields": list(self.identity_fields),
            "row_count": len(self.rows),
            "rows": [dict(row) for row in self.rows],
            "source_contract_status": self.source_contract_status,
            "units": dict(self.units),
            "derived_quantities": [],
        }


__all__ = [
    "BASE_REACTION_IDENTITY_FIELDS", "PIER_FORCE_IDENTITY_FIELDS",
    "RESULT_SOURCE_FIELDS", "STORY_FORCE_IDENTITY_FIELDS", "ResultRowEvidenceBundle",
]
