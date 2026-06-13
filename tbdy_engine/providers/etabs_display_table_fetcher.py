"""Shared read-only ETABS display-table fetcher.

This module owns the COM signature probing for ``DatabaseTables`` display-table
reads.  It is import-safe without ETABS/comtypes; callers pass an already
obtained ``database_tables`` object.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Mapping

from tbdy_engine.providers.etabs_display_table_parser import ParsedDisplayTable, parse_etabs_display_table_result


@dataclass(frozen=True, slots=True)
class DisplayTableFetchResult:
    table_name: str
    parsed: ParsedDisplayTable
    raw_response: Any = None
    selected_signature: Mapping[str, Any] = field(default_factory=dict)
    selected_signature_reason: str = "not_selected"
    signature_attempts: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)

    def header_payload(self, registry: Any) -> dict[str, Any]:
        payload = self.parsed.header_payload(registry)
        payload.update({
            "raw_response": self.raw_response,
            "signature_attempts": [dict(item) for item in self.signature_attempts],
            "selected_signature": dict(self.selected_signature),
            "selected_signature_reason": self.selected_signature_reason,
            "parser_status_by_signature": {
                str(item.get("signature_name")): item.get("parser_status") for item in self.signature_attempts
            },
            "table_data_length_by_signature": {
                str(item.get("signature_name")): item.get("table_data_length") for item in self.signature_attempts
            },
            "number_records_by_signature": {
                str(item.get("signature_name")): item.get("number_records") for item in self.signature_attempts
            },
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
        })
        payload["raw_table_diagnostics"] = raw
        return payload


# Use immutable templates only.  ETABS/comtypes may mutate output list arguments;
# concrete args must therefore be materialized fresh for every table/signature.
DISPLAY_TABLE_SIGNATURES: tuple[tuple[str, tuple[Any, ...]], ...] = (
    ("sig_7_list_fields_records_data", ("__TABLE_NAME__", ("__FRESH_LIST__",), "", 0, ("__FRESH_LIST__",), 0, ("__FRESH_LIST__",))),
    ("sig_7_string_fields_records_data", ("__TABLE_NAME__", "", "", 0, ("__FRESH_LIST__",), 0, ("__FRESH_LIST__",))),
    ("sig_6_list_fields_records_data", ("__TABLE_NAME__", ("__FRESH_LIST__",), "", ("__FRESH_LIST__",), 0, ("__FRESH_LIST__",))),
    ("sig_3_group_field_key", ("__TABLE_NAME__", "", "")),
    ("sig_1_table_name", ("__TABLE_NAME__",)),
)


def _materialize_arg(item: Any, table_name: str) -> Any:
    if item == "__TABLE_NAME__":
        return table_name
    if item == ("__FRESH_LIST__",):
        return []
    # Defensive copy: never pass a mutable object from DISPLAY_TABLE_SIGNATURES.
    return deepcopy(item)


def _materialize_args(template: tuple[Any, ...], table_name: str) -> tuple[Any, ...]:
    return tuple(_materialize_arg(item, table_name) for item in template)



def _selection_return_code(raw: Any) -> Any:
    """Best-effort return-code extraction for ETABS display selection calls."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, (list, tuple)):
        for item in reversed(raw):
            if isinstance(item, int):
                return item
    return None


def _selection_attempt_record(method: str, args: tuple[Any, ...], *, raw: Any = None, exception: Exception | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "method": method,
        "args_shape": [type(arg).__name__ for arg in args],
        "args_repr": [_short_repr(arg) for arg in args],
        "call_succeeded": exception is None,
    }
    if exception is not None:
        record.update({
            "exception_type": type(exception).__name__,
            "exception": str(exception),
            "return_value": None,
            "return_code": None,
        })
        return record
    record.update({
        "return_value": raw,
        "return_value_repr": _short_repr(raw),
        "return_code": _selection_return_code(raw),
    })
    return record


def _selection_attempt_succeeded(record: Mapping[str, Any]) -> bool:
    if not record.get("call_succeeded"):
        return False
    code = record.get("return_code")
    # ETABS selection wrappers usually return 0 or (..., 0).  If the wrapper
    # returns no code but the call did not raise, keep it as a best-effort
    # success because the display state is the only thing we need before fetch.
    return code in (None, 0, "0")


def _detect_preferred_output_kind(database_tables: Any, preferred_output_case: str) -> str:
    """Best-effort output-name classification for diagnostics only.

    ETABS API variants expose load case/combination name lists through different
    objects and wrappers.  C11.1.5 must not depend on those optional APIs, so
    unknown is the safe default unless a lightweight fake/test object advertises
    a direct membership set.
    """
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


def _call_selection_method(database_tables: Any, method_name: str, case_name: str) -> dict[str, Any]:
    method = getattr(database_tables, method_name, None)
    args = ([case_name],)
    if method is None:
        return {
            "method": method_name,
            "args_shape": ["list"],
            "args_repr": [_short_repr([case_name])],
            "call_succeeded": False,
            "exception_type": "AttributeError",
            "exception": f"{method_name} not available on DatabaseTables",
            "return_value": None,
            "return_code": None,
        }
    try:  # pragma: no cover - requires real ETABS COM
        raw = method(*args)
        return _selection_attempt_record(method_name, args, raw=raw)
    except Exception as exc:  # pragma: no cover - requires real ETABS COM
        return _selection_attempt_record(method_name, args, exception=exc)


def select_output_for_display(database_tables: Any, preferred_output_case: str | None) -> dict[str, Any]:
    """Select an ETABS output case/combination for display-table result reads.

    Real ETABS/comtypes showed that story/base result tables can report headers
    and a positive record count while returning empty TableData until display
    output is selected.  Use list-only calls only; the failing int overloads
    such as ``SetLoadCombinationsSelectedForDisplay(1, [...])`` are
    intentionally not present.  Combo selection is attempted first and, on
    success, case selection is skipped to avoid a second display-state mutation.
    """
    case_name = str(preferred_output_case or "").strip()
    diagnostic: dict[str, Any] = {
        "preferred_output_case": case_name,
        "preferred_output_kind_detected": "unknown",
        "display_selection_attempted": bool(case_name),
        "display_selection_attempts": [],
        "display_selection_selected_method": None,
        "display_selection_success": False,
        "fetch_after_display_selection": False,
        "attempted_case_fallback": False,
        "skipped_case_selection_because_combo_succeeded": False,
        "read_only_model_geometry": True,
        "model_geometry_mutated": False,
    }
    if not case_name:
        diagnostic["diagnostic"] = "preferred_output_case_missing"
        return diagnostic

    diagnostic["preferred_output_kind_detected"] = _detect_preferred_output_kind(database_tables, case_name)

    attempts: list[dict[str, Any]] = []
    combo_record = _call_selection_method(database_tables, "SetLoadCombinationsSelectedForDisplay", case_name)
    attempts.append(combo_record)
    selected = combo_record if _selection_attempt_succeeded(combo_record) else None

    if selected is not None:
        diagnostic["skipped_case_selection_because_combo_succeeded"] = True
    else:
        diagnostic["attempted_case_fallback"] = True
        case_record = _call_selection_method(database_tables, "SetLoadCasesSelectedForDisplay", case_name)
        attempts.append(case_record)
        selected = case_record if _selection_attempt_succeeded(case_record) else None

    diagnostic.update({
        "display_selection_attempts": attempts,
        "display_selection_selected_method": selected.get("method") if selected else None,
        "display_selection_success": selected is not None,
        "fetch_after_display_selection": selected is not None,
    })
    return diagnostic


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


def _safe_len(value: Any) -> int | None:
    try:
        return len(value)  # type: ignore[arg-type]
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
        out["raw_return_items_summary"] = [_summarize_item(item) | {"index": i} for i, item in enumerate(raw)]
    return out


def _args_after_summary(args: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [_summarize_item(arg) | {"index": i} for i, arg in enumerate(args)]


def _raw_return_fragments(raw: Any) -> list[Any]:
    # ETABS/comtypes return values are commonly tuple-shaped, so expose their
    # items to the legacy sequence scanner.
    if isinstance(raw, (list, tuple)):
        return list(raw)
    return [raw]


def _arg_fragments(arg: Any) -> list[Any]:
    # Do not flatten list/tuple output arguments: the parser must see each
    # mutated list as one string-sequence candidate, just like the legacy probe
    # saw return-tuple sequence items.
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


def _merge_parse_diagnostics(primary: ParsedDisplayTable, combined: ParsedDisplayTable, *, strategy: str) -> ParsedDisplayTable:
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


def _parse_with_primary_headers_from_mutated_args(primary: ParsedDisplayTable, raw: Any, args: tuple[Any, ...], *, table_name: str, max_rows: int | None) -> ParsedDisplayTable | None:
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
    data_candidates = [seq for seq in candidates if seq != headers and len(seq) > header_count and len(seq) % header_count == 0]
    if not data_candidates:
        return None
    table_data = max(data_candidates, key=len)
    parsed = parse_etabs_display_table_result({
        "return_code": primary.return_code if primary.return_code is not None else 0,
        "field_keys": list(headers),
        "table_data": list(table_data),
        "number_records": len(table_data) // header_count,
    }, actual_table_name=table_name, max_rows=max_rows)
    if not parsed.rows:
        return None
    return _merge_parse_diagnostics(primary, parsed, strategy="primary_headers_plus_mutated_args_tabledata")


def _parse_raw_and_args(raw: Any, args: tuple[Any, ...], *, table_name: str, max_rows: int | None) -> ParsedDisplayTable:
    primary = parse_etabs_display_table_result(raw, actual_table_name=table_name, max_rows=max_rows)
    if primary.rows:
        return primary
    primary_header_parse = _parse_with_primary_headers_from_mutated_args(primary, raw, args, table_name=table_name, max_rows=max_rows)
    if primary_header_parse is not None:
        return primary_header_parse
    combined_raw = _combined_response(raw, args)
    combined = parse_etabs_display_table_result(combined_raw, actual_table_name=table_name, max_rows=max_rows)
    if combined.rows and len(combined.field_keys) > 1:
        return _merge_parse_diagnostics(primary, combined, strategy="return_plus_mutated_args_sequence_scan")
    # Keep the better diagnostic: prefer raw-return status when it has headers/
    # records, otherwise combined if it found a more informative shape.
    raw_header_count = len(primary.field_keys)
    combined_header_count = len(combined.field_keys)
    if combined_header_count > raw_header_count:
        return _merge_parse_diagnostics(primary, combined, strategy="return_plus_mutated_args_sequence_scan_no_rows")
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


def _best_failed_candidate(candidates: list[tuple[ParsedDisplayTable, Any, dict[str, Any]]]) -> tuple[ParsedDisplayTable, Any, dict[str, Any]] | None:
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


def _with_fetcher_debug(parsed: ParsedDisplayTable, attempts: list[dict[str, Any]], selected: Mapping[str, Any], reason: str, extra_diagnostics: list[Mapping[str, Any]] | None = None) -> ParsedDisplayTable:
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


def fetch_display_table(database_tables: Any, table_name: str, *, max_rows: int | None = None) -> DisplayTableFetchResult:
    """Fetch a display table by trying all known read-only COM signatures.

    A return code of 0 is not sufficient.  Some wrappers return headers and a
    positive record count with empty ``TableData`` for one signature while a
    later signature or post-call mutable out arguments contain the full flat row
    payload.  This function accepts only a signature/parse strategy that actually
    produces rows.
    """
    attempts: list[dict[str, Any]] = []
    parsed_candidates: list[tuple[ParsedDisplayTable, Any, dict[str, Any]]] = []
    last_exception: Exception | None = None
    for index, (signature_name, template) in enumerate(DISPLAY_TABLE_SIGNATURES, start=1):
        args = _materialize_args(template, table_name)
        try:  # pragma: no cover - real COM requires local ETABS
            raw = database_tables.GetTableForDisplayArray(*args)
        except Exception as exc:  # pragma: no cover - real COM requires local ETABS
            last_exception = exc
            attempt = _attempt_record(index=index, signature_name=signature_name, args=args, exception=exc)
            attempts.append(attempt)
            continue
        parsed = _parse_raw_and_args(raw, args, table_name=table_name, max_rows=max_rows)
        attempt = _attempt_record(index=index, signature_name=signature_name, args=args, parsed=parsed, raw=raw)
        attempts.append(attempt)
        parsed_candidates.append((parsed, raw, attempt))
        if parsed.rows:
            selected = dict(attempt)
            reason = "first_signature_with_parsed_rows"
            parsed = _with_fetcher_debug(parsed, attempts, selected, reason, [{
                "severity": "INFO",
                "code": "DISPLAY_TABLE_SIGNATURE_SELECTED",
                "message": "Selected first GetTableForDisplayArray signature that produced parsed rows.",
                "details": {"selected_signature": signature_name, "parse_strategy_used": attempt.get("parse_strategy_used")},
            }])
            return DisplayTableFetchResult(
                table_name=table_name,
                parsed=parsed,
                raw_response=raw,
                selected_signature=selected,
                selected_signature_reason=reason,
                signature_attempts=tuple(attempts),
            )

    best = _best_failed_candidate(parsed_candidates)
    if best is not None:
        parsed, raw, selected_attempt = best
        status = _parser_status_for(parsed)
        selected_reason = "all_signatures_failed_best_empty_tabledata" if status == "TABLEDATA_EMPTY_DESPITE_RECORDS" else "all_signatures_failed_best_diagnostic_candidate"
        parsed = _with_fetcher_debug(parsed, attempts, selected_attempt, selected_reason, [{
            "severity": "WARNING",
            "code": status,
            "message": "No GetTableForDisplayArray signature produced parsed rows; selected best diagnostic response.",
            "details": {"selected_signature": selected_attempt.get("signature_name")},
        }])
        return DisplayTableFetchResult(
            table_name=table_name,
            parsed=parsed,
            raw_response=raw,
            selected_signature=selected_attempt,
            selected_signature_reason=selected_reason,
            signature_attempts=tuple(attempts),
        )

    raw = {
        "return_code": 1,
        "field_keys": [],
        "table_data": [],
        "diagnostic": f"Could not call GetTableForDisplayArray with supported signatures: {last_exception}",
    }
    parsed = parse_etabs_display_table_result(raw, actual_table_name=table_name, max_rows=max_rows)
    selected = {"signature_name": "none", "parser_status": "COM_CALL_FAILED"}
    parsed = _with_fetcher_debug(parsed, attempts, selected, "all_signatures_raised_exceptions", [{
        "severity": "ERROR",
        "code": "DISPLAY_TABLE_ALL_SIGNATURES_FAILED",
        "message": "All GetTableForDisplayArray signatures raised exceptions.",
        "details": {"last_exception": str(last_exception)},
    }])
    return DisplayTableFetchResult(
        table_name=table_name,
        parsed=parsed,
        raw_response=raw,
        selected_signature=selected,
        selected_signature_reason="all_signatures_raised_exceptions",
        signature_attempts=tuple(attempts),
    )


def try_get_display_table(database_tables: Any, table_name: str, *, max_rows: int | None = None) -> Any:
    """Backward-compatible raw-response helper using the shared fetcher."""
    return fetch_display_table(database_tables, table_name, max_rows=max_rows).raw_response


__all__ = [
    "DISPLAY_TABLE_SIGNATURES",
    "DisplayTableFetchResult",
    "fetch_display_table",
    "select_output_for_display",
    "try_get_display_table",
]
