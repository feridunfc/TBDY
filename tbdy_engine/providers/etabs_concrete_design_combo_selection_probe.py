"""Read-only Concrete Frame Design selected-combination acquisition.

The exact ETABS 23.2 factual source is the display table
``Concrete Frame Design Load Combination Data`` with raw fields ``ComboType``
and ``ComboName``.  This module owns only factual acquisition.  It does not
judge whether any selected combination is expected, correct, supported, or
governing.

The older schema-probe helper remains diagnostic-only.  Production promotion
uses :func:`acquire_actual_concrete_design_combo_selection`, which requires a
FULL shared display-table capture and fails closed on any schema, row, or
capture-integrity mismatch.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import (
    EtabsSafetyError,
    EtabsSafetyErrorCode,
    RuntimeCaptureStatus,
)
from tbdy_engine.providers.etabs_display_table_fetcher import (
    DisplayTableFetchResult,
    fetch_display_table,
)

TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA = "Concrete Frame Design Load Combination Data"
SOURCE_API_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA = "DatabaseTables.GetTableForDisplayArray"
EXPECTED_SELECTED_COMBO_FIELD_KEYS = ("ComboType", "ComboName")
SOURCE_NOT_PROVEN = "SOURCE_NOT_PROVEN"


@dataclass(frozen=True, slots=True)
class ConcreteDesignComboSelectionTableProbe:
    table_key: str
    return_code: int | None
    capture_status: str
    field_keys: tuple[str, ...]
    row_count: int
    row_count_reported: int | None
    combo_names: tuple[str, ...]
    combo_name_field_present: bool
    combo_type_or_selection_fields: tuple[str, ...]
    automatic_user_defined_fields: tuple[str, ...]
    selected_signature_name: str | None
    source_semantics_status: str = SOURCE_NOT_PROVEN


@dataclass(frozen=True, slots=True)
class ActualSelectedConcreteDesignComboRow:
    """One exact factual row from the proven ETABS selected-combo table."""

    row_id: str
    combo_type: str
    combo_name: str
    source_row_ref: str


@dataclass(frozen=True, slots=True)
class ActualConcreteDesignComboSelectionPopulation:
    """Complete factual ETABS selected-combination population for one epoch."""

    table_key: str
    source_api: str
    field_keys: tuple[str, ...]
    capture_status: RuntimeCaptureStatus
    row_count_reported: int
    rows: tuple[ActualSelectedConcreteDesignComboRow, ...]
    model_fingerprint: str
    evidence_epoch_id: str
    session_provenance_ref: str
    selected_signature_name: str
    source_refs: tuple[str, ...]

    @property
    def capture_complete(self) -> bool:
        return (
            self.capture_status is RuntimeCaptureStatus.FULL
            and self.row_count_reported == len(self.rows)
        )

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(row.combo_name for row in self.rows)


def _fail_closed(message: str, **details: Any) -> None:
    raise EtabsSafetyError(
        message,
        code=EtabsSafetyErrorCode.CAPTURE_INTEGRITY_FAILED,
        details=details,
    )


def _canonical_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        _fail_closed(
            f"{label} must be an exact nonblank string",
            field=label,
            value_repr=repr(value),
        )
    return value


def _row_identity(combo_type: str, combo_name: str) -> str:
    payload = json.dumps(
        {
            "table_key": TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
            "ComboType": combo_type,
            "ComboName": combo_name,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "selected-design-combo-row:sha256:" + hashlib.sha256(payload).hexdigest()


def _population_source_ref(
    *,
    rows: Sequence[ActualSelectedConcreteDesignComboRow],
    model_fingerprint: str,
    evidence_epoch_id: str,
    selected_signature_name: str,
) -> str:
    payload = json.dumps(
        {
            "table_key": TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
            "source_api": SOURCE_API_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
            "field_keys": EXPECTED_SELECTED_COMBO_FIELD_KEYS,
            "model_fingerprint": model_fingerprint,
            "evidence_epoch_id": evidence_epoch_id,
            "selected_signature_name": selected_signature_name,
            "rows": [
                {
                    "row_id": row.row_id,
                    "ComboType": row.combo_type,
                    "ComboName": row.combo_name,
                }
                for row in rows
            ],
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return "selected-design-combo-population:sha256:" + hashlib.sha256(payload).hexdigest()


def build_actual_concrete_design_combo_selection_population(
    fetched: DisplayTableFetchResult,
    *,
    model_fingerprint: str,
    evidence_epoch_id: str,
    session_provenance_ref: str,
) -> ActualConcreteDesignComboSelectionPopulation:
    """Promote one shared display-table fetch into typed factual evidence.

    Promotion is deliberately stricter than generic display-table parsing:
    exactly the reviewed table/schema and a FULL capture are required.  No
    expected-combination policy or engineering interpretation is performed.
    """
    if not isinstance(fetched, DisplayTableFetchResult):
        raise TypeError("fetched must be DisplayTableFetchResult")

    model_ref = _canonical_text(model_fingerprint, "model_fingerprint")
    epoch_ref = _canonical_text(evidence_epoch_id, "evidence_epoch_id")
    session_ref = _canonical_text(session_provenance_ref, "session_provenance_ref")

    if fetched.table_name != TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA:
        _fail_closed(
            "selected design-combo fetch used the wrong table",
            expected_table=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
            fetched_table=fetched.table_name,
        )
    if fetched.parsed.actual_table_name != TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA:
        _fail_closed(
            "selected design-combo parsed table identity does not match the proven source",
            expected_table=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
            actual_table=fetched.parsed.actual_table_name,
        )
    if fetched.capture_status is not RuntimeCaptureStatus.FULL:
        _fail_closed(
            "selected design-combo population requires FULL capture",
            capture_status=fetched.capture_status.value,
        )
    if fetched.parsed.return_code != 0:
        _fail_closed(
            "selected design-combo display-table read did not return exact success",
            return_code=fetched.parsed.return_code,
        )

    field_keys = tuple(str(item) for item in fetched.parsed.field_keys)
    if field_keys != EXPECTED_SELECTED_COMBO_FIELD_KEYS:
        _fail_closed(
            "selected design-combo table schema does not match the reviewed ETABS 23.2 contract",
            expected_field_keys=EXPECTED_SELECTED_COMBO_FIELD_KEYS,
            actual_field_keys=field_keys,
        )

    reported = fetched.parsed.row_count_reported
    if isinstance(reported, bool) or not isinstance(reported, int) or reported < 0:
        _fail_closed(
            "selected design-combo capture has no exact nonnegative reported row count",
            row_count_reported=reported,
        )
    raw_rows = tuple(fetched.parsed.rows)
    if reported != len(raw_rows):
        _fail_closed(
            "selected design-combo reported/captured row counts differ",
            row_count_reported=reported,
            row_count_captured=len(raw_rows),
        )

    selected_signature = dict(fetched.selected_signature)
    signature_name = _canonical_text(
        selected_signature.get("signature_name"),
        "selected_signature_name",
    )

    seen_names: set[str] = set()
    seen_rows: set[tuple[str, str]] = set()
    rows: list[ActualSelectedConcreteDesignComboRow] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, Mapping):
            _fail_closed(
                "selected design-combo row is not a mapping",
                row_repr=repr(raw_row),
            )
        raw_keys = tuple(str(key) for key in raw_row.keys())
        if set(raw_keys) != set(EXPECTED_SELECTED_COMBO_FIELD_KEYS) or len(raw_keys) != 2:
            _fail_closed(
                "selected design-combo row does not contain exactly the reviewed fields",
                expected_field_keys=EXPECTED_SELECTED_COMBO_FIELD_KEYS,
                actual_row_keys=raw_keys,
            )
        combo_type = _canonical_text(raw_row.get("ComboType"), "ComboType")
        combo_name = _canonical_text(raw_row.get("ComboName"), "ComboName")
        pair = (combo_type, combo_name)
        if pair in seen_rows or combo_name in seen_names:
            _fail_closed(
                "selected design-combo table contains duplicate factual rows or names",
                ComboType=combo_type,
                ComboName=combo_name,
            )
        seen_rows.add(pair)
        seen_names.add(combo_name)
        row_id = _row_identity(combo_type, combo_name)
        rows.append(
            ActualSelectedConcreteDesignComboRow(
                row_id=row_id,
                combo_type=combo_type,
                combo_name=combo_name,
                source_row_ref=(
                    f"CSI:{SOURCE_API_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA}:"
                    f"{TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA}:row:{row_id}"
                ),
            )
        )

    deterministic_rows = tuple(sorted(rows, key=lambda row: (row.combo_name, row.combo_type)))
    population_ref = _population_source_ref(
        rows=deterministic_rows,
        model_fingerprint=model_ref,
        evidence_epoch_id=epoch_ref,
        selected_signature_name=signature_name,
    )
    source_refs = tuple(
        dict.fromkeys(
            (
                session_ref,
                population_ref,
                *(row.source_row_ref for row in deterministic_rows),
            )
        )
    )
    return ActualConcreteDesignComboSelectionPopulation(
        table_key=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        source_api=SOURCE_API_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        field_keys=field_keys,
        capture_status=fetched.capture_status,
        row_count_reported=reported,
        rows=deterministic_rows,
        model_fingerprint=model_ref,
        evidence_epoch_id=epoch_ref,
        session_provenance_ref=session_ref,
        selected_signature_name=signature_name,
        source_refs=source_refs,
    )


def acquire_actual_concrete_design_combo_selection(
    database_tables: Any,
    *,
    model_fingerprint: str,
    evidence_epoch_id: str,
    session_provenance_ref: str,
) -> ActualConcreteDesignComboSelectionPopulation:
    """Read the full proven selected-combo table without ETABS mutation."""
    fetched = fetch_display_table(
        database_tables,
        TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        max_rows=None,
    )
    return build_actual_concrete_design_combo_selection_population(
        fetched,
        model_fingerprint=model_fingerprint,
        evidence_epoch_id=evidence_epoch_id,
        session_provenance_ref=session_provenance_ref,
    )


def probe_concrete_frame_design_combo_selection_table(database_tables: Any) -> ConcreteDesignComboSelectionTableProbe:
    fetched = fetch_display_table(
        database_tables,
        TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        max_rows=None,
    )
    fields = tuple(str(item) for item in fetched.parsed.field_keys)
    field_set = set(fields)
    names = tuple(sorted({
        str(row.get("ComboName"))
        for row in fetched.parsed.rows
        if isinstance(row.get("ComboName"), str) and str(row.get("ComboName")).strip()
    })) if "ComboName" in field_set else ()
    selected_signature = dict(fetched.selected_signature)
    return ConcreteDesignComboSelectionTableProbe(
        table_key=TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA,
        return_code=fetched.parsed.return_code,
        capture_status=fetched.capture_status.value,
        field_keys=fields,
        row_count=len(fetched.parsed.rows),
        row_count_reported=fetched.parsed.row_count_reported,
        combo_names=names,
        combo_name_field_present="ComboName" in field_set,
        combo_type_or_selection_fields=tuple(
            key for key in fields if "combo" in key.lower() or "type" in key.lower() or "select" in key.lower()
        ),
        automatic_user_defined_fields=tuple(
            key for key in fields if "auto" in key.lower() or "user" in key.lower() or "design" in key.lower()
        ),
        selected_signature_name=(
            str(selected_signature.get("signature_name"))
            if selected_signature.get("signature_name") is not None else None
        ),
    )


__all__ = [
    "ActualConcreteDesignComboSelectionPopulation",
    "ActualSelectedConcreteDesignComboRow",
    "ConcreteDesignComboSelectionTableProbe",
    "EXPECTED_SELECTED_COMBO_FIELD_KEYS",
    "SOURCE_API_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA",
    "SOURCE_NOT_PROVEN",
    "TABLE_CONCRETE_FRAME_DESIGN_LOAD_COMBINATION_DATA",
    "acquire_actual_concrete_design_combo_selection",
    "build_actual_concrete_design_combo_selection_population",
    "probe_concrete_frame_design_combo_selection_table",
]
