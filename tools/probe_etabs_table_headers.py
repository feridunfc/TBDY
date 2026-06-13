#!/usr/bin/env python
"""Manual/local ETABS display-table header and small-sample probe.

This script is opt-in only. It is import-safe without ETABS/comtypes installed
and is intended to be run manually on a Windows machine with ETABS already open.
It never starts ETABS, never modifies the model, never runs design, never runs
checks, never emits CheckResult, never emits OK/FAIL, and never computes ratios.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from tbdy_engine.audit.etabs_table_fit import EtabsTableFitAuditor
from tbdy_engine.canonical_tables.table import CanonicalTable
from tbdy_engine.contracts.loader import load_contracts
from tbdy_engine.providers.table_registry import TableRegistry, normalize_table_name

DEFAULT_TABLE_WHITELIST: tuple[str, ...] = (
    "Story Definitions",
    "Story Drifts",
    "Story Max Over Avg Drifts",
    "Modal Participating Mass Ratios",
    "Base Reactions",
    "Frame Assignments - Summary",
    "Frame Section Property Definitions - Concrete Rectangular",
    "Frame Section Property Definitions - Concrete Beam Reinforcing",
    "Frame Section Property Definitions - Concrete Column Reinforcing",
    "Concrete Beam Design Summary - TS 500-2000(R2018)",
    "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
    "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
    "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
    "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
    "Concrete Column Design Summary - TS 500-2000(R2018)",
    "Concrete Column PMM Envelope - TS 500-2000(R2018)",
    "Concrete Column Shear Envelope - TS 500-2000(R2018)",
    "Concrete Column Shear Envelope -  TS 500-2000(R2018)",
    "Load Combination Definitions",
    "Concrete Frame Design Load Combination Data",
    "Load Pattern Definitions - Auto Seismic - TSC 2018",
    "Material Properties - Concrete Data",
    "Material Properties - Rebar Data",
    "Material Properties - Basic Mechanical Properties",
    "Material Properties - General",
    "Pier Section Properties",
    "Pier Forces",
    "Shear Wall Pier Design Summary - TS 500-2000(R2018)",
)

TABLE_GROUPS: Mapping[str, tuple[str, ...]] = {
    "story": (
        "Story Definitions",
        "Story Drifts",
        "Story Max Over Avg Drifts",
    ),
    "beam": (
        "Frame Assignments - Summary",
        "Frame Section Property Definitions - Concrete Rectangular",
        "Frame Section Property Definitions - Concrete Beam Reinforcing",
        "Concrete Beam Design Summary - TS 500-2000(R2018)",
        "Concrete Beam Flexure Envelope - TS 500-2000(R2018)",
        "Concrete Beam Flexure Envelope -  TS 500-2000(R2018)",
        "Concrete Beam Shear Envelope - TS 500-2000(R2018)",
        "Concrete Beam Shear Envelope -  TS 500-2000(R2018)",
    ),
    "column": (
        "Frame Assignments - Summary",
        "Frame Section Property Definitions - Concrete Rectangular",
        "Frame Section Property Definitions - Concrete Column Reinforcing",
        "Concrete Column Design Summary - TS 500-2000(R2018)",
        "Concrete Column PMM Envelope - TS 500-2000(R2018)",
        "Concrete Column Shear Envelope - TS 500-2000(R2018)",
        "Concrete Column Shear Envelope -  TS 500-2000(R2018)",
    ),
    "wall": (
        "Pier Section Properties",
        "Pier Forces",
        "Shear Wall Pier Design Summary - TS 500-2000(R2018)",
    ),
    "global": (
        "Modal Participating Mass Ratios",
        "Base Reactions",
        "Load Combination Definitions",
        "Concrete Frame Design Load Combination Data",
        "Load Pattern Definitions - Auto Seismic - TSC 2018",
        "Material Properties - Concrete Data",
        "Material Properties - Rebar Data",
        "Material Properties - Basic Mechanical Properties",
        "Material Properties - General",
    ),
}

_COMBO_COLUMNS_EXACT = {
    "outputcase",
    "output case",
    "combo",
    "designcombo",
    "design combo",
    "loadcombo",
    "load combo",
    "load combination",
    "astopcombo",
    "asbotcombo",
    "vcombo",
    "pmmcombo",
    "vmajcombo",
    "vmincombo",
}
_NON_COMBO_MARKERS = {"max", "combination", "min", "avg", "absolute max", "absolute min"}
_FORBIDDEN_STATUS_VALUES = {"OK", "FAIL"}


@dataclass(frozen=True, slots=True)
class ParsedDisplayTable:
    actual_table_name: str
    fetch_status: str
    field_keys: tuple[str, ...] = field(default_factory=tuple)
    rows: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    row_count_reported: int = 0
    return_code: int | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    debug: Mapping[str, Any] = field(default_factory=dict)

    def header_payload(self, registry: TableRegistry) -> dict[str, Any]:
        canonical = registry.canonical_key_for_alias(self.actual_table_name)
        return {
            "actual_table_name": self.actual_table_name,
            "canonical_table_key": canonical,
            "fetch_status": self.fetch_status,
            "field_keys": list(self.field_keys),
            "headers": list(self.field_keys),
            "column_count": len(self.field_keys),
            "row_count_reported": self.row_count_reported,
            "sample_row_count": len(self.rows),
            "sample_rows_limited": [dict(r) for r in self.rows],
            "diagnostics": [dict(d) for d in self.diagnostics],
            "raw_table_diagnostics": {
                "table_name": self.actual_table_name,
                "return_code": self.return_code,
                "number_fields": self.debug.get("number_fields"),
                "number_records": self.debug.get("number_records"),
                "fields": list(self.field_keys),
                "table_data_length": self.debug.get("table_data_length"),
                "expected_flat_length": self.debug.get("expected_flat_length"),
                "parser_status": self.debug.get("row_parse_status", self.fetch_status),
            },
        }


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _safe_value(value: Any) -> Any:
    if isinstance(value, str) and value.strip().upper() in _FORBIDDEN_STATUS_VALUES:
        return "[REDACTED_STATUS_VALUE]"
    return value


def _split_field_string(value: str) -> tuple[str, ...]:
    text = value.strip()
    if not text:
        return tuple()
    delimiter = "\t" if "\t" in text else "," if "," in text else None
    if delimiter is None:
        return (text,)
    return tuple(part.strip() for part in text.split(delimiter) if part.strip())


def _is_string_sequence(value: Any) -> bool:
    return isinstance(value, (list, tuple)) and all(isinstance(x, str) for x in value)


def _as_string_tuple(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return _split_field_string(value)
    if _is_string_sequence(value):
        return tuple(str(x) for x in value)
    return tuple()


def _extract_mapping_shape(result: Mapping[str, Any]) -> tuple[int | None, tuple[str, ...], Any, int | None, int | None]:
    ret = result.get("return_code", result.get("ret", result.get("returnCode")))
    return_code = int(ret) if isinstance(ret, int) else None
    field_keys = _as_string_tuple(result.get("field_keys") or result.get("headers") or result.get("fields") or result.get("fieldKeys"))
    table_data = result.get("table_data", result.get("data", result.get("rows", result.get("tableData"))))
    number_fields = result.get("number_fields", result.get("numberFields", result.get("NumberFields")))
    number_records = result.get("number_records", result.get("numberRecords", result.get("NumberRecords")))
    return (
        return_code,
        field_keys,
        table_data,
        int(number_fields) if isinstance(number_fields, int) else None,
        int(number_records) if isinstance(number_records, int) else None,
    )


def _extract_sequence_shape(result: Sequence[Any]) -> tuple[int | None, tuple[str, ...], Any, int | None, int | None, dict[str, Any]]:
    debug: dict[str, Any] = {"sequence_length": len(result)}
    return_code: int | None = None
    if result and isinstance(result[-1], int) and result[-1] in {0, 1, -1}:
        return_code = int(result[-1])
    elif result and isinstance(result[0], int) and result[0] in {0, 1, -1}:
        return_code = int(result[0])

    number_fields: int | None = None
    number_records: int | None = None
    for item in result:
        if isinstance(item, int) and item != return_code:
            if number_fields is None:
                number_fields = item
            elif number_records is None:
                number_records = item
                break

    string_seqs = [tuple(str(x) for x in item) for item in result if _is_string_sequence(item)]
    string_scalars = [_split_field_string(item) for item in result if isinstance(item, str) and ("," in item or "\t" in item)]
    candidates = [seq for seq in string_seqs + string_scalars if seq]
    field_keys: tuple[str, ...] = tuple()
    table_data: Any = tuple()
    if candidates:
        if number_fields:
            matching = [seq for seq in candidates if len(seq) == number_fields]
            field_keys = matching[0] if matching else min(candidates, key=len)
        else:
            field_keys = min(candidates, key=len)
        remaining = [seq for seq in candidates if seq != field_keys]
        table_data = max(remaining, key=len) if remaining else tuple()
    two_d = [item for item in result if isinstance(item, (list, tuple)) and item and all(isinstance(row, (list, tuple, Mapping)) for row in item)]
    if two_d and not table_data:
        table_data = two_d[0]
    debug.update({"candidate_string_sequences": len(candidates), "return_code_guess": return_code})
    return return_code, field_keys, table_data, number_fields, number_records, debug


def _table_data_length(table_data: Any) -> int | None:
    if table_data is None:
        return 0
    if isinstance(table_data, str):
        return len(_split_field_string(table_data))
    if isinstance(table_data, (list, tuple)):
        return len(table_data)
    return None


def _is_2d_rows(table_data: Any) -> bool:
    return isinstance(table_data, (list, tuple)) and bool(table_data) and all(isinstance(row, (list, tuple, Mapping)) for row in table_data)


def _rows_from_data(
    table_data: Any,
    field_keys: tuple[str, ...],
    number_records: int | None,
    max_rows: int,
    debug: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> tuple[tuple[Mapping[str, Any], ...], str]:
    """Return parsed rows and row_parse_status.

    ETABS metadata can report an unreliable number_fields value. Row chunking is
    therefore based only on the parsed header count. If flat data does not align
    with headers, this function returns no sample rows and records a
    ROW_PARSE_PARTIAL diagnostic instead of fabricating misaligned rows.
    """
    header_count = len(field_keys)
    data_length = _table_data_length(table_data)
    expected_flat_length = (number_records * header_count) if isinstance(number_records, int) and header_count else None
    debug.update({
        "header_count": header_count,
        "table_data_length": data_length,
        "expected_flat_length": expected_flat_length,
        "row_parse_status": "NOT_PARSED",
        "mismatch_reason": None,
    })
    if table_data is None or data_length == 0:
        reason = "no_table_data" if not number_records else "no_table_data_with_reported_records"
        debug.update({"row_parse_status": "EMPTY", "mismatch_reason": reason if number_records else None})
        diagnostics.append({"severity": "INFO", "code": "TABLE_EMPTY", "message": "No sample rows parsed from display table response", "details": {"mismatch_reason": reason}})
        return tuple(), "EMPTY"
    if header_count <= 0:
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": "headers_missing"})
        diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "Cannot parse rows because headers are missing", "details": {"mismatch_reason": "headers_missing"}})
        return tuple(), "ROW_PARSE_PARTIAL"

    if isinstance(table_data, (list, tuple)) and table_data and all(isinstance(row, Mapping) for row in table_data):
        rows = tuple({str(k): _safe_value(v) for k, v in dict(row).items()} for row in table_data[:max_rows])
        debug["row_parse_status"] = "FETCHED" if rows else "EMPTY"
        return rows, debug["row_parse_status"]

    if _is_2d_rows(table_data):
        parsed_rows: list[Mapping[str, Any]] = []
        for row in table_data:
            if isinstance(row, Mapping):
                parsed_rows.append({str(k): _safe_value(v) for k, v in dict(row).items()})
                continue
            if len(row) != header_count:
                reason = f"2d_row_width_mismatch:{len(row)}!={header_count}"
                debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
                diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "2D table row width does not match header count", "details": {"mismatch_reason": reason}})
                return tuple(), "ROW_PARSE_PARTIAL"
            parsed_rows.append({field_keys[i]: _safe_value(row[i]) for i in range(header_count)})
            if len(parsed_rows) >= max_rows:
                break
        debug["row_parse_status"] = "FETCHED" if parsed_rows else "EMPTY"
        return tuple(parsed_rows), debug["row_parse_status"]

    if isinstance(table_data, str):
        flat: tuple[Any, ...] = _split_field_string(table_data)
    elif isinstance(table_data, (list, tuple)):
        flat = tuple(table_data)
    else:
        reason = f"unsupported_table_data_type:{type(table_data).__name__}"
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
        diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "Unsupported table data shape", "details": {"mismatch_reason": reason}})
        return tuple(), "ROW_PARSE_PARTIAL"

    flat_len = len(flat)
    debug["table_data_length"] = flat_len
    if expected_flat_length is not None and flat_len != expected_flat_length:
        reason = f"flat_length_mismatch:{flat_len}!={expected_flat_length}"
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
        diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "Flat table data length does not match number_records * header_count", "details": {"table_data_length": flat_len, "expected_flat_length": expected_flat_length, "mismatch_reason": reason}})
        return tuple(), "ROW_PARSE_PARTIAL"
    if flat_len % header_count != 0:
        reason = f"flat_length_not_divisible_by_header_count:{flat_len}%{header_count}"
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
        diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "Flat table data length does not align with header count", "details": {"table_data_length": flat_len, "header_count": header_count, "mismatch_reason": reason}})
        return tuple(), "ROW_PARSE_PARTIAL"

    rows = []
    for start in range(0, flat_len, header_count):
        if len(rows) >= max_rows:
            break
        chunk = flat[start : start + header_count]
        rows.append({field_keys[i]: _safe_value(chunk[i]) for i in range(header_count)})
    if not rows:
        debug.update({"row_parse_status": "EMPTY", "mismatch_reason": "no_sample_rows_after_chunking"})
        diagnostics.append({"severity": "INFO", "code": "TABLE_EMPTY", "message": "No sample rows parsed from display table response"})
        return tuple(), "EMPTY"
    debug["row_parse_status"] = "FETCHED"
    return tuple(rows), "FETCHED"


def parse_etabs_display_table_result(result: Any, *, actual_table_name: str = "UNKNOWN_TABLE", max_rows: int = 3) -> ParsedDisplayTable:
    """Parse ETABS GetTableForDisplayArray result defensively.

    Handles mapping-shaped test payloads, list/tuple field keys, comma/tab string
    field keys, flat table data, 2D table data, empty data, failed return codes,
    and malformed shapes without raising.
    """
    diagnostics: list[dict[str, Any]] = []
    debug: dict[str, Any] = {"actual_table_name": actual_table_name, "api_method": "GetTableForDisplayArray"}
    try:
        if isinstance(result, Mapping):
            return_code, field_keys, table_data, number_fields, number_records = _extract_mapping_shape(result)
            debug["return_shape_metadata"] = "mapping"
        elif isinstance(result, (list, tuple)):
            return_code, field_keys, table_data, number_fields, number_records, seq_debug = _extract_sequence_shape(result)
            debug.update(seq_debug)
            debug["return_shape_metadata"] = "sequence"
        else:
            diagnostics.append({"severity": "WARNING", "code": "MALFORMED_SHAPE", "message": "Display-table result was not a mapping or sequence"})
            debug.update({"return_shape_metadata": type(result).__name__, "parse_error": "unsupported result shape"})
            return ParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", diagnostics=tuple(diagnostics), debug=debug)

        debug.update({
            "return_code": return_code,
            "number_fields": number_fields,
            "number_records": number_records,
            "field_keys_type": type(field_keys).__name__,
            "table_data_type": type(table_data).__name__,
            "table_data_length": _table_data_length(table_data),
            "header_count": len(field_keys),
            "expected_flat_length": (number_records * len(field_keys)) if isinstance(number_records, int) and field_keys else None,
        })
        if return_code not in {None, 0}:
            diagnostics.append({"severity": "ERROR", "code": "TABLE_FETCH_FAILED", "message": "GetTableForDisplayArray returned nonzero return code", "details": {"return_code": return_code}})
            return ParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", return_code=return_code, diagnostics=tuple(diagnostics), debug=debug)
        if not field_keys:
            diagnostics.append({"severity": "WARNING", "code": "HEADERS_MISSING", "message": "No field keys/headers could be parsed from ETABS response"})
        rows, row_parse_status = _rows_from_data(table_data, field_keys, number_records, max_rows, debug, diagnostics)
        status = row_parse_status
        reported = int(number_records) if isinstance(number_records, int) else len(rows)
        return ParsedDisplayTable(
            actual_table_name=actual_table_name,
            fetch_status=status,
            field_keys=field_keys,
            rows=rows,
            row_count_reported=reported,
            return_code=return_code,
            diagnostics=tuple(diagnostics),
            debug={**debug, "parse_strategy_used": "defensive_display_array_parser"},
        )
    except Exception as exc:
        diagnostics.append({"severity": "ERROR", "code": "PARSE_ERROR", "message": "Display-table response parse failed; continuing with next table", "details": {"error": str(exc)}})
        debug["parse_error"] = str(exc)
        return ParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", diagnostics=tuple(diagnostics), debug=debug)


def parse_available_tables_result(result: Any) -> tuple[str, ...]:
    names: list[str] = []
    if isinstance(result, Mapping):
        candidate = result.get("tables") or result.get("available_tables") or result.get("table_names")
        return parse_available_tables_result(candidate)
    if isinstance(result, (list, tuple)):
        for item in result:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, (list, tuple)):
                names.extend(str(x) for x in item if isinstance(x, str))
    return tuple(sorted(dict.fromkeys(names)))


def selected_whitelist(groups: str | None) -> tuple[str, ...]:
    if not groups:
        return DEFAULT_TABLE_WHITELIST
    selected: list[str] = []
    for token in (part.strip() for part in groups.split(",") if part.strip()):
        selected.extend(TABLE_GROUPS.get(token, (token,)))
    return tuple(dict.fromkeys(selected))


def _table_is_available(target: str, available: Iterable[str]) -> str | None:
    normalized_target = normalize_table_name(target)
    for actual in available:
        if normalize_table_name(actual) == normalized_target:
            return actual
    return None


def _try_get_display_table(database_tables: Any, table_name: str) -> Any:
    """Try known read-only ETABS GetTableForDisplayArray signatures.

    Backward-compatible raw response helper.  The shared engine fetcher owns the
    actual signature probing and continues past return_code=0 responses that
    contain headers/records but empty TableData.
    """
    from tbdy_engine.providers.etabs_display_table_fetcher import try_get_display_table

    return try_get_display_table(database_tables, table_name, max_rows=None)


def _canonical_tables_from_probe(parsed: Sequence[ParsedDisplayTable], registry: TableRegistry) -> tuple[CanonicalTable, ...]:
    tables: list[CanonicalTable] = []
    for item in parsed:
        canonical = registry.canonical_key_for_alias(item.actual_table_name) or item.actual_table_name
        tables.append(
            CanonicalTable(
                table_key=canonical,
                actual_table_name=item.actual_table_name,
                columns=item.field_keys,
                rows=tuple(dict(row) for row in item.rows),
                units={},
                source="ETABS_TABLE_HEADER_PROBE",
            )
        )
    return tuple(tables)


def _combo_probe_report(parsed: Sequence[ParsedDisplayTable], auditor: EtabsTableFitAuditor) -> list[dict[str, Any]]:
    reports = [r.as_dict() for r in auditor.combo_family_fit()]
    if reports:
        return reports
    rows: list[dict[str, Any]] = []
    for table in parsed:
        for col in table.field_keys:
            col_norm_spaced = re.sub(r"[_\s]+", " ", col).strip().casefold()
            col_norm = col_norm_spaced.replace(" ", "")
            is_combo_col = col_norm in {x.replace(" ", "") for x in _COMBO_COLUMNS_EXACT} or (col_norm == "case" and "modal" in table.actual_table_name.casefold())
            if not is_combo_col:
                continue
            for sample in table.rows:
                if col not in sample:
                    continue
                raw_value = sample[col]
                raw_text = str(raw_value).strip()
                if not raw_text or raw_text.casefold() in _NON_COMBO_MARKERS:
                    continue
                try:
                    float(raw_text)
                    continue
                except ValueError:
                    pass
                rows.append({
                    "table_name": table.actual_table_name,
                    "column_name": col,
                    "raw_value": raw_value,
                    "matched_combo_family": None,
                    "status": "UNKNOWN",
                    "diagnostics": [{"severity": "WARNING", "code": "COMBO_POLICY_NOT_MATCHED", "message": "Combo-like value found but did not match policy in sample audit"}],
                })
    return rows


def write_probe_outputs(out_dir: Path, parsed: Sequence[ParsedDisplayTable], registry: TableRegistry, auditor: EtabsTableFitAuditor) -> None:
    _write_json(out_dir / "table_headers_report.json", [item.header_payload(registry) for item in parsed])
    _write_json(out_dir / "raw_table_call_debug.json", [dict(item.debug, actual_table_name=item.actual_table_name, fetch_status=item.fetch_status) for item in parsed])
    _write_json(out_dir / "column_alias_fit_report.json", [r.as_dict() for r in auditor.table_contract_fit()])
    _write_json(out_dir / "feature_column_fit_report.json", [r.as_dict() for r in auditor.feature_source_fit()])
    _write_json(out_dir / "identity_column_fit_report.json", [r.as_dict() for r in auditor.element_identity_fit()])
    _write_json(out_dir / "combo_column_probe_report.json", _combo_probe_report(parsed, auditor))


def _write_graceful_unavailable(out_dir: Path, message: str) -> int:
    diagnostic = {"severity": "WARNING", "code": "ETABS_UNAVAILABLE", "message": message, "manual_local_only": True}
    for name, payload in {
        "table_headers_report.json": [],
        "raw_table_call_debug.json": [{"diagnostics": [diagnostic]}],
        "column_alias_fit_report.json": [],
        "feature_column_fit_report.json": [],
        "identity_column_fit_report.json": [],
        "combo_column_probe_report.json": [],
    }.items():
        _write_json(out_dir / name, payload)
    print(message)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Manual ETABS table header/sample probe. Does not run checks.")
    parser.add_argument("--out", default="local_out/etabs_table_probe", help="Output directory")
    parser.add_argument("--tables", default=None, help="Comma-separated groups (story,beam,column,wall,global) or exact table names")
    parser.add_argument("--max-rows", type=int, default=3, help="Maximum sample rows per table")
    parser.add_argument("--raw-debug", action="store_true", help="Keep raw call metadata diagnostics")
    parser.add_argument("--include-unmatched", default="false", choices=("true", "false"), help="Probe available tables outside whitelist")
    args = parser.parse_args(argv)
    out_dir = Path(args.out)

    try:
        try:
            import comtypes.client  # type: ignore[import-not-found]
        except Exception as exc:  # pragma: no cover - depends on local Windows/ETABS
            return _write_graceful_unavailable(out_dir, f"ETABS COM/comtypes unavailable; table probe not run: {exc}")

        try:  # pragma: no cover - depends on local Windows/ETABS
            etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
            sap_model = etabs_object.SapModel
            database_tables = sap_model.DatabaseTables
        except Exception as exc:
            return _write_graceful_unavailable(out_dir, f"Could not attach to an open ETABS model: {exc}")

        try:  # pragma: no cover - depends on local Windows/ETABS
            available = parse_available_tables_result(database_tables.GetAvailableTables())
        except Exception as exc:
            return _write_graceful_unavailable(out_dir, f"ETABS available-table query failed: {exc}")

        bundle = load_contracts()
        registry = TableRegistry.from_dict(bundle.catalog("table_registry.yaml"))
        whitelist = list(selected_whitelist(args.tables))
        if args.include_unmatched == "true":
            whitelist.extend(x for x in available if x not in whitelist)

        parsed: list[ParsedDisplayTable] = []
        for requested in dict.fromkeys(whitelist):
            actual = _table_is_available(requested, available)
            if not actual:
                parsed.append(
                    ParsedDisplayTable(
                        actual_table_name=requested,
                        fetch_status="NOT_AVAILABLE",
                        diagnostics=({"severity": "WARNING", "code": "TABLE_NOT_AVAILABLE", "message": "Requested display table was not listed by ETABS"},),
                        debug={"actual_table_name": requested, "api_method": "GetTableForDisplayArray", "return_code": None},
                    )
                )
                continue
            result = _try_get_display_table(database_tables, actual)
            parsed.append(parse_etabs_display_table_result(result, actual_table_name=actual, max_rows=max(0, args.max_rows)))

        canonical_tables = _canonical_tables_from_probe(parsed, registry)
        auditor = EtabsTableFitAuditor(bundle, canonical_tables)
        write_probe_outputs(out_dir, parsed, registry, auditor)
        print(f"Wrote ETABS table header probe outputs to {out_dir}")
        return 0
    except Exception as exc:  # pragma: no cover - unexpected runtime error
        print(f"Unexpected table probe runtime error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
