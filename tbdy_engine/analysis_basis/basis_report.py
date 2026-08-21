"""Pure immutable analysis-basis report projection for F0.6."""
from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from typing import Sequence

from tbdy_engine.regulatory.kernel import AnalysisBasisStatus
from .contracts import AnalysisBasisCompatibility, AnalysisBasisSnapshot


def _canonical_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ValueError(f"{label} must be a nonblank canonical string")
    return value


def _canonical_epoch_ref(value: str) -> str:
    value = _canonical_text(value, "epoch_ref")
    if not value.startswith("epoch:") or not value.removeprefix("epoch:"):
        raise ValueError("epoch_ref must use canonical epoch:<id> form")
    return value


def _refs(values: tuple[str, ...], label: str) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise TypeError(f"{label} must be a tuple of strings")
    if any(not isinstance(item, str) for item in values):
        raise TypeError(f"{label} must contain strings only")
    return tuple(_canonical_text(item, label) for item in values)


def _validate_prefixed_sha(value: str, prefix: str, label: str) -> str:
    value = _canonical_text(value, label)
    if not value.startswith(prefix):
        raise ValueError(f"{label} must use {prefix}<sha256> form")
    digest = value.removeprefix(prefix)
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise ValueError(f"{label} must contain a lowercase sha256 digest")
    return value


def _row_identity(
    *,
    snapshot_ref: str,
    epoch_ref: str,
    structural_zone_ref: str,
    direction: str,
    reviewed_declaration_ref: str,
    resolved_policy_ref: str,
    analysis_assumption_ref: str,
    compatibility_ref: str,
    compatibility_status: AnalysisBasisStatus,
    analysis_evidence_refs: tuple[str, ...],
    provenance_refs: tuple[str, ...],
) -> str:
    if type(compatibility_status) is not AnalysisBasisStatus:
        raise TypeError("compatibility_status must be canonical AnalysisBasisStatus")
    payload = {
        "snapshot_ref": _canonical_text(snapshot_ref, "snapshot_ref"),
        "epoch_ref": _canonical_epoch_ref(epoch_ref),
        "structural_zone_ref": _canonical_text(structural_zone_ref, "structural_zone_ref"),
        "direction": _canonical_text(direction, "direction"),
        "reviewed_declaration_ref": _canonical_text(reviewed_declaration_ref, "reviewed_declaration_ref"),
        "resolved_policy_ref": _canonical_text(resolved_policy_ref, "resolved_policy_ref"),
        "analysis_assumption_ref": _canonical_text(analysis_assumption_ref, "analysis_assumption_ref"),
        "compatibility_ref": _canonical_text(compatibility_ref, "compatibility_ref"),
        "compatibility_status": compatibility_status.value,
        "analysis_evidence_refs": list(_refs(analysis_evidence_refs, "analysis_evidence_ref")),
        "provenance_refs": list(_refs(provenance_refs, "provenance_ref")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "analysis-basis-report-row:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AnalysisBasisReportRow:
    row_id: str
    snapshot_ref: str
    epoch_ref: str
    structural_zone_ref: str
    direction: str
    reviewed_declaration_ref: str
    resolved_policy_ref: str
    analysis_assumption_ref: str
    compatibility_ref: str
    compatibility_status: AnalysisBasisStatus
    analysis_evidence_refs: tuple[str, ...] = field(default_factory=tuple)
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    @property
    def sort_key(self) -> tuple[str, str, str]:
        return (self.structural_zone_ref, self.direction, self.snapshot_ref)

    def __post_init__(self) -> None:
        row_id = _validate_prefixed_sha(self.row_id, "analysis-basis-report-row:", "row_id")
        if type(self.compatibility_status) is not AnalysisBasisStatus:
            raise TypeError("compatibility_status must be canonical AnalysisBasisStatus")
        analysis_evidence_refs = _refs(self.analysis_evidence_refs, "analysis_evidence_ref")
        provenance_refs = _refs(self.provenance_refs, "provenance_ref")
        object.__setattr__(self, "analysis_evidence_refs", analysis_evidence_refs)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        expected_id = _row_identity(
            snapshot_ref=self.snapshot_ref,
            epoch_ref=self.epoch_ref,
            structural_zone_ref=self.structural_zone_ref,
            direction=self.direction,
            reviewed_declaration_ref=self.reviewed_declaration_ref,
            resolved_policy_ref=self.resolved_policy_ref,
            analysis_assumption_ref=self.analysis_assumption_ref,
            compatibility_ref=self.compatibility_ref,
            compatibility_status=self.compatibility_status,
            analysis_evidence_refs=analysis_evidence_refs,
            provenance_refs=provenance_refs,
        )
        if row_id != expected_id:
            raise ValueError("row_id does not match canonical stored semantic fields")

    def as_dict(self) -> dict[str, object]:
        return {
            "row_id": self.row_id,
            "snapshot_ref": self.snapshot_ref,
            "epoch_ref": self.epoch_ref,
            "structural_zone_ref": self.structural_zone_ref,
            "direction": self.direction,
            "reviewed_declaration_ref": self.reviewed_declaration_ref,
            "resolved_policy_ref": self.resolved_policy_ref,
            "analysis_assumption_ref": self.analysis_assumption_ref,
            "compatibility_ref": self.compatibility_ref,
            "compatibility_status": self.compatibility_status.value,
            "analysis_evidence_refs": list(self.analysis_evidence_refs),
            "provenance_refs": list(self.provenance_refs),
        }


def build_analysis_basis_report_row(
    *,
    snapshot: AnalysisBasisSnapshot,
    compatibility: AnalysisBasisCompatibility,
    provenance_refs: tuple[str, ...] = (),
) -> AnalysisBasisReportRow:
    if not isinstance(snapshot, AnalysisBasisSnapshot):
        raise TypeError("snapshot must be AnalysisBasisSnapshot")
    if not isinstance(compatibility, AnalysisBasisCompatibility):
        raise TypeError("compatibility must be AnalysisBasisCompatibility")
    provenance_refs = _refs(provenance_refs, "provenance_ref")
    if snapshot.compatibility_ref != compatibility.compatibility_id:
        raise ValueError("snapshot compatibility_ref does not match compatibility_id")
    if snapshot.epoch_ref != compatibility.epoch_ref:
        raise ValueError("snapshot epoch_ref does not match compatibility epoch_ref")
    if snapshot.structural_zone_ref != compatibility.structural_zone_ref:
        raise ValueError("snapshot structural_zone_ref does not match compatibility")
    if snapshot.direction != compatibility.direction:
        raise ValueError("snapshot direction does not match compatibility")
    kwargs = {
        "snapshot_ref": snapshot.snapshot_id,
        "epoch_ref": snapshot.epoch_ref,
        "structural_zone_ref": snapshot.structural_zone_ref,
        "direction": snapshot.direction,
        "reviewed_declaration_ref": snapshot.reviewed_declaration_ref,
        "resolved_policy_ref": snapshot.resolved_policy_ref,
        "analysis_assumption_ref": snapshot.analysis_assumption_ref,
        "compatibility_ref": snapshot.compatibility_ref,
        "compatibility_status": compatibility.status,
        "analysis_evidence_refs": snapshot.analysis_evidence_refs,
        "provenance_refs": provenance_refs,
    }
    return AnalysisBasisReportRow(row_id=_row_identity(**kwargs), **kwargs)


def _report_identity(*, epoch_ref: str, rows: tuple[AnalysisBasisReportRow, ...], provenance_refs: tuple[str, ...]) -> str:
    payload = {
        "epoch_ref": _canonical_epoch_ref(epoch_ref),
        "rows": [row.as_dict() for row in rows],
        "provenance_refs": list(_refs(provenance_refs, "provenance_ref")),
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return "analysis-basis-report:" + hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True, slots=True)
class AnalysisBasisReport:
    report_id: str
    epoch_ref: str
    rows: tuple[AnalysisBasisReportRow, ...]
    provenance_refs: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        report_id = _validate_prefixed_sha(self.report_id, "analysis-basis-report:", "report_id")
        epoch_ref = _canonical_epoch_ref(self.epoch_ref)
        if type(self.rows) is not tuple:
            raise TypeError("rows must be a tuple of AnalysisBasisReportRow")
        if not self.rows:
            raise ValueError("AnalysisBasisReport requires at least one row")
        if any(not isinstance(row, AnalysisBasisReportRow) for row in self.rows):
            raise TypeError("rows must contain AnalysisBasisReportRow only")
        rows = tuple(sorted(self.rows, key=lambda row: row.sort_key))
        provenance_refs = _refs(self.provenance_refs, "provenance_ref")
        if any(row.epoch_ref != epoch_ref for row in rows):
            raise ValueError("every report row must match report epoch_ref")
        snapshot_refs = [row.snapshot_ref for row in rows]
        if len(set(snapshot_refs)) != len(snapshot_refs):
            raise ValueError("duplicate snapshot_ref within AnalysisBasisReport")
        scope_directions = [(row.structural_zone_ref, row.direction) for row in rows]
        if len(set(scope_directions)) != len(scope_directions):
            raise ValueError("duplicate structural_zone_ref × direction within one epoch")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "provenance_refs", provenance_refs)
        expected_id = _report_identity(epoch_ref=epoch_ref, rows=rows, provenance_refs=provenance_refs)
        if report_id != expected_id:
            raise ValueError("report_id does not match canonical stored semantic fields")

    def as_dict(self) -> dict[str, object]:
        return {
            "report_id": self.report_id,
            "epoch_ref": self.epoch_ref,
            "rows": [row.as_dict() for row in self.rows],
            "provenance_refs": list(self.provenance_refs),
        }


def build_analysis_basis_report(*, rows: Sequence[AnalysisBasisReportRow], provenance_refs: tuple[str, ...] = ()) -> AnalysisBasisReport:
    if isinstance(rows, (str, bytes)):
        raise TypeError("rows must be a sequence of AnalysisBasisReportRow")
    frozen_rows = tuple(rows)
    if not frozen_rows:
        raise ValueError("AnalysisBasisReport requires at least one row")
    if any(not isinstance(row, AnalysisBasisReportRow) for row in frozen_rows):
        raise TypeError("rows must contain AnalysisBasisReportRow only")
    sorted_rows = tuple(sorted(frozen_rows, key=lambda row: row.sort_key))
    epoch_refs = {row.epoch_ref for row in sorted_rows}
    if len(epoch_refs) != 1:
        raise ValueError("all report rows must have one epoch_ref")
    epoch_ref = next(iter(epoch_refs))
    provenance_refs = _refs(provenance_refs, "provenance_ref")
    report_id = _report_identity(epoch_ref=epoch_ref, rows=sorted_rows, provenance_refs=provenance_refs)
    return AnalysisBasisReport(report_id=report_id, epoch_ref=epoch_ref, rows=sorted_rows, provenance_refs=provenance_refs)


__all__ = [
    "AnalysisBasisReportRow",
    "AnalysisBasisReport",
    "build_analysis_basis_report_row",
    "build_analysis_basis_report",
]
