"""Factual raw ETABS result-row evidence bundles.

Identity fields identify a result row. Payload fields carry result values. This
module does not select Vt, Ndm, envelopes, signs, governing locations, or
engineering verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Any, Mapping

from tbdy_engine.canonical_tables.table import CanonicalTable

BASE_REACTION_IDENTITY_FIELDS = ("OutputCase", "CaseType", "StepType", "StepNumber")
BASE_REACTION_PAYLOAD_FIELDS = ("FX", "FY", "FZ", "MX", "MY", "MZ", "X", "Y", "Z")
PIER_FORCE_IDENTITY_FIELDS = (
    "Story", "Pier", "OutputCase", "CaseType", "StepType", "StepNumber", "Location",
)
PIER_FORCE_PAYLOAD_FIELDS = ("P", "V2", "V3", "T", "M2", "M3")
STORY_FORCE_IDENTITY_FIELDS = (
    "Story", "OutputCase", "CaseType", "StepType", "StepNumber", "Location",
)
STORY_FORCE_PAYLOAD_FIELDS = ("P", "VX", "VY", "T", "MX", "MY")

RESULT_IDENTITY_FIELDS = MappingProxyType({
    "base_reactions": BASE_REACTION_IDENTITY_FIELDS,
    "pier_forces": PIER_FORCE_IDENTITY_FIELDS,
    "story_forces": STORY_FORCE_IDENTITY_FIELDS,
})
RESULT_PAYLOAD_FIELDS = MappingProxyType({
    "base_reactions": BASE_REACTION_PAYLOAD_FIELDS,
    "pier_forces": PIER_FORCE_PAYLOAD_FIELDS,
    "story_forces": STORY_FORCE_PAYLOAD_FIELDS,
})
# Compatibility view: complete raw capture contract, never row identity.
RESULT_SOURCE_FIELDS = MappingProxyType({
    key: RESULT_IDENTITY_FIELDS[key] + RESULT_PAYLOAD_FIELDS[key]
    for key in RESULT_IDENTITY_FIELDS
})


class RuntimeCaptureStatus(StrEnum):
    FULL = "FULL"
    TRUNCATED = "TRUNCATED"
    SAMPLED = "SAMPLED"
    PARTIAL = "PARTIAL"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ResultRowEvidenceBundle:
    table_key: str
    actual_table_name: str
    identity_fields: tuple[str, ...]
    payload_fields: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    source_contract_status: str
    units: Mapping[str, Any]
    runtime_capture_status: RuntimeCaptureStatus | str = RuntimeCaptureStatus.UNKNOWN
    captured_row_count: int | None = None
    reported_row_count: int | None = None

    def __post_init__(self) -> None:
        if self.table_key not in RESULT_SOURCE_FIELDS:
            raise ValueError(f"Unsupported Pack B raw result table: {self.table_key}")
        expected_identity = RESULT_IDENTITY_FIELDS[self.table_key]
        expected_payload = RESULT_PAYLOAD_FIELDS[self.table_key]
        if tuple(self.identity_fields) != expected_identity:
            raise ValueError("Raw result identity fields must match the frozen live-proven identity set")
        if tuple(self.payload_fields) != expected_payload:
            raise ValueError("Raw result payload fields must match the frozen live-proven payload set")
        if self.source_contract_status != "VERIFIED_LIVE":
            raise ValueError("Pack B result evidence bundle requires VERIFIED_LIVE raw source contract")
        capture_status = RuntimeCaptureStatus(str(self.runtime_capture_status))
        expected_all = expected_identity + expected_payload
        frozen_rows = []
        for index, row in enumerate(self.rows):
            missing = [field for field in expected_all if field not in row]
            if missing:
                raise ValueError(f"Raw result row {index} missing required field(s): {', '.join(missing)}")
            frozen_rows.append(MappingProxyType(dict(row)))
        captured = len(frozen_rows) if self.captured_row_count is None else int(self.captured_row_count)
        reported = None if self.reported_row_count is None else int(self.reported_row_count)
        if captured != len(frozen_rows):
            raise ValueError("captured_row_count must equal the number of captured rows")
        if reported is not None and reported < captured:
            raise ValueError("reported_row_count cannot be smaller than captured_row_count")
        object.__setattr__(self, "identity_fields", expected_identity)
        object.__setattr__(self, "payload_fields", expected_payload)
        object.__setattr__(self, "rows", tuple(frozen_rows))
        object.__setattr__(self, "units", MappingProxyType(dict(self.units or {})))
        object.__setattr__(self, "runtime_capture_status", capture_status)
        object.__setattr__(self, "captured_row_count", captured)
        object.__setattr__(self, "reported_row_count", reported)

    @property
    def is_full_capture(self) -> bool:
        if self.runtime_capture_status != RuntimeCaptureStatus.FULL:
            return False
        return self.reported_row_count is None or self.captured_row_count == self.reported_row_count

    def require_full_capture(self) -> None:
        if not self.is_full_capture:
            raise ValueError(
                "Result-derived envelopes require runtime FULL acquisition; truncated/sampled/partial capture is non-executable"
            )

    @classmethod
    def from_canonical_table(
        cls,
        table: CanonicalTable,
        *,
        source_contract_status: str,
        runtime_capture_status: RuntimeCaptureStatus | str = RuntimeCaptureStatus.UNKNOWN,
        reported_row_count: int | None = None,
    ) -> "ResultRowEvidenceBundle":
        key = str(table.table_key)
        if key not in RESULT_SOURCE_FIELDS:
            raise ValueError(f"CanonicalTable is not a Pack B raw result source: {key}")
        return cls(
            table_key=key,
            actual_table_name=str(table.actual_table_name or key),
            identity_fields=RESULT_IDENTITY_FIELDS[key],
            payload_fields=RESULT_PAYLOAD_FIELDS[key],
            rows=tuple(dict(row) for row in table.rows),
            source_contract_status=source_contract_status,
            units=dict(table.units or {}),
            runtime_capture_status=runtime_capture_status,
            captured_row_count=len(table.rows),
            reported_row_count=reported_row_count,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "table_key": self.table_key,
            "actual_table_name": self.actual_table_name,
            "identity_fields": list(self.identity_fields),
            "payload_fields": list(self.payload_fields),
            "row_count": len(self.rows),
            "rows": [dict(row) for row in self.rows],
            "source_contract_status": self.source_contract_status,
            "units": dict(self.units),
            "runtime_capture_status": self.runtime_capture_status.value,
            "captured_row_count": self.captured_row_count,
            "reported_row_count": self.reported_row_count,
            "full_capture": self.is_full_capture,
            "derived_quantities": [],
        }


__all__ = [
    "BASE_REACTION_IDENTITY_FIELDS", "BASE_REACTION_PAYLOAD_FIELDS",
    "PIER_FORCE_IDENTITY_FIELDS", "PIER_FORCE_PAYLOAD_FIELDS",
    "RESULT_IDENTITY_FIELDS", "RESULT_PAYLOAD_FIELDS", "RESULT_SOURCE_FIELDS",
    "RuntimeCaptureStatus", "STORY_FORCE_IDENTITY_FIELDS", "STORY_FORCE_PAYLOAD_FIELDS",
    "ResultRowEvidenceBundle",
]
