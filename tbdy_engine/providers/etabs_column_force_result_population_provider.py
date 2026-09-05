"""Session-bound factual result-population proof for B5 analysis execution.

This provider proves only that the canonical ETABS ``Element Forces - Columns``
population exists completely for an exact output case and exact factual column
population.  It does not choose engineering cases, calculate demand, issue
lineage identities, or expose raw SapModel/DatabaseTables capability.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
from types import MappingProxyType
from typing import Any, Mapping

from tbdy_engine.etabs.oapi import (
    fetch_display_table_for_output_from_session,
    fetch_display_table_from_session,
)
from tbdy_engine.etabs.safety import EtabsVerifiedSession, RuntimeCaptureStatus
from tbdy_engine.providers.etabs_display_table_fetcher import DisplayTableFetchResult


TABLE_COLUMN_CONNECTIVITY = "Column Object Connectivity"
TABLE_COLUMN_FORCES = "Element Forces - Columns"

COLUMN_FORCE_RESULT_IDENTITY_FIELDS: tuple[str, ...] = (
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
COLUMN_FORCE_RESULT_PAYLOAD_FIELDS: tuple[str, ...] = (
    "P",
    "V2",
    "V3",
    "T",
    "M2",
    "M3",
)

COLUMN_FORCE_POPULATION_EXPECTATION_CONTRACT = (
    "TBDY_B5_COLUMN_FORCE_POPULATION_EXPECTATION_V1"
)
COLUMN_FORCE_RESULT_POPULATION_CONTRACT = "TBDY_B5_COLUMN_FORCE_RESULT_POPULATION_V1"
COLUMN_FORCE_EXPECTATION_REF_PREFIX = "b5-column-force-expectation:sha256:"
COLUMN_FORCE_POPULATION_REF_PREFIX = "b5-column-force-population:sha256:"


class ColumnForceResultPopulationError(RuntimeError):
    """Fail-closed factual population acquisition/reconciliation error."""


def _text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise ColumnForceResultPopulationError(
            f"{label} must be a nonblank canonical string"
        )
    return value


def _finite(value: object, label: str) -> float:
    if value is None or isinstance(value, bool):
        raise ColumnForceResultPopulationError(f"{label} must be finite numeric")
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, ValueError) as exc:
            raise ColumnForceResultPopulationError(
                f"{label} must be finite numeric"
            ) from exc
        if not number.is_finite():
            raise ColumnForceResultPopulationError(f"{label} must be finite")
        result = float(number)
    if not math.isfinite(result):
        raise ColumnForceResultPopulationError(f"{label} must be finite")
    return result


def _canonical_scalar(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ColumnForceResultPopulationError("result scalar must be finite")
        return value
    return str(value)


def _digest(prefix: str, payload: object) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")
    return prefix + hashlib.sha256(encoded).hexdigest()


def _require_full(fetch: DisplayTableFetchResult, label: str) -> tuple[dict[str, Any], ...]:
    if fetch.capture_status is not RuntimeCaptureStatus.FULL:
        raise ColumnForceResultPopulationError(
            f"{label} requires FULL runtime capture; got {fetch.capture_status.value}"
        )
    if fetch.parsed.return_code not in (None, 0):
        raise ColumnForceResultPopulationError(
            f"{label} returned nonzero code {fetch.parsed.return_code}"
        )
    rows = tuple(dict(row) for row in fetch.parsed.rows)
    reported = fetch.parsed.row_count_reported
    if reported is not None and len(rows) != int(reported):
        raise ColumnForceResultPopulationError(
            f"{label} FULL row mismatch: captured={len(rows)} reported={reported}"
        )
    return rows


def _restore_verified(fetch: DisplayTableFetchResult) -> bool:
    return any(
        item.get("phase") == "restore_verify" and item.get("success") is True
        for item in fetch.state_diagnostics
    )


@dataclass(frozen=True, slots=True)
class ColumnForcePopulationExpectation:
    expected_unique_names: tuple[str, ...]
    source_row_count: int
    evidence_ref: str = field(init=False)
    contract: str = COLUMN_FORCE_POPULATION_EXPECTATION_CONTRACT

    def __post_init__(self) -> None:
        if self.contract != COLUMN_FORCE_POPULATION_EXPECTATION_CONTRACT:
            raise ColumnForceResultPopulationError("expectation contract mismatch")
        names = tuple(sorted(_text(item, "expected_unique_name") for item in self.expected_unique_names))
        if not names:
            raise ColumnForceResultPopulationError(
                "column-force expectation requires at least one factual column"
            )
        if len(set(names)) != len(names):
            raise ColumnForceResultPopulationError(
                "column-force expectation contains duplicate UniqueName"
            )
        if type(self.source_row_count) is not int or self.source_row_count != len(names):
            raise ColumnForceResultPopulationError(
                "column-force expectation row-count accounting mismatch"
            )
        object.__setattr__(self, "expected_unique_names", names)
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                COLUMN_FORCE_EXPECTATION_REF_PREFIX,
                {
                    "contract": self.contract,
                    "source_table": TABLE_COLUMN_CONNECTIVITY,
                    "expected_unique_names": list(names),
                    "source_row_count": self.source_row_count,
                },
            ),
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "source_table": TABLE_COLUMN_CONNECTIVITY,
            "expected_unique_names": list(self.expected_unique_names),
            "source_row_count": self.source_row_count,
            "evidence_ref": self.evidence_ref,
        }


@dataclass(frozen=True, slots=True)
class ColumnForceResultPopulationFact:
    case_name: str
    expectation_ref: str
    expected_unique_names: tuple[str, ...]
    observed_unique_names: tuple[str, ...]
    rows: tuple[Mapping[str, Any], ...]
    evidence_ref: str = field(init=False)
    contract: str = COLUMN_FORCE_RESULT_POPULATION_CONTRACT

    def __post_init__(self) -> None:
        case_name = _text(self.case_name, "case_name")
        expectation_ref = _text(self.expectation_ref, "expectation_ref")
        expected = tuple(sorted(_text(item, "expected_unique_name") for item in self.expected_unique_names))
        observed = tuple(sorted(_text(item, "observed_unique_name") for item in self.observed_unique_names))
        if not expected or len(set(expected)) != len(expected):
            raise ColumnForceResultPopulationError(
                "result population requires a nonempty unique expected column set"
            )
        if len(set(observed)) != len(observed):
            raise ColumnForceResultPopulationError(
                "result population contains duplicate observed column identity"
            )
        if observed != expected:
            missing = tuple(sorted(set(expected) - set(observed)))
            extra = tuple(sorted(set(observed) - set(expected)))
            raise ColumnForceResultPopulationError(
                f"column-force population mismatch for {case_name}: missing={missing} extra={extra}"
            )
        if self.contract != COLUMN_FORCE_RESULT_POPULATION_CONTRACT:
            raise ColumnForceResultPopulationError("result population contract mismatch")

        required = set(COLUMN_FORCE_RESULT_IDENTITY_FIELDS + COLUMN_FORCE_RESULT_PAYLOAD_FIELDS)
        identities: set[tuple[Any, ...]] = set()
        frozen_rows: list[Mapping[str, Any]] = []
        canonical_rows: list[list[Any]] = []
        for index, raw in enumerate(self.rows):
            row = dict(raw)

            # Live ETABS v23.2 "Element Forces - Columns" for LinStatic
            # omits StepType and StepNumber from the table schema entirely.
            # Preserve that factual not-applicable state as None. Do not
            # generalize the compatibility to other case types.
            case_type_raw = row.get("CaseType")
            if (
                isinstance(case_type_raw, str)
                and case_type_raw.strip() == "LinStatic"
                and case_type_raw == case_type_raw.strip()
            ):
                row.setdefault("StepType", None)
                row.setdefault("StepNumber", None)

            missing_fields = required - set(row)
            if missing_fields:
                raise ColumnForceResultPopulationError(
                    f"column-force row {index} missing required field(s): "
                    + ", ".join(sorted(missing_fields))
                )
            _text(row.get("Story"), f"row[{index}].Story")
            _text(row.get("Column"), f"row[{index}].Column")
            _text(row.get("UniqueName"), f"row[{index}].UniqueName")
            _text(row.get("CaseType"), f"row[{index}].CaseType")
            if _text(row.get("OutputCase"), f"row[{index}].OutputCase") != case_name:
                raise ColumnForceResultPopulationError(
                    f"column-force row {index} belongs to wrong OutputCase"
                )
            _finite(row.get("Station"), f"row[{index}].Station")
            _finite(row.get("ElemStation"), f"row[{index}].ElemStation")
            for field_name in COLUMN_FORCE_RESULT_PAYLOAD_FIELDS:
                _finite(row.get(field_name), f"row[{index}].{field_name}")
            identity = tuple(row.get(field) for field in COLUMN_FORCE_RESULT_IDENTITY_FIELDS)
            if identity in identities:
                raise ColumnForceResultPopulationError(
                    "duplicate exact column-force result row identity"
                )
            identities.add(identity)
            frozen_rows.append(MappingProxyType(row))
            canonical_rows.append(
                [
                    *[_canonical_scalar(row.get(field)) for field in COLUMN_FORCE_RESULT_IDENTITY_FIELDS],
                    *[_canonical_scalar(row.get(field)) for field in COLUMN_FORCE_RESULT_PAYLOAD_FIELDS],
                ]
            )
        if not frozen_rows:
            raise ColumnForceResultPopulationError(
                "column-force result population requires at least one exact row"
            )

        object.__setattr__(self, "case_name", case_name)
        object.__setattr__(self, "expectation_ref", expectation_ref)
        object.__setattr__(self, "expected_unique_names", expected)
        object.__setattr__(self, "observed_unique_names", observed)
        object.__setattr__(self, "rows", tuple(frozen_rows))
        object.__setattr__(
            self,
            "evidence_ref",
            _digest(
                COLUMN_FORCE_POPULATION_REF_PREFIX,
                {
                    "contract": self.contract,
                    "source_table": TABLE_COLUMN_FORCES,
                    "case_name": case_name,
                    "expectation_ref": expectation_ref,
                    "expected_unique_names": list(expected),
                    "observed_unique_names": list(observed),
                    "row_count": len(frozen_rows),
                    "fields": list(COLUMN_FORCE_RESULT_IDENTITY_FIELDS + COLUMN_FORCE_RESULT_PAYLOAD_FIELDS),
                    "rows": sorted(canonical_rows, key=lambda row: json.dumps(row, separators=(",", ":"), ensure_ascii=True)),
                },
            ),
        )

    @property
    def row_count(self) -> int:
        return len(self.rows)

    def as_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "source_table": TABLE_COLUMN_FORCES,
            "case_name": self.case_name,
            "expectation_ref": self.expectation_ref,
            "expected_unique_names": list(self.expected_unique_names),
            "observed_unique_names": list(self.observed_unique_names),
            "row_count": self.row_count,
            "evidence_ref": self.evidence_ref,
        }


def capture_column_force_population_expectation_from_session(
    session: EtabsVerifiedSession,
    *,
    timeout_seconds: float = 30.0,
) -> ColumnForcePopulationExpectation:
    """Establish the exact factual ETABS column population before execution."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    fetched = fetch_display_table_from_session(
        session,
        TABLE_COLUMN_CONNECTIVITY,
        max_rows=None,
        timeout_seconds=timeout_seconds,
    )
    rows = _require_full(fetched, TABLE_COLUMN_CONNECTIVITY)
    names = tuple(_text(row.get("UniqueName"), "Column Object Connectivity.UniqueName") for row in rows)
    return ColumnForcePopulationExpectation(
        expected_unique_names=names,
        source_row_count=len(rows),
    )


def capture_column_force_result_population_from_session(
    session: EtabsVerifiedSession,
    *,
    case_name: str,
    expectation: ColumnForcePopulationExpectation,
    timeout_seconds: float = 30.0,
) -> ColumnForceResultPopulationFact:
    """Capture and reconcile one exact post-run column-force result population."""
    if not isinstance(session, EtabsVerifiedSession):
        raise TypeError("session must be EtabsVerifiedSession")
    if not isinstance(expectation, ColumnForcePopulationExpectation):
        raise TypeError("expectation must be ColumnForcePopulationExpectation")
    case = _text(case_name, "case_name")
    fetched = fetch_display_table_for_output_from_session(
        session,
        TABLE_COLUMN_FORCES,
        preferred_output_case=case,
        max_rows=None,
        timeout_seconds=timeout_seconds,
    )
    rows = _require_full(fetched, f"{TABLE_COLUMN_FORCES}@{case}")
    if not _restore_verified(fetched):
        raise ColumnForceResultPopulationError(
            f"{TABLE_COLUMN_FORCES}@{case} output-selection restoration did not verify"
        )
    exact_rows = tuple(row for row in rows if row.get("OutputCase") == case)
    if not exact_rows:
        raise ColumnForceResultPopulationError(
            f"{TABLE_COLUMN_FORCES}@{case} contains no exact OutputCase rows"
        )
    observed = tuple(sorted({
        _text(row.get("UniqueName"), f"{TABLE_COLUMN_FORCES}@{case}.UniqueName")
        for row in exact_rows
    }))
    return ColumnForceResultPopulationFact(
        case_name=case,
        expectation_ref=expectation.evidence_ref,
        expected_unique_names=expectation.expected_unique_names,
        observed_unique_names=observed,
        rows=exact_rows,
    )


__all__ = [
    "COLUMN_FORCE_POPULATION_EXPECTATION_CONTRACT",
    "COLUMN_FORCE_RESULT_IDENTITY_FIELDS",
    "COLUMN_FORCE_RESULT_PAYLOAD_FIELDS",
    "COLUMN_FORCE_RESULT_POPULATION_CONTRACT",
    "ColumnForcePopulationExpectation",
    "ColumnForceResultPopulationError",
    "ColumnForceResultPopulationFact",
    "TABLE_COLUMN_CONNECTIVITY",
    "TABLE_COLUMN_FORCES",
    "capture_column_force_population_expectation_from_session",
    "capture_column_force_result_population_from_session",
]
