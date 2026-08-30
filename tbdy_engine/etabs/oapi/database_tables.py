"""Canonical read-only CSI DatabaseTables ABI and display-table normalization.

This module consolidates the already-proven provider fetcher/parser behavior.
It owns GetTableForDisplayArray signature probing, raw/mutated COM output
normalization, return/count/shape validation, and factual table DTOs. Temporary
output-selection state remains owned by ``tbdy_engine.etabs.safety``.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any, Mapping, Sequence

from tbdy_engine.etabs.safety import (
    DatabaseTablesReadTransaction,
    RuntimeCaptureStatus,
    classify_capture_status,
)

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

    def header_payload(self, registry: Any) -> dict[str, Any]:
        canonical = registry.canonical_key_for_alias(self.actual_table_name)
        debug_rows = tuple(self.rows[:5])
        return {
            "actual_table_name": self.actual_table_name,
            "canonical_table_key": canonical,
            "fetch_status": self.fetch_status,
            "field_keys": list(self.field_keys),
            "headers": list(self.field_keys),
            "column_count": len(self.field_keys),
            "row_count_reported": self.row_count_reported,
            "sample_row_count": len(debug_rows),
            "rows": [dict(r) for r in self.rows],
            "parsed_rows": [dict(r) for r in self.rows],
            "sample_rows": [dict(r) for r in debug_rows],
            "sample_rows_limited": [dict(r) for r in debug_rows],
            "diagnostics": [dict(d) for d in self.diagnostics],
            "raw_table_diagnostics": {
                "table_name": self.actual_table_name,
                "return_code": self.return_code,
                "number_fields": self.debug.get("number_fields"),
                "number_fields_detected": self.debug.get("number_fields_detected"),
                "number_fields_source": self.debug.get("number_fields_source"),
                "header_count": len(self.field_keys),
                "number_records": self.debug.get("number_records"),
                "fields": list(self.field_keys),
                "table_data_length": self.debug.get("table_data_length"),
                "expected_flat_length": self.debug.get("expected_flat_length"),
                "parser_status": self.debug.get("row_parse_status", self.fetch_status),
            },
        }


@dataclass(frozen=True, slots=True)
class DisplayTableFetchResult:
    table_name: str
    parsed: ParsedDisplayTable
    raw_response: Any = None
    selected_signature: Mapping[str, Any] = field(default_factory=dict)
    selected_signature_reason: str = "not_selected"
    signature_attempts: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    capture_status: RuntimeCaptureStatus = RuntimeCaptureStatus.UNKNOWN
    display_selection: Mapping[str, Any] = field(default_factory=dict)
    state_diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def header_payload(self, registry: Any) -> dict[str, Any]:
        payload = self.parsed.header_payload(registry)
        payload.update({
            "raw_response": self.raw_response,
            "signature_attempts": [dict(item) for item in self.signature_attempts],
            "selected_signature": dict(self.selected_signature),
            "selected_signature_reason": self.selected_signature_reason,
            "parser_status_by_signature": {
                str(item.get("signature_name")): item.get("parser_status")
                for item in self.signature_attempts
            },
            "table_data_length_by_signature": {
                str(item.get("signature_name")): item.get("table_data_length")
                for item in self.signature_attempts
            },
            "number_records_by_signature": {
                str(item.get("signature_name")): item.get("number_records")
                for item in self.signature_attempts
            },
            "capture_status": self.capture_status.value,
            "display_selection": dict(self.display_selection),
            "state_diagnostics": [dict(item) for item in self.state_diagnostics],
        })
        raw = dict(payload.get("raw_table_diagnostics") or {})
        raw.update({
            "signature_attempts": [dict(item) for item in self.signature_attempts],
            "selected_signature": dict(self.selected_signature),
            "selected_signature_reason": self.selected_signature_reason,
            "parser_status_by_signature": payload["parser_status_by_signature"],
            "table_data_length_by_signature": payload["table_data_length_by_signature"],
            "number_records_by_signature": payload["number_records_by_signature"],
            "header_count": len(self.parsed.field_keys),
            "number_fields_detected": self.parsed.debug.get("number_fields_detected"),
            "number_fields_source": self.parsed.debug.get("number_fields_source"),
            "capture_status": self.capture_status.value,
            "display_selection": dict(self.display_selection),
            "state_diagnostics": [dict(item) for item in self.state_diagnostics],
        })
        payload["raw_table_diagnostics"] = raw
        return payload


DISPLAY_TABLE_SIGNATURES: tuple[tuple[str, tuple[Any, ...]], ...] = (
    ("sig_7_list_fields_records_data", ("__TABLE_NAME__", ("__FRESH_LIST__",), "", 0, ("__FRESH_LIST__",), 0, ("__FRESH_LIST__",))),
    ("sig_7_string_fields_records_data", ("__TABLE_NAME__", "", "", 0, ("__FRESH_LIST__",), 0, ("__FRESH_LIST__",))),
    ("sig_6_list_fields_records_data", ("__TABLE_NAME__", ("__FRESH_LIST__",), "", ("__FRESH_LIST__",), 0, ("__FRESH_LIST__",))),
    ("sig_3_group_field_key", ("__TABLE_NAME__", "", "")),
    ("sig_1_table_name", ("__TABLE_NAME__",)),
)


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
    field_keys = _as_string_tuple(
        result.get("field_keys") or result.get("headers") or result.get("fields") or result.get("fieldKeys")
    )
    table_data = result.get("table_data", result.get("TableData", result.get("data", result.get("tableData"))))
    if table_data is None and any(k in result for k in ("rows", "parsed_rows", "full_rows", "table_rows")):
        table_data = result.get("rows") or result.get("parsed_rows") or result.get("full_rows") or result.get("table_rows")
    number_fields = result.get("number_fields", result.get("numberFields", result.get("NumberFields")))
    number_records = result.get("number_records", result.get("numberRecords", result.get("NumberRecords")))
    return (
        return_code,
        field_keys,
        table_data,
        int(number_fields) if isinstance(number_fields, int) else None,
        int(number_records) if isinstance(number_records, int) else None,
    )


def _extract_compact_six_item_etabs_shape(
    result: Sequence[Any],
) -> tuple[int | None, tuple[str, ...], Any, int | None, int | None, dict[str, Any]] | None:
    if len(result) != 6:
        return None
    headers = _as_string_tuple(result[2])
    if not headers:
        return None
    records = result[3]
    table_data = result[4]
    ret = result[5]
    if not isinstance(records, int) or not isinstance(ret, int):
        return None
    slot_1 = result[1]
    number_fields: int | None = None
    number_fields_source = "compact_6_item_slot_1_ignored_as_ambiguous"
    if isinstance(slot_1, int) and slot_1 == len(headers):
        number_fields = int(slot_1)
        number_fields_source = "compact_6_item_slot_1_matches_header_count"
    debug = {
        "sequence_length": len(result),
        "return_code_guess": int(ret),
        "integer_slots": [int(item) for item in result if isinstance(item, int)],
        "candidate_string_sequences": sum(1 for item in result if _is_string_sequence(item)),
        "number_fields_source": number_fields_source,
        "number_fields_detected": number_fields,
        "compact_six_item_shape_detected": True,
        "compact_shape_slots": {
            "headers_index": 2,
            "number_records_index": 3,
            "table_data_index": 4,
            "return_code_index": 5,
        },
    }
    return int(ret), headers, table_data, number_fields, int(records), debug


def _extract_sequence_shape(result: Sequence[Any]) -> tuple[int | None, tuple[str, ...], Any, int | None, int | None, dict[str, Any]]:
    compact = _extract_compact_six_item_etabs_shape(result)
    if compact is not None:
        return compact
    debug: dict[str, Any] = {"sequence_length": len(result), "compact_six_item_shape_detected": False}
    return_code: int | None = None
    if result and isinstance(result[-1], int) and result[-1] in {0, 1, -1}:
        return_code = int(result[-1])
    elif result and isinstance(result[0], int) and result[0] in {0, 1, -1}:
        return_code = int(result[0])
    int_candidates = [int(item) for item in result if isinstance(item, int) and item != return_code]
    number_fields: int | None = None
    number_records: int | None = None
    string_seqs = [tuple(str(x) for x in item) for item in result if _is_string_sequence(item)]
    string_scalars = [
        _split_field_string(item)
        for item in result
        if isinstance(item, str) and ("," in item or "\t" in item)
    ]
    candidates = [seq for seq in string_seqs + string_scalars if seq]
    field_keys: tuple[str, ...] = tuple()
    table_data: Any = tuple()
    if candidates:
        field_keys = min(candidates, key=len)
        remaining = [seq for seq in candidates if seq != field_keys]
        table_data = max(remaining, key=len) if remaining else tuple()
        if table_data and len(field_keys) and len(table_data) % len(field_keys) == 0:
            number_records = len(table_data) // len(field_keys)
    if number_records is None and int_candidates:
        positive = [value for value in int_candidates if value > 0]
        number_records = max(positive) if positive else None
    two_d = [
        item for item in result
        if isinstance(item, (list, tuple))
        and item
        and all(isinstance(row, (list, tuple, Mapping)) for row in item)
    ]
    if two_d and not table_data:
        table_data = two_d[0]
    debug.update({
        "candidate_string_sequences": len(candidates),
        "return_code_guess": return_code,
        "integer_slots": int_candidates,
        "number_fields_source": "ambiguous",
        "number_fields_detected": None,
    })
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
    return (
        isinstance(table_data, (list, tuple))
        and bool(table_data)
        and all(isinstance(row, (list, tuple, Mapping)) for row in table_data)
    )


def _row_limit(max_rows: int | None) -> int | None:
    if max_rows is None or max_rows < 0:
        return None
    return max_rows


def _rows_from_data(
    table_data: Any,
    field_keys: tuple[str, ...],
    number_records: int | None,
    max_rows: int | None,
    debug: dict[str, Any],
    diagnostics: list[dict[str, Any]],
) -> tuple[tuple[Mapping[str, Any], ...], str]:
    limit = _row_limit(max_rows)
    header_count = len(field_keys)
    data_length = _table_data_length(table_data)
    expected_flat_length = (
        number_records * header_count
        if isinstance(number_records, int) and header_count
        else None
    )
    debug.update({
        "header_count": header_count,
        "table_data_length": data_length,
        "expected_flat_length": expected_flat_length,
        "row_parse_status": "NOT_PARSED",
        "mismatch_reason": None,
        "max_rows": max_rows,
        "full_row_capture": limit is None,
    })
    if table_data is None or data_length == 0:
        reason = "no_table_data" if not number_records else "no_table_data_with_reported_records"
        debug.update({"row_parse_status": "EMPTY", "mismatch_reason": reason if number_records else None})
        diagnostics.append({
            "severity": "INFO",
            "code": "TABLE_EMPTY",
            "message": "No rows parsed from display table response",
            "details": {"mismatch_reason": reason},
        })
        return tuple(), "EMPTY"
    if header_count <= 0:
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": "headers_missing"})
        diagnostics.append({
            "severity": "WARNING",
            "code": "ROW_PARSE_PARTIAL",
            "message": "Cannot parse rows because headers are missing",
            "details": {"mismatch_reason": "headers_missing"},
        })
        return tuple(), "ROW_PARSE_PARTIAL"
    if isinstance(table_data, (list, tuple)) and table_data and all(isinstance(row, Mapping) for row in table_data):
        source_rows = table_data if limit is None else table_data[:limit]
        rows = tuple({str(k): _safe_value(v) for k, v in dict(row).items()} for row in source_rows)
        debug["row_parse_status"] = "FETCHED" if rows else "EMPTY"
        return rows, debug["row_parse_status"]
    if _is_2d_rows(table_data):
        parsed_rows: list[Mapping[str, Any]] = []
        for row in table_data:
            if isinstance(row, Mapping):
                parsed_rows.append({str(k): _safe_value(v) for k, v in dict(row).items()})
            else:
                if len(row) != header_count:
                    reason = f"2d_row_width_mismatch:{len(row)}!={header_count}"
                    debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
                    diagnostics.append({
                        "severity": "WARNING",
                        "code": "ROW_PARSE_PARTIAL",
                        "message": "2D table row width does not match header count",
                        "details": {"mismatch_reason": reason},
                    })
                    return tuple(), "ROW_PARSE_PARTIAL"
                parsed_rows.append({field_keys[i]: _safe_value(row[i]) for i in range(header_count)})
            if limit is not None and len(parsed_rows) >= limit:
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
        diagnostics.append({
            "severity": "WARNING",
            "code": "ROW_PARSE_PARTIAL",
            "message": "Unsupported table data shape",
            "details": {"mismatch_reason": reason},
        })
        return tuple(), "ROW_PARSE_PARTIAL"
    flat_len = len(flat)
    debug["table_data_length"] = flat_len
    if expected_flat_length is not None and flat_len != expected_flat_length:
        reason = f"flat_length_mismatch:{flat_len}!={expected_flat_length}"
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
        diagnostics.append({
            "severity": "WARNING",
            "code": "ROW_PARSE_PARTIAL",
            "message": "Flat table data length does not match number_records * header_count",
            "details": {
                "table_data_length": flat_len,
                "expected_flat_length": expected_flat_length,
                "mismatch_reason": reason,
            },
        })
        return tuple(), "ROW_PARSE_PARTIAL"
    if flat_len % header_count != 0:
        reason = f"flat_length_not_divisible_by_header_count:{flat_len}%{header_count}"
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": reason})
        diagnostics.append({
            "severity": "WARNING",
            "code": "ROW_PARSE_PARTIAL",
            "message": "Flat table data length does not align with header count",
            "details": {"table_data_length": flat_len, "header_count": header_count, "mismatch_reason": reason},
        })
        return tuple(), "ROW_PARSE_PARTIAL"
    rows = []
    for start in range(0, flat_len, header_count):
        if limit is not None and len(rows) >= limit:
            break
        chunk = flat[start : start + header_count]
        rows.append({field_keys[i]: _safe_value(chunk[i]) for i in range(header_count)})
    if not rows:
        debug.update({"row_parse_status": "EMPTY", "mismatch_reason": "no_rows_after_chunking"})
        diagnostics.append({"severity": "INFO", "code": "TABLE_EMPTY", "message": "No rows parsed from display table response"})
        return tuple(), "EMPTY"
    debug["row_parse_status"] = "FETCHED"
    return tuple(rows), "FETCHED"


def parse_etabs_display_table_result(
    result: Any,
    *,
    actual_table_name: str = "UNKNOWN_TABLE",
    max_rows: int | None = 3,
) -> ParsedDisplayTable:
    diagnostics: list[dict[str, Any]] = []
    debug: dict[str, Any] = {
        "actual_table_name": actual_table_name,
        "api_method": "GetTableForDisplayArray",
    }
    try:
        if isinstance(result, Mapping):
            return_code, field_keys, table_data, number_fields, number_records = _extract_mapping_shape(result)
            debug["return_shape_metadata"] = "mapping"
        elif isinstance(result, (list, tuple)):
            return_code, field_keys, table_data, number_fields, number_records, seq_debug = _extract_sequence_shape(result)
            debug.update(seq_debug)
            debug["return_shape_metadata"] = "sequence"
        else:
            diagnostics.append({
                "severity": "WARNING",
                "code": "MALFORMED_SHAPE",
                "message": "Display-table result was not a mapping or sequence",
            })
            debug.update({"return_shape_metadata": type(result).__name__, "parse_error": "unsupported result shape"})
            return ParsedDisplayTable(
                actual_table_name=actual_table_name,
                fetch_status="FAILED",
                diagnostics=tuple(diagnostics),
                debug=debug,
            )
        number_fields_source = debug.get("number_fields_source") or (
            "mapping" if isinstance(result, Mapping) else "ambiguous"
        )
        number_fields_detected = number_fields if number_fields_source != "ambiguous" else None
        debug.update({
            "return_code": return_code,
            "number_fields": number_fields_detected,
            "number_fields_detected": number_fields_detected,
            "number_fields_source": number_fields_source,
            "number_records": number_records,
            "field_keys_type": type(field_keys).__name__,
            "table_data_type": type(table_data).__name__,
            "table_data_length": _table_data_length(table_data),
            "header_count": len(field_keys),
            "expected_flat_length": (
                number_records * len(field_keys)
                if isinstance(number_records, int) and field_keys
                else None
            ),
        })
        if return_code not in {None, 0}:
            diagnostics.append({
                "severity": "ERROR",
                "code": "TABLE_FETCH_FAILED",
                "message": "GetTableForDisplayArray returned nonzero return code",
                "details": {"return_code": return_code},
            })
            return ParsedDisplayTable(
                actual_table_name=actual_table_name,
                fetch_status="FAILED",
                return_code=return_code,
                diagnostics=tuple(diagnostics),
                debug=debug,
            )
        if not field_keys:
            diagnostics.append({
                "severity": "WARNING",
                "code": "HEADERS_MISSING",
                "message": "No field keys/headers could be parsed from ETABS response",
            })
        rows, row_parse_status = _rows_from_data(
            table_data, field_keys, number_records, max_rows, debug, diagnostics
        )
        reported = int(number_records) if isinstance(number_records, int) else len(rows)
        return ParsedDisplayTable(
            actual_table_name=actual_table_name,
            fetch_status=row_parse_status,
            field_keys=field_keys,
            rows=rows,
            row_count_reported=reported,
            return_code=return_code,
            diagnostics=tuple(diagnostics),
            debug={**debug, "parse_strategy_used": "shared_defensive_display_array_parser"},
        )
    except Exception as exc:
        diagnostics.append({
            "severity": "ERROR",
            "code": "PARSE_ERROR",
            "message": "Display-table response parse failed; continuing with next table",
            "details": {"error": str(exc)},
        })
        debug["parse_error"] = str(exc)
        return ParsedDisplayTable(
            actual_table_name=actual_table_name,
            fetch_status="FAILED",
            diagnostics=tuple(diagnostics),
            debug=debug,
        )


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


def _materialize_arg(item: Any, table_name: str) -> Any:
    if item == "__TABLE_NAME__":
        return table_name
    if item == ("__FRESH_LIST__",):
        return []
    return deepcopy(item)


def _materialize_args(template: tuple[Any, ...], table_name: str) -> tuple[Any, ...]:
    return tuple(_materialize_arg(item, table_name) for item in template)


def _detect_preferred_output_kind(database_tables: Any, preferred_output_case: str) -> str:
    combo_names = getattr(database_tables, "load_combination_names", None)
    case_names = getattr(database_tables, "load_case_names", None)
    try:
        if combo_names is not None and preferred_output_case in set(combo_names):
            return "combo"
        if case_names is not None and preferred_output_case in set(case_names):
            return "case"
    except Exception:
        return "unknown"
    return "unknown"


def select_output_for_display(database_tables: Any, preferred_output_case: str | None) -> dict[str, Any]:
    case_name = str(preferred_output_case or "").strip()
    return {
        "preferred_output_case": case_name,
        "preferred_output_kind_detected": (
            _detect_preferred_output_kind(database_tables, case_name) if case_name else "unknown"
        ),
        "display_selection_attempted": False,
        "display_selection_attempts": [],
        "display_selection_selected_method": None,
        "display_selection_success": False,
        "fetch_after_display_selection": False,
        "attempted_case_fallback": False,
        "skipped_case_selection_because_combo_succeeded": False,
        "read_only_model_geometry": True,
        "model_geometry_mutated": False,
        "mutation_kind": "READ_WITH_OUTPUT_SELECTION_STATE_CHANGE",
        "diagnostic": "TRANSACTION_REQUIRED_USE_FETCH_DISPLAY_TABLE_FOR_OUTPUT",
    }


def _parser_status_for(parsed: ParsedDisplayTable) -> str:
    if parsed.rows:
        return "PARSED_ROWS"
    debug = dict(parsed.debug or {})
    try:
        number_records = int(debug.get("number_records") or 0)
    except Exception:
        number_records = 0
    try:
        table_data_length = int(debug.get("table_data_length") or 0)
    except Exception:
        table_data_length = 0
    if number_records > 0 and table_data_length == 0:
        return "TABLEDATA_EMPTY_DESPITE_RECORDS"
    if parsed.fetch_status == "FAILED":
        return "COM_CALL_FAILED"
    if parsed.field_keys and not parsed.rows:
        return "HEADER_ONLY"
    if not parsed.field_keys and not parsed.rows:
        return "EMPTY_TABLE"
    return parsed.fetch_status or "UNKNOWN_SHAPE"


def _capture_status_for_parsed(parsed: ParsedDisplayTable, *, max_rows: int | None) -> RuntimeCaptureStatus:
    debug = dict(parsed.debug or {})
    reported = parsed.row_count_reported
    if reported is None:
        try:
            value = debug.get("number_records")
            reported = None if value is None else int(value)
        except Exception:
            reported = None
    try:
        payload_len = int(debug.get("table_data_length")) if debug.get("table_data_length") is not None else None
    except Exception:
        payload_len = None
    parser_status = _parser_status_for(parsed)
    parser_has_error = bool(debug.get("mismatch_reason")) or parser_status in {
        "TABLEDATA_EMPTY_DESPITE_RECORDS",
        "COM_CALL_FAILED",
    }
    return classify_capture_status(
        return_code=parsed.return_code,
        row_count_reported=reported,
        row_count_captured=len(parsed.rows),
        header_count=len(parsed.field_keys),
        flat_payload_length=payload_len,
        max_rows=max_rows,
        parser_has_error=parser_has_error,
    )


def _safe_len(value: Any) -> int | None:
    try:
        return len(value)
    except Exception:
        return None


def _short_repr(value: Any, limit: int = 240) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


def _summarize_item(value: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"type": type(value).__name__, "repr": _short_repr(value)}
    length = _safe_len(value)
    if length is not None and not isinstance(value, (str, bytes)):
        out["len"] = length
        try:
            out["sample"] = list(value[:8])
        except Exception:
            out["sample"] = _short_repr(value)
    if hasattr(value, "value"):
        try:
            variant_value = value.value
            out["variant_value_type"] = type(variant_value).__name__
            out["variant_value_len"] = _safe_len(variant_value)
            out["variant_value_repr"] = _short_repr(variant_value)
        except Exception as exc:
            out["variant_value_error"] = repr(exc)
    return out


def _raw_return_summary(raw: Any) -> dict[str, Any]:
    out = {"raw_return_type": type(raw).__name__, "raw_return_repr": _short_repr(raw, 400)}
    if isinstance(raw, (list, tuple)):
        out["raw_return_len"] = len(raw)
        out["raw_return_items_summary"] = [
            _summarize_item(item) | {"index": i} for i, item in enumerate(raw)
        ]
    return out


def _args_after_summary(args: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [_summarize_item(arg) | {"index": i} for i, arg in enumerate(args)]


def _raw_return_fragments(raw: Any) -> list[Any]:
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return [raw]


def _arg_fragments(arg: Any) -> list[Any]:
    fragments = [arg]
    if hasattr(arg, "value"):
        try:
            fragments.append(arg.value)
        except Exception:
            pass
    return fragments


def _combined_response(raw: Any, args: tuple[Any, ...]) -> Any:
    combined: list[Any] = []
    combined.extend(_raw_return_fragments(raw))
    for arg in args:
        combined.extend(_arg_fragments(arg))
    return tuple(combined)


def _merge_parse_diagnostics(
    primary: ParsedDisplayTable,
    combined: ParsedDisplayTable,
    *,
    strategy: str,
) -> ParsedDisplayTable:
    debug = dict(combined.debug or {})
    debug.update({
        "parse_strategy_used": strategy,
        "raw_return_parse_status": _parser_status_for(primary),
        "raw_return_table_data_length": (primary.debug or {}).get("table_data_length"),
        "raw_return_number_records": (primary.debug or {}).get("number_records"),
    })
    diagnostics = list(primary.diagnostics) + list(combined.diagnostics)
    if combined.rows and not primary.rows:
        diagnostics.append({
            "severity": "INFO",
            "code": "DISPLAY_TABLE_PARSED_FROM_MUTATED_ARGS",
            "message": "Parsed display rows by scanning raw return plus post-call mutable COM arguments.",
            "details": {"parse_strategy_used": strategy},
        })
    return ParsedDisplayTable(
        actual_table_name=combined.actual_table_name,
        fetch_status=combined.fetch_status,
        field_keys=combined.field_keys,
        rows=combined.rows,
        row_count_reported=combined.row_count_reported,
        return_code=combined.return_code if combined.return_code is not None else primary.return_code,
        diagnostics=tuple(diagnostics),
        debug=debug,
    )


def _string_sequences_in(value: Any) -> list[tuple[str, ...]]:
    seqs: list[tuple[str, ...]] = []
    if isinstance(value, str):
        if "," in value or "\t" in value:
            parts = tuple(part.strip() for part in value.replace("\t", ",").split(",") if part.strip())
            if parts:
                seqs.append(parts)
    elif isinstance(value, (list, tuple)) and all(isinstance(item, str) for item in value):
        seqs.append(tuple(str(item) for item in value))
    if hasattr(value, "value"):
        try:
            seqs.extend(_string_sequences_in(value.value))
        except Exception:
            pass
    return seqs


def _parse_with_primary_headers_from_mutated_args(
    primary: ParsedDisplayTable,
    raw: Any,
    args: tuple[Any, ...],
    *,
    table_name: str,
    max_rows: int | None,
) -> ParsedDisplayTable | None:
    headers = tuple(primary.field_keys)
    header_count = len(headers)
    if header_count <= 0:
        return None
    candidates: list[tuple[str, ...]] = []
    for fragment in _raw_return_fragments(raw):
        candidates.extend(_string_sequences_in(fragment))
    for arg in args:
        for fragment in _arg_fragments(arg):
            candidates.extend(_string_sequences_in(fragment))
    data_candidates = [
        seq for seq in candidates
        if seq != headers and len(seq) > header_count and len(seq) % header_count == 0
    ]
    if not data_candidates:
        return None
    table_data = max(data_candidates, key=len)
    parsed = parse_etabs_display_table_result(
        {
            "return_code": primary.return_code if primary.return_code is not None else 0,
            "field_keys": list(headers),
            "table_data": list(table_data),
            "number_records": len(table_data) // header_count,
        },
        actual_table_name=table_name,
        max_rows=max_rows,
    )
    if not parsed.rows:
        return None
    return _merge_parse_diagnostics(
        primary,
        parsed,
        strategy="primary_headers_plus_mutated_args_tabledata",
    )


def _parse_raw_and_args(
    raw: Any,
    args: tuple[Any, ...],
    *,
    table_name: str,
    max_rows: int | None,
) -> ParsedDisplayTable:
    primary = parse_etabs_display_table_result(raw, actual_table_name=table_name, max_rows=max_rows)
    if primary.rows:
        return primary
    primary_header_parse = _parse_with_primary_headers_from_mutated_args(
        primary, raw, args, table_name=table_name, max_rows=max_rows
    )
    if primary_header_parse is not None:
        return primary_header_parse
    combined = parse_etabs_display_table_result(
        _combined_response(raw, args),
        actual_table_name=table_name,
        max_rows=max_rows,
    )
    if combined.rows and len(combined.field_keys) > 1:
        return _merge_parse_diagnostics(
            primary, combined, strategy="return_plus_mutated_args_sequence_scan"
        )
    if len(combined.field_keys) > len(primary.field_keys):
        return _merge_parse_diagnostics(
            primary,
            combined,
            strategy="return_plus_mutated_args_sequence_scan_no_rows",
        )
    return primary


def _attempt_record(
    *,
    index: int,
    signature_name: str,
    args: tuple[Any, ...],
    parsed: ParsedDisplayTable | None = None,
    exception: Exception | None = None,
    raw: Any = None,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "signature_index": index,
        "signature_name": signature_name,
        "arg_count": len(args),
        "arg_types": [type(arg).__name__ for arg in args],
        "args_repr": [_short_repr(arg) for arg in args],
        "args_after_summary": _args_after_summary(args),
        "call_succeeded": exception is None,
    }
    if raw is not None:
        base.update(_raw_return_summary(raw))
    if exception is not None:
        base.update({
            "exception_type": type(exception).__name__,
            "exception_message": str(exception),
            "parser_status": "COM_CALL_EXCEPTION",
            "row_count": 0,
            "table_data_length": 0,
            "number_records": None,
            "header_count": 0,
            "number_fields_detected": None,
            "number_fields_source": "exception",
        })
        return base
    assert parsed is not None
    debug = dict(parsed.debug or {})
    first_row = dict(parsed.rows[0]) if parsed.rows else None
    base.update({
        "return_code": parsed.return_code,
        "fetch_status": parsed.fetch_status,
        "parser_status": _parser_status_for(parsed),
        "row_count": len(parsed.rows),
        "number_records": debug.get("number_records"),
        "table_data_length": debug.get("table_data_length"),
        "expected_flat_length": debug.get("expected_flat_length"),
        "header_count": len(parsed.field_keys),
        "headers": list(parsed.field_keys),
        "detected_headers": list(parsed.field_keys),
        "detected_table_data_length": debug.get("table_data_length"),
        "detected_number_records": debug.get("number_records"),
        "detected_number_fields": debug.get("number_fields_detected"),
        "number_fields_detected": debug.get("number_fields_detected"),
        "number_fields_source": debug.get("number_fields_source"),
        "mismatch_reason": debug.get("mismatch_reason"),
        "parse_strategy_used": debug.get("parse_strategy_used"),
        "first_row_sample": first_row,
    })
    return base


def _best_failed_candidate(
    candidates: list[tuple[ParsedDisplayTable, Any, dict[str, Any]]],
) -> tuple[ParsedDisplayTable, Any, dict[str, Any]] | None:
    if not candidates:
        return None

    def score(item: tuple[ParsedDisplayTable, Any, dict[str, Any]]) -> tuple[int, int, int, int]:
        _parsed, _raw, attempt = item
        status_bonus = 2 if attempt.get("parser_status") == "TABLEDATA_EMPTY_DESPITE_RECORDS" else 0
        header_count = int(attempt.get("header_count") or 0)
        try:
            records = int(attempt.get("number_records") or 0)
        except Exception:
            records = 0
        return (status_bonus, header_count, records, -int(attempt.get("signature_index") or 0))

    return max(candidates, key=score)


def _with_fetcher_debug(
    parsed: ParsedDisplayTable,
    attempts: list[dict[str, Any]],
    selected: Mapping[str, Any],
    reason: str,
    extra_diagnostics: list[Mapping[str, Any]] | None = None,
) -> ParsedDisplayTable:
    diagnostics = list(parsed.diagnostics)
    if extra_diagnostics:
        diagnostics.extend(dict(item) for item in extra_diagnostics)
    return ParsedDisplayTable(
        actual_table_name=parsed.actual_table_name,
        fetch_status=parsed.fetch_status,
        field_keys=parsed.field_keys,
        rows=parsed.rows,
        row_count_reported=parsed.row_count_reported,
        return_code=parsed.return_code,
        diagnostics=tuple(diagnostics),
        debug={
            **dict(parsed.debug or {}),
            "signature_attempts": attempts,
            "selected_signature": dict(selected),
            "selected_signature_reason": reason,
        },
    )


def _result(
    *,
    table_name: str,
    parsed: ParsedDisplayTable,
    raw: Any,
    selected: Mapping[str, Any],
    reason: str,
    attempts: list[dict[str, Any]],
    max_rows: int | None,
) -> DisplayTableFetchResult:
    return DisplayTableFetchResult(
        table_name=table_name,
        parsed=parsed,
        raw_response=raw,
        selected_signature=selected,
        selected_signature_reason=reason,
        signature_attempts=tuple(attempts),
        capture_status=_capture_status_for_parsed(parsed, max_rows=max_rows),
    )


def fetch_display_table(
    database_tables: Any,
    table_name: str,
    *,
    max_rows: int | None = None,
) -> DisplayTableFetchResult:
    attempts: list[dict[str, Any]] = []
    parsed_candidates: list[tuple[ParsedDisplayTable, Any, dict[str, Any]]] = []
    last_exception: Exception | None = None
    for index, (signature_name, template) in enumerate(DISPLAY_TABLE_SIGNATURES, start=1):
        args = _materialize_args(template, table_name)
        try:
            raw = database_tables.GetTableForDisplayArray(*args)
        except Exception as exc:
            last_exception = exc
            attempts.append(
                _attempt_record(
                    index=index,
                    signature_name=signature_name,
                    args=args,
                    exception=exc,
                )
            )
            continue
        parsed = _parse_raw_and_args(raw, args, table_name=table_name, max_rows=max_rows)
        attempt = _attempt_record(
            index=index,
            signature_name=signature_name,
            args=args,
            parsed=parsed,
            raw=raw,
        )
        attempts.append(attempt)
        parsed_candidates.append((parsed, raw, attempt))
        if parsed.rows:
            selected = dict(attempt)
            reason = "first_signature_with_parsed_rows"
            parsed = _with_fetcher_debug(
                parsed,
                attempts,
                selected,
                reason,
                [{
                    "severity": "INFO",
                    "code": "DISPLAY_TABLE_SIGNATURE_SELECTED",
                    "message": "Selected first GetTableForDisplayArray signature that produced parsed rows.",
                    "details": {
                        "selected_signature": signature_name,
                        "parse_strategy_used": attempt.get("parse_strategy_used"),
                    },
                }],
            )
            return _result(
                table_name=table_name,
                parsed=parsed,
                raw=raw,
                selected=selected,
                reason=reason,
                attempts=attempts,
                max_rows=max_rows,
            )
    best = _best_failed_candidate(parsed_candidates)
    if best is not None:
        parsed, raw, selected_attempt = best
        status = _parser_status_for(parsed)
        selected_reason = (
            "all_signatures_failed_best_empty_tabledata"
            if status == "TABLEDATA_EMPTY_DESPITE_RECORDS"
            else "all_signatures_failed_best_diagnostic_candidate"
        )
        parsed = _with_fetcher_debug(
            parsed,
            attempts,
            selected_attempt,
            selected_reason,
            [{
                "severity": "WARNING",
                "code": status,
                "message": "No GetTableForDisplayArray signature produced parsed rows; selected best diagnostic response.",
                "details": {"selected_signature": selected_attempt.get("signature_name")},
            }],
        )
        return _result(
            table_name=table_name,
            parsed=parsed,
            raw=raw,
            selected=selected_attempt,
            reason=selected_reason,
            attempts=attempts,
            max_rows=max_rows,
        )
    raw = {
        "return_code": 1,
        "field_keys": [],
        "table_data": [],
        "diagnostic": f"Could not call GetTableForDisplayArray with supported signatures: {last_exception}",
    }
    parsed = parse_etabs_display_table_result(raw, actual_table_name=table_name, max_rows=max_rows)
    selected = {"signature_name": "none", "parser_status": "COM_CALL_FAILED"}
    parsed = _with_fetcher_debug(
        parsed,
        attempts,
        selected,
        "all_signatures_raised_exceptions",
        [{
            "severity": "ERROR",
            "code": "DISPLAY_TABLE_ALL_SIGNATURES_FAILED",
            "message": "All GetTableForDisplayArray signatures raised exceptions.",
            "details": {"last_exception": str(last_exception)},
        }],
    )
    return _result(
        table_name=table_name,
        parsed=parsed,
        raw=raw,
        selected=selected,
        reason="all_signatures_raised_exceptions",
        attempts=attempts,
        max_rows=max_rows,
    )


def fetch_display_table_for_output(
    database_tables: Any,
    table_name: str,
    *,
    preferred_output_case: str,
    max_rows: int | None = None,
) -> DisplayTableFetchResult:
    transaction = DatabaseTablesReadTransaction(database_tables)
    selection: Mapping[str, Any] = {}
    fetched: DisplayTableFetchResult | None = None
    with transaction:
        selection = transaction.select_output(preferred_output_case)
        fetched = fetch_display_table(database_tables, table_name, max_rows=max_rows)
    assert fetched is not None
    return replace(
        fetched,
        display_selection=dict(selection),
        state_diagnostics=tuple(dict(item) for item in transaction.diagnostics),
    )


def try_get_display_table(
    database_tables: Any,
    table_name: str,
    *,
    max_rows: int | None = None,
) -> Any:
    return fetch_display_table(database_tables, table_name, max_rows=max_rows).raw_response


__all__ = [
    "DISPLAY_TABLE_SIGNATURES",
    "DisplayTableFetchResult",
    "ParsedDisplayTable",
    "_extract_compact_six_item_etabs_shape",
    "_rows_from_data",
    "_table_data_length",
    "fetch_display_table",
    "fetch_display_table_for_output",
    "parse_available_tables_result",
    "parse_etabs_display_table_result",
    "select_output_for_display",
    "try_get_display_table",
]
