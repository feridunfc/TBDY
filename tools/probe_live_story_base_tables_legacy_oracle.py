#!/usr/bin/env python
"""C11.1.4 temporary legacy story/base ETABS table probe oracle.

This script intentionally keeps the old standalone probe behavior isolated from
new shared fetcher/parser code.  It is manual/debug only: no checks, no
CheckResult, no verdicts, and no ETABS model mutation.
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tbdy_engine.json_safe import to_jsonable
from tbdy_engine.providers.table_registry import normalize_table_name

TARGET_TABLES: Mapping[str, str] = {
    "story_drifts": "Story Drifts",
    "story_max_over_avg_drifts": "Story Max Over Avg Drifts",
    "base_reactions": "Base Reactions",
}

_FORBIDDEN_STATUS_VALUES = {"OK", "FAIL"}


@dataclass(frozen=True, slots=True)
class LegacyParsedDisplayTable:
    actual_table_name: str
    fetch_status: str
    field_keys: tuple[str, ...] = field(default_factory=tuple)
    rows: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    row_count_reported: int = 0
    return_code: int | None = None
    diagnostics: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    debug: Mapping[str, Any] = field(default_factory=dict)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(payload), indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def _safe_value(value: Any) -> Any:
    if isinstance(value, str) and value.strip().upper() in _FORBIDDEN_STATUS_VALUES:
        return "[REDACTED_STATUS_VALUE]"
    return value


def _short_repr(value: Any, limit: int = 500) -> str:
    text = repr(value)
    return text if len(text) <= limit else text[:limit] + "...<truncated>"


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


def _table_data_length(table_data: Any) -> int | None:
    if table_data is None:
        return 0
    if isinstance(table_data, str):
        return len(_split_field_string(table_data))
    if isinstance(table_data, (list, tuple)):
        return len(table_data)
    return None


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


def parse_etabs_display_table_result(result: Any, *, actual_table_name: str = "UNKNOWN_TABLE", max_rows: int = 3) -> LegacyParsedDisplayTable:
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
            return LegacyParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", diagnostics=tuple(diagnostics), debug=debug)
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
            return LegacyParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", return_code=return_code, diagnostics=tuple(diagnostics), debug=debug)
        if not field_keys:
            diagnostics.append({"severity": "WARNING", "code": "HEADERS_MISSING", "message": "No field keys/headers could be parsed from ETABS response"})
        rows, row_parse_status = _rows_from_data(table_data, field_keys, number_records, max_rows, debug, diagnostics)
        reported = int(number_records) if isinstance(number_records, int) else len(rows)
        return LegacyParsedDisplayTable(
            actual_table_name=actual_table_name,
            fetch_status=row_parse_status,
            field_keys=field_keys,
            rows=rows,
            row_count_reported=reported,
            return_code=return_code,
            diagnostics=tuple(diagnostics),
            debug={**debug, "parse_strategy_used": "legacy_defensive_display_array_parser"},
        )
    except Exception as exc:
        diagnostics.append({"severity": "ERROR", "code": "PARSE_ERROR", "message": "Display-table response parse failed; continuing with next table", "details": {"error": str(exc)}})
        debug["parse_error"] = str(exc)
        return LegacyParsedDisplayTable(actual_table_name=actual_table_name, fetch_status="FAILED", diagnostics=tuple(diagnostics), debug=debug)


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


def _table_is_available(target: str, available: Iterable[str]) -> str | None:
    normalized_target = normalize_table_name(target)
    for actual in available:
        if normalize_table_name(actual) == normalized_target:
            return actual
    return None


def _summarize_raw(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"raw_return_type": type(raw).__name__, "raw_return_repr": _short_repr(raw)}
    if isinstance(raw, (list, tuple)):
        out["raw_return_len"] = len(raw)
        out["raw_return_items_summary"] = []
        for i, item in enumerate(raw):
            summary: dict[str, Any] = {"index": i, "type": type(item).__name__, "repr": _short_repr(item, 200)}
            try:
                summary["len"] = len(item)  # type: ignore[arg-type]
                if isinstance(item, (list, tuple)):
                    summary["sample"] = list(item[:8])
            except Exception:
                pass
            out["raw_return_items_summary"].append(summary)
    return out


def _signature_attempt_payload(index: int, name: str, args: tuple[Any, ...], raw: Any = None, parsed: LegacyParsedDisplayTable | None = None, exc: Exception | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "signature_index": index,
        "signature_name": name,
        "args_repr": [_short_repr(arg) for arg in args],
        "call_succeeded": exc is None,
    }
    if exc is not None:
        payload.update({"parser_status": "COM_CALL_EXCEPTION", "exception_type": type(exc).__name__, "exception_message": str(exc), "row_count": 0})
        return payload
    assert parsed is not None
    debug = dict(parsed.debug or {})
    payload.update(_summarize_raw(raw))
    payload.update({
        "detected_headers": list(parsed.field_keys),
        "detected_table_data_length": debug.get("table_data_length"),
        "detected_number_records": debug.get("number_records"),
        "detected_number_fields": debug.get("number_fields"),
        "parser_status": "PARSED_ROWS" if parsed.rows else ("TABLEDATA_EMPTY_DESPITE_RECORDS" if int(debug.get("number_records") or 0) > 0 and int(debug.get("table_data_length") or 0) == 0 else parsed.fetch_status),
        "row_count": len(parsed.rows),
        "first_row_sample": dict(parsed.rows[0]) if parsed.rows else None,
    })
    return payload


def _legacy_attempts(table_name: str) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    return (
        ("legacy_sig_7_list_fields_records_data", (table_name, [], "", 0, [], 0, [])),
        ("legacy_sig_7_string_fields_records_data", (table_name, "", "", 0, [], 0, [])),
        ("legacy_sig_6_list_fields_records_data", (table_name, [], "", [], 0, [])),
        ("legacy_sig_3_group_field_key", (table_name, "", "")),
        ("legacy_sig_1_table_name", (table_name,)),
    )


def _try_get_display_table_with_debug(database_tables: Any, table_name: str, *, max_rows: int = 100000) -> tuple[Any, LegacyParsedDisplayTable, list[dict[str, Any]], dict[str, Any], str]:
    attempts: list[dict[str, Any]] = []
    last_exc: Exception | None = None
    for index, (name, args) in enumerate(_legacy_attempts(table_name), start=1):
        try:
            raw = database_tables.GetTableForDisplayArray(*args)
        except Exception as exc:
            last_exc = exc
            attempts.append(_signature_attempt_payload(index, name, args, exc=exc))
            continue
        parsed = parse_etabs_display_table_result(raw, actual_table_name=table_name, max_rows=max_rows)
        attempt = _signature_attempt_payload(index, name, args, raw=raw, parsed=parsed)
        attempts.append(attempt)
        # Exact old behavior: return first COM signature that does not raise.
        return raw, parsed, attempts, attempt, "legacy_first_non_exception_signature"
    raw = {"return_code": 1, "field_keys": [], "table_data": [], "diagnostic": f"Could not call GetTableForDisplayArray with supported signatures: {last_exc}"}
    parsed = parse_etabs_display_table_result(raw, actual_table_name=table_name, max_rows=max_rows)
    selected = {"signature_name": "none", "parser_status": "COM_CALL_FAILED"}
    return raw, parsed, attempts, selected, "legacy_all_signatures_failed"


def _parser_status(parsed: LegacyParsedDisplayTable) -> str:
    if parsed.rows:
        return "PARSED_ROWS"
    debug = dict(parsed.debug or {})
    try:
        records = int(debug.get("number_records") or 0)
    except Exception:
        records = 0
    try:
        data_len = int(debug.get("table_data_length") or 0)
    except Exception:
        data_len = 0
    if records > 0 and data_len == 0:
        return "TABLEDATA_EMPTY_DESPITE_RECORDS"
    if parsed.field_keys and not parsed.rows:
        return "HEADER_ONLY"
    if parsed.fetch_status == "FAILED":
        return "COM_CALL_FAILED"
    if not parsed.field_keys and not parsed.rows:
        return "EMPTY_TABLE"
    return "UNKNOWN_SHAPE"


def _attach_live_etabs_database_tables():  # pragma: no cover - requires Windows/ETABS
    try:
        import comtypes.client  # type: ignore[import-not-found]
    except Exception as exc:
        raise RuntimeError(f"ETABS COM/comtypes unavailable: {exc}") from exc
    etabs_object = comtypes.client.GetActiveObject("CSI.ETABS.API.ETABSObject")
    return etabs_object.SapModel.DatabaseTables


def run_live_probe(out_dir: Path) -> dict[str, Any]:  # pragma: no cover - requires Windows/ETABS
    database_tables = _attach_live_etabs_database_tables()
    available = parse_available_tables_result(database_tables.GetAvailableTables())
    reports: dict[str, Any] = {}
    diff_dir = Path("local_out/c11_1_4_old_vs_new_fetcher_diff")
    diff_dir.mkdir(parents=True, exist_ok=True)
    for alias, requested in TARGET_TABLES.items():
        actual = _table_is_available(requested, available) or requested
        raw, parsed, attempts, selected, selected_reason = _try_get_display_table_with_debug(database_tables, actual, max_rows=100000)
        debug = dict(parsed.debug or {})
        report = {
            "actual_table_name": actual,
            "table_alias": alias,
            "parser_status": _parser_status(parsed),
            "row_count": len(parsed.rows),
            "headers": list(parsed.field_keys),
            "number_fields": debug.get("number_fields"),
            "number_records": debug.get("number_records"),
            "table_data_length": debug.get("table_data_length"),
            "expected_flat_length": debug.get("expected_flat_length"),
            "sample_rows": [dict(row) for row in parsed.rows[:5]],
            "signature_attempts": attempts,
            "selected_signature": selected,
            "selected_signature_reason": selected_reason,
            "raw_return_summary": _summarize_raw(raw),
            "diagnostics": [dict(item) for item in parsed.diagnostics],
        }
        reports[alias] = report
        _write_json(out_dir / f"{alias}_raw_debug.json", report)
        _write_json(diff_dir / f"legacy_oracle_{alias}.json", report)
    summary = {
        "metadata": {
            "sprint": "C11_1_4_OLD_PROBE_PARITY_RECOVERY_LEGACY_ORACLE",
            "check_engine_executed": False,
            "check_result_emitted": False,
            "ok_fail_emitted": False,
            "mutated_etabs_model": False,
        },
        "tables": {alias: {"actual_table_name": r["actual_table_name"], "row_count": r["row_count"], "parser_status": r["parser_status"], "number_records": r["number_records"], "table_data_length": r["table_data_length"], "selected_signature_reason": r["selected_signature_reason"]} for alias, r in reports.items()},
    }
    _write_json(out_dir / "story_base_table_probe_summary.json", summary)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Temporary legacy C11.1.4 story/base ETABS table probe oracle. No checks; no verdicts.")
    parser.add_argument("--out", default="local_out/c11_1_4_legacy_oracle_probe_debug")
    args = parser.parse_args(argv)
    try:
        summary = run_live_probe(Path(args.out))
        print(f"Wrote legacy C11.1.4 story/base oracle outputs to {args.out}")
        print(json.dumps(to_jsonable(summary["tables"]), indent=2, ensure_ascii=False))
        return 0
    except Exception as exc:
        out = Path(args.out)
        failure = {
            "metadata": {"check_engine_executed": False, "check_result_emitted": False, "ok_fail_emitted": False},
            "error_type": type(exc).__name__,
            "message": str(exc),
        }
        _write_json(out / "story_base_table_probe_summary.json", failure)
        print(f"Legacy C11.1.4 story/base table probe failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
