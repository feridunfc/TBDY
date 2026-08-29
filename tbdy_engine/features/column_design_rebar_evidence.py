"""Provider-neutral factual concrete-column design-result contracts for P8A.

This module owns factual row/population evidence only.  It contains no design
authority, combo-eligibility dependency, governing-row selection, or live ETABS
access.  Downstream design-layer authority may consume these facts only after a
provider establishes a complete same-model/EvidenceEpoch population.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Sequence

class ColumnDesignRebarEvidenceError(ValueError):
    """Raised when the factual population or promotion authority is inconsistent."""


def _text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignRebarEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _optional_text(value: str | None, label: str) -> str | None:
    return None if value is None else _text(value, label)


def _decimal(value: Decimal, label: str, *, nonnegative: bool = True) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ColumnDesignRebarEvidenceError(f"{label} must be a finite Decimal")
    if nonnegative and value < 0:
        raise ColumnDesignRebarEvidenceError(f"{label} must be >= 0")
    return Decimal(0) if value == 0 else value.normalize()


def _refs(values: Sequence[str], label: str) -> tuple[str, ...]:
    refs = tuple(sorted({_text(value, label) for value in values}))
    if not refs:
        raise ColumnDesignRebarEvidenceError(f"{label} must be nonempty")
    return refs


def _ids(values: Sequence[str], label: str) -> tuple[str, ...]:
    result = tuple(sorted(_text(value, label) for value in values))
    if not result or len(result) != len(set(result)):
        raise ColumnDesignRebarEvidenceError(f"{label} must be nonempty and unique")
    return result

@dataclass(frozen=True, slots=True)
class FactualColumnDesignResultRow:
    """Provider-neutral exact factual row from a future accepted P8A-2 capture."""

    source_row_id: str
    component_id: str
    unique_name: str
    story: str
    label: str
    assigned_section: str
    design_section: str
    my_option: int
    pmm_combo: str | None
    location_mm: Decimal
    pmm_area_mm2: Decimal
    error_summary: str
    warning_summary: str
    model_fingerprint: str
    evidence_epoch_id: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for name in (
            "source_row_id",
            "component_id",
            "unique_name",
            "story",
            "label",
            "assigned_section",
            "design_section",
            "model_fingerprint",
            "evidence_epoch_id",
        ):
            object.__setattr__(self, name, _text(getattr(self, name), name))
        if self.my_option not in (1, 2):
            raise ColumnDesignRebarEvidenceError("my_option must be exact CSI Check=1 or Design=2")
        object.__setattr__(self, "pmm_combo", _optional_text(self.pmm_combo, "pmm_combo"))
        object.__setattr__(self, "location_mm", _decimal(self.location_mm, "location_mm"))
        object.__setattr__(self, "pmm_area_mm2", _decimal(self.pmm_area_mm2, "pmm_area_mm2"))
        if not isinstance(self.error_summary, str) or not isinstance(self.warning_summary, str):
            raise ColumnDesignRebarEvidenceError("ErrorSummary/WarningSummary must preserve exact strings")
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))

    @property
    def is_design_row(self) -> bool:
        return self.my_option == 2


@dataclass(frozen=True, slots=True)
class FactualColumnDesignResultPopulation:
    """Complete provider-neutral population contract for one model/EvidenceEpoch."""

    model_fingerprint: str
    evidence_epoch_id: str
    expected_component_ids: tuple[str, ...]
    attempted_component_ids: tuple[str, ...]
    captured_component_ids: tuple[str, ...]
    reported_result_row_count: int
    rows: tuple[FactualColumnDesignResultRow, ...]
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        expected = _ids(self.expected_component_ids, "expected_component_id")
        attempted = _ids(self.attempted_component_ids, "attempted_component_id")
        captured = _ids(self.captured_component_ids, "captured_component_id")
        object.__setattr__(self, "expected_component_ids", expected)
        object.__setattr__(self, "attempted_component_ids", attempted)
        object.__setattr__(self, "captured_component_ids", captured)
        rows = tuple(sorted(self.rows, key=lambda item: item.source_row_id))
        if any(not isinstance(item, FactualColumnDesignResultRow) for item in rows):
            raise TypeError("rows must contain FactualColumnDesignResultRow")
        if len({item.source_row_id for item in rows}) != len(rows):
            raise ColumnDesignRebarEvidenceError("source_row_id values must be unique")
        if any(
            item.model_fingerprint != self.model_fingerprint
            or item.evidence_epoch_id != self.evidence_epoch_id
            for item in rows
        ):
            raise ColumnDesignRebarEvidenceError("row model fingerprint/EvidenceEpoch mismatch")
        if set(item.component_id for item in rows) != set(captured):
            raise ColumnDesignRebarEvidenceError("captured component ids must equal exact row component population")
        if any(not any(row.component_id == component for row in rows) for component in captured):
            raise ColumnDesignRebarEvidenceError("each captured component must retain at least one result row")
        if isinstance(self.reported_result_row_count, bool) or self.reported_result_row_count != len(rows):
            raise ColumnDesignRebarEvidenceError("reported and captured result-row counts must be exactly equal")
        object.__setattr__(self, "rows", rows)
        object.__setattr__(self, "source_refs", _refs(self.source_refs, "source_ref"))

    @property
    def capture_complete(self) -> bool:
        return (
            self.expected_component_ids
            == self.attempted_component_ids
            == self.captured_component_ids
            and self.reported_result_row_count == len(self.rows)
        )

    @property
    def design_rows(self) -> tuple[FactualColumnDesignResultRow, ...]:
        return tuple(item for item in self.rows if item.is_design_row)

__all__ = [
    "ColumnDesignRebarEvidenceError",
    "FactualColumnDesignResultPopulation",
    "FactualColumnDesignResultRow",
]
