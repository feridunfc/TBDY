"""Source-bound factual P-M2-M3 evidence contract for VS6 column design demand.

This module is pure. It does not acquire ETABS data, select combinations,
resolve slenderness/minimum-eccentricity requirements, select reinforcement,
or emit compliance verdicts. Its purpose is to bind the exact force-result
rows used by VS6 to a deterministic evidence epoch that includes P, M2 and M3.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping, Sequence


class ColumnDesignDemandEvidenceError(ValueError):
    """Raised when factual VS6 demand evidence is incomplete or ambiguous."""


COLUMN_DESIGN_DEMAND_IDENTITY_FIELDS: tuple[str, ...] = (
    "Story",
    "Column",
    "UniqueName",
    "OutputCase",
    "CaseType",
    "StepType",
    "StepNumber",
    "Station",
    "Element",
    "ElemStation",
)
COLUMN_DESIGN_DEMAND_PAYLOAD_FIELDS: tuple[str, ...] = ("P", "M2", "M3")


def _text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnDesignDemandEvidenceError(f"{label} must be a nonblank canonical string")
    return value


def _finite(value: Any, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnDesignDemandEvidenceError(f"{label} must be a finite decimal scalar")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        try:
            decimal = Decimal(str(value))
        except InvalidOperation as exc:
            raise ColumnDesignDemandEvidenceError(f"{label} must be a finite decimal scalar") from exc
        if not decimal.is_finite():
            raise ColumnDesignDemandEvidenceError(f"{label} must be finite")
        result = float(decimal)
    if not math.isfinite(result):
        raise ColumnDesignDemandEvidenceError(f"{label} must be finite")
    return result


def _canonical_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ColumnDesignDemandEvidenceError("evidence scalar must be finite")
        return value
    return str(value)


@dataclass(frozen=True, slots=True)
class ColumnDesignDemandEvidenceBundle:
    model_fingerprint: str
    evidence_epoch_id: str
    output_names: tuple[str, ...]
    force_unit: str
    moment_unit: str
    rows: tuple[Mapping[str, Any], ...]
    source_table: str = "Element Forces - Columns"

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_fingerprint", _text(self.model_fingerprint, "model_fingerprint"))
        object.__setattr__(self, "evidence_epoch_id", _text(self.evidence_epoch_id, "evidence_epoch_id"))
        outputs = tuple(_text(item, "output_name") for item in self.output_names)
        if not outputs or len(outputs) != len(set(outputs)):
            raise ColumnDesignDemandEvidenceError("output_names must be a nonempty unique sequence")
        object.__setattr__(self, "output_names", outputs)
        if self.force_unit != "kN" or self.moment_unit != "kN-m":
            raise ColumnDesignDemandEvidenceError("VS6 initial design-demand evidence requires kN / kN-m")

        expected = set(COLUMN_DESIGN_DEMAND_IDENTITY_FIELDS + COLUMN_DESIGN_DEMAND_PAYLOAD_FIELDS)
        identities: set[tuple[Any, ...]] = set()
        frozen_rows: list[Mapping[str, Any]] = []
        for index, raw in enumerate(self.rows):
            row = dict(raw)
            row.setdefault("StepNumber", None)
            missing = expected - set(row)
            if missing:
                raise ColumnDesignDemandEvidenceError(
                    f"design-demand row {index} missing required field(s): {', '.join(sorted(missing))}"
                )
            for field in COLUMN_DESIGN_DEMAND_PAYLOAD_FIELDS:
                _finite(row.get(field), f"row[{index}].{field}")
            identity = tuple(row.get(field) for field in COLUMN_DESIGN_DEMAND_IDENTITY_FIELDS)
            if identity in identities:
                raise ColumnDesignDemandEvidenceError("duplicate exact column design-demand row identity")
            identities.add(identity)
            frozen_rows.append(MappingProxyType(row))
        if not frozen_rows:
            raise ColumnDesignDemandEvidenceError("design-demand evidence requires at least one row")
        object.__setattr__(self, "rows", tuple(frozen_rows))

    def rows_for_column(self, unique_name: str) -> tuple[Mapping[str, Any], ...]:
        uid = _text(unique_name, "unique_name")
        return tuple(row for row in self.rows if str(row.get("UniqueName")) == uid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifact_type": "VS6_COLUMN_DESIGN_DEMAND_EVIDENCE",
            "model_fingerprint": self.model_fingerprint,
            "evidence_epoch_id": self.evidence_epoch_id,
            "source_table": self.source_table,
            "output_names": list(self.output_names),
            "force_unit": self.force_unit,
            "moment_unit": self.moment_unit,
            "row_count": len(self.rows),
            "rows": [dict(row) for row in self.rows],
        }


def build_column_design_demand_evidence(
    *,
    model_fingerprint: str,
    rows: Sequence[Mapping[str, Any]],
    output_names: Sequence[str],
    reviewed_force_unit: str,
    reviewed_moment_unit: str,
) -> ColumnDesignDemandEvidenceBundle:
    """Bind exact P-M2-M3 result rows into a deterministic VS6 evidence epoch."""
    fingerprint = _text(model_fingerprint, "model_fingerprint")
    outputs = tuple(_text(item, "output_name") for item in output_names)
    if not outputs or len(outputs) != len(set(outputs)):
        raise ColumnDesignDemandEvidenceError("output_names must be a nonempty unique sequence")
    if reviewed_force_unit != "kN" or reviewed_moment_unit != "kN-m":
        raise ColumnDesignDemandEvidenceError("VS6 initial design-demand evidence requires kN / kN-m")

    exact_rows: list[dict[str, Any]] = []
    for raw in rows:
        if raw.get("OutputCase") not in outputs:
            continue
        row = dict(raw)
        row.setdefault("StepNumber", None)
        exact_rows.append(row)
    if not exact_rows:
        raise ColumnDesignDemandEvidenceError("no exact rows remained for reviewed output_names")

    # Construct first so schema, finiteness and duplicate identity are validated
    # before an epoch is accepted.
    provisional = ColumnDesignDemandEvidenceBundle(
        model_fingerprint=fingerprint,
        evidence_epoch_id="epoch:vs6-column-design-demand:pending",
        output_names=outputs,
        force_unit=reviewed_force_unit,
        moment_unit=reviewed_moment_unit,
        rows=tuple(exact_rows),
    )
    canonical_rows = sorted(
        (
            [_canonical_scalar(row.get(field)) for field in COLUMN_DESIGN_DEMAND_IDENTITY_FIELDS]
            + [_finite(row.get(field), field) for field in COLUMN_DESIGN_DEMAND_PAYLOAD_FIELDS]
        )
        for row in provisional.rows
    )
    payload = {
        "model_fingerprint": fingerprint,
        "source_table": provisional.source_table,
        "output_names": list(outputs),
        "force_unit": reviewed_force_unit,
        "moment_unit": reviewed_moment_unit,
        "fields": list(COLUMN_DESIGN_DEMAND_IDENTITY_FIELDS + COLUMN_DESIGN_DEMAND_PAYLOAD_FIELDS),
        "rows": canonical_rows,
    }
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode("utf-8")
    epoch = "epoch:vs6-column-design-demand:sha256:" + hashlib.sha256(encoded).hexdigest()
    return ColumnDesignDemandEvidenceBundle(
        model_fingerprint=fingerprint,
        evidence_epoch_id=epoch,
        output_names=outputs,
        force_unit=reviewed_force_unit,
        moment_unit=reviewed_moment_unit,
        rows=tuple(exact_rows),
    )


__all__ = [
    "COLUMN_DESIGN_DEMAND_IDENTITY_FIELDS",
    "COLUMN_DESIGN_DEMAND_PAYLOAD_FIELDS",
    "ColumnDesignDemandEvidenceBundle",
    "ColumnDesignDemandEvidenceError",
    "build_column_design_demand_evidence",
]
