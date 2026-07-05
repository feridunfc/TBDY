"""Shared source-table evidence helpers for live FeatureResolver smoke paths.

This module is intentionally small and data-only.  It normalizes evidence that
is already fetched by the existing ETABS display-table/provider path; it does
not fetch ETABS data, resolve features, execute checks, or emit engineering
verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.json_safe import to_jsonable


@dataclass(frozen=True, slots=True)
class SourceTableRowEvidence:
    """Deterministic source-row evidence shape shared by resolver features."""

    table_key: str
    actual_table_name: str | None
    source_kind: str | None
    source_column: str | None
    row_index: int | None
    stable_row_reference: Any
    reported_row_count: int | None
    resolver_row_count: int
    parser_status: Any
    selection_reason: str
    complete_source_row: Mapping[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "source_kind": self.source_kind,
            "source_table": self.table_key,
            "actual_table_name": self.actual_table_name,
            "source_column": self.source_column,
            "row_index": self.row_index,
            "stable_row_reference": self.stable_row_reference,
            "reported_row_count": self.reported_row_count,
            "resolver_row_count": self.resolver_row_count,
            "parser_status": self.parser_status,
            "selection_reason": self.selection_reason,
            "complete_source_row": dict(self.complete_source_row),
        }


def int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def raw_table_diagnostics_from_table(table: CanonicalTable | None) -> dict[str, Any]:
    """Return the stable raw diagnostics shape used by source evidence.

    The function preserves the existing resolver diagnostics contract while
    making the shape reusable outside ``live_smoke.py``.
    """
    if table is None:
        return {
            "table_name": None,
            "return_code": None,
            "number_fields": 0,
            "number_records": 0,
            "fields": [],
            "table_data_length": 0,
            "expected_flat_length": None,
            "parser_status": "TABLE_MISSING",
        }
    raw = table.units.get("raw_table_diagnostics") if isinstance(table.units, Mapping) else None
    if isinstance(raw, Mapping):
        out = dict(raw)
        out.setdefault("header_count", len(table.columns))
        if out.get("number_fields_source") == "ambiguous":
            out["number_fields"] = None
            out["number_fields_detected"] = None
        else:
            out.setdefault("number_fields_detected", out.get("number_fields"))
            out.setdefault("number_fields_source", "raw_table_diagnostics")
        out.setdefault("signature_attempts", [])
        out.setdefault("selected_signature", {})
        out.setdefault("selected_signature_reason", None)
        out.setdefault("parser_status_by_signature", {})
        out.setdefault("table_data_length_by_signature", {})
        out.setdefault("number_records_by_signature", {})
        out.setdefault("preferred_output_kind_detected", "unknown")
        out.setdefault("attempted_case_fallback", False)
        out.setdefault("skipped_case_selection_because_combo_succeeded", False)
        out.setdefault("display_selection_attempted", False)
        out.setdefault("display_selection_attempts", [])
        out.setdefault("display_selection_selected_method", None)
        out.setdefault("display_selection_success", False)
        out.setdefault("fetch_after_display_selection", False)
        return to_jsonable(out)
    return {
        "table_name": table.actual_table_name,
        "return_code": None,
        "number_fields": len(table.columns),
        "number_records": len(table.rows),
        "fields": list(table.columns),
        "table_data_length": len(table.rows) * len(table.columns),
        "expected_flat_length": len(table.rows) * len(table.columns),
        "parser_status": "FETCHED" if table.rows else "EMPTY",
    }


def row_index(table: CanonicalTable | None, row: Mapping[str, Any] | None) -> int | None:
    if table is None or row is None:
        return None
    for index, candidate in enumerate(table.rows):
        if candidate is row or dict(candidate) == dict(row):
            return index
    return None


def stable_row_reference(table_key: str, table: CanonicalTable | None, row: Mapping[str, Any] | None) -> str | None:
    index = row_index(table, row)
    if index is None:
        return None
    actual = table.actual_table_name if table else table_key
    return f"{table_key}|actual={actual}|row_index={index}"


def stable_row_reference_object(
    table_key: str,
    table: CanonicalTable | None,
    row: Mapping[str, Any] | None,
    *,
    identity_fields: Sequence[str] = (),
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "table_key": table_key,
        "actual_table_name": table.actual_table_name if table else None,
        "row_index": row_index(table, row),
    }
    if row:
        for field in identity_fields:
            value = row.get(field)
            if value not in (None, ""):
                payload[field.casefold()] = value
    return payload


def source_reference(
    source_kind: str,
    table_key: str,
    table: CanonicalTable | None,
    row: Mapping[str, Any] | None,
    *,
    column: str | None = None,
    identity_fields: Sequence[str] = (),
) -> str:
    actual = table.actual_table_name if table else table_key
    index = row_index(table, row)
    parts = [source_kind, str(actual or table_key), f"row={index if index is not None else 'unresolved'}"]
    if row:
        for field in identity_fields:
            value = row.get(field)
            if value not in (None, ""):
                parts.append(f"{field.casefold()}={value}")
    if column:
        parts.append(f"column={column}")
    return ":".join(parts)


def source_row_evidence(
    table_key: str,
    table: CanonicalTable | None,
    row: Mapping[str, Any] | None,
    *,
    source_column: str | None,
    selection_reason: str,
    stable_reference: Any | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    raw = raw_table_diagnostics_from_table(table)
    payload = SourceTableRowEvidence(
        table_key=table_key,
        actual_table_name=table.actual_table_name if table else None,
        source_kind=table.source if table else None,
        source_column=source_column,
        row_index=row_index(table, row),
        stable_row_reference=stable_reference if stable_reference is not None else stable_row_reference(table_key, table, row),
        reported_row_count=int_or_none(raw.get("number_records")),
        resolver_row_count=len(table.rows) if table else 0,
        parser_status=raw.get("parser_status"),
        selection_reason=selection_reason,
        complete_source_row=to_jsonable(dict(row or {})),
    ).as_dict()
    if extra:
        payload.update(to_jsonable(dict(extra)))
    return {key: value for key, value in payload.items() if value is not None}


def table_fetch_evidence(table_key: str, table: CanonicalTable | None) -> dict[str, Any]:
    raw = raw_table_diagnostics_from_table(table)
    return {
        "table_key": table_key,
        "actual_table_name": table.actual_table_name if table else None,
        "source_kind": table.source if table else None,
        "columns": list(table.columns) if table else [],
        "row_count": len(table.rows) if table else 0,
        "reported_row_count": int_or_none(raw.get("number_records")),
        "parser_status": raw.get("parser_status"),
        "raw_table_diagnostics": to_jsonable(raw),
    }
