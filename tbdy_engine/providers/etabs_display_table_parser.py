"""Shared ETABS display-table parser.

Import-safe engine/runtime parser for ETABS ``GetTableForDisplayArray`` shaped
responses.  It parses observed display-table data only; it never mutates ETABS,
executes checks, or emits engineering verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

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
    table_data = result.get("table_data", result.get("TableData", result.get("data", result.get("tableData"))))
    # Mapping payloads may already contain row dictionaries.  Treat these as
    # row-shaped table data only when no flat TableData/data field exists.
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
    """Parse the compact six-item ETABS COM return shape observed live.

    Accepted live C11.1.11 traces returned:

    ``[field_key_list_or_empty, number_fields_or_wrapper_slot, headers, number_records, table_data, ret]``

    The second slot may be a COM wrapper/status value (often 1 or 2), so it is
    trusted as ``number_fields`` only when it exactly equals ``len(headers)``.
    This compact shape must be recognized before the generic sequence fallback,
    otherwise the large TableData tuple can be missed or misdiagnosed as empty.
    """
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
    debug: dict[str, Any] = {
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

    # ETABS COM wrappers expose several out/ref integer slots in tuple-shaped
    # results.  In live traces these slots can include small wrapper/status
    # values (for example 1 or 2) before the actual record count, so treating
    # the first integer as ``number_fields`` produces misleading diagnostics.
    # Row reconstruction is based on the parsed header count instead.
    int_candidates = [int(item) for item in result if isinstance(item, int) and item != return_code]
    number_fields: int | None = None
    number_records: int | None = None

    string_seqs = [tuple(str(x) for x in item) for item in result if _is_string_sequence(item)]
    string_scalars = [_split_field_string(item) for item in result if isinstance(item, str) and ("," in item or "\t" in item)]
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
        # Best-effort only: with empty TableData the record count is usually the
        # largest positive integer in observed ETABS tuples.  We keep
        # number_fields ambiguous rather than reporting a wrong small value.
        positive = [value for value in int_candidates if value > 0]
        number_records = max(positive) if positive else None

    two_d = [item for item in result if isinstance(item, (list, tuple)) and item and all(isinstance(row, (list, tuple, Mapping)) for row in item)]
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
    return isinstance(table_data, (list, tuple)) and bool(table_data) and all(isinstance(row, (list, tuple, Mapping)) for row in table_data)


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
    """Return parsed rows and row_parse_status.

    Row chunking is based on the parsed header count.  ``max_rows=None`` means
    full production row capture; positive values are debug/sample limits only.
    """
    limit = _row_limit(max_rows)
    header_count = len(field_keys)
    data_length = _table_data_length(table_data)
    expected_flat_length = (number_records * header_count) if isinstance(number_records, int) and header_count else None
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
        diagnostics.append({"severity": "INFO", "code": "TABLE_EMPTY", "message": "No rows parsed from display table response", "details": {"mismatch_reason": reason}})
        return tuple(), "EMPTY"
    if header_count <= 0:
        debug.update({"row_parse_status": "ROW_PARSE_PARTIAL", "mismatch_reason": "headers_missing"})
        diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "Cannot parse rows because headers are missing", "details": {"mismatch_reason": "headers_missing"}})
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
                    diagnostics.append({"severity": "WARNING", "code": "ROW_PARSE_PARTIAL", "message": "2D table row width does not match header count", "details": {"mismatch_reason": reason}})
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


def parse_etabs_display_table_result(result: Any, *, actual_table_name: str = "UNKNOWN_TABLE", max_rows: int | None = 3) -> ParsedDisplayTable:
    """Parse ETABS display table response defensively.

    Supports mapping-shaped tests, common COM tuple shapes, flat TableData,
    two-dimensional row arrays, and already-parsed row mappings.
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

        number_fields_source = debug.get("number_fields_source") or ("mapping" if isinstance(result, Mapping) else "ambiguous")
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
            "expected_flat_length": (number_records * len(field_keys)) if isinstance(number_records, int) and field_keys else None,
        })
        if return_code not in {None, 0}:
            diagnostics.append({"severity": "ERROR", "code": "TABLE_FETCH_FAILED", "message": "GetTableForDisplayArray returned nonzero return code", "details": {"return_code": return_code}})
            return ParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", return_code=return_code, diagnostics=tuple(diagnostics), debug=debug)
        if not field_keys:
            diagnostics.append({"severity": "WARNING", "code": "HEADERS_MISSING", "message": "No field keys/headers could be parsed from ETABS response"})
        rows, row_parse_status = _rows_from_data(table_data, field_keys, number_records, max_rows, debug, diagnostics)
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


__all__ = [
    "ParsedDisplayTable",
    "_extract_compact_six_item_etabs_shape",
    "_rows_from_data",
    "_table_data_length",
    "parse_available_tables_result",
    "parse_etabs_display_table_result",
]
